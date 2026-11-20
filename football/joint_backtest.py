"""Backtest du modèle commun : chaque semaine, ajustement sur les seuls matchs déjà joués,
puis pronostic des matchs de la semaine (championnats recherchables et coupes d'Europe)."""
import numpy as np
import pandas as pd

try:
    from football import joint as J
    from football import model as M
except ImportError:  # lancé comme script
    import joint as J  # type: ignore
    import model as M  # type: ignore

TARGET_LEAGUES = ["E0", "D1", "SP1", "F1", "LDC", "LEC"]


def sot_ratio(m: pd.DataFrame, before: pd.Timestamp) -> float:
    d = m[(m["date"] < before) & m["hst"].notna() & m["ast"].notna()]
    return float((d["hg"].sum() + d["ag"].sum()) / max(d["hst"].sum() + d["ast"].sum(), 1))


def season_of(ts: pd.Timestamp) -> int:
    return ts.year if ts.month >= 7 else ts.year - 1


def weekly(m: pd.DataFrame, seasons: list[int], xi: float, s: float) -> pd.DataFrame:
    """Buts attendus de chaque match visé des saisons demandées."""
    rows = m[m["league"].isin(TARGET_LEAGUES) & m["date"].map(season_of).isin(seasons)].dropna(subset=["hg", "ag"])
    out = []
    ratio_cache = {}
    for _, g in rows.groupby(rows["date"].dt.to_period("W-MON")):
        cutoff = g["date"].min()
        y = season_of(cutoff)
        if y not in ratio_cache:   # rapport buts / tirs cadrés figé avant chaque saison
            ratio_cache[y] = sot_ratio(m, pd.Timestamp(y, 7, 1))
        fit = J.fit(m, cutoff, xi, s, ratio_cache[y])
        lam = [J.rates(fit, h, a, bool(n), bool(c)) for h, a, n, c in zip(g["home"], g["away"], g["neutral"], g["is_cup"])]
        out.append(g.assign(lh=[x[0] for x in lam], la=[x[1] for x in lam]))
    p = pd.concat(out, ignore_index=True)
    p["result"] = np.select([p["hg"] > p["ag"], p["hg"] == p["ag"]], [0, 1], 2)
    return p


def probs(p: pd.DataFrame, rho: float) -> np.ndarray:
    return np.array([M.outcome(M.score_matrix(a, b, rho)) for a, b in zip(p["lh"], p["la"])])


def score(pr: np.ndarray, y: np.ndarray) -> dict:
    return {"matchs": int(len(y)), "rps": float(M.rps(pr, y).mean()), "log_loss": float(M.logloss(pr, y).mean()),
            "bons_favoris": float((pr.argmax(axis=1) == y).mean())}
