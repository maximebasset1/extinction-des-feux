"""Recherche de matchs : Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions, Ligue Europa.

python football/europe_main.py            télécharge ce qui manque puis calcule
python football/europe_main.py --offline  calcule avec les fichiers déjà présents
"""
import argparse
import hashlib
import os
import pickle
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import config as C  # noqa: E402
from football import cups, joint, leagues  # noqa: E402
from football import joint_backtest as JB  # noqa: E402
from football import main as L1  # noqa: E402
from football import model as M  # noqa: E402
from football import season as S  # noqa: E402
from football import sources as SRC  # noqa: E402
from football.data import _get, season_code  # noqa: E402

RAW = Path(os.environ.get("EU_DATA_DIR", C.ROOT / "data" / "football" / "eu"))
OUT = C.ROOT / "site" / "data" / "recherche"
FIRST_SEASON = 2010
XI, SOT_SHARE, RHO = 0.002, 0.4, -0.1        # choisis sur la saison 2021-22 (voir le README)
CHOICE, TEST = [2021], list(range(2022, C.CURRENT_SEASON + 1))
BACKTEST_MAX_AGE = timedelta(days=7)
H2H_SHOWN = 8
DOMESTIC = {"E0": ("en.1", "ENG", "Europe/London"), "D1": ("de.1", "GER", "Europe/Berlin"),
            "SP1": ("es.1", "ESP", "Europe/Madrid"), "F1": ("fr.1", "FRA", "Europe/Paris")}
NAMES_FR = {"E0": "Premier League", "D1": "Bundesliga", "SP1": "Liga", "F1": "Ligue 1", "LDC": "Ligue des champions",
            "LEC": "Ligue Europa"}
CUP_HISTORY = "https://raw.githubusercontent.com/openfootball/champions-league/master/{season}/{code}.txt"
LEAGUE_FILE = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{file}.json"
SUFFIX = re.compile(r"\s+(FC|CF|AFC|SC|FK|SK|KV|CFC)$")


def season_dir(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).timestamp()

    def keep(f: Path, max_age_h: float | None = None) -> bool:
        return f.exists() and f.stat().st_size > 0 and (max_age_h is None or now - f.stat().st_mtime < max_age_h * 3600)

    for code in leagues.MAIN:
        for y in range(FIRST_SEASON, C.CURRENT_SEASON + 1):
            f = RAW / f"{code}_{y}.csv"
            if keep(f, None if y < C.CURRENT_SEASON else 1):
                continue
            try:
                f.write_bytes(_get(f"https://www.football-data.co.uk/mmz4281/{season_code(y)}/{code}.csv"))
            except Exception as e:  # noqa: BLE001
                print(f"   {code} {y} indisponible : {e}")
    for code in leagues.NEW:   # gros fichiers toutes saisons : une fois par jour suffit
        f = RAW / f"new_{code}.csv"
        if not keep(f, 20):
            f.write_bytes(_get(f"https://www.football-data.co.uk/new/{code}.csv"))
    (RAW / "fixtures.csv").write_bytes(_get("https://www.football-data.co.uk/fixtures.csv"))
    for code, (file, _, _) in DOMESTIC.items():
        (RAW / f"{file}.json").write_bytes(_get(LEAGUE_FILE.format(season=season_dir(C.CURRENT_SEASON), file=file)))
    for y in range(2011, C.CURRENT_SEASON):
        for c in cups.COMPETITIONS:
            d = RAW / "cups" / season_dir(y)
            f = d / f"{c}.txt"
            if keep(f):
                continue
            d.mkdir(parents=True, exist_ok=True)
            try:
                f.write_bytes(_get(CUP_HISTORY.format(season=season_dir(y), code=c)))
            except Exception:  # noqa: BLE001
                pass   # la Ligue Europa n'est publiée que depuis 2020-21


def display(name: str) -> str:
    return SUFFIX.sub("", str(name)).strip()


def load_all():
    """Tous les matchs joués (championnats + coupes passées + coupes de la saison) et les matchs à venir."""
    dom = leagues.load(RAW, FIRST_SEASON, C.CURRENT_SEASON)
    dom["is_cup"], dom["neutral"] = False, False
    idx = SRC.TeamIndex(list(pd.unique(dom[["home", "away"]].values.ravel())))
    hist = cups.load(RAW / "cups").dropna(subset=["hg", "ag"])
    hist["home"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["home_of"], hist["home_cc"])]
    hist["away"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["away_of"], hist["away_cc"])]
    hist["league"], hist["is_cup"] = hist["competition"], True
    names = {}
    for t, n in zip(pd.concat([hist["home"], hist["away"]]), pd.concat([hist["home_of"], hist["away_of"]])):
        names[t] = display(n)

    now = datetime.now(timezone.utc)
    upcoming, played_cup = [], []
    token, key = os.environ.get("FOOTBALL_DATA_ORG_TOKEN"), os.environ.get("ODDS_API_KEY")
    # une source en panne ou une clé refusée ne bloque pas les autres compétitions
    try:
        cl = SRC.football_data_org("CL", C.CURRENT_SEASON, token, RAW)
    except RuntimeError as e:
        print(f"   Ligue des champions (football-data.org) indisponible : {e}")
        cl = SRC.football_data_org("CL", C.CURRENT_SEASON, None, RAW)
    if cl:
        f = SRC.fdorg_frame(cl, "LDC", idx)
        played_cup.append(f[f["played"]])
        upcoming.append(f[~f["played"]])
    for comp in ("LDC", "LEC"):
        kos = [datetime.fromisoformat(k.replace("Z", "+00:00")) for u in upcoming for k in u["kickoff"].dropna()]
        try:
            events, odds = SRC.odds_api(comp, key, RAW, now, kos)
        except RuntimeError as e:
            print(f"   {comp} (The Odds API) indisponible : {e}")
            events, odds = SRC.odds_api(comp, None, RAW, now, kos)
        o = SRC.odds_frame(events, odds, comp, idx)
        if comp == "LDC" and len(upcoming) and len(o):
            # le calendrier vient de football-data.org ; The Odds API n'apporte que les cotes
            base = upcoming[0].merge(o[["home", "away", "oh", "od", "oa"]], on=["home", "away"], how="left")
            upcoming[0] = base
        elif len(o):
            upcoming.append(o)
    for code, (file, cc, tz) in DOMESTIC.items():
        f = RAW / f"{file}.json"
        if not f.exists():
            continue
        cal = SRC.openfootball_league(f, code, cc, tz, idx)
        for t, n in zip(pd.concat([cal["home"], cal["away"]]), pd.concat([cal["home_name"], cal["away_name"]])):
            names[t] = display(n)
        # openfootball n'est pas toujours à jour des scores : un match est joué s'il figure dans football-data
        done = set(zip(dom.loc[(dom["league"] == code) & (dom["season"] == C.CURRENT_SEASON), "home"],
                       dom.loc[(dom["league"] == code) & (dom["season"] == C.CURRENT_SEASON), "away"]))
        cal["played"] = [(h, a) in done for h, a in zip(cal["home"], cal["away"])]
        upcoming.append(cal[~cal["played"]])
    for u in upcoming:
        for t, n in zip(pd.concat([u["home"], u["away"]]), pd.concat([u["home_name"], u["away_name"]])):
            names.setdefault(t, display(n))
    cur = pd.concat(played_cup, ignore_index=True) if played_cup else pd.DataFrame()
    if len(cur):
        cur = cur.assign(date=pd.to_datetime(cur["kickoff"]).dt.tz_localize(None).dt.normalize(), league=cur["competition"],
                         is_cup=True, season=C.CURRENT_SEASON)
    cols = ["date", "home", "away", "hg", "ag", "league", "is_cup", "neutral", "season"]
    allm = pd.concat([dom, hist[cols]] + ([cur[cols]] if len(cur) else []), ignore_index=True)
    allm = allm.dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)
    up = pd.concat(upcoming, ignore_index=True) if upcoming else pd.DataFrame()
    fx = odds_for_domestic(up)
    return allm, fx, names, idx


def odds_for_domestic(up: pd.DataFrame) -> pd.DataFrame:
    """Cotes des matchs de championnat des prochains jours (football-data.co.uk), quand elles sont publiées."""
    f = RAW / "fixtures.csv"
    for c in ("oh", "od", "oa"):
        if c not in up:
            up[c] = np.nan
    if not f.exists() or not len(up):
        return up
    u = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip")
    u = u[u["Div"].isin(DOMESTIC)]
    from football.data import _odds, PRE_MATCH
    o = _odds(u, PRE_MATCH)
    cc = u["Div"].map({k: v[1] for k, v in DOMESTIC.items()})
    from football.data import _dates
    # heures de football-data : heure de Londres
    ko = [S.kickoff_utc(d, t, S.LONDON) for d, t in zip(_dates(u["Date"]), u["Time"])]
    odds = pd.DataFrame({"home": cc + ":" + u["HomeTeam"].str.strip(), "away": cc + ":" + u["AwayTeam"].str.strip(),
                         "_oh": o[:, 0], "_od": o[:, 1], "_oa": o[:, 2], "_ko": ko})
    up = up.merge(odds, on=["home", "away"], how="left")
    for c in ("oh", "od", "oa"):
        up[c] = up[c].fillna(up.pop(f"_{c}"))
    up["kickoff"] = up["_ko"].where(up["_ko"].notna(), up["kickoff"])
    return up.drop(columns="_ko")


def code_hash() -> str:
    h = hashlib.sha256()
    for f in ("joint.py", "joint_backtest.py", "names.py", "leagues.py", "cups.py", "model.py"):
        h.update((C.ROOT / "football" / f).read_bytes())
    return h.hexdigest()[:16]


def backtest(allm: pd.DataFrame) -> dict:
    """Rejoué chaque semaine depuis 2021 ; gardé une semaine (les saisons passées ne changent plus)."""
    cache = RAW / "backtest_recherche.pkl"
    key = (code_hash(), XI, SOT_SHARE, RHO)
    if cache.exists():
        try:
            c = pickle.loads(cache.read_bytes())
            if c["key"] == key and datetime.now(timezone.utc) - c["when"] < BACKTEST_MAX_AGE:
                return c
        except Exception:  # noqa: BLE001
            pass   # cache illisible : on recalcule
    p = JB.weekly(allm, CHOICE + TEST, XI, SOT_SHARE)
    p["season"] = p["date"].map(JB.season_of)
    pm = JB.probs(p, RHO)
    mk = M.market_probs(p[["oh", "od", "oa"]].to_numpy(float))
    has = np.isfinite(mk).all(axis=1)
    y = p["result"].to_numpy()
    ch = p["season"].isin(CHOICE).to_numpy() & has
    best = min(((a, b) for a in np.round(np.arange(C.MIN_MODEL_WEIGHT, 1.21, 0.1), 2) for b in np.round(np.arange(0, 1.21, 0.1), 2)),
               key=lambda ab: M.logloss(M.blend(pm[ch], mk[ch], *ab), y[ch]).mean())
    bl = M.blend(pm, mk, *best)
    table = []
    for comp in JB.TARGET_LEAGUES:
        i = ((p["league"] == comp) & p["season"].isin(TEST)).to_numpy()
        if not i.any():
            continue
        prev = p[(p["league"] == comp) & p["season"].isin(CHOICE)]
        freq = np.bincount(prev["result"], minlength=3) / max(len(prev), 1)
        row = {"competition": comp, "nom": NAMES_FR[comp], "matchs": int(i.sum()),
               "modele": JB.score(pm[i], y[i]), "habitudes": JB.score(np.tile(freq, (i.sum(), 1)), y[i])}
        j = i & has
        if j.sum() > 100:
            row["avec_cotes"] = JB.score(bl[j], y[j])
            row["marche"] = JB.score(mk[j], y[j])
        table.append(row)
    c = {"key": key, "when": datetime.now(timezone.utc), "a": float(best[0]), "b": float(best[1]), "table": table}
    RAW.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(c))
    return c


def club_info(t: str, names: dict) -> dict:
    """Nom affiché, sigle, couleurs (connues pour la Ligue 1) et logo libre s'il existe."""
    cc, fd = t.split(":", 1)
    nom = names.get(t, fd)
    words = [w for w in re.split(r"[\s.\-]+", nom) if w and w[0].isalpha() and w.lower() not in {"de", "la", "le", "of", "fc"}]
    sigle = "".join(w[0] for w in words[:3]) if len(words) > 1 else (words[0] if words else fd)[:3]
    info = {"nom": nom, "pays": cc, "competitions": [], "sigle": sigle.upper()}
    if cc == "FRA" and fd in C.CLUBS:
        _, sigle, c1, c2 = C.CLUBS[fd]
        info.update(sigle=sigle, couleur=c1, couleur2=c2)
        logo = C.ROOT / "site" / "assets" / "logos" / f"{fd.lower().replace(' ', '-')}.svg"
        if logo.exists():
            info["logo"] = f"assets/logos/{logo.name}"
    return info


def h2h_index(allm: pd.DataFrame) -> dict:
    out = {}
    for r in allm.sort_values("date").itertuples():
        out.setdefault(frozenset((r.home, r.away)), []).append([r.date.strftime("%Y-%m-%d"), r.home, r.away, int(r.hg), int(r.ag), r.league])
    return out


def main(offline: bool = False) -> None:
    now = datetime.now(timezone.utc)
    if not offline:
        print("1/4 Téléchargement")
        download()
    print("2/4 Données")
    allm, fx, names, idx = load_all()
    print(f"   {len(allm)} matchs joués, {len(fx)} à venir")
    unknown = sorted({t for t in pd.concat([fx["home"], fx["away"]]) if t.startswith("?:")})
    if unknown:
        print("   clubs non reconnus (pronostic au niveau d'un championnat modeste) :", unknown)
    print("3/4 Backtest")
    bt = backtest(allm)
    print(f"   mélange avec les cotes : a={bt['a']}, b={bt['b']}")
    print("4/4 Pronostics et fichiers du site")
    ratio = JB.sot_ratio(allm, pd.Timestamp(now.date()))
    fit = joint.fit(allm, pd.Timestamp(now.date()) + pd.Timedelta(days=1), XI, SOT_SHARE, ratio)
    h2h = h2h_index(allm)
    rows = []
    for r in fx.itertuples():
        is_cup = r.competition in ("LDC", "LEC")
        lh, la = joint.rates(fit, r.home, r.away, bool(r.neutral), is_cup)
        p_model = M.outcome(M.score_matrix(lh, la, RHO))
        odds = np.array([[r.oh, r.od, r.oa]], float)
        has = bool(np.isfinite(odds).all())
        p = M.blend(p_model[None], M.market_probs(odds), bt["a"], bt["b"])[0] if has else p_model
        if has:
            lh, la = S.calibrate_rates(lh, la, p, RHO)
        mat = M.score_matrix(lh, la, RHO)
        top = np.argsort(mat, axis=None)[::-1][:3]
        rows.append({"competition": r.competition, "kickoff": r.kickoff if isinstance(r.kickoff, str) else None,
                     "jour": getattr(r, "jour", None) if isinstance(getattr(r, "jour", None), str) else
                     (r.kickoff[:10] if isinstance(r.kickoff, str) else None),
                     "home": r.home, "away": r.away, "p": S.round_probs(p), "avec_cotes": has,
                     "xg": [round(lh, 1), round(la, 1)],
                     "scores": [{"score": f"{i // mat.shape[1]}-{i % mat.shape[1]}", "p": round(float(mat.flat[i]), 2)} for i in top],
                     "h2h": h2h.get(frozenset((r.home, r.away)), [])[-H2H_SHOWN:][::-1]})
    rows.sort(key=lambda x: (x["kickoff"] or (x["jour"] or "9999") + "T23:59"))
    today = now.strftime("%Y-%m-%d")
    rows = [x for x in rows if (x["jour"] or "9999") >= today]
    clubs = {}
    for x in rows:
        for t in (x["home"], x["away"]):
            c = clubs.setdefault(t, club_info(t, names))
            if x["competition"] not in c["competitions"]:
                c["competitions"].append(x["competition"])
    perf = {"maj_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "saisons_test": TEST, "part_marche": round(bt["b"] / (bt["a"] + bt["b"]), 1),
            "competitions": bt["table"]}
    write_all({"matchs": {"maj_utc": perf["maj_utc"], "competitions": NAMES_FR, "clubs": clubs, "matchs": rows},
               "performance": perf})
    print(f"   {len(rows)} matchs, {len(clubs)} clubs publiés. Terminé.")


def write_all(files: dict) -> None:
    import json
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = {}
    for name, obj in files.items():
        t = OUT / f".{name}.json.tmp"
        t.write_text(json.dumps(L1._clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        tmp[name] = t
    for name, t in tmp.items():
        os.replace(t, OUT / f"{name}.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
