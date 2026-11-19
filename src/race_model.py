"""Étape 6 : probabilité de VICTOIRE en course, une fois la grille connue.

Logit conditionnel (comme pour la pole). Variables candidates, connues au départ :
- ecart_qualif  : écart au poleman en qualif (%) : la vitesse pure du week-end ;
- log_grille    : log de la place en qualif : partir devant compte beaucoup (dépassements, 1er virage) ;
- forme_course  : moyenne pondérée des places d'arrivée du pilote cette saison (demi-vie 5 courses) ;
- grille_pluie  : log_grille si la course est mouillée, 0 sinon (sous la pluie, la grille compte moins ?).
Avant la course, on mélange les scénarios sec et pluie selon la prévision météo.
Le jeu de variables est CHOISI sur 2024-2025 et TESTÉ sur 2026.
La place de départ réelle peut différer (pénalités) : on utilise l'ordre de la qualif.
Les disqualifications prononcées après la course ne sont pas prises en compte.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from features import ewm_mean  # noqa: E402
from model import HISTORIES, bootstrap_gain, fit_logit, logit_probabilities, per_race_logloss, scores  # noqa: E402

CANDIDATES = {
    "place sur la grille": ["log_grille"],
    "grille + forme en course": ["log_grille", "forme_course"],
    "grille + écart en qualif + forme": ["log_grille", "ecart_qualif", "forme_course"],
}
# L'effet de la pluie n'est PAS un candidat ordinaire : il utilise le fait qu'une course a été mouillée,
# connu seulement après coup. Il est jugé à part, sur les courses mouillées (comme pour la qualif).
RACE_HISTORIES = {k: HISTORIES[k] for k in ("2023 et après", "depuis 2018")}
RACE_FEATURES = ["log_grille", "ecart_qualif", "forme_course", "grille_pluie"]  # toutes les colonnes calculées


def race_table(best: pd.DataFrame, results: pd.DataFrame, min_prior: int = 3) -> pd.DataFrame:
    q = best[best["session"] == "Qualifying"][["season", "grand_prix", "driver", "deficit_pct", "pole", "quali_pos"]].copy()
    q["ecart_qualif"] = q["deficit_pct"].fillna(5.0).clip(upper=5.0)
    q["grille"] = q["quali_pos"]   # ordre officiel de la qualif (Q3, puis Q2, puis Q1)
    r = results.merge(q, on=["season", "grand_prix", "driver"], how="inner")
    order = r.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    order["race_idx"] = order.groupby("season").cumcount() + 1
    r = r.merge(order[["season", "grand_prix", "race_idx"]], on=["season", "grand_prix"])
    r["log_grille"] = np.log(r["grille"])
    wet = r["wet"].fillna(False).astype(bool) if "wet" in r else pd.Series(False, index=r.index)
    r["grille_pluie"] = r["log_grille"].where(wet, 0.0)
    form = []
    for (season, gp, idx), g in r.groupby(["season", "grand_prix", "race_idx"]):
        past = r[(r["season"] == season) & (r["race_idx"] < idx)].sort_values("race_idx")
        for drv in g["driver"]:
            form.append((season, gp, drv, ewm_mean(past.loc[past["driver"] == drv, "finish"].to_numpy(float))))
    f = pd.DataFrame(form, columns=["season", "grand_prix", "driver", "forme_course"])
    r = r.merge(f, on=["season", "grand_prix", "driver"])
    r["forme_course"] = r["forme_course"].fillna(r.groupby(["season", "grand_prix"])["forme_course"].transform("max")).fillna(15)
    r["is_pole"] = r["finish"] == 1          # « gagnant » : on réutilise le même code que pour la pole
    r = r[r["race_idx"] > min_prior]
    return r.sort_values(["date", "finish"]).reset_index(drop=True)


def rolling_race(table: pd.DataFrame, feats: list[str], hist: dict, min_train: int = 8) -> pd.DataFrame:
    races = table[table["season"] >= hist["start"]].drop_duplicates(["season", "grand_prix"]).sort_values("date")
    out = []
    for i, (_, r) in enumerate(races.iterrows()):
        if i < min_train:
            continue
        w = fit_logit(table[table["date"] < r["date"]], feats, hist, int(r["season"]))
        g = table[(table["season"] == r["season"]) & (table["grand_prix"] == r["grand_prix"])].copy()
        g["p_win"] = logit_probabilities(g, feats, w)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def grid_baseline(table: pd.DataFrame) -> pd.DataFrame:
    """Référence : fréquence historique de victoire selon la place de départ (lissée), calculée
    uniquement sur les courses précédentes."""
    out = []
    for (season, gp), g in table.groupby(["season", "grand_prix"]):
        past = table[table["date"] < g["date"].iloc[0]]
        wins = past[past["is_pole"]]["grille"].value_counts()
        starts = past["grille"].value_counts()
        rate = ((wins.reindex(starts.index).fillna(0) + 0.1) / (starts + 1)).to_dict()
        w = g["grille"].map(rate).fillna(0.005).to_numpy()
        out.append(g.assign(p_win=w / w.sum()))
    return pd.concat(out, ignore_index=True)


def evaluate(best: pd.DataFrame, results: pd.DataFrame) -> dict:
    table = race_table(best, results)
    runs, hists = {}, {}
    for hname, hist in RACE_HISTORIES.items():
        for name, feats in CANDIDATES.items():
            label = f"{name} ({'2023+' if hname.startswith('2023') else 'depuis 2018'})"
            runs[label], hists[label] = rolling_race(table, feats, hist), (name, hist)
    keys = runs[next(iter(runs))].set_index(["season", "grand_prix"]).index
    base = grid_baseline(table).loc[lambda d: d.set_index(["season", "grand_prix"]).index.isin(keys)]
    rows = []
    for name, p in list(runs.items()) + [("référence : fréquence de victoire selon la place", base)]:
        p = p.rename(columns={"p_win": "p_pole"})
        p = p[p.set_index(["season", "grand_prix"]).index.isin(keys)]  # mêmes courses pour tous
        rows.append({"modele": name,
                     "log_loss_2024_2025_choix": scores(p[p["season"].isin([2024, 2025])])["log_loss"],
                     **{f"{k}_2026_test": v for k, v in scores(p[p["season"] == 2026]).items()}})
    res = pd.DataFrame(rows)
    cand = res[~res["modele"].str.startswith("référence")]
    best_name = cand.loc[cand["log_loss_2024_2025_choix"].idxmin(), "modele"]
    res["choisi"] = np.where(res["modele"] == best_name, "oui", "")
    model = runs[best_name]
    # effet de la pluie : le même modèle + grille_pluie, comparé sur les courses mouillées 2018-2025
    name0, hist0 = hists[best_name]
    with_rain = rolling_race(table, CANDIDATES[name0] + ["grille_pluie"], hist0)
    def wet_ll(p, seasons):
        w = p[p["wet"].fillna(False).astype(bool) & p["season"].isin(seasons) & p["is_pole"]]
        return (round(float(-np.log(w["p_win"].clip(lower=1e-6)).mean()), 3) if len(w) else np.nan), int(len(w))
    old = list(range(2018, 2026))
    (ll0, n0), (ll1, _) = wet_ll(model, old), wet_ll(with_rain, old)
    (t0, nt), (t1, _) = wet_ll(model, [2026]), wet_ll(with_rain, [2026])
    rain_ok = bool(n0 >= 3 and ll1 < ll0)
    rain = {"courses_mouillees": n0, "log_loss_sans": ll0, "log_loss_avec": ll1, "retenu": rain_ok,
            "courses_mouillees_2026": nt, "log_loss_sans_2026": t0, "log_loss_avec_2026": t1}
    gains = []
    for period, seasons in [("2024-2025", [2024, 2025]), ("2026", [2026])]:
        a = per_race_logloss(model[model["season"].isin(seasons)].rename(columns={"p_win": "p_pole"}))
        b = per_race_logloss(base[base["season"].isin(seasons)].rename(columns={"p_win": "p_pole"}))
        g, lo, hi = bootstrap_gain(a, b)
        gains.append({"periode": period, "gain_vs_grille": g, "ic95_bas": lo, "ic95_haut": hi})
    name, hist = hists[best_name]
    feats = CANDIDATES[name] + (["grille_pluie"] if rain_ok else [])
    from config import TARGET_SEASON
    return {"table": table, "history": model, "scores": res, "gains": pd.DataFrame(gains),
            "chosen": best_name + (" + effet de la pluie" if rain_ok else ""), "feats": feats, "pluie": rain, "weights": fit_logit(table, feats, hist, TARGET_SEASON)}


def predict_race(best: pd.DataFrame, results: pd.DataFrame, entrants: pd.DataFrame, quali: pd.DataFrame | None,
                 pole_probs: pd.Series, feats: list[str], weights: np.ndarray, n_sim: int = 4000,
                 seed: int = 0, rain: float = 0.0) -> pd.DataFrame:
    """Probabilités de victoire au GP cible.
    - qualif disputée : on utilise la vraie grille ;
    - sinon : on tire au sort 4 000 grilles possibles (ordre tiré selon les probabilités de pole,
      modèle de Plackett-Luce) et on fait la moyenne des probabilités de victoire."""
    from config import TARGET_SEASON
    f = entrants[["driver", "team"]].copy().reset_index(drop=True)
    season_res = results[results["season"] == TARGET_SEASON].sort_values("date")
    f["forme_course"] = [ewm_mean(season_res.loc[season_res["driver"] == d, "finish"].to_numpy(float)) for d in f["driver"]]
    f["forme_course"] = f["forme_course"].fillna(f["forme_course"].max()).fillna(15)
    if quali is not None and len(quali):
        q = quali.set_index("driver")
        f["ecart_qualif"] = f["driver"].map(q["deficit_pct"]).fillna(5.0).clip(upper=5.0)
        pos = f["driver"].map(q["quali_pos"]).fillna(len(f))
        f["grille"] = pos.rank(method="first").astype(int)
        f["log_grille"] = np.log(f["grille"])
        f["proba_victoire"] = _mixed(f, feats, weights, rain)
    else:
        rng = np.random.default_rng(seed)
        worth = f["driver"].map(pole_probs).fillna(1e-4).to_numpy() + 1e-6
        # Plackett-Luce : trier par -log(U)/worth revient à tirer l'ordre selon les probabilités
        keys = rng.exponential(size=(n_sim, len(f))) / worth
        grids = keys.argsort(axis=1).argsort(axis=1) + 1          # place de chaque pilote, par tirage
        total = np.zeros(len(f))
        for g in grids:
            # ecart_qualif simulé = approximation (0,1 % par place) ; non utilisé par le modèle « grille »
            sim = f.assign(log_grille=np.log(g), ecart_qualif=(g - 1) * 0.1)
            total += _mixed(sim, feats, weights, rain)
        f["proba_victoire"] = total / n_sim
    return f.sort_values("proba_victoire", ascending=False).reset_index(drop=True)


def _mixed(f: pd.DataFrame, feats: list[str], weights: np.ndarray, rain: float) -> np.ndarray:
    """Probabilités sur le sec et sous la pluie, mélangées selon le risque de pluie prévu."""
    dry = logit_probabilities(f.assign(grille_pluie=0.0), feats, weights)
    if "grille_pluie" not in feats or rain <= 0:
        return dry
    wet = logit_probabilities(f.assign(grille_pluie=f["log_grille"]), feats, weights)
    return (1 - rain) * dry + rain * wet
