"""Étude de novembre 2026 : la qualif sprint et la course sprint améliorent-elles les pronostics ?

    F1_DATA_DIR=... F1DB_DIR=... python src/etude_sprint.py

Règle fixée avant de regarder les résultats (la même que pour l'étude du rythme, etude_rythme.py) :
une variable n'entre dans le modèle que si elle améliore à la fois la log-loss et le score de Brier sur les
week-ends sprint de la période de choix, puis se confirme sur les week-ends sprint de 2026 (test, jamais
utilisés pour choisir). Chaque Grand Prix est prédit avec les seules courses d'avant (backtest glissant).

- Pole : week-ends sprint 2024-2025 pour choisir, 2026 pour tester. En 2023, la qualification précédait
  le shootout : la qualif sprint n'était pas connue au moment de prédire la pole, la variable vaut alors les
  essais (aucune fuite du futur).
- Victoire : week-ends sprint 2023-2025 pour choisir, 2026 pour tester (le sprint précède toujours la course).
Les scores sur l'ensemble des Grands Prix sont donnés aussi : une variable sprint ne doit rien abîmer ailleurs.
Résultats écrits dans data/processed/etude_sprint.json (affichés sur la page « Méthode et bilan F1 »).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import f1db  # noqa: E402
import race_model as RM  # noqa: E402
import sprint  # noqa: E402
from config import DATA_PROCESSED, MAX_DEFICIT_PCT  # noqa: E402
from features import training_table  # noqa: E402
from model import HISTORIES  # noqa: E402
from predict import run_method  # noqa: E402

# modèles en production en novembre 2026 (site/data/performance.json) : c'est à eux qu'on ajoute les variables
POLE_FEATS = ["forme_pilote", "forme_equipe", "forme_type", "essais"]
POLE_METHOD, POLE_HIST = "régression + aléa", HISTORIES["depuis 2018, récent d'abord"]
RACE_FEATS = ["log_grille", "log_qualif", "ecart_qualif", "forme_course"]
RACE_HIST = HISTORIES["depuis 2018"]
POLE_CHOICE, RACE_CHOICE, TEST = [2024, 2025], [2023, 2024, 2025], [2026]

POLE_VARIANTS = {"qualif sprint à la place des essais": [c + "_sprint" if c == "essais" else c for c in POLE_FEATS],
                 "qualif sprint en plus des essais": POLE_FEATS + ["ecart_qualif_sprint"]}
RACE_VARIANTS = {"place au sprint (par rapport à la grille)": RACE_FEATS + ["sprint_vs_grille"],
                 "sprints comptés dans la forme en course":
                     [c if c != "forme_course" else "forme_course_sprint" for c in RACE_FEATS]}


def per_race(p: pd.DataFrame, prob: str, won: str) -> pd.DataFrame:
    """Une ligne par Grand Prix : log-loss (−log chance du gagnant) et Brier (somme sur les pilotes)."""
    rows = []
    for (season, gp), g in p.groupby(["season", "grand_prix"]):
        y = g[won].astype(bool)
        if y.sum() != 1:
            continue
        rows.append({"season": season, "grand_prix": gp, "sprint": bool(g["sprint_connu"].any()),
                     "log_loss": float(-np.log(max(g.loc[y, prob].iloc[0], 1e-6))),
                     "brier": float(((g[prob] - y) ** 2).sum())})
    return pd.DataFrame(rows)


def summary(r: pd.DataFrame, seasons: list, sprint_only: bool = True) -> dict:
    r = r[r["season"].isin(seasons) & (r["sprint"] | (not sprint_only))]
    return {"gp": int(len(r)), "log_loss": round(float(r["log_loss"].mean()), 3), "brier": round(float(r["brier"].mean()), 3),
            "_ll": r.set_index(["season", "grand_prix"])["log_loss"]}


def gain_ci(a: pd.Series, b: pd.Series, seed: int = 0) -> list:
    d = (a - b.reindex(a.index)).to_numpy()
    rng = np.random.default_rng(seed)
    bs = rng.choice(d, size=(2000, len(d)), replace=True).mean(axis=1)
    return [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)]


def compare(base: pd.DataFrame, runs: dict, choice: list, sprint_rows: pd.DataFrame, title: str) -> dict:
    """Tableau avant/après pour une famille de variables (pole ou victoire)."""
    b_c, b_t, b_all = summary(base, choice), summary(base, TEST), summary(base, choice + TEST, sprint_only=False)
    out = {"modele": title, "periode_choix": f"{min(choice)}-{max(choice)}", "periode_test": "2026",
           "week_ends_choix": b_c["gp"], "week_ends_test": b_t["gp"],
           "sans": {k: v for k, v in b_c.items() if k == "log_loss" or k == "brier"} |
                   {"log_loss_test": b_t["log_loss"], "brier_test": b_t["brier"]}, "variables": []}
    for name, r in runs.items():
        c, t, a = summary(r, choice), summary(r, TEST), summary(r, choice + TEST, sprint_only=False)
        keep_choice = c["log_loss"] < b_c["log_loss"] and c["brier"] < b_c["brier"]
        confirmed = keep_choice and t["log_loss"] < b_t["log_loss"] and t["brier"] < b_t["brier"]
        out["variables"].append({
            "variable": name,
            "log_loss_choix": [b_c["log_loss"], c["log_loss"]], "brier_choix": [b_c["brier"], c["brier"]],
            "log_loss_test": [b_t["log_loss"], t["log_loss"]], "brier_test": [b_t["brier"], t["brier"]],
            "log_loss_tous_gp": [b_all["log_loss"], a["log_loss"]], "brier_tous_gp": [b_all["brier"], a["brier"]],
            "gain_choix_ic95": gain_ci(b_c["_ll"], c["_ll"]), "retenue": bool(confirmed)})
    return out


def main() -> None:
    best = pd.read_csv(DATA_PROCESSED / "best_laps.csv")
    official = f1db.load()
    results = f1db.official_results(pd.read_csv(DATA_PROCESSED / "race_results.csv"), official)
    grids = f1db.official_grids(results, official)
    sprints = f1db.match(f1db.sprint_results(), results)
    out = {"date": "novembre 2026"}

    # 1) pole
    table = sprint.add_quali_sprint(training_table(best, MAX_DEFICIT_PCT), best, ["essais"])
    print(f"Pole : {table.loc[table['sprint_connu']].groupby(['season', 'grand_prix']).ngroups} week-ends avec qualif "
          "sprint connue avant la qualification")
    base = per_race(run_method(table, POLE_FEATS, POLE_METHOD, POLE_HIST)["probs"], "p_pole", "is_pole")
    runs = {n: per_race(run_method(table, f, POLE_METHOD, POLE_HIST)["probs"], "p_pole", "is_pole")
            for n, f in POLE_VARIANTS.items()}
    out["pole"] = compare(base, runs, POLE_CHOICE, table, "pole, après les essais (forme + type + essais)")

    # 2) victoire
    rt = RM.race_table(best, results, grids=grids, sprints=sprints)
    print(f"Victoire : {rt.loc[rt['sprint_connu']].groupby(['season', 'grand_prix']).ngroups} week-ends sprint")
    base = per_race(RM.rolling_race(rt, RACE_FEATS, RACE_HIST), "p_win", "is_pole")
    runs = {n: per_race(RM.rolling_race(rt, f, RACE_HIST), "p_win", "is_pole") for n, f in RACE_VARIANTS.items()}
    out["victoire"] = compare(base, runs, RACE_CHOICE, rt, "victoire (grille + qualif + écart + forme)")

    (DATA_PROCESSED / "etude_sprint.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
