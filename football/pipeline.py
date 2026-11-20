"""Football : Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions, Ligue Europa.

Un seul modèle pour les six compétitions. Chaque lancement télécharge les nouveaux résultats, réajuste les forces
de tous les clubs, publie les pronostics des matchs à venir, tient le journal des pronostics publiés,
calcule les classements et simule les fins de saison, puis écrit les fichiers du site (site/data/foot/).

python football/pipeline.py            télécharge ce qui manque puis calcule
python football/pipeline.py --offline  calcule avec les fichiers déjà présents
"""
import argparse
import hashlib
import json
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
from football import journal as JR  # noqa: E402
from football import joint_backtest as JB  # noqa: E402
from football import model as M  # noqa: E402
from football import season as S  # noqa: E402
from football import sources as SRC  # noqa: E402
from football.data import PRE_MATCH, _dates, _get, _odds, season_code  # noqa: E402

RAW = Path(os.environ.get("EU_DATA_DIR", C.ROOT / "data" / "football" / "eu"))
ODDS_STATE = Path(os.environ.get("ODDS_STATE_DIR", C.ROOT / "data" / "football" / "cotes"))   # gardé à chaque lancement
OUT = Path(os.environ.get("FOOT_OUT_DIR", C.ROOT / "site" / "data" / "foot"))
# fichiers gardés dans le dépôt ; des chemins à part pour les essais, pour ne jamais écrire dans le vrai journal
JOURNAL = Path(os.environ.get("FOOT_JOURNAL", C.ROOT / "data" / "journal" / "foot.csv"))
CUP_RESULTS = Path(os.environ.get("FOOT_CUP_RESULTS", C.ROOT / "data" / "football" / "resultats_coupes.csv"))
FIRST_SEASON = 2010          # données du modèle (sa mémoire ne remonte qu'à 4 ans, le reste sert au backtest)
H2H_FIRST = 2000             # face-à-face des quatre grands championnats
XI, SOT_SHARE, RHO = 0.002, 0.4, -0.1        # choisis sur la saison 2021-22 (voir le README)
CHOICE, TEST = [2021], list(range(2022, C.CURRENT_SEASON + 1))
BACKTEST_MAX_AGE = timedelta(days=7)
H2H_SHOWN = 8
RECENT_DAYS = 14             # surprises récentes affichées à l'accueil
FEATURED = 6
CUP_FIRST = {"cl": 2011, "el": 2020}   # premières saisons publiées par openfootball
CUP_HISTORY = "https://raw.githubusercontent.com/openfootball/champions-league/master/{season}/{code}.txt"
LEAGUE_FILE = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{file}.json"
SUFFIX = re.compile(r"\s+(FC|CF|AFC|SC|FK|SK|KV|CFC)$")
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# zones du classement : (clé, libellé, première place, dernière place)
LEAGUE_ZONES = {20: [("titre", "Titre", 1, 1), ("top4", "Top 4", 1, 4), ("relegation", "Relégation", 18, 20)],
                18: [("titre", "Titre", 1, 1), ("top4", "Top 4", 1, 4), ("barrage", "Barrage", 16, 16),
                     ("relegation", "Relégation", 17, 18)]}
CUP_ZONES = [("top8", "Top 8", 1, 8), ("barrages", "9e à 24e", 9, 24), ("elimine", "Éliminé", 25, 36)]
COMPS = {
    "E0": {"slug": "premier-league", "nom": "Premier League", "type": "ligue", "cc": "ENG", "of": "en.1", "tz": "Europe/London"},
    "D1": {"slug": "bundesliga", "nom": "Bundesliga", "type": "ligue", "cc": "GER", "of": "de.1", "tz": "Europe/Berlin"},
    "SP1": {"slug": "liga", "nom": "Liga", "type": "ligue", "cc": "ESP", "of": "es.1", "tz": "Europe/Madrid"},
    "F1": {"slug": "ligue-1", "nom": "Ligue 1", "type": "ligue", "cc": "FRA", "of": "fr.1", "tz": "Europe/Paris"},
    "LDC": {"slug": "ligue-des-champions", "nom": "Ligue des champions", "type": "coupe"},
    "LEC": {"slug": "ligue-europa", "nom": "Ligue Europa", "type": "coupe"},
}
KEEP_SUFFIX = {"Paris FC"}
# noms officiels trop longs pour une ligne de match
DISPLAY = {"Club Atlético de Madrid": "Atlético de Madrid", "Stade Rennais FC 1901": "Stade Rennais", "FC Internazionale Milano": "Inter",
           "Paris Saint-Germain FC": "Paris Saint-Germain", "Real Sociedad de Fútbol": "Real Sociedad", "Real Betis Balompié": "Real Betis",
           "RCD Espanyol de Barcelona": "Espanyol", "Rayo Vallecano de Madrid": "Rayo Vallecano", "TSG 1899 Hoffenheim": "Hoffenheim",
           "Racing Club de Lens": "RC Lens", "Real Racing Club de Santander": "Racing Santander", "RC Deportivo La Coruña": "Deportivo La Coruña",
           "SV 07 Elversberg": "Elversberg", "SC Paderborn 07": "Paderborn", "Brighton & Hove Albion FC": "Brighton",
           "Brighton & Hove Albion": "Brighton", "RC Strasbourg Alsace": "RC Strasbourg", "Stade Brestois 29": "Stade Brestois",
           "Sport Lisboa e Benfica": "Benfica", "Sporting Clube de Portugal": "Sporting CP", "Bayer 04 Leverkusen": "Bayer Leverkusen",
           "FC Bayern München": "Bayern Munich", "Club Brugge KV": "Club Brugge", "Real Madrid CF": "Real Madrid",
           "Wolverhampton Wanderers FC": "Wolverhampton", "Wolverhampton Wanderers": "Wolverhampton",
           "Tottenham Hotspur FC": "Tottenham", "Tottenham Hotspur": "Tottenham", "Nottingham Forest FC": "Nottingham Forest",
           "West Ham United FC": "West Ham", "Newcastle United FC": "Newcastle", "Borussia Mönchengladbach": "Mönchengladbach",
           "1. FSV Mainz 05": "Mainz", "1. FC Union Berlin": "Union Berlin", "1. FC Heidenheim 1846": "Heidenheim",
           "Olympique Lyonnais": "Lyon", "Olympique de Marseille": "Marseille", "Lille OSC": "Lille", "AS Monaco FC": "Monaco",
           "OGC Nice": "Nice", "Toulouse FC": "Toulouse", "FC Lorient": "Lorient", "AJ Auxerre": "Auxerre", "Angers SCO": "Angers",
           "Le Havre AC": "Le Havre", "ES Troyes AC": "Troyes", "Le Mans FC": "Le Mans"}


def season_dir(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


def display(name: str) -> str:
    """Nom court lisible (« Arsenal FC » -> « Arsenal ») ; « Paris FC » garde son « FC », sinon on le confondrait avec le PSG."""
    name = str(name).strip()
    if name in DISPLAY:
        return DISPLAY[name]
    return name if name in KEEP_SUFFIX else SUFFIX.sub("", name).strip() or name


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------- téléchargement

def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).timestamp()

    def keep(f: Path, max_age_h: float | None = None) -> bool:
        return f.exists() and f.stat().st_size > 0 and (max_age_h is None or now - f.stat().st_mtime < max_age_h * 3600)

    # (fichier, adresse, âge maximal en heures : None = jamais retéléchargé, 0 = à chaque lancement)
    jobs = []
    for code in leagues.MAIN:
        for y in range(FIRST_SEASON, C.CURRENT_SEASON + 1):
            jobs.append((RAW / f"{code}_{y}.csv", f"https://www.football-data.co.uk/mmz4281/{season_code(y)}/{code}.csv",
                         None if y < C.CURRENT_SEASON else 1))
    for code in ("E0", "D1", "SP1", "F1"):          # anciennes saisons : seulement pour les face-à-face
        for y in range(H2H_FIRST, FIRST_SEASON):
            jobs.append((RAW / f"{code}_{y}.csv", f"https://www.football-data.co.uk/mmz4281/{season_code(y)}/{code}.csv", None))
    jobs += [(RAW / f"new_{c}.csv", f"https://www.football-data.co.uk/new/{c}.csv", 20) for c in leagues.NEW]
    jobs.append((RAW / "fixtures.csv", "https://www.football-data.co.uk/fixtures.csv", 0))
    jobs += [(RAW / f"{v['of']}.json", LEAGUE_FILE.format(season=season_dir(C.CURRENT_SEASON), file=v["of"]), 0)
             for v in COMPS.values() if "of" in v]
    for y in range(2011, C.CURRENT_SEASON):
        for c, first in CUP_FIRST.items():
            if y >= first:
                jobs.append((RAW / "cups" / season_dir(y) / f"{c}.txt", CUP_HISTORY.format(season=season_dir(y), code=c), None))
    # chaque fichier à part : une source absente (changement de saison...) ne bloque pas les autres
    for f, url, max_age_h in jobs:
        if max_age_h != 0 and keep(f, max_age_h):
            continue
        try:
            data = _get(url)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        except Exception as e:  # noqa: BLE001
            print(f"   {f.name} indisponible ({type(e).__name__}) : on garde la version précédente s'il y en a une")


# ---------------------------------------------------------------- données

def domestic_odds() -> pd.DataFrame:
    """Cotes d'avant-match des prochains jours (football-data.co.uk) et heure de coup d'envoi (heure de Londres)."""
    f = RAW / "fixtures.csv"
    if not f.exists():
        return pd.DataFrame(columns=["competition", "home", "away", "oh", "od", "oa", "fd_kickoff"])
    u = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip")
    u = u[u["Div"].isin([k for k, v in COMPS.items() if "cc" in v])]
    o = _odds(u, PRE_MATCH)
    cc = u["Div"].map({k: v["cc"] for k, v in COMPS.items() if "cc" in v})
    return pd.DataFrame({"competition": u["Div"].to_numpy(), "home": (cc + ":" + u["HomeTeam"].str.strip()).to_numpy(),
                         "away": (cc + ":" + u["AwayTeam"].str.strip()).to_numpy(), "oh": o[:, 0], "od": o[:, 1], "oa": o[:, 2],
                         "fd_kickoff": [S.kickoff_utc(d, t, S.LONDON) for d, t in zip(_dates(u["Date"]), u["Time"])]})


def calendar_for(comp: str, js: dict | None, idx: SRC.TeamIndex) -> pd.DataFrame:
    """Calendrier complet de la saison : football-data.org si la clé est là, sinon openfootball (championnats)."""
    if js:
        f = SRC.fdorg_frame(js, comp, idx)
    else:
        info = COMPS[comp]
        path = RAW / f"{info.get('of')}.json"
        if "of" not in info or not path.exists():
            return pd.DataFrame()
        f = SRC.openfootball_league(path, comp, info["cc"], info["tz"], idx)
        n = pd.to_numeric(f["round"].astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0).astype(int)
        f["journee"], f["ordre"] = [f"Journée {k}" for k in n], n
        f["heure_connue"], f["stage"], f["status"] = f["kickoff"].notna(), None, None
        f["home_tla"] = f["away_tla"] = None
    f["jour"] = [S.paris_day(k) if isinstance(k, str) else j for k, j in zip(f["kickoff"], f.get("jour", [None] * len(f)))]
    f.loc[~f["heure_connue"].astype(bool), "kickoff"] = None
    return f


def europa_calendar(events: list, odds: dict, results: pd.DataFrame, idx: SRC.TeamIndex, now: datetime) -> pd.DataFrame:
    """Ligue Europa : matchs à venir de The Odds API et résultats déjà relevés. Pas de numéro de journée :
    les matchs d'une même semaine forment une journée."""
    up = SRC.odds_frame(events, odds, "LEC", idx, now)
    rows = [up] if len(up) else []
    if len(results):
        r = results.copy()
        r["home"] = [idx.resolve(n) for n in r["home_name"]]
        r["away"] = [idx.resolve(n) for n in r["away_name"]]
        r["played"], r["neutral"] = True, False
        rows.append(r[["competition", "kickoff", "home", "away", "home_name", "away_name", "hg", "ag", "played", "neutral"]])
    if not rows:
        return pd.DataFrame()
    f = pd.concat(rows, ignore_index=True)
    f["jour"] = [S.paris_day(k) for k in f["kickoff"]]
    f["heure_connue"], f["stage"], f["status"] = True, None, None
    f["home_tla"] = f["away_tla"] = None
    days = pd.to_datetime(f["jour"])
    week = days.dt.to_period("W-SUN").astype(str)
    order = {w: i + 1 for i, w in enumerate(sorted(set(week)))}
    first = days.groupby(week).transform("min")
    f["ordre"] = week.map(order).astype(int)
    f["journee"] = [f"Semaine du {d.day} {MONTHS[d.month - 1]}" for d in first]
    return f


def load(now: datetime):
    """Tous les matchs joués (pour le modèle et les face-à-face) et le calendrier de chaque compétition."""
    dom = leagues.load(RAW, FIRST_SEASON, C.CURRENT_SEASON)
    dom["is_cup"], dom["neutral"] = False, False
    old = leagues.load(RAW, H2H_FIRST, FIRST_SEASON - 1)
    idx = SRC.TeamIndex(list(pd.unique(pd.concat([dom, old])[["home", "away"]].values.ravel())))
    hist = cups.load(RAW / "cups").dropna(subset=["hg", "ag"])
    hist["home"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["home_of"], hist["home_cc"])]
    hist["away"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["away_of"], hist["away_cc"])]
    hist["league"], hist["is_cup"] = hist["competition"], True
    names, tlas = {}, {}
    for t, nm in zip(pd.concat([hist["home"], hist["away"]]), pd.concat([hist["home_of"], hist["away_of"]])):
        names[t] = display(nm)

    token, key = os.environ.get("FOOTBALL_DATA_ORG_TOKEN"), os.environ.get("ODDS_API_KEY")
    cal = {}
    for comp in ("E0", "D1", "SP1", "F1", "LDC"):
        try:
            js = SRC.football_data_org(SRC.FDORG_CODES[comp], C.CURRENT_SEASON, token, RAW, now)
        except RuntimeError as e:   # une source en panne ou une clé refusée ne bloque pas le reste
            print(f"   {COMPS[comp]['nom']} (football-data.org) indisponible : {e}")
            js = SRC.football_data_org(SRC.FDORG_CODES[comp], C.CURRENT_SEASON, None, RAW, now)
        cal[comp] = calendar_for(comp, js, idx)
    odds_cups = {}
    for comp in ("LDC", "LEC"):
        try:
            events, odds = SRC.odds_api(comp, key, ODDS_STATE, now)
            if comp == "LEC":
                SRC.odds_scores(comp, key, ODDS_STATE, now, CUP_RESULTS)
        except RuntimeError as e:
            print(f"   {COMPS[comp]['nom']} (The Odds API) indisponible : {e}")
            events, odds = SRC.odds_api(comp, None, ODDS_STATE, now)
        odds_cups[comp] = (events, odds)
    results = pd.read_csv(CUP_RESULTS) if CUP_RESULTS.exists() and CUP_RESULTS.stat().st_size else pd.DataFrame()
    cal["LEC"] = europa_calendar(*odds_cups["LEC"], results[results["competition"] == "LEC"] if len(results) else results, idx, now)
    if len(cal["LDC"]):
        for c in ("oh", "od", "oa"):
            cal["LDC"][c] = np.nan
        o = SRC.odds_frame(*odds_cups["LDC"], "LDC", idx, now)
        if len(o):
            up = ~cal["LDC"]["played"].astype(bool)
            got, lost = SRC.attach_odds(cal["LDC"][up], o)
            for c in ("oh", "od", "oa"):
                cal["LDC"].loc[got.index, c] = got[c]
            if lost:
                print(f"   Ligue des champions : {lost} match(s) avec cotes sans place dans le calendrier")

    # championnats : un match est joué s'il a un score chez football-data.co.uk (tirs cadrés, cotes) ou football-data.org
    fdo = domestic_odds()
    extra = []
    for comp, f in cal.items():
        if not len(f):
            continue
        for c in ("oh", "od", "oa"):
            if c not in f:
                f[c] = np.nan
        if "cc" in COMPS[comp]:
            cur = dom[(dom["league"] == comp) & (dom["season"] == C.CURRENT_SEASON)]
            sc = {(h, a): (g1, g2) for h, a, g1, g2 in zip(cur["home"], cur["away"], cur["hg"], cur["ag"])}
            for i, r in f.iterrows():
                if (r["home"], r["away"]) in sc:
                    f.loc[i, ["hg", "ag"]] = sc[(r["home"], r["away"])]
                    f.loc[i, "played"] = True
                elif bool(r["played"]):
                    extra.append({"date": pd.Timestamp(r["jour"]), "home": r["home"], "away": r["away"], "hg": r["hg"],
                                  "ag": r["ag"], "league": comp, "is_cup": False, "neutral": False, "season": C.CURRENT_SEASON})
            o = fdo[fdo["competition"] == comp].set_index(["home", "away"])
            for i, r in f[~f["played"].astype(bool)].iterrows():
                if (r["home"], r["away"]) in o.index:
                    x = o.loc[(r["home"], r["away"])]
                    f.loc[i, ["oh", "od", "oa"]] = [x["oh"], x["od"], x["oa"]]
                    if not isinstance(r["kickoff"], str) and isinstance(x["fd_kickoff"], str):
                        f.loc[i, "kickoff"], f.loc[i, "jour"] = x["fd_kickoff"], S.paris_day(x["fd_kickoff"])
        else:
            for r in f[f["played"].astype(bool)].itertuples():
                extra.append({"date": pd.Timestamp(r.jour), "home": r.home, "away": r.away, "hg": r.hg, "ag": r.ag,
                              "league": comp, "is_cup": True, "neutral": bool(r.neutral), "season": C.CURRENT_SEASON})
        for side in ("home", "away"):
            for t, nm, tla in zip(f[side], f[f"{side}_name"], f[f"{side}_tla"]):
                names[t] = display(nm)
                if isinstance(tla, str) and tla:
                    tlas[t] = tla
        cal[comp] = f
    cols = ["date", "home", "away", "hg", "ag", "league", "is_cup", "neutral", "season"]
    allm = pd.concat([dom, hist[cols]] + ([pd.DataFrame(extra)[cols]] if extra else []), ignore_index=True)
    allm = allm.dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)
    h2h = pd.concat([old.assign(is_cup=False), allm], ignore_index=True).dropna(subset=["hg", "ag"])
    unknown = sorted({t for f in cal.values() if len(f) for t in pd.concat([f["home"], f["away"]]) if t.startswith("?:")})
    if unknown:
        print("   clubs non reconnus, ajouter leur nom à names.NO_COUNTRY :", unknown)
    if idx.approx:
        print("   rapprochements de noms à vérifier :", sorted(idx.approx))
    return allm, h2h, cal, names, tlas


# ---------------------------------------------------------------- backtest et reconstitution

def code_hash() -> str:
    h = hashlib.sha256()
    for f in ("joint.py", "joint_backtest.py", "names.py", "leagues.py", "cups.py", "model.py", "pipeline.py", "config.py"):
        h.update((C.ROOT / "football" / f).read_bytes())
    return h.hexdigest()[:16]


def backtest(allm: pd.DataFrame) -> dict:
    """Rejoué chaque semaine depuis 2021 ; gardé une semaine (les saisons passées ne changent plus)."""
    cache = RAW / "backtest_foot.pkl"
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
        row = {"competition": comp, "nom": COMPS[comp]["nom"], "matchs": int(i.sum()),
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


def reconstitute(allm: pd.DataFrame, a: float, b: float) -> dict:
    """Ce que le modèle aurait annoncé avant chaque match déjà joué cette saison (réajusté chaque semaine
    sur les seuls matchs d'avant). Clé : (compétition, domicile, extérieur) -> liste de (date, probabilités)."""
    p = JB.weekly(allm, [C.CURRENT_SEASON], XI, SOT_SHARE)
    if not len(p):
        return {}
    pm = JB.probs(p, RHO)
    mk = M.market_probs(p[["oh", "od", "oa"]].to_numpy(float)) if "oh" in p else np.full_like(pm, np.nan)
    bl = M.blend(pm, mk, a, b)
    out = {}
    for r, q in zip(p.itertuples(), bl):
        out.setdefault((r.league, r.home, r.away), []).append((r.date, S.round_probs(q)))
    return out


# ---------------------------------------------------------------- pronostics

def club_info(t: str, names: dict, tlas: dict) -> dict:
    """Nom affiché, sigle, couleurs (connues pour la Ligue 1) et logo libre s'il existe."""
    cc, fd = t.split(":", 1)
    nom = names.get(t, fd)
    words = [w for w in re.split(r"[\s.\-]+", nom) if w and w[0].isalpha() and w.lower() not in {"de", "la", "le", "of", "fc"}]
    sigle = tlas.get(t) or ("".join(w[0] for w in words[:3]) if len(words) > 1 else (words[0] if words else fd)[:3])
    info = {"nom": nom, "sigle": sigle.upper()}
    if cc == "FRA" and fd in C.CLUBS:
        _, sigle, c1, c2 = C.CLUBS[fd]
        info.update(sigle=sigle, couleur=c1, couleur2=c2)
        logo = C.ROOT / "site" / "assets" / "logos" / f"{fd.lower().replace(' ', '-')}.svg"
        if logo.exists():
            info["logo"] = f"assets/logos/{logo.name}"
    return info


def predict(fit: dict, r, bt: dict) -> dict:
    is_cup = r["competition"] in ("LDC", "LEC")
    lh, la = joint.rates(fit, r["home"], r["away"], bool(r["neutral"]), is_cup)
    p_model = M.outcome(M.score_matrix(lh, la, RHO))
    odds = np.array([[r["oh"], r["od"], r["oa"]]], float)
    has = bool(np.isfinite(odds).all())
    p = M.blend(p_model[None], M.market_probs(odds), bt["a"], bt["b"])[0] if has else p_model
    if has:
        lh, la = S.calibrate_rates(lh, la, p, RHO)
    mat = M.score_matrix(lh, la, RHO)
    top = np.argsort(mat, axis=None)[::-1][:3]
    g = np.add.outer(np.arange(mat.shape[0]), np.arange(mat.shape[1]))
    return {"p": S.round_probs(p), "avec_cotes": has, "xg": [round(lh, 1), round(la, 1)], "lam": (lh, la),
            "scores": [{"score": f"{i // mat.shape[1]}-{i % mat.shape[1]}", "p": round(float(mat.flat[i]), 2)} for i in top],
            "plus25": round(float(mat[g > 2].sum()), 2)}


def strength(fit: dict, t: str) -> float:
    i = fit["teams"].get(t)
    return float(fit["att"][i] + fit["def"][i]) if i is not None else -1.0


def entropy(p) -> float:
    q = np.clip(np.asarray(p, float), 1e-9, 1)
    return float(-(q * np.log(q)).sum() / np.log(3))


# ---------------------------------------------------------------- export

def write_all(files: dict) -> None:
    """Écrit tous les fichiers d'abord à côté, puis les met en place : jamais de mélange ancien/nouveau."""
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = {}
    for name, obj in files.items():
        t = OUT / f".{name}.json.tmp"
        t.write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        tmp[name] = t
    for name, t in tmp.items():
        os.replace(t, OUT / f"{name}.json")


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    return o


def zones_for(comp: str, n: int) -> list:
    if COMPS[comp]["type"] == "coupe":
        return CUP_ZONES if n == 36 else []
    return LEAGUE_ZONES.get(n, [("titre", "Titre", 1, 1), ("top4", "Top 4", 1, 4)])


def main(offline: bool = False) -> None:
    now = datetime.now(timezone.utc)
    today = now.astimezone(S.PARIS).strftime("%Y-%m-%d")
    if not offline:
        print("1/5 Téléchargement")
        download()
    print("2/5 Données")
    allm, h2h_all, cal, names, tlas = load(now)
    print(f"   {len(allm)} matchs joués ; calendrier : " + ", ".join(f"{COMPS[c]['nom']} {len(f)}" for c, f in cal.items()))
    print("3/5 Backtest et reconstitution")
    bt = backtest(allm)
    rec = reconstitute(allm, bt["a"], bt["b"])
    print("4/5 Pronostics")
    fit = joint.fit(allm, pd.Timestamp(now.date()) + pd.Timedelta(days=1), XI, SOT_SHARE, JB.sot_ratio(allm, pd.Timestamp(now.date())))
    upcoming_rows = []
    for comp, f in cal.items():
        if not len(f):
            continue
        preds = []
        for _, r in f.iterrows():
            started = isinstance(r["kickoff"], str) and ts(r["kickoff"]) <= now
            preds.append(None if bool(r["played"]) or started else predict(fit, r, bt))
        f["pred"] = preds
        for r in f[f["pred"].notna()].itertuples():
            upcoming_rows.append({"competition": comp, "journee": r.journee, "jour": r.jour, "kickoff": r.kickoff,
                                  "home": r.home, "away": r.away, "p": r.pred["p"], "avec_cotes": r.pred["avec_cotes"]})
    added = JR.record(upcoming_rows, JOURNAL, now)
    print(f"   journal : {added} pronostic(s) publié(s)")

    # résultats connus, pour juger le journal (un match reporté garde son identifiant d'origine)
    results, by_pair = {}, {}
    for comp, f in cal.items():
        if not len(f):
            continue
        for r in f[f["played"].astype(bool)].itertuples():
            results[JR.match_id(comp, r.home, r.away, r.jour)] = (int(r.hg), int(r.ag))
            by_pair.setdefault(f"{comp}|{r.home}|{r.away}", []).append((r.jour, (int(r.hg), int(r.ag))))
    jr = JR.read(JOURNAL)
    for r in jr.itertuples():
        if r.match_id in results:
            continue
        cand = [x for x in by_pair.get(r.match_id.rsplit("|", 1)[0], []) if x[0] >= r.publie_utc[:10]]
        if cand:
            results[r.match_id] = min(cand)[1]
    evals = JR.evaluate(JOURNAL, results)
    published = {e["match_id"]: e for e in evals}
    published_pair = {e["match_id"].rsplit("|", 1)[0]: e for e in evals}   # match reporté : même affiche, autre date
    pending = {r.match_id: [r.p_dom, r.p_nul, r.p_ext] for r in jr.itertuples()}

    print("5/5 Classements, simulations et fichiers du site")
    files, summary, search, recent = {}, [], [], []
    for comp, info in COMPS.items():
        f = cal.get(comp, pd.DataFrame())
        clubs = sorted(set(f["home"]) | set(f["away"])) if len(f) else []
        matchs = []
        for _, r in f.sort_values(["ordre", "jour"]).iterrows() if len(f) else []:
            mid = JR.match_id(comp, r["home"], r["away"], r["jour"])
            item = {"id": mid, "journee": r["journee"], "ordre": int(r["ordre"]), "jour": r["jour"],
                    "kickoff": r["kickoff"] if isinstance(r["kickoff"], str) else None, "home": r["home"], "away": r["away"]}
            if bool(r["played"]):
                hg, ag = int(r["hg"]), int(r["ag"])
                item.update(etat="joue", score=[hg, ag])
                y = JR.outcome(hg, ag)
                pub = published.get(mid) or (published_pair.get(mid.rsplit("|", 1)[0]) if info["type"] == "ligue" else None)
                if pub:
                    item.update(p=pub["p"], source="publie")
                else:
                    cands = [q for d, q in rec.get((comp, r["home"], r["away"]), []) if abs((d - pd.Timestamp(r["jour"])).days) <= 3]
                    if cands:
                        item.update(p=cands[0], source="reconstitue")
                if "p" in item:
                    item["surprise"] = bool(item["p"][y] < JR.SURPRISE)
                    if (now.date() - pd.Timestamp(r["jour"]).date()).days <= RECENT_DAYS and item["surprise"]:
                        recent.append({**item, "competition": comp})
            elif isinstance(r["pred"], dict):
                pr = r["pred"]
                item.update(etat="a_venir", p=pr["p"], avec_cotes=pr["avec_cotes"], xg=pr["xg"], scores=pr["scores"],
                            plus25=pr["plus25"])
            else:
                item["etat"] = "en_cours" if isinstance(r["kickoff"], str) and now - ts(r["kickoff"]) < timedelta(hours=3) else "en_attente"
                if mid in pending:
                    item.update(p=S.round_probs(pending[mid]), source="publie")
            matchs.append(item)
        ahead = [m for m in matchs if m["etat"] == "a_venir" and (m["jour"] or "9999") >= today]
        prochaine = min(ahead, key=lambda m: (m["jour"] or "9999", m["ordre"]))["journee"] if ahead else (matchs[-1]["journee"] if matchs else None)
        journees = []
        for m in matchs:
            if m["journee"] not in journees:
                journees.append(m["journee"])

        # classement et fin de saison simulée (phase de ligue seulement pour la Ligue des champions)
        classement, projection, zones = [], [], []
        league_part = f if info["type"] == "ligue" else (f[f["stage"] == "LEAGUE_STAGE"] if len(f) and "stage" in f and comp == "LDC" else f.iloc[0:0])
        if len(league_part):
            teams = sorted(set(league_part["home"]) | set(league_part["away"]))
            played = league_part[league_part["played"].astype(bool)][["home", "away", "hg", "ag"]].astype({"hg": int, "ag": int})
            tab = S.table(played, teams)
            classement = [{"club": t, **{k: int(v) for k, v in row.items()}} for t, row in tab.to_dict("index").items()]
            rest = league_part[league_part["pred"].notna()]
            if len(rest):
                up = pd.DataFrame({"home": rest["home"], "away": rest["away"], "lam_h": [x["lam"][0] for x in rest["pred"]],
                                   "lam_a": [x["lam"][1] for x in rest["pred"]]})
                pts, places = S.simulate_places(played, up, teams, RHO)
                zones = zones_for(comp, len(teams))
                for i, t in enumerate(teams):
                    row = {"club": t, "points_attendus": round(float(pts[i]), 1),
                           "rang_moyen": round(float((places[i] * np.arange(1, len(teams) + 1)).sum()), 1),
                           "places": [round(float(x), 4) for x in places[i]]}
                    for key, _, lo, hi in zones:
                        row[key] = round(float(places[i][lo - 1:hi].sum()), 4)
                    projection.append(row)
                projection.sort(key=lambda x: x["rang_moyen"])

        perf = next((x for x in bt["table"] if x["competition"] == comp), None)
        jc = [e for e in evals if e["competition"] == comp]
        pair = set(clubs)
        hh = h2h_all[h2h_all["home"].isin(pair) & h2h_all["away"].isin(pair)].sort_values("date", ascending=False)
        files[f"h2h_{info['slug']}"] = {"matchs": [[r.date.strftime("%Y-%m-%d"), r.home, r.away, int(r.hg), int(r.ag), r.league]
                                                   for r in hh.itertuples()]}
        clubs_info = {t: club_info(t, names, tlas) for t in clubs}
        files[info["slug"]] = {
            "maj_utc": iso(now), "code": comp, "slug": info["slug"], "nom": info["nom"], "type": info["type"],
            "saison": f"{C.CURRENT_SEASON}-{C.CURRENT_SEASON + 1}", "clubs": clubs_info, "matchs": matchs,
            "journees": journees, "prochaine": prochaine, "classement": classement, "projection": projection,
            "zones": [{"cle": k, "nom": nm, "de": lo, "a": hi} for k, nm, lo, hi in zones],
            "fiabilite": perf, "journal": jc[-60:], "simulations": S.N_SIM,
        }
        nxt = [m for m in ahead if m["journee"] == prochaine]
        summary.append({"code": comp, "slug": info["slug"], "nom": info["nom"], "type": info["type"], "prochaine": prochaine,
                        "du": min((m["jour"] for m in nxt), default=None), "au": max((m["jour"] for m in nxt), default=None),
                        "a_venir": len(ahead), "leader": classement[0]["club"] if classement and classement[0]["j"] else None,
                        "leader_nom": clubs_info.get(classement[0]["club"], {}).get("nom") if classement and classement[0]["j"] else None,
                        "favori": (lambda b: {"club": b["club"], "nom": clubs_info[b["club"]]["nom"], "p": b[zones[0][0]]})(
                            max(projection, key=lambda x: x[zones[0][0]])) if projection and zones else None,
                        "zone_favori": zones[0][1] if zones else None,
                        "journal": {"matchs": len(jc), "favoris_justes": sum(e["favori_juste"] for e in jc)}})
        for m in ahead:
            search.append({"c": comp, "id": m["id"], "jour": m["jour"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
                           "p": m["p"]})

    # matchs à la une : coupes d'Europe d'abord, grands clubs, issue ouverte ; deux par compétition au plus
    horizon = (now + timedelta(days=7)).astimezone(S.PARIS).strftime("%Y-%m-%d")
    weight = {"LDC": 1.0, "LEC": 0.6}
    cand = sorted((m for m in search if m["jour"] and m["jour"] <= horizon),
                  key=lambda m: -(weight.get(m["c"], 0.3) + 0.35 * (strength(fit, m["home"]) + strength(fit, m["away"])) + 0.6 * entropy(m["p"])))
    featured, per = [], {}
    for m in cand:
        if per.get(m["c"], 0) < 2:
            featured.append(m)
            per[m["c"]] = per.get(m["c"], 0) + 1
        if len(featured) == FEATURED:
            break
    featured.sort(key=lambda m: m["kickoff"] or m["jour"])
    recent.sort(key=lambda m: (m["jour"], -min(m["p"][JR.outcome(*m["score"])], 1)), reverse=True)
    all_clubs = {}
    for comp, info in COMPS.items():
        for t, c in files[info["slug"]]["clubs"].items():
            e = all_clubs.setdefault(t, {**c, "competitions": []})
            e["competitions"].append(comp)
    search.sort(key=lambda m: m["kickoff"] or (m["jour"] or "9999") + "T23:59")
    shown = {t for m in featured + recent[:8] for t in (m["home"], m["away"])}
    files["index"] = {"maj_utc": iso(now), "competitions": summary, "a_la_une": featured,
                      "surprises": recent[:8], "part_marche": round(bt["b"] / (bt["a"] + bt["b"]), 1),
                      "fiabilite": bt["table"], "saisons_test": TEST,
                      "slugs": {c: v["slug"] for c, v in COMPS.items()}, "noms": {c: v["nom"] for c, v in COMPS.items()},
                      "clubs": {t: all_clubs[t] for t in shown if t in all_clubs}}
    files["recherche"] = {"maj_utc": iso(now), "clubs": all_clubs, "matchs": search,
                          "competitions": {c: {"nom": v["nom"], "slug": v["slug"]} for c, v in COMPS.items()}}
    write_all(files)
    print(f"   {len(search)} matchs à venir, {len(all_clubs)} clubs, {len(recent)} surprise(s) récente(s). Terminé.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
