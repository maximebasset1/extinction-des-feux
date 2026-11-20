"""Calendriers et cotes des matchs à venir, pour la recherche.

- championnats : calendrier complet openfootball (domaine public), cotes football-data.co.uk (fixtures.csv) ;
- Ligue des champions : football-data.org (clé gratuite FOOTBALL_DATA_ORG_TOKEN) ;
- Ligue Europa et cotes des coupes : The Odds API (clé gratuite ODDS_API_KEY, quota mensuel limité).
Sans clé, la compétition est simplement absente : rien ne plante.
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
    """Noms football-data connus par pays, pour relier n'importe quelle source."""

    def __init__(self, ids: list[str]):
        self.by_cc: dict[str, list[str]] = {}
        for t in ids:
            cc, nm = t.split(":", 1)
            self.by_cc.setdefault(cc, []).append(nm)

    def resolve(self, name: str, cc: str | None = None) -> str:
        """Identifiant « pays:nom ». Sans pays (The Odds API), on cherche un rapprochement unique dans tous les pays."""
        if cc:
            r = N.match(cc, name, sorted(self.by_cc.get(cc, [])))
            return f"{cc}:{r or name}"
        hits = {f"{c}:{r}" for c, names in self.by_cc.items() if (r := N.match(c, name, sorted(names)))}
        manual = {f"{c}:{v}" for (c, k), v in N.MANUAL.items() if k == name}
        hits = manual or hits
        return hits.pop() if len(hits) == 1 else f"?:{name}"


def football_data_org(code: str, season: int, token: str | None, raw: Path) -> dict | None:
    """Matchs et clubs d'une compétition (avec la clé gratuite). Le résultat est gardé pour les lancements sans réseau."""
    f = raw / f"fdorg_{code}_{season}.json"
    if token:
        h = {"X-Auth-Token": token}
        matches, _ = _get_json(FDORG.format(code=code, what="matches", season=season), h)
        teams, _ = _get_json(FDORG.format(code=code, what="teams", season=season), h)
        f.write_text(json.dumps({"matches": matches.get("matches", []), "teams": teams.get("teams", [])}), encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def fdorg_frame(js: dict, comp: str, idx: TeamIndex) -> pd.DataFrame:
    """Une ligne par match ; score après 90 minutes pour les matchs joués."""
    area = {t["id"]: ISO.get((t.get("area") or {}).get("code", ""), (t.get("area") or {}).get("code")) for t in js["teams"]}
    rows = []
    for x in js["matches"]:
        h, a = x.get("homeTeam") or {}, x.get("awayTeam") or {}
        if not h.get("name") or not a.get("name"):
            continue   # tirage pas encore fait
        sc = x.get("score") or {}
        reg = sc.get("regularTime") or sc.get("fullTime") or {}
        done = x.get("status") == "FINISHED" and reg.get("home") is not None
        rows.append({"competition": comp, "kickoff": x.get("utcDate"), "stage": x.get("stage"),
                     "home": idx.resolve(h["name"], area.get(h.get("id"))), "away": idx.resolve(a["name"], area.get(a.get("id"))),
                     "home_name": h.get("shortName") or h["name"], "away_name": a.get("shortName") or a["name"],
                     "home_tla": h.get("tla"), "away_tla": a.get("tla"),
                     "hg": reg.get("home") if done else None, "ag": reg.get("away") if done else None,
                     "neutral": x.get("stage") == "FINAL", "played": done})
    return pd.DataFrame(rows)


def odds_api(comp: str, key: str | None, raw: Path, now: datetime, upcoming_ko: list[datetime]) -> list:
    """Événements à venir (gratuit) et cotes 1/N/2 (1 crédit par appel, appelées avec parcimonie)."""
    sport = ODDS_SPORTS[comp]
    f_ev, f_od = raw / f"odds_events_{comp}.json", raw / f"odds_{comp}.json"
    if key:
        ev, _ = _get_json(ODDS.format(sport=sport, what="events") + f"?apiKey={key}")
        f_ev.write_text(json.dumps(ev), encoding="utf-8")
        soon = any(timedelta(0) < k - now < timedelta(hours=ODDS_HORIZON_HOURS) for k in upcoming_ko)
        # l'heure de récupération est écrite dans le fichier : le cache de GitHub ne garde pas toujours les dates
        last = json.loads(f_od.read_text(encoding="utf-8")).get("fetched", 0) if f_od.exists() else 0
        if soon and now.timestamp() - last >= ODDS_MIN_HOURS * 3600:
            od, hdr = _get_json(ODDS.format(sport=sport, what="odds") + f"?apiKey={key}&regions=eu&markets=h2h&oddsFormat=decimal")
            f_od.write_text(json.dumps({"fetched": now.timestamp(), "data": od}), encoding="utf-8")
            print(f"   The Odds API {comp} : crédits restants {hdr.get('x-requests-remaining', '?')}")
    events = json.loads(f_ev.read_text(encoding="utf-8")) if f_ev.exists() else []
    odds = json.loads(f_od.read_text(encoding="utf-8")).get("data", []) if f_od.exists() else []
    return events, odds


def odds_frame(events: list, odds: list, comp: str, idx: TeamIndex) -> pd.DataFrame:
    """Matchs de The Odds API avec la moyenne des cotes 1/N/2 des bookmakers (jamais affichées)."""
    avg = {}
    for e in odds:
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
        o = avg.get(e["id"], [np.nan] * 3)
        rows.append({"competition": comp, "kickoff": e["commence_time"], "home": idx.resolve(e["home_team"]),
                     "away": idx.resolve(e["away_team"]), "home_name": e["home_team"], "away_name": e["away_team"],
                     "oh": o[0], "od": o[1], "oa": o[2], "played": False, "neutral": False})
    return pd.DataFrame(rows)


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
