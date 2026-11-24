"""Facteurs contextuels des prochains matchs (100 % gratuit, budget API maîtrisé).

- Buteurs en forme : `/competitions/{code}/scorers` sur football-data.org (gratuit, cache 12 h). Seuls les
  titulaires réguliers sont proposés : d'après les compositions des derniers matchs quand football-data.org
  les fournit, sinon d'après le nombre de matchs joués (entrées en jeu comprises : un remplaçant qui joue
  à chaque match n'est alors pas repéré). L'offre gratuite ne donne en principe pas les compositions.
- Absents signalés par la presse : flux RSS sportifs publics des 72 dernières heures (sans clé, cache 6 h).
  Un joueur n'est retenu que s'il figure dans l'effectif d'un club cité et qu'un mot d'absence le désigne.
  Aucun texte de presse n'est publié : le site n'affiche que des noms tirés de l'effectif.
- Blessures / suspensions et changements d'entraîneur : API-Football (`/injuries`, `/coachs`),
  strictement bornés à 15 requêtes/jour au total dans `mise-a-jour.yml` et stoppés si le quota
  global du compte descend sous 25 requêtes restantes (réserve prioritaire pour le direct live).
- Tout appel réseau est isolé : en cas d'indisponibilité ou d'absence de clé, repli silencieux
  sur le cache existant ou sur des données vides.
"""
from __future__ import annotations

import html
import math
import re
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np

try:
    from football import names as N
    from football import sources as SRC
except ImportError:  # lancé comme script
    import names as N  # type: ignore
    import sources as SRC  # type: ignore

APIFOOT_BASE = "https://v3.football.api-sports.io"
APIFOOT_LEAGUES = {39: "E0", 78: "D1", 140: "SP1", 135: "I1", 61: "F1", 2: "LDC", 3: "LEC"}
LEAGUE_CC = {"E0": "ENG", "D1": "GER", "SP1": "ESP", "I1": "ITA", "F1": "FRA"}

APIFOOT_MAX_JOUR = 15          # plafond journalier dans mise-a-jour.yml (cumul avec direct.yml < 100/j)
APIFOOT_RESERVE_DIRECT = 25    # sous ce seuil global API-Football, on laisse tout le quota au direct live
SCORERS_CACHE_H = 12
INJURIES_CACHE_H = 12
COACH_CACHE_DAYS = 14
COACH_RECENT_DAYS = 30
HORIZON_DAYS = 3

# Bornes strictes sur les ajustements contextuels de lambda (avant mélange avec les cotes)
MAX_LAM_MALUS = -0.12
MAX_LAM_BONUS = 0.06
COACH_VARIANCE_TEMP = 0.92     # lissage léger des probabilités si un club change d'entraîneur (< 30 j)
MAX_SCORER_SHARE = 0.55        # plafond de la part de buts d'un joueur (évite les petits échantillons)

# Titulaires réguliers
STARTER_MIN_RATIO = 0.6        # part minimale des matchs de l'équipe (titularisations, ou à défaut matchs joués)
STARTER_MIN_MATCHS = 3         # en dessous, trop peu de matchs pour juger
LINEUPS_LAST = 5               # compositions regardées
LINEUPS_JOURS = 45             # fenêtre de recherche des derniers matchs
LINEUPS_CACHE_H = 24
LINEUPS_MAX_PAR_RUN = 10       # appels football-data.org (6,5 s chacun) par lancement
LINEUPS_PAUSE_JOURS = 7        # sans compositions dans la réponse (offre gratuite) : nouvel essai une semaine plus tard
FDORG_TEAM = "https://api.football-data.org/v4/teams/{id}"
SQUADS_CACHE_DAYS = 7
SQUADS_MAX_PAR_RUN = 12

# Presse (RSS publics, sans clé)
RSS_FEEDS = {
    "rmc": "https://rmcsport.bfmtv.com/rss/football/",
    "lequipe": "https://dwh.lequipe.fr/api/edito/rss?path=/Football/",
    "bbc": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "skysports": "https://www.skysports.com/rss/12040",
    "kicker": "https://newsfeed.kicker.de/news/bundesliga",
    "marca": "https://e00-marca.uecdn.es/rss/portada.xml",
    "as": "https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/portada/",
    "gazzetta": "https://www.gazzetta.it/dynamic-feed/rss/section/Calcio.xml",
}
RSS_CACHE_H = 6
RSS_TIMEOUT_S = 5
RSS_WINDOW_H = 72
RSS_MAX_OCTETS = 2_000_000
PRESS_MAX_ECART = 6            # mots au plus entre le mot d'absence et le nom du joueur
PRESS_MALUS_JOUEUR = 0.015     # malus offensif par absent signalé
PRESS_MALUS_BUTEUR_MAX = 0.05  # supplément au plus pour l'un des trois meilleurs buteurs du club
MAX_PRESS_MALUS = -0.08        # la presse seule ne retire jamais plus de 8 %


# lettres que la décomposition Unicode ne ramène pas à une lettre simple (Højlund, Groß...)
_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "đ": "d",
                           "Đ": "D", "ł": "l", "Ł": "L", "ı": "i"})


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").translate(_TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def same_player(a: str, b: str) -> bool:
    """Rapproche deux noms de joueur (« K. Mbappé » et « Kylian Mbappé »)."""
    ta, tb = _fold(a).split(), _fold(b).split()
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    # même nom de famille (>= 4 lettres) et initiale compatible
    if len(ta[-1]) >= 4 and ta[-1] == tb[-1]:
        return len(ta) == 1 or len(tb) == 1 or ta[0][0] == tb[0][0]
    return False


# ---------------------------------------------------------------- football-data.org : buteurs

def fetch_scorers(code: str, season: int, token: str | None, raw: Path, now: datetime) -> dict | None:
    """Meilleurs buteurs d'une compétition (football-data.org, gratuit, cache 12 h)."""
    f = raw / f"fdorg_scorers_{code}_{season}.json"
    old = SRC.read_json(f, {})
    t = now.timestamp()
    if token and (not old.get("scorers") or t - old.get("fetched", 0) >= SCORERS_CACHE_H * 3600):
        url = SRC.FDORG.format(code=code, what="scorers", season=season) + "&limit=40"
        data, _ = SRC._get_json(url, {"X-Auth-Token": token})
        time.sleep(SRC.FDORG_PAUSE_S)
        SRC.write_json(f, {"scorers": data.get("scorers", []), "fetched": t})
    return SRC.read_json(f, None)


def scorers_by_team(scorers_js: dict[str, dict | None], idx: SRC.TeamIndex) -> dict[str, list[dict]]:
    """Regroupe les meilleurs buteurs par club (`club_id` -> liste triée par buts décroissants)."""
    by_team: dict[str, dict[str, dict]] = {}
    for comp, js in scorers_js.items():
        if not js:
            continue
        cc_default = LEAGUE_CC.get(comp)
        for item in js.get("scorers") or []:
            player = (item.get("player") or {}).get("name")
            team = item.get("team") or {}
            tname = team.get("name")
            goals = item.get("goals") or 0
            if not player or not tname or goals <= 0:
                continue
            cc = cc_default or SRC.ISO.get((team.get("area") or {}).get("code", ""))
            tid = idx.resolve(tname, cc)
            if tid.startswith("?:"):
                continue
            key = _fold(player)
            cur = by_team.setdefault(tid, {}).get(key)
            entry = {"nom": player, "buts": int(goals), "matchs": int(item.get("playedMatches") or 0),
                     "penalties": int(item.get("penalties") or 0), "comp": comp}
            # On garde le plus gros total de buts (ex. championnat national plutôt que 3 matchs de coupe)
            if cur is None or entry["buts"] > cur["buts"]:
                by_team[tid][key] = entry
    return {tid: sorted(players.values(), key=lambda x: (-x["buts"], x["nom"])) for tid, players in by_team.items()}


def team_match_counts(cal: dict) -> dict[tuple[str, str], int]:
    """Matchs joués par chaque club dans chaque compétition (hors tours de qualification, absents des buteurs)."""
    counts: dict[tuple[str, str], int] = {}
    for comp, f in cal.items():
        if f is None or not len(f):
            continue
        for r in f.to_dict("records"):
            if not bool(r.get("played")) or "QUALIF" in str(r.get("stage") or ""):
                continue
            for t in (r["home"], r["away"]):
                counts[(t, comp)] = counts.get((t, comp), 0) + 1
    return counts


def mark_regular_starters(scorers_map: dict[str, list[dict]], team_matches: dict[tuple[str, str], int],
                          lineups: dict[str, list[list[str]]]) -> dict[str, list[dict]]:
    """Ajoute `titulaire` à chaque buteur. Les compositions priment ; sans elles, le nombre de matchs joués.
    Sans information suffisante, le joueur est gardé."""
    out = {}
    for tid, players in scorers_map.items():
        compos = lineups.get(tid) or []
        marques = []
        for p in players:
            if len(compos) >= STARTER_MIN_MATCHS:
                fois = sum(any(same_player(p["nom"], x) for x in compo) for compo in compos)
                regulier = fois / len(compos) >= STARTER_MIN_RATIO
            else:
                total = team_matches.get((tid, p.get("comp")), 0)
                joues = p.get("matchs") or 0
                regulier = total < STARTER_MIN_MATCHS or joues <= 0 or joues / total >= STARTER_MIN_RATIO
            marques.append({**p, "titulaire": bool(regulier)})
        out[tid] = marques
    return out


def fetch_lineups(team_ids: dict[str, int], token: str | None, state: Path, now: datetime) -> dict[str, list[list[str]]]:
    """Compositions des derniers matchs (`club_id -> liste de onze de départ`), si football-data.org les fournit.
    L'offre gratuite n'en renvoie en principe pas : le premier appel le constate et suspend la collecte."""
    f = state / "fdorg_lineups.json"
    cache = SRC.read_json(f, {})
    t = now.timestamp()
    clubs = cache.get("clubs") or {}
    pause = cache.get("indisponible_jusqu", 0)
    if token and t >= pause:
        appels = 0
        for tid, api_id in sorted(team_ids.items()):
            cur = clubs.get(tid)
            if cur and t - cur.get("fetched", 0) < LINEUPS_CACHE_H * 3600:
                continue
            if appels >= LINEUPS_MAX_PAR_RUN:
                break
            url = (FDORG_TEAM.format(id=api_id) + "/matches?status=FINISHED"
                   f"&dateFrom={(now - timedelta(days=LINEUPS_JOURS)):%Y-%m-%d}&dateTo={now:%Y-%m-%d}")
            appels += 1
            try:
                data, _ = SRC._get_json(url, {"X-Auth-Token": token, "X-Unfold-Lineups": "true"}, tries=1)
            except Exception as e:  # noqa: BLE001
                print(f"   Compositions football-data.org indisponibles : {type(e).__name__} {e}")
                if "403" in str(e):
                    pause = t + LINEUPS_PAUSE_JOURS * 86400
                break
            time.sleep(SRC.FDORG_PAUSE_S)
            matchs = sorted(data.get("matches") or [], key=lambda m: str(m.get("utcDate") or ""))
            compos = []
            for m in matchs:
                for side in (m.get("homeTeam") or {}, m.get("awayTeam") or {}):
                    if side.get("id") == api_id and side.get("lineup"):
                        compos.append([x["name"] for x in side["lineup"] if x.get("name")])
            if matchs and not compos:
                pause = t + LINEUPS_PAUSE_JOURS * 86400
                print("   Compositions absentes de l'offre football-data.org : titulaires jugés sur les matchs joués")
                break
            clubs[tid] = {"fetched": t, "compos": compos[-LINEUPS_LAST:]}
        SRC.write_json(f, {"clubs": clubs, "indisponible_jusqu": pause})
    return {tid: c["compos"] for tid, c in clubs.items()
            if c.get("compos") and t - c.get("fetched", 0) < LINEUPS_PAUSE_JOURS * 86400}


def probable_scorers(team_id: str, lam_team: float, scorers_map: dict[str, list[dict]],
                     team_goals: dict[str, int], absent_names: list[str] | None = None,
                     top: int = 2) -> list[dict]:
    """Calcule les 2 buteurs les plus probables d'une équipe par loi de Poisson : P(>=1) = 1 - exp(-lam * part)."""
    players = scorers_map.get(team_id) or []
    if not players or lam_team <= 0:
        return []
    absents = absent_names or []
    g_team = max(int(team_goals.get(team_id, 0)), sum(p["buts"] for p in players), 10)
    out = []
    for p in players:
        if p["buts"] < 2 or p.get("titulaire") is False:
            continue
        if any(same_player(p["nom"], ab) for ab in absents):
            continue
        share = min(MAX_SCORER_SHARE, p["buts"] / max(g_team, p["buts"], 10))
        prob = 1.0 - math.exp(-lam_team * share)
        if prob >= 0.05:
            out.append({"nom": p["nom"], "p": round(float(prob), 2), "buts": p["buts"]})
        if len(out) >= top:
            break
    return out


# ---------------------------------------------------------------- presse : flux RSS publics

def _texte_brut(brut: str) -> str:
    texte = html.unescape(str(brut or ""))
    texte = re.sub(r"<[^>]*>", " ", texte)
    return re.sub(r"\s+", " ", html.unescape(texte)).strip()


def _date_flux(brut: str) -> float | None:
    brut = str(brut or "").strip()
    if not brut:
        return None
    try:
        d = datetime.fromisoformat(brut.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(brut)
        except (TypeError, ValueError, IndexError):
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def parse_rss(data: bytes) -> list[dict]:
    """Articles datés d'un flux RSS ou Atom (`titre`, `resume`, `date`) ; liste vide si le document est illisible.
    Un document qui déclare des entités est refusé : aucun flux n'en a besoin."""
    if not data or b"<!ENTITY" in data:
        return []
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError, LookupError):
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    out = []
    for node in [*root.iter("item"), *root.iter(f"{atom}entry")]:
        champ = lambda *noms: next((node.findtext(n) for n in noms if node.findtext(n)), "")  # noqa: E731
        titre = _texte_brut(champ("title", f"{atom}title"))
        date = _date_flux(champ("pubDate", f"{atom}published", f"{atom}updated", "{http://purl.org/dc/elements/1.1/}date"))
        if titre and date is not None:
            resume = _texte_brut(champ("description", f"{atom}summary"))[:600]
            out.append({"titre": titre, "resume": resume, "date": date})
    return out


def _get_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "extinction-des-feux/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(RSS_MAX_OCTETS)


def fetch_press(state: Path, now: datetime, offline: bool = False, fetch=None) -> list[dict]:
    """Articles des 72 dernières heures. Chaque flux est relu au plus toutes les 6 h ; un flux en panne
    garde ses articles en cache (qui vieillissent et disparaissent) et sera réessayé au lancement suivant."""
    f = state / "presse_rss.json"
    cache = SRC.read_json(f, {})
    t = now.timestamp()
    recent = lambda i: -3600 <= t - i["date"] <= RSS_WINDOW_H * 3600  # noqa: E731
    pannes, change = [], False
    for nom, url in RSS_FEEDS.items():
        if offline or t - (cache.get(nom) or {}).get("fetched", 0) < RSS_CACHE_H * 3600:
            continue
        try:
            items = parse_rss((fetch or _get_bytes)(url, RSS_TIMEOUT_S))
        except Exception:  # noqa: BLE001
            items = []
        if items:
            cache[nom] = {"fetched": t, "items": [i for i in items if recent(i)]}
            change = True
        else:
            pannes.append(nom)
    if pannes:
        print(f"   Presse : flux indisponibles ({', '.join(pannes)})")
    if change:
        SRC.write_json(f, cache)
    vus, out = set(), []
    for nom in RSS_FEEDS:
        for i in (cache.get(nom) or {}).get("items") or []:
            if recent(i) and i["titre"] not in vus:
                vus.add(i["titre"])
                out.append(i)
    return out


def _phrases(*mots: str) -> list[tuple[str, ...]]:
    return [tuple(m.split()) for m in mots]


# formes repliées (minuscules, sans accents). « out » seul est trop courant (« knocked out ») : expressions seulement.
MOTS_ABSENCE = _phrases(
    "blesse", "blessee", "blesses", "blessure", "forfait", "forfaits", "absent", "absents", "absence", "indisponible",
    "suspendu", "suspendus", "injured", "injury", "ruled out", "out for", "out with", "out injured", "is out",
    "are out", "sidelined", "suspended", "verletzt", "verletzung", "gesperrt", "ausfall", "fallt aus", "baja", "bajas",
    "lesionado", "lesion", "sancionado", "infortunio", "infortunato", "squalificato", "indisponibile")
MOTS_DOUTE = _phrases("incertain", "incertains", "doubtful", "a doubt", "injury doubt", "in doubt", "fraglich",
                      "es duda", "en duda", "in dubbio", "in forse")
FAUX_AMIS = _phrases("injury time", "baja forma")
# retour de blessure ou démenti : la phrase entière est ignorée (mieux vaut manquer un absent qu'en inventer un)
MOTS_RETOUR = _phrases(
    "de retour", "retour de", "son retour", "revient", "retrouve", "apte", "retabli", "pas blesse", "pas forfait",
    "pas absent", "pas suspendu", "sans blessure", "return", "returns", "returned", "returning", "back from", "is back",
    "back in", "back after", "fit again", "recovered", "recovers", "not injured", "no injury", "not ruled out",
    "zuruck", "comeback", "wieder fit", "entwarnung", "vuelve", "regresa", "regreso", "recuperado", "alta",
    "reaparece", "rientra", "rientro", "recuperato", "torna")
LIAISONS = {"et", "and", "und", "y", "e"}
# « Kane marque, Olise blessé » : ces mots séparent deux propositions
COUPURES = re.compile(r"(?<=\w\w[.!?])\s+|(?<=[!?;|…])\s*|\s[–—-]\s|"
                      r"\b(?:as|while|but|mais|tandis que|alors que|pendant que|aber|pero|mientras|mentre)\b", re.I)

# mots seuls qui ne désignent pas un club précis
ALIAS_TROP_VAGUES = {"real", "sporting", "athletic", "united", "city", "paris", "racing", "olympique", "stade",
                     "borussia", "atletico", "deportivo", "union", "club"}
SIGLES_CLUB = {"fc", "cf", "afc", "sc", "ac", "as", "ss", "ssc", "us", "fk", "sk", "bk", "sv", "vfb", "vfl", "tsg",
               "rc", "ogc", "ud", "cd", "rcd", "club", "de", "calcio", "1", "04", "05", "07", "1846", "1899", "1901",
               "1907", "1909", "1910", "1913", "29"}
# surnoms employés par la presse, rattachés au nom officiel du club (replié)
ALIAS_PRESSE = {
    "paris saint germain": ["PSG", "Paris SG"], "paris sg": ["PSG", "Paris Saint-Germain"],
    "bayern": ["Bayern"], "manchester city": ["Man City"], "manchester united": ["Man United", "Man Utd"],
    "tottenham": ["Spurs"], "juventus": ["Juve"], "internazionale": ["Inter"], "barcelona": ["Barça", "Barca", "Barcelone"],
    "atletico madrid": ["Atlético", "Atleti"], "atletico de madrid": ["Atlético Madrid", "Atlético", "Atleti"],
    "olympique de marseille": ["OM", "Marseille"], "olympique lyonnais": ["OL", "Lyon"], "lille": ["Lille", "LOSC"],
    "borussia dortmund": ["BVB", "Dortmund"], "monchengladbach": ["Gladbach"], "newcastle": ["Newcastle"],
    "leverkusen": ["Leverkusen"], "napoli": ["Napoli", "Naples"],
}


def _mots(texte: str) -> list[tuple[str, str, bool]]:
    """(mot d'origine, mot replié, virgule avant lui)."""
    texte = unicodedata.normalize("NFC", texte)
    out, fin = [], 0
    for m in re.finditer(r"[^\W_]+", texte):
        out.append((m.group(), _fold(m.group()), "," in texte[fin:m.start()]))
        fin = m.end()
    return out


def _positions(plies: list[str], phrase: tuple[str, ...]):
    n = len(phrase)
    return [(i, i + n) for i in range(len(plies) - n + 1) if tuple(plies[i:i + n]) == phrase]


def club_aliases(*noms: str) -> set[tuple[str, ...]]:
    """Façons dont la presse peut désigner un club (suites de mots repliés)."""
    out: set[tuple[str, ...]] = set()
    for nom in noms:
        mots = _fold(nom).split()
        if not mots:
            continue
        court = list(mots)
        while len(court) > 1 and court[0] in SIGLES_CLUB:
            court.pop(0)
        while len(court) > 1 and court[-1] in SIGLES_CLUB:
            court.pop()
        for forme in (mots, court):
            if len(forme) > 1 or (len(forme[0]) >= 4 and forme[0] not in ALIAS_TROP_VAGUES):
                out.add(tuple(forme))
        plein = " ".join(mots)
        for cle, surnoms in ALIAS_PRESSE.items():
            if f" {cle} " in f" {plein} ":
                out.update(tuple(_fold(a).split()) for a in surnoms)
    return out


def clubs_in_news(items: list[dict], aliases: dict[str, set]) -> list[set[str]]:
    """Pour chaque article : les clubs cités (le nom doit commencer par une majuscule)."""
    out = []
    for item in items:
        mots = _mots(f"{item['titre']} . {item.get('resume', '')}")
        plies = [m[1] for m in mots]
        cites = set()
        for tid, formes in aliases.items():
            if any(not mots[i][0][0].islower() for forme in formes for i, _ in _positions(plies, forme)):
                cites.add(tid)
        out.append(cites)
    return out


def has_absence_word(item: dict) -> bool:
    plies = _fold(f"{item['titre']} {item.get('resume', '')}").split()
    return any(_positions(plies, p) for p in MOTS_ABSENCE + MOTS_DOUTE)


def _joueurs_cites(mots: list, effectifs: dict[str, list[str]], mots_clubs: set[str]) -> list[tuple[int, int, str, str]]:
    """(début, fin, club, joueur) pour chaque joueur désigné sans ambiguïté dans la phrase."""
    plies = [m[1] for m in mots]
    complets, familles = {}, {}
    for tid, noms in effectifs.items():
        for nom in noms:
            parts = _fold(nom).split()
            if not parts:
                continue
            if len(parts) > 1:
                for a, b in _positions(plies, tuple(parts)):
                    complets[(a, b)] = (tid, nom)
            famille = parts[-2] if len(parts) > 1 and parts[-1] in ("junior", "jr", "neto", "filho") else parts[-1]
            if len(famille) < 4 or famille in mots_clubs:
                continue
            for a, _ in _positions(plies, (famille,)):
                if not mots[a][0][0].islower():          # un nom propre porte une majuscule
                    familles.setdefault(a, {})[(tid, nom)] = parts
    out = [(a, b, tid, nom) for (a, b), (tid, nom) in complets.items()]
    couverts = {i for a, b, _, _ in out for i in range(a, b)}
    for a, candidats in familles.items():
        if a in couverts:
            continue
        if len(candidats) > 1:                           # nom partagé : il faut l'initiale
            initiale = plies[a - 1] if a else ""
            candidats = {k: p for k, p in candidats.items() if len(initiale) == 1 and p[0][0] == initiale}
        if len(candidats) == 1:
            (tid, nom), = candidats
            out.append((a, a + 1, tid, nom))
    return sorted(out)


def _lies(mots: list, x: tuple, y: tuple) -> bool:
    """Deux noms d'une même énumération (« Kane, Olise », « Kane et Olise »)."""
    gauche, droite = sorted((x, y))
    return all(mots[i][1] in LIAISONS for i in range(gauche[1], droite[0]))


def _absents_phrase(mots: list, joueurs: list) -> dict[tuple[str, str], str]:
    plies = [m[1] for m in mots]
    if any(_positions(plies, p) for p in MOTS_RETOUR):
        return {}
    faux = {i for p in FAUX_AMIS for a, b in _positions(plies, p) for i in range(a, b)}
    trouves: dict[tuple[str, str], str] = {}
    for statut, liste in (("absent", MOTS_ABSENCE), ("incertain", MOTS_DOUTE)):   # le doute l'emporte
        for p in liste:
            for a, b in _positions(plies, p):
                if faux & set(range(a, b)):
                    continue
                proches = []
                for j in joueurs:
                    apres = j[0] >= b
                    ecart = j[0] - b if apres else a - j[1]
                    if ecart < 0 or ecart > PRESS_MAX_ECART:
                        continue
                    # « un supporter blessé avant le match, Kane... » : la virgule ferme la proposition du mot
                    if apres and ecart and any(mots[i][2] for i in range(b, j[0] + 1)):
                        continue
                    proches.append((ecart, j))
                if not proches:
                    continue
                retenus = [min(proches)[1]]
                ajout = True
                while ajout:
                    ajout = False
                    for j in joueurs:
                        if j not in retenus and any(_lies(mots, j, r) for r in retenus):
                            retenus.append(j)
                            ajout = True
                for _, _, tid, nom in retenus:
                    trouves[(tid, nom)] = statut
    return trouves


def detect_press_absences(items: list[dict], effectifs: dict[str, list[str]],
                          aliases: dict[str, set]) -> dict[str, list[dict]]:
    """`club_id -> [{nom, statut}]` : un article cite le club, et une de ses phrases rattache un mot d'absence
    à un joueur de l'effectif. Un seul article « absent » suffit à lever un doute."""
    trouves: dict[tuple[str, str], str] = {}
    for item, cites in zip(items, clubs_in_news(items, aliases)):
        vises = {tid: effectifs[tid] for tid in cites if tid in effectifs}
        if not vises:
            continue
        mots_clubs = {m for tid in cites for forme in aliases[tid] for m in forme}
        for champ in (item["titre"], item.get("resume", "")):
            for phrase in COUPURES.split(champ):
                mots = _mots(phrase or "")
                for cle, statut in _absents_phrase(mots, _joueurs_cites(mots, vises, mots_clubs)).items():
                    if trouves.get(cle) != "absent":
                        trouves[cle] = statut
    out: dict[str, list[dict]] = {}
    for tid, noms in effectifs.items():
        liste = [{"nom": nom, "statut": trouves[(tid, nom)]} for nom in noms if (tid, nom) in trouves]
        if liste:
            out[tid] = liste
    return out


def squad_names(club_ids: list[str], teams: dict[str, dict], scorers_map: dict[str, list[dict]],
                token: str | None, state: Path, now: datetime) -> dict[str, list[str]]:
    """Effectif de chaque club : fichier des clubs de la compétition s'il le contient, sinon `/teams/{id}`
    (cache 7 jours, budget par lancement). Les buteurs connus complètent la liste."""
    f = state / "fdorg_squads.json"
    cache = SRC.read_json(f, {})
    t = now.timestamp()
    appels, change, out = 0, False, {}
    for tid in sorted(set(club_ids)):
        equipe = teams.get(tid) or {}
        noms = [p["name"] for p in equipe.get("squad") or [] if p.get("name")]
        if not noms:
            cur = cache.get(tid)
            frais = cur and t - cur.get("fetched", 0) < SQUADS_CACHE_DAYS * 86400
            if not frais and token and equipe.get("id") and appels < SQUADS_MAX_PAR_RUN:
                appels += 1
                try:
                    data, _ = SRC._get_json(FDORG_TEAM.format(id=equipe["id"]), {"X-Auth-Token": token}, tries=1)
                    cur = {"fetched": t, "noms": [p["name"] for p in data.get("squad") or [] if p.get("name")]}
                    cache[tid], change = cur, True
                except Exception as e:  # noqa: BLE001
                    print(f"   Effectif {tid} indisponible : {type(e).__name__} {e}")
                time.sleep(SRC.FDORG_PAUSE_S)
            noms = list((cur or {}).get("noms") or [])
        for p in scorers_map.get(tid) or []:
            if not any(same_player(p["nom"], n) for n in noms):
                noms.append(p["nom"])
        if noms:
            out[tid] = noms
    if change:
        SRC.write_json(f, cache)
    return out


# ---------------------------------------------------------------- API-Football : budget strict <= 15 req/j

def _quota_state(state: Path, jour: str) -> dict:
    q = SRC.read_json(state / "apifoot_quota.json", {})
    if q.get("jour") != jour:
        return {"jour": jour, "appels": 0, "restant": None}
    return q


def _can_call_apifoot(q: dict) -> bool:
    if q.get("appels", 0) >= APIFOOT_MAX_JOUR:
        return False
    restant = q.get("restant")
    return restant is None or restant > APIFOOT_RESERVE_DIRECT


def _apifoot_get(path: str, key: str, state: Path, jour: str) -> list | None:
    q = _quota_state(state, jour)
    if not key or not _can_call_apifoot(q):
        return None
    data, hdr = SRC._get_json(f"{APIFOOT_BASE}/{path}", {"x-apisports-key": key}, tries=2)
    q["appels"] = int(q.get("appels", 0)) + 1
    rem = hdr.get("x-ratelimit-requests-remaining") or hdr.get("X-RateLimit-Requests-Remaining")
    if rem is not None:
        try:
            q["restant"] = int(rem)
        except ValueError:
            pass
    SRC.write_json(state / "apifoot_quota.json", q)
    errors = data.get("errors")
    if errors and (len(errors) if isinstance(errors, (list, dict)) else True):
        raise RuntimeError(f"API-Football {path} : {errors}")
    return data.get("response") or []


def fetch_injuries(dates_iso: list[str], key: str | None, state: Path, now: datetime,
                   idx: SRC.TeamIndex) -> tuple[dict[tuple[str, str], list[dict]], dict[str, int]]:
    """Récupère les blessures/suspensions pour les dates demandées (cache 12 h par date, 1 appel/date).
    Renvoie (`(date, club_id) -> liste d'absents`, `club_id -> team_api_id`)."""
    jour = now.strftime("%Y-%m-%d")
    t = now.timestamp()
    team_ids = SRC.read_json(state / "apifoot_teams.json", {})
    injuries: dict[tuple[str, str], list[dict]] = {}

    for d_iso in sorted(set(dates_iso))[:HORIZON_DAYS]:
        f = state / f"injuries_{d_iso}.json"
        cached = SRC.read_json(f, {})
        if key and (not cached or t - cached.get("fetched", 0) >= INJURIES_CACHE_H * 3600):
            try:
                resp = _apifoot_get(f"injuries?date={d_iso}", key, state, jour)
                if resp is not None:
                    # On ne garde que nos 7 compétitions
                    kept = [x for x in resp if (x.get("league") or {}).get("id") in APIFOOT_LEAGUES]
                    cached = {"fetched": t, "items": kept}
                    SRC.write_json(f, cached)
            except Exception as e:  # noqa: BLE001
                print(f"   API-Football injuries {d_iso} indisponible : {type(e).__name__} {e}")
        seen_player: set[tuple[str, str, str]] = set()
        for item in cached.get("items") or []:
            lid = (item.get("league") or {}).get("id")
            comp = APIFOOT_LEAGUES.get(lid)
            team = item.get("team") or {}
            player = (item.get("player") or {}).get("name")
            if not comp or not team.get("name") or not player:
                continue
            tid = idx.resolve(team["name"], LEAGUE_CC.get(comp))
            if tid.startswith("?:"):
                continue
            if team.get("id"):
                team_ids[tid] = int(team["id"])
            dedup = (d_iso, tid, _fold(player))
            if dedup in seen_player:
                continue
            seen_player.add(dedup)
            ptype = str((item.get("player") or {}).get("type") or "")
            reason = str((item.get("player") or {}).get("reason") or "")
            statut = "incertain" if "question" in ptype.lower() or "doubt" in reason.lower() else "absent"
            injuries.setdefault((d_iso, tid), []).append({"nom": player, "raison": reason, "statut": statut})

    if team_ids:
        SRC.write_json(state / "apifoot_teams.json", team_ids)
    return injuries, team_ids


def fetch_coaches(club_ids: list[str], team_api_ids: dict[str, int], key: str | None,
                  state: Path, now: datetime) -> dict[str, dict]:
    """Vérifie les entraîneurs actuels (cache 14 jours/club, plafonné au reste du budget journalier <= 15)."""
    jour = now.strftime("%Y-%m-%d")
    t = now.timestamp()
    cache = SRC.read_json(state / "apifoot_coaches.json", {})
    changed = False
    for cid in sorted(set(club_ids)):
        api_id = team_api_ids.get(cid)
        if not api_id:
            continue
        cur = cache.get(cid)
        if key and (not cur or t - cur.get("fetched", 0) >= COACH_CACHE_DAYS * 86400):
            try:
                resp = _apifoot_get(f"coachs?team={api_id}", key, state, jour)
                if resp is None:
                    break   # budget journalier ou réserve direct atteinte : on s'arrête proprement
                best_nom, best_start = None, ""
                for coach in resp:
                    for job in coach.get("career") or []:
                        if (job.get("team") or {}).get("id") == api_id and job.get("end") is None:
                            st = str(job.get("start") or "")
                            if st >= best_start:
                                best_start = st
                                best_nom = coach.get("name") or f"{coach.get('firstname', '')} {coach.get('lastname', '')}".strip()
                cache[cid] = {"nom": best_nom, "debut": best_start or None, "fetched": t}
                changed = True
            except Exception as e:  # noqa: BLE001
                print(f"   API-Football coach {cid} indisponible : {type(e).__name__} {e}")
    if changed:
        SRC.write_json(state / "apifoot_coaches.json", cache)
    out = {}
    for cid, info in cache.items():
        debut = info.get("debut")
        recent = False
        if debut:
            try:
                days = (now.date() - datetime.fromisoformat(debut[:10]).date()).days
                recent = 0 <= days < COACH_RECENT_DAYS
            except ValueError:
                recent = False
        out[cid] = {"nom": info.get("nom"), "debut": debut, "recent": recent}
    return out


# ---------------------------------------------------------------- ajustements bornés & facteurs clés

def _injury_delta(injuries: list[dict], top_scorers: list[dict], g_team: int) -> tuple[float, float, list[str]]:
    """Retourne (delta_att, delta_def_conceded, noms_absents_notables) strictement bornés."""
    if not injuries:
        return 0.0, 0.0, []
    confirmed = [x for x in injuries if x.get("statut") != "incertain"]
    doubtful = [x for x in injuries if x.get("statut") == "incertain"]
    key_missing = []
    delta_att = 0.0
    g_base = max(g_team, 10)
    for sc in top_scorers[:3]:
        if sc["buts"] < 3:
            continue
        hit = next((x for x in confirmed if same_player(sc["nom"], x["nom"])), None)
        if hit:
            key_missing.append(sc["nom"])
            # Malus offensif proportionnel à la part de buts du joueur absent (plafonné)
            delta_att -= min(0.08, 0.25 * (sc["buts"] / g_base))
    eff_count = len(confirmed) + 0.5 * len(doubtful)
    if eff_count >= 3:
        delta_att -= min(0.05, 0.015 * (eff_count - 2))
    delta_def = min(MAX_LAM_BONUS, 0.012 * max(0.0, eff_count - 2)) if eff_count >= 3 else 0.0
    delta_att = max(MAX_LAM_MALUS, delta_att)
    notables = key_missing + [x["nom"] for x in confirmed if not any(same_player(x["nom"], k) for k in key_missing)]
    return delta_att, delta_def, notables


def _press_delta(presse: list[dict], injuries: list[dict], top_scorers: list[dict], g_team: int) -> float:
    """Malus offensif des absents signalés par la presse, hors ceux qu'API-Football compte déjà."""
    delta = 0.0
    for x in presse:
        if any(same_player(x["nom"], a["nom"]) and a.get("statut") != "incertain" for a in injuries):
            continue
        sc = next((s for s in top_scorers[:3] if s["buts"] >= 3 and same_player(s["nom"], x["nom"])), None)
        part = min(PRESS_MALUS_BUTEUR_MAX, 0.2 * sc["buts"] / max(g_team, 10)) if sc else 0.0
        delta -= (0.5 if x.get("statut") == "incertain" else 1.0) * (PRESS_MALUS_JOUEUR + part)
    return max(MAX_PRESS_MALUS, delta)


def apply_context_adjustments(
    lh: float, la: float, home_id: str, away_id: str, home_nom: str, away_nom: str,
    injuries_h: list[dict], injuries_a: list[dict],
    coach_h: dict | None, coach_a: dict | None,
    scorers_map: dict[str, list[dict]], team_goals: dict[str, int],
    rest_h: float | None = None, rest_a: float | None = None,
    rest_comp_h: str | None = None, rest_comp_a: str | None = None,
    presse_h: list[dict] | None = None, presse_a: list[dict] | None = None,
) -> dict:
    """Ajuste (lh, la) de façon bornée avant le mélange avec les cotes, et prépare facteurs clés & buteurs."""
    da_h, dd_h, abs_h = _injury_delta(injuries_h, scorers_map.get(home_id) or [], team_goals.get(home_id, 0))
    da_a, dd_a, abs_a = _injury_delta(injuries_a, scorers_map.get(away_id) or [], team_goals.get(away_id, 0))

    presse_h, presse_a = presse_h or [], presse_a or []
    da_h += _press_delta(presse_h, injuries_h, scorers_map.get(home_id) or [], team_goals.get(home_id, 0))
    da_a += _press_delta(presse_a, injuries_a, scorers_map.get(away_id) or [], team_goals.get(away_id, 0))

    # Ajustement borné sur les taux de buts attendus
    mult_h = float(np.clip(1.0 + da_h + dd_a, 1.0 + MAX_LAM_MALUS, 1.0 + MAX_LAM_BONUS))
    mult_a = float(np.clip(1.0 + da_a + dd_h, 1.0 + MAX_LAM_MALUS, 1.0 + MAX_LAM_BONUS))
    lh_adj, la_adj = lh * mult_h, la * mult_a

    # Changement d'entraîneur récent (< 30 j) : légère hausse d'incertitude (température)
    new_coach_h = bool(coach_h and coach_h.get("recent"))
    new_coach_a = bool(coach_a and coach_a.get("recent"))
    variance_temp = COACH_VARIANCE_TEMP if (new_coach_h or new_coach_a) else 1.0

    # Facteurs clés lisibles en français
    facteurs: list[str] = []
    for nom, r, comp_nom in ((home_nom, rest_h, rest_comp_h), (away_nom, rest_a, rest_comp_a)):
        if r is not None and r <= 3:
            apres = f" après {comp_nom}" if comp_nom else ""
            facteurs.append(f"Repos court ({nom}) : {int(round(r))} j{apres}")
    if new_coach_h:
        c_nom = f" ({coach_h['nom']})" if coach_h and coach_h.get("nom") else ""
        facteurs.append(f"Nouvel entraîneur (< 30 j) à {home_nom}{c_nom}")
    if new_coach_a:
        c_nom = f" ({coach_a['nom']})" if coach_a and coach_a.get("nom") else ""
        facteurs.append(f"Nouvel entraîneur (< 30 j) à {away_nom}{c_nom}")
    for nom, abs_list in ((home_nom, abs_h), (away_nom, abs_a)):
        if abs_list:
            shown = ", ".join(abs_list[:2])
            extra = f" (+{len(abs_list) - 2})" if len(abs_list) > 2 else ""
            facteurs.append(f"Absents notables ({nom}) : {shown}{extra}")

    for nom, liste in ((home_nom, presse_h), (away_nom, presse_a)):
        if liste:
            shown = ", ".join(x["nom"] + (" (incertain)" if x.get("statut") == "incertain" else "") for x in liste[:4])
            extra = f" (+{len(liste) - 4})" if len(liste) > 4 else ""
            facteurs.append(f"Absents signalés (presse, {nom}) : {shown}{extra}")

    # Buteurs probables : hors absents confirmés, et hors tout joueur signalé par la presse (même incertain)
    exclus = {cote: [x["nom"] for x in inj if x.get("statut") != "incertain"] + [x["nom"] for x in presse]
              for cote, inj, presse in (("dom", injuries_h, presse_h), ("ext", injuries_a, presse_a))}
    but_h = probable_scorers(home_id, lh_adj, scorers_map, team_goals, exclus["dom"])
    but_a = probable_scorers(away_id, la_adj, scorers_map, team_goals, exclus["ext"])

    return {
        "lh": float(lh_adj),
        "la": float(la_adj),
        "variance_temp": float(variance_temp),
        "new_coach": new_coach_h or new_coach_a,
        "facteurs": facteurs,
        "exclus": exclus,
        "buteurs": {"dom": but_h, "ext": but_a} if (but_h or but_a) else None,
    }
