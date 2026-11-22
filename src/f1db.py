"""Données officielles des courses passées (f1db, licence CC BY 4.0) : grille de départ réelle et classement.

Les tours de TracingInsights ne disent ni où chaque pilote a vraiment pris le départ (pénalités moteur,
départs des stands) ni le classement officiel (pénalités après course, disqualifications).
f1db publie les deux après chaque course. On lit ses fichiers sources (YAML) depuis son dépôt GitHub,
avec une copie partielle qui ne contient que les fichiers utiles.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pandas as pd
import yaml

from config import DATA_RAW

REPO = "https://github.com/f1db/f1db"
FIRST_SEASON = 2018
REFRESH_HOURS = 6          # f1db est mis à jour dans les heures qui suivent une course
MATCH_DAYS = 1             # dates TracingInsights et f1db : à un jour près (fuseaux horaires)


def folder() -> Path:
    return Path(os.environ["F1DB_DIR"]) if os.environ.get("F1DB_DIR") else DATA_RAW / "f1db"


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=600)


def sync(last_season: int) -> bool:
    """Copie partielle à jour du dépôt f1db. Renvoie False si elle n'a pas pu être obtenue."""
    d = folder()
    stamp = d / ".maj"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < REFRESH_HOURS * 3600:
        return True
    pats = [f"/src/data/seasons/{y}/races/*/{f}" for y in range(FIRST_SEASON, last_season + 1)
            for f in ("race.yml", "starting-grid-positions.yml", "race-results.yml")] + ["/src/data/drivers/*.yml"]
    try:
        if not (d / ".git").exists():
            d.mkdir(parents=True, exist_ok=True)
            _git("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", REPO, str(d))
            _git("sparse-checkout", "init", "--no-cone", cwd=d)
        _git("sparse-checkout", "set", "--no-cone", *pats, cwd=d)
        _git("fetch", "--depth", "1", "origin", "HEAD", cwd=d)
        _git("checkout", "-q", "-f", "FETCH_HEAD", cwd=d)
        stamp.touch()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"f1db indisponible ({type(e).__name__}) : grilles officielles des courses passées non mises à jour")
        return (d / "src").exists()


def _read(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def load() -> pd.DataFrame:
    """Une ligne par pilote et par course : grille réelle, départ des stands, pénalité, classement officiel."""
    root = folder() / "src" / "data"
    if not root.exists():
        return pd.DataFrame(columns=["season", "date", "driver", "grille_officielle", "stands", "penalite",
                                     "arrivee_officielle", "statut"])
    abbr = {}
    for f in (root / "drivers").glob("*.yml"):
        d = _read(f) or {}
        if d.get("abbreviation"):
            abbr[d["id"]] = d["abbreviation"]
    rows = []
    for race_dir in sorted((root / "seasons").glob("*/races/*")):
        race = _read(race_dir / "race.yml")
        grid = _read(race_dir / "starting-grid-positions.yml") or []
        res = _read(race_dir / "race-results.yml") or []
        if not race or not (grid or res):
            continue
        season, date = int(race_dir.parts[-3]), pd.Timestamp(str(race["date"]))
        numeric = [int(g["position"]) for g in grid if str(g.get("position")).isdigit()]
        back = max(numeric, default=len(grid)) + 1   # départ des stands : derrière toute la grille
        per = {}
        for g in grid:
            pos = str(g.get("position"))
            per[g["driverId"]] = {"grille_officielle": int(pos) if pos.isdigit() else back, "stands": pos == "PL",
                                  "penalite": g.get("gridPenalty")}
        # classement : classés dans l'ordre, puis non classés, puis disqualifiés (ordre du fichier)
        for order, r in enumerate(res, start=1):
            e = per.setdefault(r["driverId"], {"grille_officielle": None, "stands": False, "penalite": None})
            e["arrivee_officielle"] = order
            e["statut"] = "classé" if str(r.get("position")).isdigit() else str(r.get("position"))
        for driver_id, e in per.items():
            if driver_id in abbr:
                rows.append({"season": season, "date": date, "driver": abbr[driver_id], **e})
    out = pd.DataFrame(rows)
    for c in ("arrivee_officielle", "statut"):
        if c not in out:
            out[c] = None
    return out


def match(official: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    """Rattache chaque course f1db au Grand Prix de nos données (même saison, date à un jour près)."""
    if official.empty:
        return official.assign(grand_prix=pd.Series(dtype=str))
    ours = races[["season", "grand_prix", "date"]].drop_duplicates(["season", "grand_prix"]).copy()
    ours["date"] = pd.to_datetime(ours["date"])
    keys = official[["season", "date"]].drop_duplicates()
    pairs = []
    for k in keys.itertuples():
        cand = ours[(ours["season"] == k.season) & ((ours["date"] - k.date).abs() <= pd.Timedelta(days=MATCH_DAYS))]
        if len(cand) == 1:
            pairs.append((k.season, k.date, cand["grand_prix"].iloc[0]))
    m = pd.DataFrame(pairs, columns=["season", "date", "grand_prix"])
    return official.merge(m, on=["season", "date"], how="inner").drop(columns="date")


def official_results(results: pd.DataFrame, official: pd.DataFrame) -> pd.DataFrame:
    """Classement officiel à la place de l'ordre recalculé à partir des tours, quand f1db le connaît."""
    o = match(official, results)[["season", "grand_prix", "driver", "arrivee_officielle"]].dropna()
    out = results.merge(o, on=["season", "grand_prix", "driver"], how="left")
    known = out.groupby(["season", "grand_prix"])["arrivee_officielle"].transform("count") > 0
    # course connue de f1db : son ordre fait foi (un pilote absent de f1db passe en dernier)
    out.loc[known, "finish"] = out.loc[known, "arrivee_officielle"].fillna(99)
    out["finish"] = out.groupby(["season", "grand_prix"])["finish"].rank(method="first").astype(int)
    return out.drop(columns="arrivee_officielle")


def official_grids(results: pd.DataFrame, official: pd.DataFrame) -> pd.DataFrame:
    """Grille réelle de chaque course passée (season, grand_prix, driver, grille_officielle, stands, penalite)."""
    o = match(official, results)
    return o.dropna(subset=["grille_officielle"])[["season", "grand_prix", "driver", "grille_officielle", "stands", "penalite"]]
