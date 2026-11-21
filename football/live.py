"""Chances en direct : ce qui reste à jouer, selon le temps restant et le score du moment.

Chaque équipe marque à un rythme proportionnel à ses buts attendus, réparti entre les deux mi-temps,
et modulé par l'écart au score : une équipe menée pousse, une équipe qui mène gère.
Le calcul avance par pas de quelques minutes sur la grille des buts encore à marquer ; seul l'écart
au score change le rythme, ce qui garde le calcul exact et rapide (même calcul en JavaScript sur le site).

Les buts attendus d'un match sont réglés pour retrouver, au coup d'envoi, les chances publiées avant
le match : le direct part toujours du pronostic affiché.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

PARAMS_FILE = Path(__file__).with_name("live_params.json")
# durées moyennes des mi-temps, arrêts de jeu compris (en minutes) : servent à convertir la minute affichée
HALF_MINUTES = (48.0, 52.0)
STEPS_PER_HALF = 10
MAX_ADDED = 10        # buts encore possibles par équipe pris en compte (au-delà : regroupés dans le dernier)
STATES = (-2, -1, 0, 1, 2)   # écart au score vu par l'équipe : mené de 2 ou plus, ..., mène de 2 ou plus

DEFAULT = {"part_1re_mi_temps": 0.44, "rythme_selon_ecart": [1.0, 1.0, 1.0, 1.0, 1.0]}


def load_params(path: Path = PARAMS_FILE) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(DEFAULT)


def _state_mult(params: dict, diff: np.ndarray) -> np.ndarray:
    m = np.asarray(params["rythme_selon_ecart"], float)
    return m[np.clip(diff, STATES[0], STATES[-1]) - STATES[0]]


def _pois3(mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P(0), P(1), P(2 ou plus) buts pendant un pas."""
    p0 = np.exp(-mu)
    p1 = mu * p0
    return p0, p1, np.clip(1 - p0 - p1, 0, None)


def _run(dist: np.ndarray, lh: np.ndarray, la: np.ndarray, d0: np.ndarray, rate: float, minutes: np.ndarray,
         params: dict, steps: int) -> np.ndarray:
    """Fait avancer `dist` (n, K, K : buts ajoutés domicile × extérieur) de `minutes` à un rythme par minute `rate`."""
    n, k, _ = dist.shape
    i = np.arange(k)
    diff = d0[:, None, None] + i[None, :, None] - i[None, None, :]
    mh = _state_mult(params, diff) * (lh * rate)[:, None, None]
    ma = _state_mult(params, -diff) * (la * rate)[:, None, None]
    dt = (minutes / steps)[:, None, None]
    ph, pa = _pois3(mh * dt), _pois3(ma * dt)
    for _ in range(steps):
        out = np.zeros((n, k + 2, k + 2))
        for a in range(3):
            for b in range(3):
                out[:, a:a + k, b:b + k] += dist * ph[a] * pa[b]
        out[:, k - 1, :] += out[:, k:, :].sum(axis=1)
        out[:, :, k - 1] += out[:, :, k:].sum(axis=2)
        dist = out[:, :k, :k]
    return dist


def remaining(lh, la, hg, ag, half: int, frac_left: float | np.ndarray, params: dict,
              k: int = MAX_ADDED + 1) -> np.ndarray:
    """Loi des buts encore à marquer (n, k, k) depuis le score hg-ag, dans la mi-temps `half` (1 ou 2,
    0 = avant le coup d'envoi, 3 = terminé), avec `frac_left` de cette mi-temps restant à jouer."""
    lh, la = np.atleast_1d(np.asarray(lh, float)), np.atleast_1d(np.asarray(la, float))
    n = len(lh)
    d0 = np.broadcast_to(np.asarray(hg, int) - np.asarray(ag, int), (n,)).copy()
    frac = np.broadcast_to(np.asarray(frac_left, float), (n,))
    dist = np.zeros((n, k, k))
    dist[:, 0, 0] = 1.0
    if half >= 3:
        return dist
    s1 = params["part_1re_mi_temps"]
    rates = (s1 / HALF_MINUTES[0], (1 - s1) / HALF_MINUTES[1])
    if half <= 1:
        f1 = np.ones(n) if half == 0 else frac
        dist = _run(dist, lh, la, d0, rates[0], f1 * HALF_MINUTES[0], params, STEPS_PER_HALF)
        # la case (buts ajoutés) donne l'écart au score : la seconde mi-temps continue sur la même grille
        return _run(dist, lh, la, d0, rates[1], np.full(n, HALF_MINUTES[1]), params, STEPS_PER_HALF)
    return _run(dist, lh, la, d0, rates[1], frac * HALF_MINUTES[1], params, STEPS_PER_HALF)


def outcome_from(dist: np.ndarray, hg, ag) -> np.ndarray:
    """(victoire domicile, nul, victoire extérieur) en fin de match."""
    n, k, _ = dist.shape
    i = np.arange(k)
    d = (np.asarray(hg) - np.asarray(ag)).reshape(-1, 1, 1) + i[None, :, None] - i[None, None, :]
    return np.stack([(dist * (d > 0)).sum((1, 2)), (dist * (d == 0)).sum((1, 2)), (dist * (d < 0)).sum((1, 2))], axis=1)


def kickoff_outcome(lh, la, params: dict) -> np.ndarray:
    lh = np.atleast_1d(np.asarray(lh, float))
    return outcome_from(remaining(lh, la, np.zeros(len(lh), int), np.zeros(len(lh), int), 0, 1.0, params), 0, 0)


def calibrate(p: np.ndarray, params: dict, iters: int = 12, start: np.ndarray | None = None) -> np.ndarray:
    """Buts attendus (n, 2) qui redonnent, au coup d'envoi, les chances 1/N/2 `p` (n, 3)."""
    p = np.atleast_2d(np.asarray(p, float))
    p = p / p.sum(axis=1, keepdims=True)
    # départ : rapport des chances de victoire, total de buts habituel (ou la solution d'un calcul voisin)
    x = (np.log(start) if start is not None else
         np.column_stack([np.log(1.35) + 0.6 * np.log(p[:, 0] / p[:, 2]) / 2, np.log(1.35) - 0.6 * np.log(p[:, 0] / p[:, 2]) / 2]))
    target = np.column_stack([p[:, 0], p[:, 2]])
    eps = 1e-4
    for _ in range(iters):
        f = kickoff_outcome(np.exp(x[:, 0]), np.exp(x[:, 1]), params)[:, [0, 2]] - target
        jac = np.empty((len(p), 2, 2))
        for c in range(2):
            xe = x.copy()
            xe[:, c] += eps
            jac[:, :, c] = (kickoff_outcome(np.exp(xe[:, 0]), np.exp(xe[:, 1]), params)[:, [0, 2]] - target - f) / eps
        det = jac[:, 0, 0] * jac[:, 1, 1] - jac[:, 0, 1] * jac[:, 1, 0]
        det = np.where(np.abs(det) < 1e-12, 1e-12, det)
        dx0 = (jac[:, 1, 1] * f[:, 0] - jac[:, 0, 1] * f[:, 1]) / det
        dx1 = (-jac[:, 1, 0] * f[:, 0] + jac[:, 0, 0] * f[:, 1]) / det
        x[:, 0] -= np.clip(dx0, -1, 1)
        x[:, 1] -= np.clip(dx1, -1, 1)
        x = np.clip(x, math.log(0.05), math.log(6))
        if np.abs(f).max() < 1e-6:
            break
    return np.exp(x)
