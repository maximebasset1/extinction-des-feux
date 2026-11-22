"""Recalcule, après coup, un pronostic de victoire publié sur une grille fausse (pénalités ignorées).

    F1DB_DIR=... python src/corriger_journal.py 2026 "Las Vegas"

Seules les données connues avant le départ sont utilisées : essais, qualification, courses précédentes,
grille officielle. Le recalcul est ajouté au journal avec la mention « recalculé après la course ».
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import f1db  # noqa: E402
import journal  # noqa: E402
import race_model  # noqa: E402
from config import DATA_PROCESSED  # noqa: E402


def recompute(season: int, gp: str) -> pd.DataFrame:
    best = pd.read_csv(DATA_PROCESSED / "best_laps.csv")
    results = pd.read_csv(DATA_PROCESSED / "race_results.csv")
    official = f1db.load()
    quali = best[(best["season"] == season) & (best["grand_prix"] == gp) & (best["session"] == "Qualifying")]
    day = pd.Timestamp(quali["date"].iloc[0])
    # rien de la course elle-même ni de ce qui suit
    best = best[pd.to_datetime(best["date"]) <= day + pd.Timedelta(days=1)]
    results = results[pd.to_datetime(results["date"]) < day]
    results = f1db.official_results(results, official)
    grids = f1db.official_grids(results, official)
    race = race_model.evaluate(best, results, grids=grids)
    # grille officielle de la course à recalculer (f1db la publie après la course ; elle ne dépend que d'avant)
    target = official[(official["season"] == season) & ((official["date"] - day).abs() <= pd.Timedelta(days=2))]
    q = quali[["driver", "quali_pos"]].assign(qualif=lambda d: d["quali_pos"].rank(method="first").astype(int))
    grid = target[["driver", "grille_officielle", "stands"]].rename(columns={"grille_officielle": "grille"}).merge(q, on="driver")
    entrants = quali.drop_duplicates("driver")[["driver", "team"]]
    win = race_model.predict_race(best, results, entrants, quali, pd.Series(dtype=float), race["feats"], race["weights"],
                                  grid=grid)
    win.attrs["modele"] = race["chosen"]
    return win


if __name__ == "__main__":
    season, gp = int(sys.argv[1]), sys.argv[2]
    win = recompute(season, gp)
    print(win[["driver", "grille", "proba_victoire"]].head(8).to_string(index=False))
    if "--ecrire" in sys.argv:
        print(journal.record_correction(season, gp, win, win.attrs["modele"]), "lignes ajoutées au journal")
