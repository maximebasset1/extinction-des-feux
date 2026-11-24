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

# Forme à court terme (double horizon, validée sur 2021 choix -> 2022-2026 test)
XI_SHORT = 0.0173           # demi-vie ~40 jours (6 à 8 derniers matchs)
FORM_WEIGHT = 0.15          # part de l'ajustement court terme sur les résidus
RIDGE_FORM = 12.0           # rappel fort vers le niveau intrinsèque pour éviter de sur-réagir


def rest_days(m: pd.DataFrame) -> pd.DataFrame:
    """Calcule `repos_dom` et `repos_ext` (jours depuis le dernier match strictement antérieur, plafonné à 14)."""
    m = m.sort_values("date").reset_index(drop=True)
    last_date: dict[str, pd.Timestamp] = {}
    rh = np.full(len(m), 14.0)
    ra = np.full(len(m), 14.0)
    for dt, grp in m.groupby("date", sort=True):
        idxs = grp.index.to_numpy()
        homes, aways = grp["home"].to_numpy(), grp["away"].to_numpy()
        for idx_i, h, a in zip(idxs, homes, aways):
            if h in last_date:
                rh[idx_i] = min(14.0, float((dt - last_date[h]).days))
            if a in last_date:
                ra[idx_i] = min(14.0, float((dt - last_date[a]).days))
        for h, a in zip(homes, aways):
            last_date[h] = dt
            last_date[a] = dt
    return m.assign(repos_dom=rh, repos_ext=ra)


def last_match_info(m: pd.DataFrame, cutoff: pd.Timestamp) -> dict[str, tuple[pd.Timestamp, str]]:
    """Date et compétition du dernier match joué par chaque club strictement avant `cutoff`."""
    d = m[m["date"] < cutoff].dropna(subset=["hg", "ag"])
    if not len(d):
        return {}
    both = pd.concat([
        d[["date", "home", "league"]].rename(columns={"home": "t"}),
        d[["date", "away", "league"]].rename(columns={"away": "t"}),
    ]).sort_values("date")
    last = both.groupby("t").last()
    return {t: (r.date, str(r.league)) for t, r in last.iterrows()}


def _league_of(d: pd.DataFrame, teams: list[str]) -> list[str]:
    """Championnat de chaque club : celui de son dernier match de championnat, sinon un groupe « pays sans données »."""
    dom = d[~d["is_cup"]]
    last = pd.concat([dom[["date", "home", "league"]].rename(columns={"home": "t"}),
                      dom[["date", "away", "league"]].rename(columns={"away": "t"})]).sort_values("date")
    lg = last.groupby("t")["league"].last().to_dict()
    return [lg.get(t, "X" + t.split(":", 1)[0]) for t in teams]


def fit(m: pd.DataFrame, cutoff: pd.Timestamp, xi: float, s: float, sot_ratio: float,
        form_weight: float = FORM_WEIGHT, xi_short: float = XI_SHORT, ridge_form: float = RIDGE_FORM,
        prev_fit: dict | None = None) -> dict:
    """Ajuste toutes les forces sur les matchs joués avant `cutoff` (jamais après).

    Double horizon temporel :
    - niveau intrinsèque (décroissance exponentielle `xi`, demi-vie ~347 j) ;
    - composante de forme à court terme (`xi_short`, demi-vie ~40 j) estimée sur les résidus
      du modèle long terme avec fort rappel Ridge (`ridge_form`).

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
    days = (cutoff - d["date"]).dt.days.to_numpy(float)
    w = np.exp(-xi * days)
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

    att0, def0 = off[:, 0].copy(), off[:, 1].copy()
    A0, D0 = l0[:, 0].copy(), l0[:, 1].copy()
    mu0, h0, hc0 = np.log(max(yh.mean(), 0.1)), 0.2, 0.2
    if prev_fit is not None:
        pt = prev_fit["teams"]
        pb_att = prev_fit.get("att_base", prev_fit["att"])
        pb_def = prev_fit.get("def_base", prev_fit["def"])
        for t, i in idx.items():
            if t in pt:
                j = pt[t]
                att0[i], def0[i] = pb_att[j], pb_def[j]
        for l, i in lidx.items():
            if l in prev_fit["league_level"]:
                A0[i], D0[i] = prev_fit["league_level"][l]
        mu0, h0, hc0 = prev_fit["mu"], prev_fit["home"], prev_fit["home_cup"]

    th0 = np.concatenate([att0, def0, A0, D0, [mu0, h0, hc0]])
    r = minimize(nll, th0, jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    att, dfn, A, Dl, mu, h, hc = unpack(r.x)

    form_att = np.zeros(n)
    form_def = np.zeros(n)
    if form_weight > 0.0 and n > 0:
        eh0 = np.exp(mu + h * home_dom + hc * home_cup + att[hi] - dfn[ai])
        ea0 = np.exp(mu + att[ai] - dfn[hi])
        ws = np.exp(-xi_short * days)
        num_a = np.bincount(hi, ws * (yh - eh0), n) + np.bincount(ai, ws * (ya - ea0), n)
        den_a = np.bincount(hi, ws * eh0, n) + np.bincount(ai, ws * ea0, n) + ridge_form
        num_d = np.bincount(ai, ws * (eh0 - yh), n) + np.bincount(hi, ws * (ea0 - ya), n)
        den_d = np.bincount(ai, ws * eh0, n) + np.bincount(hi, ws * ea0, n) + ridge_form
        form_att = form_weight * (num_a / den_a)
        form_def = form_weight * (num_d / den_d)

    return {"teams": idx, "att_base": att, "def_base": dfn, "form_att": form_att, "form_def": form_def,
            "att": att + form_att, "def": dfn + form_def, "league": dict(zip(teams, leagues)),
            "league_level": {l: (float(A[i]), float(Dl[i])) for l, i in lidx.items()},
            "mu": float(mu), "home": float(h), "home_cup": float(hc), "converged": bool(r.success)}


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
