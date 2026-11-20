"""Modèle commun à tous les championnats et aux coupes d'Europe.

Chaque club a une force absolue (attaque, défense), attirée vers le niveau moyen de son
championnat. Les niveaux des championnats ne sont reliés entre eux que par les matchs
européens et par les clubs qui montent ou descendent : c'est ce qui permet d'estimer
Lille - Bayern alors que la Ligue 1 et la Bundesliga ne se rencontrent jamais.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

RIDGE_TEAM = 2.0            # rappel d'un club vers le niveau de son championnat
RIDGE_LEAGUE = 0.5          # rappel (faible) des niveaux de championnat vers leur valeur a priori
MINOR_LEAGUE = (-0.35, -0.35)   # championnat sans données (Kazakhstan, Chypre...) : niveau supposé modeste
NEW_TEAM = (-0.3, -0.3)     # club absent la saison d'avant (promu d'une division non couverte)
WINDOW_DAYS = 1500
BIG_LEAGUES = {"E0", "SP1", "D1", "I1", "F1"}   # les autres partent d'un niveau modeste, que les matchs européens corrigent


def _league_of(d: pd.DataFrame, teams: list[str]) -> list[str]:
    """Championnat de chaque club : celui de son dernier match de championnat, sinon un groupe « pays sans données »."""
    dom = d[~d["is_cup"]]
    last = pd.concat([dom[["date", "home", "league"]].rename(columns={"home": "t"}),
                      dom[["date", "away", "league"]].rename(columns={"away": "t"})]).sort_values("date")
    lg = last.groupby("t")["league"].last().to_dict()
    return [lg.get(t, "X" + t.split(":", 1)[0]) for t in teams]


def fit(m: pd.DataFrame, cutoff: pd.Timestamp, xi: float, s: float, sot_ratio: float) -> dict:
    """Ajuste toutes les forces sur les matchs joués avant `cutoff` (jamais après).

    `m` : colonnes date, home, away, hg, ag, hst, ast, league, is_cup, neutral."""
    d = m[(m["date"] < cutoff) & (m["date"] > cutoff - pd.Timedelta(days=WINDOW_DAYS))]
    d = d.dropna(subset=["hg", "ag"])
    teams = sorted(set(d["home"]) | set(d["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    leagues = _league_of(d, teams)
    lnames = sorted(set(leagues))
    lidx = {l: i for i, l in enumerate(lnames)}
    k = len(lnames)
    lt = np.array([lidx[l] for l in leagues])
    hi, ai = d["home"].map(idx).to_numpy(), d["away"].map(idx).to_numpy()
    yh, ya = d["hg"].to_numpy(float), d["ag"].to_numpy(float)
    if s > 0:
        ok = (d["hst"].notna() & d["ast"].notna()).to_numpy()
        yh = np.where(ok, (1 - s) * yh + s * sot_ratio * d["hst"].fillna(0).to_numpy(float), yh)
        ya = np.where(ok, (1 - s) * ya + s * sot_ratio * d["ast"].fillna(0).to_numpy(float), ya)
    home_on = (~d["neutral"].fillna(False).astype(bool)).to_numpy(float)
    cup = d["is_cup"].to_numpy(bool)
    # avantage du terrain estimé à part pour les coupes (voyages plus longs, ambiance différente)
    home_dom, home_cup = home_on * ~cup, home_on * cup
    w = np.exp(-xi * (cutoff - d["date"]).dt.days.to_numpy(float))
    # club absent de la saison précédente : un cran sous le niveau de son championnat
    start = cutoff.year if cutoff.month >= 7 else cutoff.year - 1
    prev = d[(d["date"] >= pd.Timestamp(start - 1, 7, 1)) & (d["date"] < pd.Timestamp(start, 7, 1))]
    seen = set(prev["home"]) | set(prev["away"])
    off = np.array([(0.0, 0.0) if t in seen else NEW_TEAM for t in teams])
    l0 = np.array([(0.0, 0.0) if l in BIG_LEAGUES else MINOR_LEAGUE for l in lnames])

    def unpack(th):
        return th[:n], th[n:2 * n], th[2 * n:2 * n + k], th[2 * n + k:2 * n + 2 * k], th[-3], th[-2], th[-1]

    def nll(th):
        att, dfn, A, Dl, mu, h, hc = unpack(th)
        lh = mu + h * home_dom + hc * home_cup + att[hi] - dfn[ai]
        la = mu + att[ai] - dfn[hi]
        eh, ea = np.exp(lh), np.exp(la)
        f = -(w * (yh * lh - eh + ya * la - ea)).sum()
        ra, rd = att - A[lt] - off[:, 0], dfn - Dl[lt] - off[:, 1]
        qa, qd = A - l0[:, 0], Dl - l0[:, 1]
        f += RIDGE_TEAM * (ra @ ra + rd @ rd) + RIDGE_LEAGUE * (qa @ qa + qd @ qd)
        gh, ga = w * (eh - yh), w * (ea - ya)
        g_att = np.bincount(hi, gh, n) + np.bincount(ai, ga, n) + 2 * RIDGE_TEAM * ra
        g_def = -np.bincount(ai, gh, n) - np.bincount(hi, ga, n) + 2 * RIDGE_TEAM * rd
        g_A = -2 * RIDGE_TEAM * np.bincount(lt, ra, k) + 2 * RIDGE_LEAGUE * qa
        g_D = -2 * RIDGE_TEAM * np.bincount(lt, rd, k) + 2 * RIDGE_LEAGUE * qd
        g = np.concatenate([g_att, g_def, g_A, g_D, [gh.sum() + ga.sum(), (gh * home_dom).sum(), (gh * home_cup).sum()]])
        return f, g

    th0 = np.concatenate([off[:, 0], off[:, 1], l0[:, 0], l0[:, 1], [np.log(max(yh.mean(), 0.1)), 0.2, 0.2]])
    r = minimize(nll, th0, jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    att, dfn, A, Dl, mu, h, hc = unpack(r.x)
    return {"teams": idx, "att": att, "def": dfn, "league": dict(zip(teams, leagues)),
            "league_level": {l: (float(A[i]), float(Dl[i])) for l, i in lidx.items()}, "mu": float(mu), "home": float(h), "home_cup": float(hc),
            "converged": bool(r.success)}


def rates(fit: dict, home: str, away: str, neutral: bool = False, cup: bool = False,
          league_hint: dict | None = None) -> tuple[float, float]:
    """Buts attendus. Club jamais vu : niveau de son championnat (s'il est connu) moins un cran."""
    def ad(t):
        if t in fit["teams"]:
            i = fit["teams"][t]
            return fit["att"][i], fit["def"][i]
        lg = (league_hint or {}).get(t, "X" + t.split(":", 1)[0])
        A, Dl = fit["league_level"].get(lg, MINOR_LEAGUE)
        return A + NEW_TEAM[0], Dl + NEW_TEAM[1]
    ah, dh = ad(home)
    aa, da = ad(away)
    h = 0.0 if neutral else fit["home_cup"] if cup else fit["home"]
    return float(np.exp(fit["mu"] + h + ah - da)), float(np.exp(fit["mu"] + aa - dh))
