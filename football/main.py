"""Ligue 1 : télécharge, réentraîne, prédit la saison et écrit les fichiers du site (site/data/ligue1/).

python football/main.py            télécharge ce qui manque puis calcule
python football/main.py --offline  calcule avec les fichiers déjà présents
"""
import argparse
import json
import os
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


def write(files: dict) -> None:
    """Écrit tous les fichiers d'abord à côté, puis les met en place : jamais de mélange ancien/nouveau
    si le calcul s'arrête en route."""
    C.SITE_DATA.mkdir(parents=True, exist_ok=True)
    tmp = {}
    for name, obj in files.items():
        t = C.SITE_DATA / f".{name}.json.tmp"
        t.write_text(json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        tmp[name] = t
    for name, t in tmp.items():
        os.replace(t, C.SITE_DATA / f"{name}.json")


def check_names(fx: pd.DataFrame, cur: pd.DataFrame) -> None:
    """Un nom de club mal relié ferait disparaître ses matchs sans bruit : on préfère s'arrêter
    (la page garde alors les derniers pronostics valides)."""
    cal = set(fx["home"]) | set(fx["away"])
    unknown = sorted(cal - set(C.CLUBS))
    if unknown:
        raise SystemExit(f"Clubs absents de config.CLUBS : {unknown}")
    played = set(cur["home"]) | set(cur["away"])
    if played and played != cal:
        raise SystemExit(f"Noms différents entre calendrier et résultats : {sorted(cal ^ played)}")


def match_id(home: str, away: str) -> str:
    return f"{C.CURRENT_SEASON}:{home}:{away}"


def record_journal(fx: pd.DataFrame, now: datetime) -> int:
    """Chaque pronostic est enregistré une seule fois, au moins 30 min avant le coup d'envoi, et jamais réécrit.
    Les calculs tournent au moins toutes les 3 h : un match est donc toujours figé à temps."""
    C.JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    done = set(pd.read_csv(C.JOURNAL)["match_id"]) if C.JOURNAL.exists() else set()
    rows = []
    for r in fx[~fx["played"]].itertuples():
        if not isinstance(r.kickoff, str):   # heure pas encore connue : on attend
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
    check_names(fx, cur)
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
    pred["p_reconstitue"] = [season.round_probs([tp.loc[(h, a), k] for k in ("p_h", "p_d", "p_a")]) if pl and (h, a) in tp.index else None
                             for h, a, pl in zip(pred["home"], pred["away"], pred["played"])]
    upcoming = pred[~pred["played"]]
    sim = season.simulate(cur, upcoming, teams, st["rho"])
    standings = season.table(cur, teams)

    print("5/5 Journal et fichiers du site")
    added = record_journal(pred, now)
    print(f"   journal : {added} pronostics publiés")
    # un match reporté ne bloque pas la page sur sa journée : on prend le prochain match à venir
    today = now.strftime("%Y-%m-%d")
    pending = (pred["jour"].fillna("9999") < today) & ~pred["played"]
    pred["en_attente"] = pending
    ahead = upcoming[upcoming["jour"].fillna("9999") >= today]
    next_round = int(ahead.sort_values("jour")["round"].iloc[0]) if len(ahead) else int(pred["round"].max())

    clubs = {k: {"nom": v[0], "sigle": v[1], "couleur": v[2], "couleur2": v[3]} for k, v in C.CLUBS.items() if k in teams}
    for k in clubs:
        f = C.ROOT / "site" / "assets" / "logos" / f"{k.lower().replace(' ', '-')}.svg"
        clubs[k]["logo"] = f"assets/logos/{f.name}" if f.exists() else None
    strength = {t: {"attaque": float(fit["att"][fit["teams"][t]]), "defense": float(fit["def"][fit["teams"][t]])}
                for t in teams if t in fit["teams"]}
    files = {}
    files["matches"] = ({"maj_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "saison": f"{C.CURRENT_SEASON}-{(C.CURRENT_SEASON + 1) % 100:02d}",
                      "prochaine_journee": next_round, "journees": int(pred["round"].max()), "clubs": clubs, "forces": strength,
                      "matchs": pred.drop(columns=[c for c in pred.columns if c.startswith("lam_")]).to_dict("records")})
    files["season"] = ({"maj_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "simulations": season.N_SIM,
                     "classement": [{"club": k, **v} for k, v in standings.to_dict("index").items()],
                     "projection": sim.to_dict("records")})
    pairs = set(teams)
    h2h = m[m["home"].isin(pairs) & m["away"].isin(pairs)]
    files["h2h"] = ({"matchs": [[r.date.strftime("%Y-%m-%d"), r.home, r.away, int(r.hg), int(r.ag)] for r in h2h.itertuples()]})
    test = bt["test"].to_dict("records")
    # les poids exacts du mélange ne sont pas publiés : avec eux, on pourrait remonter aux cotes
    reglages = {"memoire_jours": round(np.log(2) / st["xi"]), "part_tirs_cadres": st["s"],
                "part_marche": round(st["b"] / (st["a"] + st["b"]), 1)}
    files["performance"] = ({"reglages": reglages, "test": test, "gains": bt["gains"], "par_saison": bt["by_season"],
                          "saisons_choix": C.CHOICE_SEASONS, "saisons_test": C.TEST_SEASONS,
                          "journal": evaluate_journal(cur)})
    write(files)
    print("Terminé.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
