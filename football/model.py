"""Modèle de match : force d'attaque et de défense de chaque équipe (Poisson pondéré dans le temps,
correction de Dixon-Coles pour les petits scores), puis mélange avec le marché quand les cotes existent.

Buts du club à domicile  ~ Poisson(exp(mu + h + att[dom] - def[ext]))
Buts du club à l'extérieur ~ Poisson(exp(mu + att[ext] - def[dom]))
- les matchs récents comptent plus : poids exp(-xi * âge en jours) ;
- la « cible » peut mêler les buts et les tirs cadrés (plus stables que les buts) : part s ;
- une équipe sans passé récent en Ligue 1 (promue) part de la force moyenne des derniers promus ;
- les cotes d'avant-match résument blessures, compositions et actualité : p ∝ p_modèle^a × p_marché^b.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10
RIDGE = 2.0          # attire les forces vers leur valeur a priori (stabilise les débuts de saison)


def _prior(train: pd.DataFrame, teams: list[str], cutoff: pd.Timestamp, params_hist: dict | None) -> np.ndarray:
    """Valeur a priori (attaque, défense) de chaque équipe : 0 si elle était en L1 la saison d'avant,
    sinon la moyenne des promus (param. appris) ou une équipe faible par défaut. Le statut de promu
    dure toute la saison : il ne disparaît pas après le premier match."""
    if "season" in train:
        start = cutoff.year if cutoff.month >= 7 else cutoff.year - 1
        recent = set(train.loc[train["season"] == start - 1, ["home", "away"]].values.ravel())
    else:
        recent = set(train.loc[train["date"] > cutoff - pd.Timedelta(days=200), ["home", "away"]].values.ravel())
    promoted = (params_hist or {}).get("promoted", (-0.25, -0.25))
    p = np.zeros(2 * len(teams))
    for i, t in enumerate(teams):
        if t not in recent:
            p[i], p[len(teams) + i] = promoted
    return p


def fit(train: pd.DataFrame, cutoff: pd.Timestamp, xi: float, s: float, sot_ratio: float,
        params_hist: dict | None = None, window_days: int = 1500) -> dict:
    """Ajuste les forces sur les matchs joués avant `cutoff` (jamais après)."""
    d = train[(train["date"] < cutoff) & (train["date"] > cutoff - pd.Timedelta(days=window_days))]
    teams = sorted(set(d["home"]) | set(d["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi, ai = d["home"].map(idx).to_numpy(), d["away"].map(idx).to_numpy()
    yh, ya = d["hg"].to_numpy(float), d["ag"].to_numpy(float)
    if s > 0:
        ok = d["hst"].notna() & d["ast"].notna()
        yh = np.where(ok, (1 - s) * yh + s * sot_ratio * d["hst"].fillna(0).to_numpy(float), yh)
        ya = np.where(ok, (1 - s) * ya + s * sot_ratio * d["ast"].fillna(0).to_numpy(float), ya)
    age = (cutoff - d["date"]).dt.days.to_numpy(float)
    w = np.exp(-xi * age)
    prior = _prior(d, teams, cutoff, params_hist)

    def nll(theta):
        att, dfn, mu, h = theta[:n], theta[n:2 * n], theta[2 * n], theta[2 * n + 1]
        lh = mu + h + att[hi] - dfn[ai]
        la = mu + att[ai] - dfn[hi]
        eh, ea = np.exp(lh), np.exp(la)
        f = -(w * (yh * lh - eh + ya * la - ea)).sum()
        r = theta[:2 * n] - prior
        f += RIDGE * (r @ r)
        gh, ga = w * (eh - yh), w * (ea - ya)
        g = np.zeros_like(theta)
        np.add.at(g, hi, gh); np.add.at(g, ai, ga)              # attaque
        np.add.at(g, n + ai, -gh); np.add.at(g, n + hi, -ga)    # défense
        g[2 * n] = gh.sum() + ga.sum()
        g[2 * n + 1] = gh.sum()
        g[:2 * n] += 2 * RIDGE * r
        return f, g

    x0 = np.concatenate([prior, [np.log(max(yh.mean(), 0.1)), 0.2]])
    res = minimize(nll, x0, jac=True, method="L-BFGS-B")
    th = res.x
    return {"teams": idx, "att": th[:n], "def": th[n:2 * n], "mu": th[2 * n], "home": th[2 * n + 1],
            "prior": params_hist}


def rates(m: dict, home: str, away: str) -> tuple[float, float]:
    """Buts attendus (domicile, extérieur). Équipe inconnue : force des promus."""
    promoted = (m.get("prior") or {}).get("promoted", (-0.25, -0.25))

    def ad(t):
        i = m["teams"].get(t)
        return (m["att"][i], m["def"][i]) if i is not None else promoted
    (ah, dh), (aa, da) = ad(home), ad(away)
    return float(np.exp(m["mu"] + m["home"] + ah - da)), float(np.exp(m["mu"] + aa - dh))


def score_matrix(lh: float, la: float, rho: float) -> np.ndarray:
    """P(score = i-j), avec la correction de Dixon-Coles sur 0-0, 1-0, 0-1 et 1-1."""
    g = np.arange(MAX_GOALS + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    m[0, 0] *= max(1 - lh * la * rho, 0)
    m[0, 1] *= max(1 + lh * rho, 0)
    m[1, 0] *= max(1 + la * rho, 0)
    m[1, 1] *= max(1 - rho, 0)
    return m / m.sum()


def outcome(mat: np.ndarray) -> np.ndarray:
    """(victoire domicile, nul, victoire extérieur)."""
    return np.array([np.tril(mat, -1).sum(), np.trace(mat), np.triu(mat, 1).sum()])


def market_probs(odds: np.ndarray) -> np.ndarray:
    """Cotes décimales (n, 3) -> probabilités implicites, marge du bookmaker retirée. NaN si absentes."""
    inv = 1.0 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def blend(p_model: np.ndarray, p_market: np.ndarray, a: float, b: float) -> np.ndarray:
    """Mélange log-linéaire : p ∝ p_modèle^a × p_marché^b (modèle seul quand il n'y a pas de cotes)."""
    has = np.isfinite(p_market).all(axis=1)
    out = p_model.copy()
    if has.any():
        z = a * np.log(np.clip(p_model[has], 1e-9, 1)) + b * np.log(np.clip(p_market[has], 1e-9, 1))
        z = np.exp(z - z.max(axis=1, keepdims=True))
        out[has] = z / z.sum(axis=1, keepdims=True)
    return out


def rps(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ranked probability score (plus bas = mieux), la mesure de référence pour 1/N/2."""
    onehot = np.eye(3)[y]
    c = np.cumsum(p, axis=1)[:, :2] - np.cumsum(onehot, axis=1)[:, :2]
    return (c ** 2).sum(axis=1) / 2


def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))
