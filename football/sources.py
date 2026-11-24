"""Calendriers, résultats récents et cotes des matchs à venir.

- championnats et Ligue des champions : football-data.org (clé gratuite FOOTBALL_DATA_ORG_TOKEN) : calendrier
  complet avec les heures, résultats dans l'heure ; sans clé, calendrier openfootball (domaine public) ;
- cotes des championnats : football-data.co.uk (fixtures.csv) ;
- Ligue Europa (calendrier et résultats) et cotes des coupes : The Odds API (clé gratuite ODDS_API_KEY,
  quota mensuel limité).
Sans clé, la source est simplement absente : rien ne plante.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from football import names as N
except ImportError:  # lancé comme script
    import names as N  # type: ignore

FDORG = "https://api.football-data.org/v4/competitions/{code}/{what}?season={season}"
ODDS = "https://api.the-odds-api.com/v4/sports/{sport}/{what}"
ODDS_SPORTS = {"LDC": "soccer_uefa_champs_league", "LEC": "soccer_uefa_europa_league"}
ODDS_MIN_HOURS = 3          # pas plus d'un appel payant toutes les 3 h par compétition
ODDS_HORIZON_HOURS = 72     # et seulement quand un match a lieu dans les 3 jours
ODDS_RESERVE = 50           # crédits gardés de côté : en dessous, plus aucun appel payant jusqu'au mois suivant
SCORES_MIN_HOURS = 12       # résultats de Ligue Europa (2 crédits) : au plus deux fois par jour, et seulement après des matchs
FDORG_PAUSE_S = 6.5         # football-data.org gratuit : 10 appels par minute au plus
FDORG_CODES = {"E0": "PL", "D1": "BL1", "SP1": "PD", "I1": "SA", "F1": "FL1", "LDC": "CL"}
# codes pays de football-data.org (ISO) -> codes openfootball utilisés partout ailleurs
ISO = {"DEU": "GER", "NLD": "NED", "PRT": "POR", "CHE": "SUI", "DNK": "DEN", "HRV": "CRO", "GRC": "GRE", "SVN": "SVN",
       "SCT": "SCO", "MCO": "FRA", "CZE": "CZE", "SRB": "SRB", "AUT": "AUT", "BEL": "BEL", "TUR": "TUR", "POL": "POL",
       "NOR": "NOR", "SWE": "SWE", "UKR": "UKR", "ROU": "ROU", "HUN": "HUN", "CYP": "CYP", "ISR": "ISR", "AZE": "AZE",
       "KAZ": "KAZ", "BGR": "BUL", "SVK": "SVK", "ENG": "ENG", "ESP": "ESP", "FRA": "FRA", "ITA": "ITA", "IRL": "IRL",
       "FIN": "FIN", "RUS": "RUS", "MDA": "MDA", "LVA": "LVA", "ARM": "ARM", "GEO": "GEO", "ISL": "ISL", "BIH": "BIH"}


def _get_json(url: str, headers: dict | None = None, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "extinction-des-feux/1.0", **(headers or {})})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8")), dict(r.headers)
        except urllib.error.HTTPError as e:
            # jamais l'adresse dans le message : celle de The Odds API contient la clé
            if e.code in (401, 403, 404, 422) or i == tries - 1:
                raise RuntimeError(f"réponse HTTP {e.code}") from None
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"connexion impossible ({type(e).__name__})") from None
        time.sleep(6 * (i + 1))   # football-data.org : 10 appels par minute au plus
    raise RuntimeError("connexion impossible")


class TeamIndex:
    """Noms football-data connus par pays, pour relier n'importe quelle source.

    Les pays sans championnat dans nos données (Croatie, Tchéquie...) n'ont que des noms de coupe :
    ils sont ajoutés au fur et à mesure, pour qu'un club garde la même identité d'une saison à l'autre."""

    def __init__(self, ids: list[str]):
        self.by_cc: dict[str, list[str]] = {}
        for t in ids:
            cc, nm = t.split(":", 1)
            self.by_cc.setdefault(cc, []).append(nm)
        self.covered = set(self.by_cc)
        self.approx: set[tuple[str, str]] = set()   # rapprochements non évidents, affichés dans le journal du calcul

    def resolve(self, name: str, cc: str | None = None) -> str:
        if cc:
            cands = self.by_cc.setdefault(cc, [])
            r = N.match(cc, name, sorted(cands))
            if r is None:
                cands.append(name)   # premier nom vu pour ce club
                return f"{cc}:{name}"
            if N.norm(r) != N.norm(name) and (cc, name) not in N.MANUAL:
                self.approx.add((f"{cc}:{name}", f"{cc}:{r}"))
            return f"{cc}:{r}"
        # sans pays (The Odds API) : table manuelle, ou nom identique une fois normalisé dans un seul pays
        if name in N.NO_COUNTRY:
            return N.NO_COUNTRY[name]
        n = N.norm(name)
        hits = {f"{c}:{x}" for c, names in self.by_cc.items() for x in names if N.norm(x) == n}
        return hits.pop() if len(hits) == 1 else f"?:{name}"


def read_json(f: Path, default):
    """Fichier gardé d'un lancement à l'autre ; illisible (écriture interrompue) : comme absent."""
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"   {f.name} illisible, ignoré ({type(e).__name__})")
        return default


def write_json(f: Path, obj) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    t = f.with_suffix(".tmp")
    t.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(t, f)


def football_data_org(code: str, season: int, token: str | None, raw: Path, now: datetime | None = None) -> dict | None:
    """Matchs et clubs d'une compétition (avec la clé gratuite). Les clubs ne changent pas : relus une fois par jour.
    Le résultat est gardé pour les lancements sans réseau."""
    f = raw / f"fdorg_{code}_{season}.json"
    if token:
        old = read_json(f, {})
        h = {"X-Auth-Token": token}
        matches, _ = _get_json(FDORG.format(code=code, what="matches", season=season), h)
        time.sleep(FDORG_PAUSE_S)
        teams, fetched = old.get("teams"), old.get("teams_fetched", 0)
        t = (now or datetime.now(timezone.utc)).timestamp()
        if not teams or t - fetched > 86400:
            tj, _ = _get_json(FDORG.format(code=code, what="teams", season=season), h)
            time.sleep(FDORG_PAUSE_S)
            teams, fetched = tj.get("teams", []), t
        write_json(f, {"matches": matches.get("matches", []), "teams": teams, "teams_fetched": fetched})
    return read_json(f, None)


STAGES = {"LEAGUE_STAGE": None, "REGULAR_SEASON": None, "PLAYOFFS": "Barrages", "LAST_16": "Huitièmes de finale",
          "QUARTER_FINALS": "Quarts de finale", "SEMI_FINALS": "Demi-finales", "FINAL": "Finale"}


STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}
FRAME_COLUMNS = ["competition", "kickoff", "stage", "status", "heure_connue", "journee", "ordre", "home", "away", "home_name",
                 "away_name", "home_tla", "away_tla", "hg", "ag", "neutral", "played"]


def fdorg_frame(js: dict, comp: str, idx: TeamIndex) -> pd.DataFrame:
    """Une ligne par match ; score après 90 minutes pour les matchs joués."""
    area = {t["id"]: ISO.get((t.get("area") or {}).get("code", ""), (t.get("area") or {}).get("code")) for t in js["teams"]}
    rows = []
    for x in js["matches"]:
        h, a = x.get("homeTeam") or {}, x.get("awayTeam") or {}
        if not h.get("name") or not a.get("name"):
            continue   # tirage pas encore fait
        sc = x.get("score") or {}
        rt, ft = sc.get("regularTime") or {}, sc.get("fullTime") or {}
        reg = rt if rt.get("home") is not None and rt.get("away") is not None else ft
        # match attribué sur tapis vert : il compte comme joué, avec le score décidé
        done = x.get("status") in ("FINISHED", "AWARDED") and reg.get("home") is not None and reg.get("away") is not None
        stage = x.get("stage")
        if stage in STAGES:
            label = STAGES[stage]
        elif "QUALIF" in str(stage):
            label = "Qualifications"
        else:
            label = str(stage or "").replace("_", " ").capitalize() or None
        journee = f"Journée {x['matchday']}" if label is None and x.get("matchday") else (label or "")
        rows.append({"competition": comp, "kickoff": x.get("utcDate"), "stage": stage, "status": x.get("status"),
                     # heure pas encore fixée par la ligue : football-data.org met une heure de remplissage
                     "heure_connue": x.get("status") != "SCHEDULED",
                     # phase à élimination : après les journées de la phase de ligue, dans l'ordre des tours
                     "journee": journee, "ordre": (x.get("matchday") or 0) if label is None
                     else (-1 if label == "Qualifications" else 100 + STAGE_ORDER.get(stage, len(STAGE_ORDER))),
                     "home": idx.resolve(h["name"], area.get(h.get("id"))), "away": idx.resolve(a["name"], area.get(a.get("id"))),
                     "home_name": h["name"], "away_name": a["name"], "home_tla": h.get("tla"), "away_tla": a.get("tla"),
                     "hg": reg.get("home") if done else None, "ag": reg.get("away") if done else None,
                     "neutral": stage == "FINAL", "played": done})
    return pd.DataFrame(rows, columns=FRAME_COLUMNS)


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def odds_api(comp: str, key: str | None, state: Path, now: datetime) -> tuple[list, dict]:
    """Matchs à venir (appel gratuit) et cotes 1/N/2 (1 crédit), demandées au plus toutes les 3 h,
    seulement si un match de cette compétition a lieu dans les 3 jours, et jamais sous la réserve de crédits.
    `state` est un dossier gardé à chaque lancement (pas seulement une fois par jour)."""
    sport = ODDS_SPORTS[comp]
    f_ev, f_od, f_q = state / f"events_{comp}.json", state / f"odds_{comp}.json", state / "quota.json"
    if key:
        ev, _ = _get_json(ODDS.format(sport=sport, what="events") + f"?apiKey={key}")
        write_json(f_ev, ev)
        seen = read_json(state / f"seen_{comp}.json", {})
        seen.update({e["id"]: e for e in ev})   # matchs vus un jour : on saura lesquels ont été joués
        write_json(state / f"seen_{comp}.json", seen)
        t = now.timestamp()
        soon = any(0 < _ts(e["commence_time"]) - t < ODDS_HORIZON_HOURS * 3600 for e in ev)
        last = read_json(f_od, {}).get("fetched", 0)
        q = read_json(f_q, {})
        month = now.strftime("%Y-%m")
        is_low = q.get("month") == month and q.get("remaining", ODDS_RESERVE + 1) <= ODDS_RESERVE
        if soon and t - last >= ODDS_MIN_HOURS * 3600 and not is_low:
            od, hdr = _get_json(ODDS.format(sport=sport, what="odds") + f"?apiKey={key}&regions=eu&markets=h2h&oddsFormat=decimal")
            write_json(f_od, {"fetched": t, "data": od})
            left = hdr.get("x-requests-remaining") or hdr.get("X-Requests-Remaining")
            if left is not None:
                write_json(f_q, {"month": month, "remaining": float(left)})
            print(f"   The Odds API {comp} : cotes mises à jour, crédits restants {left or '?'}")
        elif is_low:
            print(f"   The Odds API {comp} : réserve de crédits atteinte, cotes en pause jusqu'au mois prochain")
    return read_json(f_ev, []), read_json(f_od, {})


def odds_scores(comp: str, key: str | None, state: Path, now: datetime, results_csv: Path) -> int:
    """Résultats des matchs vus ces 3 derniers jours (2 crédits l'appel), ajoutés au fichier des résultats.
    Appelé au plus toutes les 12 h, seulement s'il manque le résultat d'un match commencé il y a plus de 2 h.
    En phase à élimination, le score peut inclure la prolongation : The Odds API ne la distingue pas."""
    if not key:
        return 0
    seen = read_json(state / f"seen_{comp}.json", {})
    known = pd.read_csv(results_csv) if results_csv.exists() and results_csv.stat().st_size else pd.DataFrame(columns=["id"])
    t = now.timestamp()
    waiting = [e for e in seen.values() if 2 * 3600 < t - _ts(e["commence_time"]) < 3 * 86400 and e["id"] not in set(known["id"])]
    f_q = state / f"scores_{comp}.json"
    if not waiting or t - read_json(f_q, {}).get("fetched", 0) < SCORES_MIN_HOURS * 3600:
        return 0
    q = read_json(state / "quota.json", {})
    if q.get("month") == now.strftime("%Y-%m") and q.get("remaining", ODDS_RESERVE + 1) <= ODDS_RESERVE:
        return 0
    data, hdr = _get_json(ODDS.format(sport=ODDS_SPORTS[comp], what="scores") + f"?apiKey={key}&daysFrom=3")
    write_json(f_q, {"fetched": t})
    left = hdr.get("x-requests-remaining") or hdr.get("X-Requests-Remaining")
    if left is not None:
        write_json(state / "quota.json", {"month": now.strftime("%Y-%m"), "remaining": float(left)})
    rows = []
    for e in data:
        sc = {x["name"]: x["score"] for x in (e.get("scores") or [])}
        if not e.get("completed") or e["home_team"] not in sc or e["away_team"] not in sc:
            continue
        try:
            hg, ag = int(sc[e["home_team"]]), int(sc[e["away_team"]])
        except (TypeError, ValueError):
            continue
        if e["id"] not in set(known["id"]):
            rows.append({"id": e["id"], "competition": comp, "kickoff": e["commence_time"], "home_name": e["home_team"],
                         "away_name": e["away_team"], "hg": hg, "ag": ag})
    if rows:
        results_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(results_csv, mode="a", header=not results_csv.exists() or not results_csv.stat().st_size,
                                  index=False)
    print(f"   The Odds API {comp} : {len(rows)} résultat(s) ajouté(s), crédits restants {left or '?'}")
    return len(rows)


def odds_frame(events: list, odds: dict, comp: str, idx: TeamIndex, now: datetime) -> pd.DataFrame:
    """Matchs pas encore commencés, avec la moyenne des cotes 1/N/2 des bookmakers (jamais affichées).
    Une cote relevée après le coup d'envoi (cote en direct) est ignorée."""
    fetched = odds.get("fetched", 0)
    avg = {}
    for e in odds.get("data", []):
        if fetched >= _ts(e["commence_time"]):
            continue
        prices = []
        for b in e.get("bookmakers", []):
            for mk in b.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                o = {x["name"]: x["price"] for x in mk.get("outcomes", [])}
                if e["home_team"] in o and e["away_team"] in o and "Draw" in o:
                    prices.append([o[e["home_team"]], o["Draw"], o[e["away_team"]]])
        if prices:
            avg[e["id"]] = np.mean(prices, axis=0)
    rows = []
    for e in events:
        if _ts(e["commence_time"]) <= now.timestamp():
            continue
        o = avg.get(e["id"], [np.nan] * 3)
        rows.append({"competition": comp, "kickoff": e["commence_time"], "home": idx.resolve(e["home_team"]),
                     "away": idx.resolve(e["away_team"]), "home_name": e["home_team"], "away_name": e["away_team"],
                     "oh": o[0], "od": o[1], "oa": o[2], "played": False, "neutral": False})
    return pd.DataFrame(rows)


def attach_odds(fx: pd.DataFrame, od: pd.DataFrame, hours: float = 3) -> tuple[pd.DataFrame, int]:
    """Rattache les cotes de The Odds API au calendrier de football-data.org : même coup d'envoi (à 3 h près)
    et au moins un des deux clubs reconnu. Renvoie aussi le nombre de matchs à cotes restés sans place."""
    fx = fx.copy()
    for c in ("oh", "od", "oa"):
        fx[c] = np.nan
    used, lost = set(), 0
    for j, e in od.dropna(subset=["oh"]).iterrows():
        t = _ts(e["kickoff"])
        cand = [i for i, r in fx.iterrows() if isinstance(r["kickoff"], str) and abs(_ts(r["kickoff"]) - t) <= hours * 3600
                and (r["home"] == e["home"] or r["away"] == e["away"]) and i not in used]
        if len(cand) != 1:
            lost += 1
            continue
        used.add(cand[0])
        fx.loc[cand[0], ["oh", "od", "oa"]] = [e["oh"], e["od"], e["oa"]]
    return fx, lost


def openfootball_league(path: Path, code: str, cc: str, tz: str, idx: TeamIndex) -> pd.DataFrame:
    """Calendrier complet d'un championnat ; heures locales du pays converties en UTC."""
    from zoneinfo import ZoneInfo
    js = json.loads(path.read_text(encoding="utf-8"))
    zone = ZoneInfo(tz)
    rows = []
    for x in js["matches"]:
        ko = None
        if x.get("time"):
            hh, mm = x["time"].split(":")[:2]
            d = datetime.fromisoformat(x["date"]).replace(hour=int(hh), minute=int(mm), tzinfo=zone)
            ko = d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sc = x.get("score")
        ft = sc.get("ft") if isinstance(sc, dict) else sc if isinstance(sc, list) and len(sc) == 2 else None
        rows.append({"competition": code, "round": x.get("round"), "jour": x["date"], "kickoff": ko,
                     "home": idx.resolve(x["team1"], cc), "away": idx.resolve(x["team2"], cc),
                     "home_name": x["team1"], "away_name": x["team2"],
                     "hg": ft[0] if ft else None, "ag": ft[1] if ft else None, "played": bool(ft), "neutral": False})
    return pd.DataFrame(rows)
