"""Ligue 1 : télécharge, réentraîne, prédit la saison et écrit les fichiers du site (site/data/ligue1/).

python football/main.py            télécharge ce qui manque puis calcule
python football/main.py --offline  calcule avec les fichiers déjà présents
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import backtest, data, season  # noqa: E402
from football import config as C  # noqa: E402
from football import model as M  # noqa: E402

JOURNAL_MARGIN = timedelta(minutes=30)
JOURNAL_LAST_CALL = timedelta(hours=6)
JOURNAL_COLUMNS = ["publie_utc", "match_id", "journee", "domicile", "exterieur", "coup_envoi", "p_dom", "p_nul", "p_ext", "avec_marche"]


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def write(name: str, obj) -> None:
    C.SITE_DATA.mkdir(parents=True, exist_ok=True)
    (C.SITE_DATA / f"{name}.json").write_text(json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                                              encoding="utf-8")


def match_id(home: str, away: str) -> str:
    return f"{C.CURRENT_SEASON}:{home}:{away}"


def record_journal(fx: pd.DataFrame, now: datetime) -> int:
    """Chaque pronostic est enregistré une seule fois, au moins 30 min avant le coup d'envoi, et jamais réécrit.
    Les calculs tournent au moins toutes les 3 h : un match est donc toujours figé à temps."""
    C.JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    done = set(pd.read_csv(C.JOURNAL)["match_id"]) if C.JOURNAL.exists() else set()
    rows = []
    for r in fx[~fx["played"]].itertuples():
        if not r.kickoff:
            continue
        ko = datetime.fromisoformat(r.kickoff.replace("Z", "+00:00"))
        mid = match_id(r.home, r.away)
        # on attend les cotes (blessures, actualité) ; sans elles, on fige quand même à 6 h du match
        is_ready = bool(r.with_market) or ko - now < JOURNAL_LAST_CALL
        if mid in done or not (now < ko - JOURNAL_MARGIN and ko - now < timedelta(days=7) and is_ready):
            continue
        rows.append([now.strftime("%Y-%m-%dT%H:%M:%SZ"), mid, r.round, r.home, r.away, r.kickoff, *r.p, bool(r.with_market)])
    if rows:
        pd.DataFrame(rows, columns=JOURNAL_COLUMNS).to_csv(C.JOURNAL, mode="a", header=not C.JOURNAL.exists(), index=False)
    return len(rows)


def evaluate_journal(played: pd.DataFrame) -> list[dict]:
    if not C.JOURNAL.exists():
        return []
    j = pd.read_csv(C.JOURNAL)
    res = played.set_index(["home", "away"])
    out = []
    for r in j.itertuples():
        if (r.domicile, r.exterieur) not in res.index:
            continue
        x = res.loc[(r.domicile, r.exterieur)]
        y = 0 if x["hg"] > x["ag"] else 1 if x["hg"] == x["ag"] else 2
        p = np.array([[r.p_dom, r.p_nul, r.p_ext]])
        out.append({"journee": int(r.journee), "domicile": r.domicile, "exterieur": r.exterieur, "publie_utc": r.publie_utc,
                    "score": f"{int(x['hg'])}-{int(x['ag'])}", "p": [r.p_dom, r.p_nul, r.p_ext], "resultat": y,
                    "favori_juste": bool(p.argmax() == y), "rps": round(float(M.rps(p, np.array([y]))[0]), 4)})
    return out


def main(offline: bool = False) -> None:
    now = datetime.now(timezone.utc)
    if not offline:
        print("1/5 Téléchargement")
        data.download()
    print("2/5 Données")
    m = data.load_matches()
    fx = data.load_fixtures()
    cur = m[m["season"] == C.CURRENT_SEASON]
    teams = sorted(set(fx["home"]) | set(fx["away"]))
    print(f"   {len(m)} matchs depuis 1993, {len(cur)} joués cette saison, {len(fx)} au calendrier")

    print("3/5 Backtest et réglages")
    bt = backtest.run(m)
    st = bt["settings"]
    print("   réglages :", st)

    print("4/5 Pronostics et simulation")
    ratio = backtest.sot_ratio(m, pd.Timestamp(now.date()) + pd.Timedelta(days=1))
    fit = M.fit(m, pd.Timestamp(now.date()) + pd.Timedelta(days=1), st["xi"], st["s"], ratio, {"promoted": st["promoted"]})
    pred = season.predict_fixtures(fx, cur, fit, st)
    tp = bt["test_predictions"]
    tp = tp[tp["season"] == C.CURRENT_SEASON].set_index(["home", "away"])
    pred["p_reconstitue"] = [[round(float(tp.loc[(h, a), k]), 4) for k in ("p_h", "p_d", "p_a")] if pl and (h, a) in tp.index else None
                             for h, a, pl in zip(pred["home"], pred["away"], pred["played"])]
    upcoming = pred[~pred["played"]]
    sim = season.simulate(cur, upcoming, teams)
    standings = season.table(cur, teams)

    print("5/5 Journal et fichiers du site")
    added = record_journal(pred, now)
    print(f"   journal : {added} pronostics publiés")
    next_round = int(upcoming["round"].min()) if len(upcoming) else int(pred["round"].max())

    clubs = {k: {"nom": v[0], "sigle": v[1], "couleur": v[2], "couleur2": v[3]} for k, v in C.CLUBS.items() if k in teams}
    for k in clubs:
        f = C.ROOT / "site" / "assets" / "logos" / f"{k.lower().replace(' ', '-')}.svg"
        clubs[k]["logo"] = f"assets/logos/{f.name}" if f.exists() else None
    strength = {t: {"attaque": float(fit["att"][fit["teams"][t]]), "defense": float(fit["def"][fit["teams"][t]])}
                for t in teams if t in fit["teams"]}
    write("matches", {"maj_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "saison": f"{C.CURRENT_SEASON}-{(C.CURRENT_SEASON + 1) % 100:02d}",
                      "prochaine_journee": next_round, "journees": int(pred["round"].max()), "clubs": clubs, "forces": strength,
                      "matchs": pred.drop(columns=[c for c in pred.columns if c.startswith("lam_")]).to_dict("records")})
    write("season", {"maj_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "simulations": season.N_SIM,
                     "classement": [{"club": k, **v} for k, v in standings.to_dict("index").items()],
                     "projection": sim.to_dict("records")})
    pairs = set(teams)
    h2h = m[m["home"].isin(pairs) & m["away"].isin(pairs)]
    write("h2h", {"matchs": [[r.date.strftime("%Y-%m-%d"), r.home, r.away, int(r.hg), int(r.ag)] for r in h2h.itertuples()]})
    test = bt["test"].to_dict("records")
    write("performance", {"reglages": st, "test": test, "gains": bt["gains"], "par_saison": bt["by_season"],
                          "saisons_choix": C.CHOICE_SEASONS, "saisons_test": C.TEST_SEASONS,
                          "journal": evaluate_journal(cur)})
    print("Terminé.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
