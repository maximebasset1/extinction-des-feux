"""Outils de match communs : grille des scores (Poisson, correction de Dixon-Coles pour les petits scores),
probabilités 1/N/2, cotes sans marge, mélange avec le marché et scores de fiabilité.

Les forces des équipes viennent de joint.py (modèle commun à tous les championnats et coupes).
Les cotes d'avant-match résument blessures, compositions et actualité : p ∝ p_modèle^a × p_marché^b.
"""
import numpy as np
from scipy.stats import poisson

MAX_GOALS = 10


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
