"""Championnats européens de football-data.co.uk, réunis dans une seule table.

Chaque club est identifié par « pays:nom football-data » (deux clubs de pays différents
peuvent porter le même nom court)."""
import io
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from football import data as D
except ImportError:  # lancé comme script
    import data as D  # type: ignore

# code football-data -> (pays au format openfootball, nom affiché, compétition recherchable)
MAIN = {"E0": ("ENG", "Premier League", True), "E1": ("ENG", "Championship", False),
        "D1": ("GER", "Bundesliga", True), "SP1": ("ESP", "Liga", True), "I1": ("ITA", "Serie A", True),
        "F1": ("FRA", "Ligue 1", True), "N1": ("NED", "Eredivisie", False), "P1": ("POR", "Liga Portugal", False),
        "B1": ("BEL", "Pro League", False), "SC0": ("SCO", "Premiership", False), "T1": ("TUR", "Süper Lig", False),
        "G1": ("GRE", "Super League", False)}
# fichiers « new » : une seule table toutes saisons, cotes de clôture seulement (non utilisées)
NEW = {"AUT": "AUT", "DNK": "DEN", "SWZ": "SUI", "NOR": "NOR", "SWE": "SWE", "POL": "POL",
       "ROU": "ROU", "RUS": "RUS", "IRL": "IRL", "FIN": "FIN"}


def team_id(country: str, name: str) -> str:
    return f"{country}:{name}"


def _read_main(path: Path, code: str, season: int) -> pd.DataFrame:
    d = D._read_fd(path, season)
    cc = MAIN[code][0]
    d["league"], d["country"] = code, cc
    d["home"], d["away"] = cc + ":" + d["home"], cc + ":" + d["away"]
    return d


def _read_new(path: Path, code: str) -> pd.DataFrame:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(raw), on_bad_lines="skip")
    cc = NEW[code]
    start = pd.to_numeric(df["Season"].astype(str).str[:4], errors="coerce")
    date = D._dates(df["Date"])
    # championnats sur l'année civile (Norvège, Suède...) : la saison est l'année du match
    season = np.where(df["Season"].astype(str).str.contains("/"), start, date.dt.year)
    return pd.DataFrame({"season": season, "date": date, "time": df.get("Time"),
                         "home": cc + ":" + df["Home"].astype(str).str.strip(), "away": cc + ":" + df["Away"].astype(str).str.strip(),
                         "hg": D._num(df["HG"]), "ag": D._num(df["AG"]), "hst": np.nan, "ast": np.nan,
                         "oh": np.nan, "od": np.nan, "oa": np.nan, "league": code, "country": cc}).dropna(subset=["date"])


def load(raw: Path, first: int, last: int) -> pd.DataFrame:
    parts = []
    for code in MAIN:
        for y in range(first, last + 1):
            f = raw / f"{code}_{y}.csv"
            if f.exists() and f.stat().st_size:
                parts.append(_read_main(f, code, y))
    for code in NEW:
        f = raw / f"new_{code}.csv"
        if f.exists() and f.stat().st_size:
            parts.append(_read_new(f, code))
    m = pd.concat(parts, ignore_index=True)
    m = m[(m["season"] >= first) & (m["season"] <= last)]
    keep = ["league", "country", "season", "date", "time", "home", "away", "hg", "ag", "hst", "ast", "oh", "od", "oa"]
    return m[keep].sort_values("date").reset_index(drop=True)
