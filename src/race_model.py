"""Étape 6 : probabilité de VICTOIRE en course, une fois la grille connue.

Logit conditionnel (comme pour la pole). Variables candidates, connues au départ :
- ecart_qualif  : écart au poleman en qualif (%) : la vitesse pure du week-end ;
- log_grille    : log de la place en qualif : partir devant compte beaucoup (dépassements, 1er virage) ;
- forme_course  : moyenne pondérée des places d'arrivée du pilote cette saison (demi-vie 5 courses).
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
from model import bootstrap_gain, fit_logit, logit_probabilities, per_race_logloss, scores  # noqa: E402

CANDIDATES = {
    "place sur la grille": ["log_grille"],
    "grille + forme en course": ["log_grille", "forme_course"],
    "grille + écart en qualif + forme": ["log_grille", "ecart_qualif", "forme_course"],
}
RACE_FEATURES = ["log_grille", "ecart_qualif", "forme_course"]  # toutes les colonnes calculées


def race_table(best: pd.DataFrame, results: pd.DataFrame, min_prior: int = 3) -> pd.DataFrame:
    q = best[best["session"] == "Qualifying"][["season", "grand_prix", "driver", "deficit_pct", "pole", "quali_pos"]].copy()
    q["ecart_qualif"] = q["deficit_pct"].fillna(5.0).clip(upper=5.0)
    q["grille"] = q["quali_pos"]   # ordre officiel de la qualif (Q3, puis Q2, puis Q1)
    r = results.merge(q, on=["season", "grand_prix", "driver"], how="inner")
    order = r.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    order["race_idx"] = order.groupby("season").cumcount() + 1
    r = r.merge(order[["season", "grand_prix", "race_idx"]], on=["season", "grand_prix"])
    r["log_grille"] = np.log(r["grille"])
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


def rolling_race(table: pd.DataFrame, feats: list[str], min_train: int = 8) -> pd.DataFrame:
    races = table.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    out = []
    for i, (_, r) in enumerate(races.iterrows()):
        if i < min_train:
            continue
        w = fit_logit(table[table["date"] < r["date"]], feats)
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
    runs = {name: rolling_race(table, feats) for name, feats in CANDIDATES.items()}
    first = next(iter(runs.values()))
    keys = first.set_index(["season", "grand_prix"]).index
    base = grid_baseline(table).loc[lambda d: d.set_index(["season", "grand_prix"]).index.isin(keys)]
    rows = []
    for name, p in list(runs.items()) + [("référence : fréquence de victoire selon la place", base)]:
        p = p.rename(columns={"p_win": "p_pole"})
        rows.append({"modele": name,
                     "log_loss_2024_2025_choix": scores(p[p["season"].isin([2024, 2025])])["log_loss"],
                     **{f"{k}_2026_test": v for k, v in scores(p[p["season"] == 2026]).items()}})
    res = pd.DataFrame(rows)
    cand = res[~res["modele"].str.startswith("référence")]
    best_name = cand.loc[cand["log_loss_2024_2025_choix"].idxmin(), "modele"]
    res["choisi"] = np.where(res["modele"] == best_name, "oui", "")
    model = runs[best_name]
    gains = []
    for period, seasons in [("2024-2025", [2024, 2025]), ("2026", [2026])]:
        a = per_race_logloss(model[model["season"].isin(seasons)].rename(columns={"p_win": "p_pole"}))
        b = per_race_logloss(base[base["season"].isin(seasons)].rename(columns={"p_win": "p_pole"}))
        g, lo, hi = bootstrap_gain(a, b)
        gains.append({"periode": period, "gain_vs_grille": g, "ic95_bas": lo, "ic95_haut": hi})
    feats = CANDIDATES[best_name]
    return {"table": table, "history": model, "scores": res, "gains": pd.DataFrame(gains),
            "chosen": best_name, "feats": feats, "weights": fit_logit(table, feats)}


def predict_race(best: pd.DataFrame, results: pd.DataFrame, entrants: pd.DataFrame, quali: pd.DataFrame | None,
                 pole_probs: pd.Series, feats: list[str], weights: np.ndarray, n_sim: int = 4000,
                 seed: int = 0) -> pd.DataFrame:
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
        f["proba_victoire"] = logit_probabilities(f, feats, weights)
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
            total += logit_probabilities(sim, feats, weights)
        f["proba_victoire"] = total / n_sim
    return f.sort_values("proba_victoire", ascending=False).reset_index(drop=True)
