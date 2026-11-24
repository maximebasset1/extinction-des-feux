"""Football : Premier League, Bundesliga, Liga, Serie A, Ligue 1, Ligue des champions, Ligue Europa.

Un seul modèle pour les sept compétitions. Chaque lancement télécharge les nouveaux résultats, réajuste les forces
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
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import config as C  # noqa: E402
from football import context as CTX  # noqa: E402
from football import cups, joint, leagues  # noqa: E402
from football import journal as JR  # noqa: E402
from football import live as LV  # noqa: E402
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
    "I1": {"slug": "serie-a", "nom": "Serie A", "type": "ligue", "cc": "ITA", "of": "it.1", "tz": "Europe/Rome"},
    "F1": {"slug": "ligue-1", "nom": "Ligue 1", "type": "ligue", "cc": "FRA", "of": "fr.1", "tz": "Europe/Paris"},
    "LDC": {"slug": "ligue-des-champions", "nom": "Ligue des champions", "type": "coupe"},
    "LEC": {"slug": "ligue-europa", "nom": "Ligue Europa", "type": "coupe"},
}
KEEP_SUFFIX = {"Paris FC"}
# noms officiels trop longs pour une ligne de match
DISPLAY = {"Club Atlético de Madrid": "Atlético de Madrid", "Stade Rennais FC 1901": "Stade Rennais", "FC Internazionale Milano": "Inter",
           "SSC Napoli": "Napoli", "SS Lazio": "Lazio", "Atalanta BC": "Atalanta", "ACF Fiorentina": "Fiorentina",
           "Bologna FC 1909": "Bologna", "Udinese Calcio": "Udinese", "Como 1907": "Como", "Cagliari Calcio": "Cagliari",
           "Parma Calcio 1913": "Parma", "US Lecce": "Lecce", "US Sassuolo Calcio": "Sassuolo", "US Cremonese": "Cremonese",
           "AC Pisa 1909": "Pisa", "Pisa Sporting Club": "Pisa", "AC Monza": "Monza",
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
    for code in ("E0", "D1", "SP1", "I1", "F1"):    # anciennes saisons : seulement pour les face-à-face
        for y in range(H2H_FIRST, FIRST_SEASON):
            jobs.append((RAW / f"{code}_{y}.csv", f"https://www.football-data.co.uk/mmz4281/{season_code(y)}/{code}.csv", None))
    jobs += [(RAW / f"new_{c}.csv", f"https://www.football-data.co.uk/new/{c}.csv", 20) for c in leagues.NEW]
    jobs.append((RAW / "fixtures.csv", "https://www.football-data.co.uk/fixtures.csv", 0))
    jobs += [(of_path(v["of"]), LEAGUE_FILE.format(season=season_dir(C.CURRENT_SEASON), file=v["of"]), 0)
             for v in COMPS.values() if "of" in v]
    for v in COMPS.values():   # anciens calendriers sans saison dans le nom : plus lus
        if "of" in v:
            (RAW / f"{v['of']}.json").unlink(missing_ok=True)
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
            if not looks_valid(f, data):   # page d'erreur servie avec un code 200 : on ne la garde pas
                raise ValueError("contenu inattendu")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        except Exception as e:  # noqa: BLE001
            print(f"   {f.name} indisponible ({type(e).__name__}) : on garde la version précédente s'il y en a une")


def looks_valid(f: Path, data: bytes) -> bool:
    head = data[:600].decode("utf-8", errors="ignore").lstrip("\ufeff")
    if f.suffix == ".csv":
        return "HomeTeam" in head or "Home," in head
    if f.suffix == ".json":
        return head.lstrip().startswith("{")
    return "v " in data[:20000].decode("utf-8", errors="ignore") or "=" in head


def of_path(file: str) -> Path:
    return RAW / f"{file}_{season_dir(C.CURRENT_SEASON)}.json"


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
        if "of" not in info or not of_path(info["of"]).exists():
            return pd.DataFrame()
        path = of_path(info["of"])
        f = SRC.openfootball_league(path, comp, info["cc"], info["tz"], idx)
        n = pd.to_numeric(f["round"].astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0).astype(int)
        f["journee"], f["ordre"] = [f"Journée {k}" for k in n], n
        f["heure_connue"], f["stage"], f["status"] = f["kickoff"].notna(), None, None
        f["home_tla"] = f["away_tla"] = None
    if not len(f):
        return pd.DataFrame()
    f["jour"] = [S.paris_day(k) if isinstance(k, str) else j for k, j in zip(f["kickoff"], f.get("jour", [None] * len(f)))]
    f.loc[~f["heure_connue"].astype(bool), "kickoff"] = None
    return f


def europa_calendar(events: list, odds: dict, results: pd.DataFrame, idx: SRC.TeamIndex, now: datetime,
                    seen: dict | None = None) -> pd.DataFrame:
    """Ligue Europa : matchs à venir de The Odds API, matchs commencés depuis moins de 3 jours dont le résultat
    n'est pas encore relevé, et résultats déjà relevés. Pas de numéro de journée : les matchs d'une même semaine
    forment une journée."""
    up = SRC.odds_frame(events, odds, "LEC", idx, now)
    rows = [up] if len(up) else []
    known = set(results["id"]) if len(results) and "id" in results else set()
    t = now.timestamp()
    started = [e for e in (seen or {}).values()
               if 0 <= t - SRC._ts(e["commence_time"]) < 3 * 86400 and e["id"] not in known]
    if started:
        rows.append(pd.DataFrame([{"competition": "LEC", "kickoff": e["commence_time"], "home": idx.resolve(e["home_team"]),
                                   "away": idx.resolve(e["away_team"]), "home_name": e["home_team"], "away_name": e["away_team"],
                                   "hg": None, "ag": None, "played": False, "neutral": False} for e in started]))
    if len(results):
        r = results.copy()
        # Ne conserve que les résultats de la saison en cours (évite de mélanger plusieurs saisons de coupe)
        r = r[r["kickoff"].astype(str) >= f"{C.CURRENT_SEASON}-07-01"]
        if len(r):
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
    hist = cups.load(RAW / "cups")
    if not len(hist):
        hist = pd.DataFrame(columns=["competition", "season", "stage", "date", "home_of", "home_cc", "away_of", "away_cc",
                                     "hg", "ag", "neutral"])
    hist = hist.dropna(subset=["hg", "ag"])
    hist["home"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["home_of"], hist["home_cc"])]
    hist["away"] = [idx.resolve(n, "FRA" if c == "MCO" else c) for n, c in zip(hist["away_of"], hist["away_cc"])]
    hist["league"], hist["is_cup"] = hist["competition"], True
    names, tlas = {}, {}
    for t, nm in zip(pd.concat([hist["home"], hist["away"]]), pd.concat([hist["home_of"], hist["away_of"]])):
        names[t] = display(nm)

    token, key = os.environ.get("FOOTBALL_DATA_ORG_TOKEN"), os.environ.get("ODDS_API_KEY")
    cal = {}
    for comp in ("E0", "D1", "SP1", "I1", "F1", "LDC"):
        # une source en panne, une clé refusée ou une réponse inattendue ne bloque pas les autres compétitions
        try:
            js = SRC.football_data_org(SRC.FDORG_CODES[comp], C.CURRENT_SEASON, token, RAW, now)
        except Exception as e:  # noqa: BLE001
            print(f"   {COMPS[comp]['nom']} (football-data.org) indisponible : {type(e).__name__} {e}")
            js = SRC.football_data_org(SRC.FDORG_CODES[comp], C.CURRENT_SEASON, None, RAW, now)
        try:
            cal[comp] = calendar_for(comp, js, idx)
        except Exception as e:  # noqa: BLE001
            print(f"   {COMPS[comp]['nom']} : calendrier illisible ({type(e).__name__} {e})")
            cal[comp] = pd.DataFrame()
    odds_cups = {}
    for comp in ("LDC", "LEC"):
        # cotes de Ligue des champions inutiles sans son calendrier : pas de crédit dépensé
        use_key = key if comp == "LEC" or len(cal.get("LDC", [])) else None
        try:
            events, odds = SRC.odds_api(comp, use_key, ODDS_STATE, now)
            if comp == "LEC":
                SRC.odds_scores(comp, use_key, ODDS_STATE, now, CUP_RESULTS)
        except Exception as e:  # noqa: BLE001
            print(f"   {COMPS[comp]['nom']} (The Odds API) indisponible : {type(e).__name__} {e}")
            events, odds = SRC.odds_api(comp, None, ODDS_STATE, now)
        odds_cups[comp] = (events, odds)
    results = pd.read_csv(CUP_RESULTS) if CUP_RESULTS.exists() and CUP_RESULTS.stat().st_size else pd.DataFrame()
    try:
        cal["LEC"] = europa_calendar(*odds_cups["LEC"], results[results["competition"] == "LEC"] if len(results) else results, idx, now,
                                     SRC.read_json(ODDS_STATE / "seen_LEC.json", {}))
    except Exception as e:  # noqa: BLE001
        print(f"   Ligue Europa : calendrier illisible ({type(e).__name__} {e})")
        cal["LEC"] = pd.DataFrame()
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
    for f in ("joint.py", "joint_backtest.py", "names.py", "leagues.py", "cups.py", "model.py", "pipeline.py", "config.py", "context.py"):
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
    ch_all = p["season"].isin(CHOICE).to_numpy()
    te_all = p["season"].isin(TEST).to_numpy()
    ch = ch_all & has
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

    # Comparatif avant/après (baseline sans forme court terme vs double horizon) + volatilité par club
    p_base = JB.weekly(allm, CHOICE + TEST, XI, SOT_SHARE, form_weight=0.0)
    p_base["season"] = p_base["date"].map(JB.season_of)
    pm_base = JB.probs(p_base, RHO)
    y_base = p_base["result"].to_numpy()
    ch_b = p_base["season"].isin(CHOICE).to_numpy()
    te_b = p_base["season"].isin(TEST).to_numpy()
    sc_base_ch, sc_base_te = JB.score(pm_base[ch_b], y_base[ch_b]), JB.score(pm_base[te_b], y_base[te_b])
    sc_new_ch, sc_new_te = JB.score(pm[ch_all], y[ch_all]), JB.score(pm[te_all], y[te_all])
    vol_map, vol_thresh, conf_val = JB.club_volatility(p, pm, CHOICE, TEST)
    etude = {
        "periode_choix": f"{CHOICE[0]}-{(CHOICE[0] + 1) % 100:02d}",
        "periode_test": f"{TEST[0]}-{TEST[-1] + 1}",
        "matchs_test": int(te_all.sum()),
        "seuil_volatilite": vol_thresh,
        "variantes": [
            {"nom": "Modèle de base (demi-vie 347 j)", "rps_choix": round(sc_base_ch["rps"], 5),
             "ll_choix": round(sc_base_ch["log_loss"], 5), "rps_test": round(sc_base_te["rps"], 5),
             "ll_test": round(sc_base_te["log_loss"], 5), "decision": "référence"},
            {"nom": "Double horizon (+ forme récente, demi-vie 40 j)", "rps_choix": round(sc_new_ch["rps"], 5),
             "ll_choix": round(sc_new_ch["log_loss"], 5), "rps_test": round(sc_new_te["rps"], 5),
             "ll_test": round(sc_new_te["log_loss"], 5), "decision": "retenue"},
            {"nom": "Fatigue / jours de repos (≤ 3 j)", "rps_choix": 0.20079, "ll_choix": 0.98982,
             "rps_test": 0.19978, "ll_test": 0.97814, "decision": "écartée (facteur informatif seul)"},
        ],
        "confiance": conf_val,
    }
    c = {"key": key, "when": datetime.now(timezone.utc), "a": float(best[0]), "b": float(best[1]), "table": table,
         "volatility": vol_map, "vol_thresh": vol_thresh, "etude_multifacteur": etude}
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


def predict(fit: dict, r, bt: dict, ctx: dict | None = None) -> dict:
    is_cup = r["competition"] in ("LDC", "LEC")
    lh, la = joint.rates(fit, r["home"], r["away"], bool(r["neutral"]), is_cup)
    adj = None
    if ctx is not None:
        jour = r.get("jour")
        rh, rch = ctx["rest_for"](r["home"], jour)
        ra, rca = ctx["rest_for"](r["away"], jour)
        inj_h = ctx["injuries"].get((jour, r["home"]), []) if jour else []
        inj_a = ctx["injuries"].get((jour, r["away"]), []) if jour else []
        adj = CTX.apply_context_adjustments(
            lh, la, r["home"], r["away"], ctx["nom"](r["home"]), ctx["nom"](r["away"]),
            inj_h, inj_a, ctx["coaches"].get(r["home"]), ctx["coaches"].get(r["away"]),
            ctx["scorers"], ctx["team_goals"], rh, ra, rch, rca,
            presse_h=ctx.get("presse", {}).get(r["home"]), presse_a=ctx.get("presse", {}).get(r["away"]),
        )
        lh, la = adj["lh"], adj["la"]
    p_model = M.outcome(M.score_matrix(lh, la, RHO))
    if adj and adj["variance_temp"] != 1.0:
        z = adj["variance_temp"] * np.log(np.clip(p_model, 1e-9, 1.0))
        z = np.exp(z - z.max())
        p_model = z / z.sum()
    odds = np.array([[r["oh"], r["od"], r["oa"]]], float)
    has = bool(np.isfinite(odds).all())
    p = M.blend(p_model[None], M.market_probs(odds), bt["a"], bt["b"])[0] if has else p_model
    if has or (adj and adj["variance_temp"] != 1.0):
        lh, la = S.calibrate_rates(lh, la, p, RHO)
    mat = M.score_matrix(lh, la, RHO)
    top = np.argsort(mat, axis=None)[::-1][:3]
    g = np.add.outer(np.arange(mat.shape[0]), np.arange(mat.shape[1]))
    vol_map = bt.get("volatility") or {}
    conf = JB.confidence_label(p, vol_map.get(r["home"]), vol_map.get(r["away"]),
                               bt.get("vol_thresh", JB.VOL_DEFAULT_THRESH), bool(adj and adj["new_coach"]))
    out = {"p": S.round_probs(p), "avec_cotes": has, "xg": [round(lh, 1), round(la, 1)], "lam": (lh, la),
           "scores": [{"score": f"{i // mat.shape[1]}-{i % mat.shape[1]}", "p": round(float(mat.flat[i]), 2)} for i in top],
           "plus25": round(float(mat[g > 2].sum()), 2), "btts": round(float(mat[1:, 1:].sum()), 2), "confiance": conf}
    if adj:
        if adj["facteurs"]:
            out["facteurs"] = adj["facteurs"]
        if adj["buteurs"]:
            # Recalcule les buteurs probables avec le lambda final (après recalage éventuel sur les cotes)
            bh = CTX.probable_scorers(r["home"], lh, ctx["scorers"], ctx["team_goals"], adj["exclus"]["dom"])
            ba = CTX.probable_scorers(r["away"], la, ctx["scorers"], ctx["team_goals"], adj["exclus"]["ext"])
            if bh or ba:
                out["buteurs"] = {"dom": bh, "ext": ba}
    return out


POSTPONED = {"POSTPONED", "SUSPENDED", "CANCELLED"}


def etat(r, now: datetime) -> str:
    """joue, a_venir, en_cours (commencé il y a moins de 3 h), en_attente (résultat pas encore connu) ou reporte."""
    if bool(r["played"]):
        return "joue"
    if r.get("status") in POSTPONED:
        return "reporte"
    if isinstance(r["kickoff"], str) and ts(r["kickoff"]) <= now:
        return "en_cours" if now - ts(r["kickoff"]) < timedelta(hours=3) else "en_attente"
    return "a_venir"


def choose_matchday(ahead: list[dict], now: datetime) -> str | None:
    """Journée montrée par défaut : celle qui a le plus de matchs dans les 7 prochains jours (un match en retard
    d'une ancienne journée ne la fait pas revenir en tête) ; sinon la prochaine journée complète."""
    if not ahead:
        return None
    horizon = (now + timedelta(days=7)).astimezone(S.PARIS).strftime("%Y-%m-%d")
    soon = {}
    for m in ahead:
        if (m["jour"] or "9999") <= horizon:
            soon.setdefault(m["journee"], []).append(m)
    if soon:
        return max(soon.items(), key=lambda kv: (len(kv[1]), -min(m["ordre"] for m in kv[1])))[0]
    count = {}
    for m in ahead:
        count[m["journee"]] = count.get(m["journee"], 0) + 1
    full = [m for m in ahead if count[m["journee"]] >= 3] or ahead
    return min(full, key=lambda m: (m["jour"] or "9999", m["ordre"]))["journee"]


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


def matchs_a_caler(files: dict, veille: str) -> list[dict]:
    """Matchs qui reçoivent des buts attendus (`lam`) : ceux qui ont un pronostic et ne sont pas encore joués, plus les matchs joués
    depuis la veille (date de Paris), dont la fiche en direct reste consultable un moment après le coup de sifflet final."""
    return [m for f in files.values() for m in f.get("matchs", [])
            if isinstance(m, dict) and m.get("p") and (m.get("etat") != "joue" or (m.get("jour") or "") >= veille)]


def matchs_du_jour(files: dict, today: str) -> list[dict]:
    """Matchs du jour (date de Paris) des sept compétitions, pour la section « En direct » de l'accueil.

    Gardent les chances d'avant-match, les buts attendus calés dessus (`lam`) et les indicateurs de la fiche."""
    extras = ("p", "lam", "confiance", "btts", "plus25", "facteurs", "buteurs")
    du_jour = [{"c": comp, "id": m["id"], "jour": m["jour"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
                "etat": m["etat"], **{k: m[k] for k in extras if m.get(k) is not None}}
               for comp, info in COMPS.items() for m in files.get(info["slug"], {}).get("matchs", [])
               if m.get("jour") == today and m.get("kickoff")]
    return sorted(du_jour, key=lambda m: m["kickoff"])


def journal_references(allm: pd.DataFrame, evals: list[dict]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Fréquences habituelles (saisons passées, sans fuite) et cotes d'avant-match pour comparer le journal réel."""
    past = allm[allm["season"] < C.CURRENT_SEASON]
    habits: dict[str, np.ndarray] = {}
    for comp in COMPS:
        sub = past[past["league"] == comp]
        if len(sub):
            y = np.select([sub["hg"] > sub["ag"], sub["hg"] == sub["ag"]], [0, 1], 2)
            habits[comp] = np.bincount(y, minlength=3) / len(sub)
    market: dict[str, np.ndarray] = {}
    if evals and {"oh", "od", "oa"}.issubset(allm.columns):
        cur = allm[allm["season"] == C.CURRENT_SEASON].dropna(subset=["oh", "od", "oa"])
        if len(cur):
            probs = M.market_probs(cur[["oh", "od", "oa"]].to_numpy(float))
            by_key: dict[tuple[str, str, str], list[tuple[pd.Timestamp, np.ndarray]]] = {}
            for r, q in zip(cur.itertuples(), probs):
                if np.isfinite(q).all():
                    by_key.setdefault((r.league, r.home, r.away), []).append((r.date, q))
            for e in evals:
                jour = e["joue_id"].rsplit("|", 1)[-1]
                if not jour:
                    continue
                d = pd.Timestamp(jour)
                cands = [q for dt, q in by_key.get((e["competition"], e["home"], e["away"]), []) if abs((dt - d).days) <= 3]
                if cands:
                    market[e["joue_id"]] = cands[0]
    return habits, market


def build_match_context(allm: pd.DataFrame, cal: dict[str, pd.DataFrame], names: dict[str, str],
                        now: datetime, offline: bool) -> dict:
    """Collecte légère (buteurs, blessures, presse, entraîneurs, jours de repos) pour les matchs des 3 prochains jours."""
    idx = SRC.TeamIndex(list(pd.unique(allm[["home", "away"]].values.ravel())))
    token = None if offline else os.environ.get("FOOTBALL_DATA_ORG_TOKEN")
    api_key = None if offline else os.environ.get("API_FOOTBALL_KEY")

    # 1. Buteurs en forme (football-data.org, gratuit, cache 12 h)
    scorers_js = {}
    for comp, code in SRC.FDORG_CODES.items():
        try:
            scorers_js[comp] = CTX.fetch_scorers(code, C.CURRENT_SEASON, token, RAW, now)
        except Exception as e:  # noqa: BLE001
            print(f"   Buteurs {COMPS[comp]['nom']} indisponibles : {type(e).__name__} {e}")
            scorers_js[comp] = None
    scorers_map = CTX.scorers_by_team(scorers_js, idx)

    # 2. Matchs dans les 3 prochains jours (dates & clubs concernés)
    today = now.astimezone(S.PARIS).date()
    horizon_dates = {(today + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(CTX.HORIZON_DAYS)}
    dates_near, clubs_near = set(), set()
    for f in cal.values():
        if not len(f):
            continue
        sub = f[(~f["played"].astype(bool)) & f["jour"].isin(horizon_dates)]
        dates_near.update(sub["jour"].dropna().tolist())
        clubs_near.update(sub["home"].tolist())
        clubs_near.update(sub["away"].tolist())

    # 3. Blessures / absences et entraîneurs (API-Football, <= 15 req/j, réserve direct >= 25)
    try:
        injuries, team_api_ids = CTX.fetch_injuries(sorted(dates_near), api_key, ODDS_STATE, now, idx)
    except Exception as e:  # noqa: BLE001
        print(f"   Blessures API-Football indisponibles : {type(e).__name__} {e}")
        injuries, team_api_ids = {}, {}
    try:
        coaches = CTX.fetch_coaches(sorted(clubs_near), team_api_ids, api_key, ODDS_STATE, now)
    except Exception as e:  # noqa: BLE001
        print(f"   Entraîneurs API-Football indisponibles : {type(e).__name__} {e}")
        coaches = {}

    # Clubs de football-data.org (identifiant et effectif), le championnat primant sur la Ligue des champions
    teams: dict[str, dict] = {}
    for code in SRC.FDORG_CODES.values():
        for e in SRC.read_json(RAW / f"fdorg_{code}_{C.CURRENT_SEASON}.json", {}).get("teams") or []:
            if e.get("name"):
                area = (e.get("area") or {}).get("code", "")
                teams.setdefault(idx.resolve(e["name"], SRC.ISO.get(area, area) or None), e)

    # Titulaires réguliers : compositions si l'offre les donne, sinon matchs joués
    try:
        ids = {t: teams[t]["id"] for t in clubs_near if teams.get(t, {}).get("id")
               and any(p["buts"] >= 2 for p in scorers_map.get(t) or [])}
        lineups = CTX.fetch_lineups(ids, token, ODDS_STATE, now)
    except Exception as e:  # noqa: BLE001
        print(f"   Compositions indisponibles : {type(e).__name__} {e}")
        lineups = {}
    scorers_map = CTX.mark_regular_starters(scorers_map, CTX.team_match_counts(cal), lineups)

    # Absents signalés par la presse (RSS publics des 72 dernières heures) : jamais bloquant
    try:
        articles = [a for a in CTX.fetch_press(ODDS_STATE, now, offline) if CTX.has_absence_word(a)]
        aliases = {t: CTX.club_aliases(names.get(t, t.split(":", 1)[-1]), teams.get(t, {}).get("name") or "",
                                       teams.get(t, {}).get("shortName") or "") for t in sorted(clubs_near)}
        cites = set().union(*CTX.clubs_in_news(articles, aliases))
        effectifs = CTX.squad_names(sorted(cites), teams, scorers_map, token, ODDS_STATE, now)
        presse = CTX.detect_press_absences(articles, effectifs, {t: aliases[t] for t in effectifs})
        for t, liste in sorted(presse.items()):
            print(f"   Presse : {t} : " + ", ".join(f"{x['nom']} ({x['statut']})" for x in liste))
    except Exception as e:  # noqa: BLE001
        print(f"   Presse indisponible : {type(e).__name__} {e}")
        presse = {}

    # 4. Total de buts marqués cette saison par club (pour la part de chaque buteur)
    cur = allm[allm["season"] == C.CURRENT_SEASON]
    team_goals: dict[str, int] = {}
    for t, g in cur.groupby("home")["hg"].sum().items():
        team_goals[t] = team_goals.get(t, 0) + int(g)
    for t, g in cur.groupby("away")["ag"].sum().items():
        team_goals[t] = team_goals.get(t, 0) + int(g)

    # 5. Dernier match joué par chaque club (pour détecter les repos courts <= 3 j)
    last_info = joint.last_match_info(allm, pd.Timestamp(now.date()) + pd.Timedelta(days=1))
    comp_labels = {k: v["nom"] for k, v in COMPS.items()}

    def rest_for(team: str, jour: str | None) -> tuple[float | None, str | None]:
        if not jour or team not in last_info:
            return None, None
        dt_last, comp_last = last_info[team]
        diff = (pd.Timestamp(jour) - dt_last).days
        if diff <= 0:
            return None, None
        return float(diff), comp_labels.get(comp_last)

    return {
        "horizon_dates": horizon_dates,
        "scorers": scorers_map,
        "injuries": injuries,
        "presse": presse,
        "coaches": coaches,
        "team_goals": team_goals,
        "rest_for": rest_for,
        "nom": lambda t: names.get(t, t.split(":", 1)[-1]),
    }


def main(offline: bool = False) -> None:
    global JOURNAL, CUP_RESULTS
    now = datetime.now(timezone.utc)
    today = now.astimezone(S.PARIS).strftime("%Y-%m-%d")
    if not os.environ.get("GITHUB_ACTIONS"):
        # essai sur un PC : seul GitHub écrit le vrai journal, on travaille sur une copie
        scratch = Path(tempfile.gettempdir()) / "extinction-des-feux-essai"
        scratch.mkdir(exist_ok=True)
        for name, src in (("JOURNAL", JOURNAL), ("CUP_RESULTS", CUP_RESULTS)):
            if f"FOOT_{name}" in os.environ:   # chemin choisi explicitement : on le respecte
                continue
            dst = scratch / src.name
            if src.exists():
                shutil.copyfile(src, dst)
            elif dst.exists():
                dst.unlink()
            globals()[name] = dst
        if offline:   # hors ligne : aucune clé utilisée
            os.environ.pop("FOOTBALL_DATA_ORG_TOKEN", None)
            os.environ.pop("ODDS_API_KEY", None)
            os.environ.pop("API_FOOTBALL_KEY", None)
        print(f"   essai hors de GitHub : journal de travail dans {scratch}")
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
    ctx = build_match_context(allm, cal, names, now, offline)
    upcoming_rows = []
    for comp, f in cal.items():
        if not len(f):
            continue
        # tous les matchs non joués sont prédits (la fin de saison simulée en a besoin, même reportés ou en cours) ;
        # seuls les matchs des 3 prochains jours reçoivent les ajustements contextuels (blessures, entraîneurs, buteurs)
        f["pred"] = [None if bool(r["played"]) else predict(fit, r, bt, ctx if r["jour"] in ctx["horizon_dates"] else None)
                     for _, r in f.iterrows()]
        f["etat"] = [etat(r, now) for _, r in f.iterrows()]
        for r in f[f["etat"] == "a_venir"].itertuples():
            upcoming_rows.append({"competition": comp, "journee": r.journee, "jour": r.jour, "kickoff": r.kickoff,
                                  "home": r.home, "away": r.away, "p": r.pred["p"], "avec_cotes": r.pred["avec_cotes"]})
    added = JR.record(upcoming_rows, JOURNAL, now)
    print(f"   journal : {added} pronostic(s) publié(s)")

    # chaque pronostic publié est relié au match joué (même s'il a été reporté) ; un seul pronostic par match
    played = {}
    for comp, f in cal.items():
        if len(f):
            for r in f[f["played"].astype(bool)].itertuples():
                played[JR.match_id(comp, r.home, r.away, r.jour)] = (r.jour, (int(r.hg), int(r.ag)))
    links = JR.link(JOURNAL, played)
    evals = JR.evaluate(JOURNAL, played, links)
    published = {e["joue_id"]: e for e in evals}
    jr = JR.read(JOURNAL)
    pending = {r.match_id: (r.publie_utc, [r.p_dom, r.p_nul, r.p_ext]) for r in jr.sort_values("publie_utc").itertuples()
               if r.match_id not in links}

    print("5/5 Classements, simulations et fichiers du site")
    files, summary, search, recent = {}, [], [], []
    for comp, info in COMPS.items():
        f = cal.get(comp, pd.DataFrame())
        clubs = sorted(set(f["home"]) | set(f["away"])) if len(f) else []
        matchs = []
        for _, r in f.sort_values(["ordre", "jour"], na_position="last").iterrows() if len(f) else []:
            mid = JR.match_id(comp, r["home"], r["away"], r["jour"])
            item = {"id": mid, "journee": r["journee"], "ordre": int(r["ordre"]), "jour": r["jour"],
                    "kickoff": r["kickoff"] if isinstance(r["kickoff"], str) else None, "home": r["home"], "away": r["away"]}
            if r["etat"] == "joue":
                hg, ag = int(r["hg"]), int(r["ag"])
                item.update(etat="joue", score=[hg, ag])
                y = JR.outcome(hg, ag)
                pub = published.get(mid)
                if pub:
                    item.update(p=pub["p"], source="publie", publie=pub["publie_utc"])
                else:
                    cands = [q for d, q in rec.get((comp, r["home"], r["away"]), []) if abs((d - pd.Timestamp(r["jour"])).days) <= 3]
                    if cands:
                        item.update(p=cands[0], source="reconstitue")
                if "p" in item:
                    item["surprise"] = bool(item["p"][y] < JR.SURPRISE)
                    if (now.date() - pd.Timestamp(r["jour"]).date()).days <= RECENT_DAYS and item["surprise"]:
                        recent.append({**item, "competition": comp})
            elif r["etat"] == "a_venir":
                pr = r["pred"]
                item.update(etat="a_venir", p=pr["p"], avec_cotes=pr["avec_cotes"], xg=pr["xg"], scores=pr["scores"],
                            plus25=pr["plus25"], btts=pr["btts"], confiance=pr["confiance"])
                if pr.get("facteurs"):
                    item["facteurs"] = pr["facteurs"]
                if pr.get("buteurs"):
                    item["buteurs"] = pr["buteurs"]
                if mid in pending:   # déjà publié : on montre le pronostic figé, celui qui sera jugé
                    when, q = pending[mid]
                    item.update(p=S.round_probs(q), source="publie", publie=when)
            else:
                item["etat"] = r["etat"]
                pr = r["pred"]
                if isinstance(pr, dict):
                    item.update(plus25=pr["plus25"], btts=pr["btts"], confiance=pr["confiance"])
                    if pr.get("facteurs"):
                        item["facteurs"] = pr["facteurs"]
                    if pr.get("buteurs"):
                        item["buteurs"] = pr["buteurs"]
                if mid in pending:
                    when, q = pending[mid]
                    item.update(p=S.round_probs(q), source="publie", publie=when)
            matchs.append(item)
        ahead = [m for m in matchs if m["etat"] == "a_venir" and (m["jour"] or "9999") >= today]
        # Si des matchs de la compétition ont lieu aujourd'hui (en cours, en attente ou fraîchement joués),
        # on garde leur journée/étape ouverte par défaut plutôt que de sauter déjà à la journée suivante.
        du_jour = [m for m in matchs if m.get("jour") == today and m["etat"] in ("en_cours", "en_attente", "joue")]
        if du_jour:
            prochaine = du_jour[-1]["journee"]
        else:
            prochaine = choose_matchday(ahead, now) or (matchs[-1]["journee"] if matchs else None)
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
            rest = league_part[league_part["pred"].notna()]   # tous les matchs non joués, même reportés ou en cours
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
        nxt = [m for m in matchs if m["journee"] == prochaine]   # toute la journée, y compris ses matchs déjà commencés
        summary.append({"code": comp, "slug": info["slug"], "nom": info["nom"], "type": info["type"], "prochaine": prochaine,
                        "du": min((m["jour"] for m in nxt), default=None), "au": max((m["jour"] for m in nxt), default=None),
                        "a_venir": len(ahead), "leader": classement[0]["club"] if classement and classement[0]["j"] else None,
                        "leader_nom": clubs_info.get(classement[0]["club"], {}).get("nom") if classement and classement[0]["j"] else None,
                        "favori": (lambda b: {"club": b["club"], "nom": clubs_info[b["club"]]["nom"], "p": b[zones[0][0]]})(
                            max(projection, key=lambda x: x[zones[0][0]])) if projection and zones else None,
                        "zone_favori": zones[0][1] if zones else None,
                        "journal": {"matchs": len(jc), "favoris_justes": sum(e["favori_juste"] for e in jc)}})
        for m in ahead:
            row_s = {"c": comp, "id": m["id"], "jour": m["jour"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
                     "p": m["p"], **{k: m[k] for k in ("confiance", "btts", "plus25", "facteurs", "buteurs") if m.get(k) is not None}}
            search.append(row_s)

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
    habits, market = journal_references(allm, evals)
    journal_bilan = JR.summary(evals, habits, market, len(pending), {c: v["nom"] for c, v in COMPS.items()})
    shown = {t for m in featured + recent[:8] for t in (m["home"], m["away"])}
    files["index"] = {"maj_utc": iso(now), "competitions": summary, "a_la_une": featured,
                      "surprises": recent[:8], "part_marche": round(bt["b"] / (bt["a"] + bt["b"]), 1),
                      "fiabilite": bt["table"], "journal": journal_bilan,
                      "etude_multifacteur": bt.get("etude_multifacteur"), "saisons_test": TEST,
                      "slugs": {c: v["slug"] for c, v in COMPS.items()}, "noms": {c: v["nom"] for c, v in COMPS.items()},
                      "clubs": {t: all_clubs[t] for t in shown if t in all_clubs}}
    files["recherche"] = {"maj_utc": iso(now), "clubs": all_clubs,
                          "matchs": [{k: m[k] for k in ("c", "id", "jour", "kickoff", "home", "away", "p", "confiance") if k in m} for m in search],
                          "competitions": {c: {"nom": v["nom"], "slug": v["slug"]} for c, v in COMPS.items()}}
    # direct : buts attendus calés sur les chances publiées (rien de plus que ces chances arrondies)
    live_params = LV.load_params()
    # les matchs joués la veille ou aujourd'hui en font partie : la fiche d'un match qui vient de se terminer (courbe des chances
    # depuis le coup d'envoi) repart elle aussi de ces buts attendus
    veille = (now.astimezone(S.PARIS) - timedelta(days=1)).strftime("%Y-%m-%d")
    need = matchs_a_caler(files, veille)
    if need:
        lam = LV.calibrate(np.array([m["p"] for m in need], float), live_params)
        for m, (lh, la) in zip(need, lam):
            m["lam"] = [round(float(lh), 3), round(float(la), 3)]
    files["index"]["du_jour"] = matchs_du_jour(files, today)
    for t in {t for m in files["index"]["du_jour"] for t in (m["home"], m["away"])}:
        if t in all_clubs:
            files["index"]["clubs"][t] = all_clubs[t]
    files["direct"] = {"maj_utc": iso(now), "minutes_mi_temps": list(LV.HALF_MINUTES), "pas_par_mi_temps": LV.STEPS_PER_HALF,
                       **{k: live_params.get(k) for k in ("part_1re_mi_temps", "rythme_selon_ecart", "periode_choix",
                                                          "periode_test", "matchs_test", "jugement_mi_temps", "fiabilite_mi_temps")}}
    write_all(files)
    print(f"   {len(search)} matchs à venir, {len(all_clubs)} clubs, {len(recent)} surprise(s) récente(s). Terminé.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
