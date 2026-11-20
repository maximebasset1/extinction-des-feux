"""Téléchargement et lecture des fichiers de football-data.co.uk (résultats, tirs, cotes)."""
import io
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

try:
    from football import config as C
except ImportError:  # lancé comme script
    import config as C  # type: ignore


def season_code(y: int) -> str:
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def _get(url: str, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def _dates(s: pd.Series) -> pd.Series:
    """Dates football-data : jj/mm/aa (anciennes saisons) ou jj/mm/aaaa."""
    s = s.astype(str).str.strip()
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    return d.fillna(pd.to_datetime(s, format="%d/%m/%y", errors="coerce"))


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _odds(df: pd.DataFrame, prefixes: tuple[str, ...]) -> np.ndarray:
    """Première série de cotes 1/N/2 disponible (moyenne du marché d'abord), ligne par ligne."""
    out = np.full((len(df), 3), np.nan)
    for p in prefixes:
        cols = [f"{p}H", f"{p}D", f"{p}A"]
        if not all(c in df for c in cols):
            continue
        v = df[cols].apply(_num).to_numpy(float, copy=True)
        v[(v <= 1).any(axis=1)] = np.nan
        miss = np.isnan(out).any(axis=1)
        out[miss] = v[miss]
    return out


PRE_MATCH = ("Avg", "BbAv", "B365", "PS", "WH", "IW", "BW", "VC", "LB")   # cotes publiées avant le match


def _read_fd(path, season: int) -> pd.DataFrame:
    raw = path.read_bytes().decode("latin-1").lstrip("﻿").replace("ï»¿", "")
    df = pd.read_csv(io.StringIO(raw), on_bad_lines="skip")
    df = df[df["HomeTeam"].notna() & df["AwayTeam"].notna()]
    out = pd.DataFrame({
        "season": season,
        "date": _dates(df["Date"]),
        "time": df.get("Time"),
        "home": df["HomeTeam"].str.strip(), "away": df["AwayTeam"].str.strip(),
        "hg": _num(df.get("FTHG")), "ag": _num(df.get("FTAG")),
        "hst": _num(df["HST"]) if "HST" in df else np.nan, "ast": _num(df["AST"]) if "AST" in df else np.nan,
        "hs": _num(df["HS"]) if "HS" in df else np.nan, "as_": _num(df["AS"]) if "AS" in df else np.nan,
        "hxg": _num(df["HxG"]) if "HxG" in df else np.nan, "axg": _num(df["AxG"]) if "AxG" in df else np.nan,
    })
    o = _odds(df, PRE_MATCH)
    out["oh"], out["od"], out["oa"] = o[:, 0], o[:, 1], o[:, 2]
    return out.dropna(subset=["date"])
