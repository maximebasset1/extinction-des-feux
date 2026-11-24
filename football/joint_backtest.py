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

TARGET_LEAGUES = ["E0", "D1", "SP1", "I1", "F1", "LDC", "LEC"]
VOL_WINDOW = 25          # derniers matchs utilisés pour la volatilité historique d'un club
VOL_MIN_MATCHES = 10
VOL_DEFAULT_THRESH = 1.237   # 80e percentile calibré sur 2021-22
CONF_HIGH_PROB = 0.55


def sot_ratio(m: pd.DataFrame, before: pd.Timestamp) -> float:
    d = m[(m["date"] < before) & m["hst"].notna() & m["ast"].notna()]
    return float((d["hg"].sum() + d["ag"].sum()) / max(d["hst"].sum() + d["ast"].sum(), 1))


def season_of(ts: pd.Timestamp) -> int:
    return ts.year if ts.month >= 7 else ts.year - 1


def weekly(m: pd.DataFrame, seasons: list[int], xi: float, s: float,
           form_weight: float = J.FORM_WEIGHT) -> pd.DataFrame:
    """Buts attendus de chaque match visé des saisons demandées."""
    rows = m[m["league"].isin(TARGET_LEAGUES) & m["date"].map(season_of).isin(seasons)].dropna(subset=["hg", "ag"])
    if not len(rows):   # début de saison, aucun match joué : rien à rejouer
        return rows.assign(lh=pd.Series(dtype=float), la=pd.Series(dtype=float), result=pd.Series(dtype=int))
    out = []
    ratio_cache = {}
    prev_fit = None
    for _, g in rows.groupby(rows["date"].dt.to_period("W-MON")):
        cutoff = g["date"].min()
        y = season_of(cutoff)
        if y not in ratio_cache:   # rapport buts / tirs cadrés figé avant chaque saison
            ratio_cache[y] = sot_ratio(m, pd.Timestamp(y, 7, 1))
        fit = J.fit(m, cutoff, xi, s, ratio_cache[y], form_weight=form_weight, prev_fit=prev_fit)
        prev_fit = fit
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


def confidence_label(p: np.ndarray | list[float], vol_h: float | None, vol_a: float | None,
                     vol_thresh: float = VOL_DEFAULT_THRESH, new_coach: bool = False) -> str:
    """Classe de confiance d'un pronostic : `elevee`, `indecis` ou `imprevisible`."""
    vols = [v for v in (vol_h, vol_a) if v is not None and np.isfinite(v)]
    vol = float(np.mean(vols)) if vols else None
    mp = float(np.max(p))
    if (vol is not None and vol >= vol_thresh) or (new_coach and mp < 0.65):
        return "imprevisible"
    return "elevee" if mp >= CONF_HIGH_PROB else "indecis"


def club_volatility(p: pd.DataFrame, pm: np.ndarray, choice_seasons: list[int], test_seasons: list[int],
                    window: int = VOL_WINDOW, min_matches: int = VOL_MIN_MATCHES) -> tuple[dict[str, float], float, list[dict]]:
    """Écart-type historique (sans fuite du futur) entre points réels et points attendus par club.

    Renvoie :
    - `vol_current` : volatilité actuelle par club (utilisée pour les matchs à venir) ;
    - `thresh` : seuil du 80e percentile calibré sur `choice_seasons` ;
    - `validation` : performance empirique des 3 classes de confiance sur `test_seasons`.
    """
    if not len(p):
        return {}, VOL_DEFAULT_THRESH, []
    res = p["result"].to_numpy()
    pts_h_real = np.where(res == 0, 3.0, np.where(res == 1, 1.0, 0.0))
    pts_a_real = np.where(res == 2, 3.0, np.where(res == 1, 1.0, 0.0))
    res_h = pts_h_real - (3.0 * pm[:, 0] + pm[:, 1])
    res_a = pts_a_real - (3.0 * pm[:, 2] + pm[:, 1])

    hist: dict[str, list[float]] = {}
    match_vol = np.full(len(p), np.nan)
    for i, (h, a, rh, ra) in enumerate(zip(p["home"], p["away"], res_h, res_a)):
        vh = float(np.std(hist[h][-window:])) if len(hist.get(h, [])) >= min_matches else np.nan
        va = float(np.std(hist[a][-window:])) if len(hist.get(a, [])) >= min_matches else np.nan
        if np.isfinite(vh) and np.isfinite(va):
            match_vol[i] = 0.5 * (vh + va)
        elif np.isfinite(vh) or np.isfinite(va):
            match_vol[i] = vh if np.isfinite(vh) else va
        hist.setdefault(h, []).append(float(rh))
        hist.setdefault(a, []).append(float(ra))

    vol_current = {t: round(float(np.std(vals[-window:])), 4) for t, vals in hist.items() if len(vals) >= min_matches}
    seasons = p["season"] if "season" in p else p["date"].map(season_of)
    ch_vals = match_vol[seasons.isin(choice_seasons).to_numpy()]
    ch_vals = ch_vals[np.isfinite(ch_vals)]
    thresh = float(np.percentile(ch_vals, 80)) if len(ch_vals) >= 20 else VOL_DEFAULT_THRESH

    te = seasons.isin(test_seasons).to_numpy()
    rps_all = M.rps(pm, res)
    max_p = pm.max(axis=1)
    labels = np.where(match_vol >= thresh, "imprevisible", np.where(max_p >= CONF_HIGH_PROB, "elevee", "indecis"))
    names = [("elevee", "Confiance élevée"), ("indecis", "Match indécis"), ("imprevisible", "Équipe imprévisible")]
    validation = []
    for key, nom in names:
        m_i = te & (labels == key)
        if m_i.any():
            validation.append({"cle": key, "nom": nom, "matchs": int(m_i.sum()),
                               "rps": round(float(rps_all[m_i].mean()), 4),
                               "favori_juste": round(float((pm[m_i].argmax(axis=1) == res[m_i]).mean()), 4)})
    return vol_current, round(thresh, 4), validation
