"""Grille de départ de la prochaine course : pénalités et départs des stands compris.

Source : OpenF1 (grille publiée quelques minutes après celle du site officiel de la F1, une fois les
pénalités connues). Tant qu'elle n'est pas publiée, la grille est l'ordre de la qualification et elle
est annoncée comme provisoire.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from config import DATA_RAW

API = "https://api.openf1.org/v1"
MIN_DRIVERS = 15            # moins de lignes : grille incomplète, on ne s'y fie pas
SESSION_TOLERANCE_H = 3     # la qualif OpenF1 doit commencer à 3 h près de l'horaire du calendrier


def _get(path: str, **params) -> list:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "extinction-des-feux"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def quali_session(sessions: list, quali_start: str | None) -> dict | None:
    """La séance de qualification OpenF1 du week-end : la plus proche de l'horaire du calendrier."""
    if not quali_start or not sessions:
        return None
    target = _ts(quali_start)
    best = min(sessions, key=lambda s: abs((_ts(s["date_start"]) - target).total_seconds()))
    return best if abs((_ts(best["date_start"]) - target).total_seconds()) <= SESSION_TOLERANCE_H * 3600 else None


def from_openf1(rows: list, numbers: dict, entrants: list) -> pd.DataFrame | None:
    """Lignes OpenF1 (position, driver_number) -> grille par code pilote ; absents = départ des stands."""
    rows = [r for r in rows if r.get("position") is not None and str(r.get("driver_number")) in numbers]
    if len(rows) < MIN_DRIVERS or len({r["position"] for r in rows}) != len(rows):
        return None
    g = pd.DataFrame({"driver": [numbers[str(r["driver_number"])] for r in rows],
                      "grille": [int(r["position"]) for r in rows], "stands": False})
    missing = [d for d in entrants if d not in set(g["driver"])]
    back = int(g["grille"].max()) + 1
    g = pd.concat([g, pd.DataFrame({"driver": missing, "grille": back, "stands": True})], ignore_index=True)
    return g.sort_values("grille").reset_index(drop=True)


def numbers_from_raw(season: int, gp_folder: str) -> dict:
    """Numéro de voiture -> code pilote, d'après les fichiers TracingInsights de la qualif."""
    f = DATA_RAW / str(season) / gp_folder / "Qualifying" / "drivers.json"
    if not f.exists():
        return {}
    return {str(d.get("dn")): d["driver"] for d in json.loads(f.read_text(encoding="utf-8")).get("drivers", []) if d.get("dn")}


def official(season: int, gp_folder: str, info: dict, quali: pd.DataFrame) -> tuple[pd.DataFrame | None, str]:
    """(grille, source). Grille : driver, grille, stands, qualif, penalite. Source : « officielle » ou « provisoire »."""
    if quali is None or not len(quali):
        return None, "inconnue"
    q = quali[["driver", "quali_pos"]].copy()
    q["qualif"] = q["quali_pos"].rank(method="first", na_option="bottom").astype(int)
    provisional = q.assign(grille=q["qualif"], stands=False)[["driver", "grille", "stands", "qualif"]]
    grid = None
    if not (info.get("sessions") or {}).get("Q"):
        return provisional.assign(penalite=0), "provisoire"
    try:
        sessions = _get("sessions", year=season, session_name="Qualifying")
        s = quali_session(sessions, (info.get("sessions") or {}).get("Q"))
        if s:
            numbers = numbers_from_raw(season, gp_folder) or {
                str(d["driver_number"]): d["name_acronym"] for d in _get("drivers", session_key=s["session_key"])}
            grid = from_openf1(_get("starting_grid", session_key=s["session_key"]), numbers, list(q["driver"]))
    except Exception as e:  # noqa: BLE001
        print(f"Grille officielle indisponible ({type(e).__name__}) : grille de la qualif, annoncée provisoire")
    if grid is None:
        return provisional.assign(penalite=0), "provisoire"
    g = grid.merge(q[["driver", "qualif"]], on="driver", how="left")
    g["qualif"] = g["qualif"].fillna(len(g)).astype(int)
    g["penalite"] = (g["grille"] - g["qualif"]).clip(lower=0).astype(int)
    return g[["driver", "grille", "stands", "qualif", "penalite"]], "officielle"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
