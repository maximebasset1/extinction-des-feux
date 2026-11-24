"""Facteurs contextuels des prochains matchs (100 % gratuit, budget API maîtrisé).

- Buteurs en forme : `/competitions/{code}/scorers` sur football-data.org (gratuit, cache 12 h).
- Blessures / suspensions et changements d'entraîneur : API-Football (`/injuries`, `/coachs`),
  strictement bornés à 15 requêtes/jour au total dans `mise-a-jour.yml` et stoppés si le quota
  global du compte descend sous 25 requêtes restantes (réserve prioritaire pour le direct live).
- Tout appel réseau est isolé : en cas d'indisponibilité ou d'absence de clé, repli silencieux
  sur le cache existant ou sur des données vides.
"""
from __future__ import annotations

import math
import re
import time
import unicodedata
from datetime import datetime, timedelta
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


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
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
                     "penalties": int(item.get("penalties") or 0)}
            # On garde le plus gros total de buts (ex. championnat national plutôt que 3 matchs de coupe)
            if cur is None or entry["buts"] > cur["buts"]:
                by_team[tid][key] = entry
    return {tid: sorted(players.values(), key=lambda x: (-x["buts"], x["nom"])) for tid, players in by_team.items()}


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
        if p["buts"] < 2:
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


def apply_context_adjustments(
    lh: float, la: float, home_id: str, away_id: str, home_nom: str, away_nom: str,
    injuries_h: list[dict], injuries_a: list[dict],
    coach_h: dict | None, coach_a: dict | None,
    scorers_map: dict[str, list[dict]], team_goals: dict[str, int],
    rest_h: float | None = None, rest_a: float | None = None,
    rest_comp_h: str | None = None, rest_comp_a: str | None = None,
) -> dict:
    """Ajuste (lh, la) de façon bornée avant le mélange avec les cotes, et prépare facteurs clés & buteurs."""
    da_h, dd_h, abs_h = _injury_delta(injuries_h, scorers_map.get(home_id) or [], team_goals.get(home_id, 0))
    da_a, dd_a, abs_a = _injury_delta(injuries_a, scorers_map.get(away_id) or [], team_goals.get(away_id, 0))

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

    # Buteurs probables (hors absents confirmés)
    conf_h = [x["nom"] for x in injuries_h if x.get("statut") != "incertain"]
    conf_a = [x["nom"] for x in injuries_a if x.get("statut") != "incertain"]
    but_h = probable_scorers(home_id, lh_adj, scorers_map, team_goals, conf_h)
    but_a = probable_scorers(away_id, la_adj, scorers_map, team_goals, conf_a)

    return {
        "lh": float(lh_adj),
        "la": float(la_adj),
        "variance_temp": float(variance_temp),
        "new_coach": new_coach_h or new_coach_a,
        "facteurs": facteurs,
        "buteurs": {"dom": but_h, "ext": but_a} if (but_h or but_a) else None,
    }
