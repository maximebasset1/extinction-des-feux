"""Étude de novembre 2026 : grille officielle, rythme des longs relais, usure, sprint et podium.

    F1_DATA_DIR=... F1DB_DIR=... python src/etude_rythme.py

Règle fixée avant de regarder les résultats : une variable n'entre dans le modèle que si elle améliore
à la fois la log-loss et le score de Brier sur 2024-2025 (période de choix), puis se confirme sur 2026
(période de test, jamais utilisée pour choisir). Chaque course est prédite avec les seules courses d'avant.
Résultats écrits dans data/processed/etude_f1.json (affichés sur la page Méthode & Bilan).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import f1db  # noqa: E402
import race_model as RM  # noqa: E402
import rythme  # noqa: E402
from config import DATA_PROCESSED, DATA_RAW  # noqa: E402
from model import HISTORIES  # noqa: E402

CHOICE, TEST = [2024, 2025], [2026]
BASE = ["log_grille", "log_qualif", "ecart_qualif", "forme_course"]
VARIANTS = {"rythme des longs relais": ["rythme_relais"], "usure des pneus": ["usure"],
            "rythme en course sprint": ["rythme_sprint"], "longs relais et usure": ["rythme_relais", "usure"]}


def metrics(p: pd.DataFrame, seasons: list) -> tuple[np.ndarray, np.ndarray]:
    p = p[p["season"].isin(seasons)]
    ll = -np.log(p.loc[p["finish"] == 1, "p_win"].clip(lower=1e-6)).to_numpy()
    brier = p.groupby(["season", "grand_prix"]).apply(lambda d: float(((d["p_win"] - (d["finish"] == 1)) ** 2).sum())).to_numpy()
    return ll, brier


def gain_ci(a: np.ndarray, b: np.ndarray, seed: int = 0) -> tuple[float, float]:
    rng, d = np.random.default_rng(seed), a - b
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main() -> None:
    best = pd.read_csv(DATA_PROCESSED / "best_laps.csv")
    raw_results = pd.read_csv(DATA_PROCESSED / "race_results.csv")
    official = f1db.load()
    results = f1db.official_results(raw_results, official)
    grids = f1db.official_grids(results, official)
    pace = rythme.build(DATA_RAW)
    hist = HISTORIES["depuis 2018"]
    out = {"periode_choix": "2024-2025", "periode_test": "2026", "grille": [], "variables": []}

    # 1) grille : ordre de la qualif contre grille officielle (même classement officiel à prédire)
    for name, table, feats in [
            ("grille = ordre de la qualif (avant)", RM.race_table(best, results), ["log_grille", "ecart_qualif", "forme_course"]),
            ("grille officielle + place en qualif (après)", RM.race_table(best, results, grids=grids), BASE)]:
        p = RM.rolling_race(table, feats, hist)
        (lc, bc), (lt, bt) = metrics(p, CHOICE), metrics(p, TEST)
        out["grille"].append({"modele": name, "log_loss_choix": round(lc.mean(), 3), "brier_choix": round(bc.mean(), 3),
                              "log_loss_test": round(lt.mean(), 3), "brier_test": round(bt.mean(), 3)})

    # 2) rythme : chaque variable ajoutée au modèle retenu à l'étape 1
    table = RM.race_table(best, results, grids=grids, pace=pace)
    ref = RM.rolling_race(table, BASE, hist)
    (l0c, b0c), (l0t, b0t) = metrics(ref, CHOICE), metrics(ref, TEST)
    for name, extra in VARIANTS.items():
        p = RM.rolling_race(table, BASE + extra, hist)
        (l1c, b1c), (l1t, b1t) = metrics(p, CHOICE), metrics(p, TEST)
        keep_choice = l1c.mean() < l0c.mean() and b1c.mean() < b0c.mean()
        confirmed = keep_choice and l1t.mean() < l0t.mean() and b1t.mean() < b0t.mean()
        lo, hi = gain_ci(l0c, l1c)
        out["variables"].append({
            "variable": name, "log_loss_choix": [round(l0c.mean(), 3), round(l1c.mean(), 3)],
            "brier_choix": [round(b0c.mean(), 3), round(b1c.mean(), 3)],
            "log_loss_test": [round(l0t.mean(), 3), round(l1t.mean(), 3)], "brier_test": [round(b0t.mean(), 3), round(b1t.mean(), 3)],
            "gain_choix_ic95": [round(lo, 3), round(hi, 3)], "retenue": bool(confirmed)})
    (DATA_PROCESSED / "etude_f1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
