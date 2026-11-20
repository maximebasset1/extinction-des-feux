"""Backtest « comme en vrai » : chaque semaine, le modèle est réajusté avec les seuls matchs
joués AVANT, puis il prédit les matchs de la semaine.

Protocole :
- CHOIX des réglages (mémoire xi, part des tirs cadrés s, correction rho, poids du marché) sur 2015-16 à 2019-20 ;
- TEST sur 2021-22 à aujourd'hui, jamais utilisé pour choisir ;
- comparaison au hasard, à la fréquence des résultats domicile/nul/extérieur, et au marché seul.
"""
import itertools

import numpy as np
import pandas as pd

try:
    from football import config as C
    from football import model as M
except ImportError:
    import config as C  # type: ignore
    import model as M  # type: ignore

XI_GRID = [0.003, 0.004, 0.005]          # mémoire : demi-vie d'environ 230, 175 et 140 jours
SOT_GRID = [0.0, 0.4, 0.6, 0.8]          # part des tirs cadrés dans la cible
RHO_GRID = np.round(np.arange(-0.20, 0.01, 0.02), 2)
A_GRID = np.round(np.arange(C.MIN_MODEL_WEIGHT, 1.21, 0.1), 2)   # poids du modèle dans le mélange
B_GRID = np.round(np.arange(0.0, 1.21, 0.1), 2)   # poids du marché


def sot_ratio(m: pd.DataFrame, before: pd.Timestamp) -> float:
    d = m[(m["date"] < before) & m["hst"].notna()]
    return float((d["hg"].sum() + d["ag"].sum()) / max(d["hst"].sum() + d["ast"].sum(), 1))


def promoted_prior(m: pd.DataFrame, seasons: list[int], xi: float) -> tuple[float, float]:
    """Force moyenne (attaque, défense) des promus en fin de première saison, sur des saisons
    antérieures aux périodes de choix et de test."""
    vals = []
    for y in seasons:
        prev = set(m.loc[m["season"] == y - 1, "home"])
        cur = m[m["season"] == y]
        new = set(cur["home"]) - prev
        end = cur["date"].max() + pd.Timedelta(days=1)
        fit = M.fit(m, end, xi, 0.0, 0.0, None, window_days=330)
        vals += [(fit["att"][fit["teams"][t]], fit["def"][fit["teams"][t]]) for t in new if t in fit["teams"]]
    v = np.array(vals)
    return (float(v[:, 0].mean()), float(v[:, 1].mean())) if len(v) else (-0.25, -0.25)


def weekly_predictions(m: pd.DataFrame, seasons: list[int], xi: float, s: float, prior: dict) -> pd.DataFrame:
    """Buts attendus de chaque match des saisons demandées, modèle réajusté chaque semaine."""
    out = []
    for y in seasons:
        cur = m[m["season"] == y]
        ratio = sot_ratio(m, cur["date"].min())
        weeks = cur["date"].dt.to_period("W-MON")
        for _, g in cur.groupby(weeks):
            cutoff = g["date"].min()
            fit = M.fit(m, cutoff, xi, s, ratio, prior)
            lam = [M.rates(fit, h, a) for h, a in zip(g["home"], g["away"])]
            out.append(g.assign(lh=[x[0] for x in lam], la=[x[1] for x in lam]))
    return pd.concat(out, ignore_index=True)


def probs_from_rates(p: pd.DataFrame, rho: float) -> np.ndarray:
    return np.array([M.outcome(M.score_matrix(a, b, rho)) for a, b in zip(p["lh"], p["la"])])


def home_frequency(m: pd.DataFrame, rows: pd.DataFrame) -> np.ndarray:
    """Référence naïve : fréquence domicile / nul / extérieur des 5 saisons précédentes."""
    out = []
    for y, g in rows.groupby("season", sort=False):
        past = m[(m["season"] < y) & (m["season"] >= y - 5)]
        f = np.bincount(past["result"], minlength=3) / len(past)
        out.append(np.tile(f, (len(g), 1)))
    return np.vstack(out)


def score(p: np.ndarray, y: np.ndarray) -> dict:
    return {"log_loss": round(float(M.logloss(p, y).mean()), 4), "rps": round(float(M.rps(p, y).mean()), 4),
            "brier": round(float(((p - np.eye(3)[y]) ** 2).sum(axis=1).mean()), 4),
            "bons_favoris": round(float((p.argmax(axis=1) == y).mean()), 3), "matchs": int(len(y))}


def bootstrap(a: np.ndarray, b: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float, float]:
    """Écart moyen b - a (positif = a meilleur) et intervalle de confiance à 95 %."""
    d = b - a
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, size=(n, len(d)), replace=True).mean(axis=1)
    return round(float(d.mean()), 4), round(float(np.quantile(boots, 0.025)), 4), round(float(np.quantile(boots, 0.975)), 4)


def run(m: pd.DataFrame) -> dict:
    prior_xi = 0.004
    prior = {"promoted": promoted_prior(m, list(range(2006, 2015)), prior_xi)}
    # 1) réglages du modèle seul, sur la période de choix
    grid = []
    preds = {}
    for xi, s in itertools.product(XI_GRID, SOT_GRID):
        p = weekly_predictions(m, C.CHOICE_SEASONS, xi, s, prior)
        preds[(xi, s)] = p
        for rho in RHO_GRID:
            grid.append({"xi": xi, "s": s, "rho": float(rho), **score(probs_from_rates(p, rho), p["result"].to_numpy())})
    grid = pd.DataFrame(grid)
    best = grid.loc[grid["rps"].idxmin()]
    xi, s, rho = float(best["xi"]), float(best["s"]), float(best["rho"])
    pc = preds[(xi, s)]
    pm_c = probs_from_rates(pc, rho)
    mk_c = M.market_probs(pc[["oh", "od", "oa"]].to_numpy(float))
    has_c = np.isfinite(mk_c).all(axis=1)
    yc = pc["result"].to_numpy()
    # 2) poids du marché, sur la même période de choix
    mix = []
    for a, b in itertools.product(A_GRID, B_GRID):
        if a == 0 and b == 0:
            continue
        pb = M.blend(pm_c[has_c], mk_c[has_c], a, b)
        mix.append({"a": float(a), "b": float(b), **score(pb, yc[has_c])})
    mix = pd.DataFrame(mix)
    bm = mix.loc[mix["log_loss"].idxmin()]
    a, b = float(bm["a"]), float(bm["b"])
    # 3) test, jamais vu pendant les choix
    pt = weekly_predictions(m, C.TEST_SEASONS, xi, s, prior)
    yt = pt["result"].to_numpy()
    pm_t = probs_from_rates(pt, rho)
    mk_t = M.market_probs(pt[["oh", "od", "oa"]].to_numpy(float))
    has_t = np.isfinite(mk_t).all(axis=1)
    bl_t = M.blend(pm_t, mk_t, a, b)
    base = {"hasard": np.full((len(pt), 3), 1 / 3), "fréquence domicile/nul/extérieur": home_frequency(m, pt)}
    rows = [{"modele": "notre modèle (statistiques)", **score(pm_t, yt)},
            {"modele": "notre modèle + marché", **score(bl_t, yt)},
            {"modele": "marché seul (cotes)", **score(np.where(has_t[:, None], mk_t, pm_t), yt)}]
    rows += [{"modele": k, **score(v, yt)} for k, v in base.items()]
    per = {"modèle": M.rps(pm_t, yt), "mélange": M.rps(bl_t, yt), "marché": M.rps(np.where(has_t[:, None], mk_t, pm_t), yt),
           "fréquence": M.rps(base["fréquence domicile/nul/extérieur"], yt)}
    gains = [{"compare": "modèle vs fréquence", "gain_rps": bootstrap(per["modèle"], per["fréquence"])},
             {"compare": "mélange vs marché", "gain_rps": bootstrap(per["mélange"], per["marché"])},
             {"compare": "mélange vs modèle", "gain_rps": bootstrap(per["mélange"], per["modèle"])}]
    by_season = []
    for y, g in pt.assign(_i=np.arange(len(pt))).groupby("season"):
        i = g["_i"].to_numpy()
        by_season.append({"saison": int(y), "modele": score(pm_t[i], yt[i]), "melange": score(bl_t[i], yt[i]),
                          "marche": score(np.where(has_t[i][:, None], mk_t[i], pm_t[i]), yt[i])})
    return {"settings": {"xi": xi, "s": s, "rho": rho, "a": a, "b": b, "promoted": prior["promoted"]},
            "grid": grid, "mix": mix, "test": pd.DataFrame(rows), "gains": gains, "by_season": by_season,
            "test_predictions": pt.assign(p_model_h=pm_t[:, 0], p_model_d=pm_t[:, 1], p_model_a=pm_t[:, 2],
                                          p_h=bl_t[:, 0], p_d=bl_t[:, 1], p_a=bl_t[:, 2])}
