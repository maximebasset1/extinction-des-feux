"""Coupes d'Europe passées (openfootball, domaine public CC0) : lecture du format Football.TXT."""
import re
from datetime import date
from pathlib import Path

import pandas as pd

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
DAY = re.compile(r"^\s+[A-Z][a-z]{2} ([A-Z][a-z]{2}) (\d{1,2})(?: (\d{4}))?\s*$")
GAME = re.compile(r"^\s+(?:(\d{1,2}:\d{2})\s+)?(.+?) \(([A-Z]{3})\)\s+v\s+(.+?) \(([A-Z]{3})\)\s+(.*)$")
SCORE = re.compile(r"(\d+)-(\d+)")
COMPETITIONS = {"cl": "LDC", "el": "LEC"}


def score90(rest: str) -> tuple[int, int] | None:
    """Score après 90 minutes : prolongations et tirs au but sont ignorés (le modèle prédit le temps réglementaire)."""
    rest = rest.strip()
    if not rest or not rest[0].isdigit():
        return None
    if "a.e.t." in rest:
        m = re.search(r"\((\d+)-(\d+)", rest)
        return (int(m.group(1)), int(m.group(2))) if m else None
    m = SCORE.match(rest)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse(path: Path, competition: str, season: int) -> pd.DataFrame:
    rows, day, stage = [], None, ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("▪"):
            stage = line[1:].strip()
            continue
        d = DAY.match(line)
        if d:
            # les groupes recommencent en septembre : l'année se déduit de la saison, pas de l'ordre des lignes
            mon, dd = MONTHS[d.group(1)], int(d.group(2))
            day = date(season if mon >= 7 else season + 1, mon, dd)
            continue
        g = GAME.match(line)
        if not g or day is None:
            continue
        sc = score90(g.group(6))
        rows.append({"competition": competition, "season": season, "stage": stage, "date": pd.Timestamp(day),
                     "home_of": g.group(2).strip(), "home_cc": g.group(3), "away_of": g.group(4).strip(), "away_cc": g.group(5),
                     "hg": None if sc is None else sc[0], "ag": None if sc is None else sc[1],
                     "neutral": stage.endswith("Final") and not stage.endswith("finals")})
    return pd.DataFrame(rows)


def load(root: Path) -> pd.DataFrame:
    out = []
    for d in sorted(root.glob("20??-??")):
        season = int(d.name[:4])
        for code, comp in COMPETITIONS.items():
            f = d / f"{code}.txt"
            if f.exists():
                out.append(parse(f, comp, season))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
