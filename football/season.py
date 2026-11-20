"""Classements, fins de saison simulées et petits outils de pronostic communs à toutes les compétitions."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.optimize import minimize

try:
    from football import model as M
except ImportError:  # lancé comme script
    import model as M  # type: ignore

PARIS = ZoneInfo("Europe/Paris")
LONDON = ZoneInfo("Europe/London")   # heures de football-data.co.uk
N_SIM = 10000


def round_probs(p) -> list[float]:
    """Probabilités 1/N/2 au pour cent près, qui somment toujours à 1."""
    q = np.round(np.asarray(p, float) * 100)
    q[int(np.argmax(q))] += 100 - q.sum()
    return [round(float(x) / 100, 2) for x in q]


def calibrate_rates(lh: float, la: float, target: np.ndarray, rho: float) -> tuple[float, float]:
    """Ajuste les buts attendus pour que le score probable colle aux probabilités 1/N/2 retenues
    (celles du mélange avec le marché), en restant proche du modèle."""
    def loss(x):
        p = M.outcome(M.score_matrix(np.exp(x[0]), np.exp(x[1]), rho))
        return ((p - target) ** 2).sum() + 1e-3 * ((x[0] - np.log(lh)) ** 2 + (x[1] - np.log(la)) ** 2)
    r = minimize(loss, np.log([lh, la]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 400})
    return float(np.exp(r.x[0])), float(np.exp(r.x[1]))


def kickoff_utc(date: pd.Timestamp, time: str | None, tz: ZoneInfo = PARIS) -> str | None:
    """Heure locale -> ISO UTC. Sans heure connue : None (la page affiche alors seulement la date)."""
    if pd.isna(date) or not time or str(time) == "nan":
        return None
    hh, mm = (str(time).split(":") + ["0"])[:2]
    local = datetime(date.year, date.month, date.day, int(hh), int(mm), tzinfo=tz)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def paris_day(iso: str) -> str:
    """Jour du match à l'heure de Paris : un match à 0 h 30 ne tombe pas la veille."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PARIS).strftime("%Y-%m-%d")


def table(played: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    """Classement : points, différence de buts, buts marqués."""
    t = pd.DataFrame(0, index=teams, columns=["j", "g", "n", "p", "bp", "bc", "pts"])
    for r in played.itertuples():
        for team, gf, ga in ((r.home, r.hg, r.ag), (r.away, r.ag, r.hg)):
            if team not in t.index:
                continue
            t.loc[team, ["j", "bp", "bc"]] += [1, gf, ga]
            k = "g" if gf > ga else "n" if gf == ga else "p"
            t.loc[team, k] += 1
            t.loc[team, "pts"] += 3 if gf > ga else 1 if gf == ga else 0
    t["diff"] = t["bp"] - t["bc"]
    return t.sort_values(["pts", "diff", "bp"], ascending=False)


def simulate_places(played: pd.DataFrame, upcoming: pd.DataFrame, teams: list[str], rho: float = 0.0,
                    seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Fin de saison tirée 10 000 fois : chaque match restant est tiré dans la même grille de scores que le
    pronostic affiché (correction des nuls comprise). Renvoie les points moyens et la probabilité de chaque place
    (une ligne par club de `teams`, une colonne par place)."""
    rng = np.random.default_rng(seed)
    idx = {t: i for i, t in enumerate(teams)}
    base = table(played, teams).reindex(teams)
    pts = np.tile(base["pts"].to_numpy(float), (N_SIM, 1))
    gd = np.tile(base["diff"].to_numpy(float), (N_SIM, 1))
    gf = np.tile(base["bp"].to_numpy(float), (N_SIM, 1))
    for r in upcoming.itertuples():
        if r.home not in idx or r.away not in idx:
            continue
        h, a = idx[r.home], idx[r.away]
        mat = M.score_matrix(r.lam_h, r.lam_a, rho)
        k = rng.choice(mat.size, N_SIM, p=mat.ravel() / mat.sum())
        x, y = k // mat.shape[1], k % mat.shape[1]
        pts[:, h] += np.where(x > y, 3, np.where(x == y, 1, 0))
        pts[:, a] += np.where(y > x, 3, np.where(x == y, 1, 0))
        gd[:, h] += x - y
        gd[:, a] += y - x
        gf[:, h] += x
        gf[:, a] += y
    key = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random(pts.shape) * 1e-3
    rank = (-key).argsort(axis=1).argsort(axis=1)          # 0 = premier
    n = len(teams)
    places = np.stack([(rank == k).mean(axis=0) for k in range(n)], axis=1)
    return pts.mean(axis=0), places
