"""Téléchargement et mise en forme des matchs de Ligue 1.

- football-data.co.uk : résultats depuis 2000-01, tirs, cotes, xG (2026-27) ; matchs à venir avec cotes ;
- copie GitHub de football-data : saisons 1993-94 à 1999-2000, pour les face-à-face ;
- openfootball : calendrier complet de la saison en cours (journées, dates, heures).
"""
import io
import json
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


def download(refresh_current: bool = True) -> None:
    """Télécharge ce qui manque ; la saison en cours et les matchs à venir sont toujours repris."""
    C.RAW.mkdir(parents=True, exist_ok=True)
    for y in range(C.FIRST_ODDS_SEASON, C.CURRENT_SEASON + 1):
        f = C.RAW / f"F1_{season_code(y)}.csv"
        if f.exists() and f.stat().st_size and not (refresh_current and y == C.CURRENT_SEASON):
            continue
        f.write_bytes(_get(C.FD_URL.format(code=season_code(y))))
        time.sleep(1)
    for y in range(C.FIRST_MIRROR_SEASON, C.FIRST_ODDS_SEASON):
        f = C.RAW / f"mirror_{season_code(y)}.csv"
        if not (f.exists() and f.stat().st_size):
            f.write_bytes(_get(C.MIRROR_URL.format(code=season_code(y))))
    if refresh_current:
        (C.RAW / "fixtures.csv").write_bytes(_get(C.FD_FIXTURES))
        name = f"{C.CURRENT_SEASON}-{(C.CURRENT_SEASON + 1) % 100:02d}"
        (C.RAW / f"openfootball_{name}.json").write_bytes(_get(C.OPENFOOTBALL_URL.format(season=name)))


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


def load_matches() -> pd.DataFrame:
    """Tous les matchs joués, du plus ancien au plus récent."""
    parts = []
    for y in range(C.FIRST_MIRROR_SEASON, C.FIRST_ODDS_SEASON):
        f = C.RAW / f"mirror_{season_code(y)}.csv"
        if f.exists():
            d = pd.read_csv(f)
            parts.append(pd.DataFrame({"season": y, "date": pd.to_datetime(d["Date"], errors="coerce"),
                                       "home": d["HomeTeam"].str.strip(), "away": d["AwayTeam"].str.strip(),
                                       "hg": _num(d["FTHG"]), "ag": _num(d["FTAG"])}))
    for y in range(C.FIRST_ODDS_SEASON, C.CURRENT_SEASON + 1):
        f = C.RAW / f"F1_{season_code(y)}.csv"
        if f.exists():
            parts.append(_read_fd(f, y))
    m = pd.concat(parts, ignore_index=True)
    m = m.dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)
    m["result"] = np.select([m["hg"] > m["ag"], m["hg"] == m["ag"]], [0, 1], 2)
    return m


def load_fixtures() -> pd.DataFrame:
    """Calendrier de la saison en cours (openfootball) + cotes des matchs à venir (football-data)."""
    name = f"{C.CURRENT_SEASON}-{(C.CURRENT_SEASON + 1) % 100:02d}"
    js = json.loads((C.RAW / f"openfootball_{name}.json").read_text(encoding="utf-8"))
    rows = []
    for x in js["matches"]:
        rows.append({"round": int(str(x.get("round", "0")).split()[-1]), "date": pd.to_datetime(x["date"]),
                     "time": x.get("time"), "home": C.OPENFOOTBALL_NAMES.get(x["team1"], x["team1"]),
                     "away": C.OPENFOOTBALL_NAMES.get(x["team2"], x["team2"])})
    fx = pd.DataFrame(rows)
    up = C.RAW / "fixtures.csv"
    if up.exists() and up.stat().st_size:
        u = pd.read_csv(io.StringIO(up.read_bytes().decode("latin-1").lstrip("﻿").replace("ï»¿", "")), on_bad_lines="skip")
        u = u[u.get("Div") == "F1"] if "Div" in u else u.iloc[0:0]
        if len(u):
            o = _odds(u, PRE_MATCH)
            u = pd.DataFrame({"home": u["HomeTeam"].str.strip(), "away": u["AwayTeam"].str.strip(),
                              "oh": o[:, 0], "od": o[:, 1], "oa": o[:, 2],
                              "fd_date": _dates(u["Date"]), "fd_time": u.get("Time")})
            fx = fx.merge(u, on=["home", "away"], how="left")
    for c in ("oh", "od", "oa"):
        if c not in fx:
            fx[c] = np.nan
    return fx
