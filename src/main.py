"""Lance tout le calcul et écrit les résultats lus par le site (reports/results/).

    python src/main.py             télécharge ce qui manque (et toujours le week-end cible), puis calcule
    python src/main.py --offline   calcule avec les données déjà présentes
    python src/main.py --open      ouvre aussi le rapport HTML à la fin

Le site (app.py) lit les fichiers produits ; son bouton « Recharger » relance ce script.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import build_dataset  # noqa: E402
import f1db  # noqa: E402
import fetch_data  # noqa: E402
import grille  # noqa: E402
import plots  # noqa: E402
import race_model  # noqa: E402
import report  # noqa: E402
from config import DATA_PROCESSED, RESULTS, TARGET_GP, TARGET_SEASON  # noqa: E402
from predict import entry_list, run  # noqa: E402


def step(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="(conservé pour compatibilité : même effet que sans option)")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    if not args.offline:
        step("1/5 Téléchargement (seuls les fichiers manquants et le week-end cible)")
        fetch_data.main()
    step("2/5 Mise en forme des données")
    build_dataset.main()
    best = pd.read_csv(DATA_PROCESSED / "best_laps.csv")
    results = pd.read_csv(DATA_PROCESSED / "race_results.csv")
    # données officielles des courses passées : vraie grille (pénalités, stands) et classement final
    if not args.offline:
        f1db.sync(TARGET_SEASON)
    official = f1db.load()
    results = f1db.official_results(results, official)
    grids = f1db.official_grids(results, official)
    print(f"f1db : {grids.groupby(['season', 'grand_prix']).ngroups} grilles officielles, "
          f"{int(grids['stands'].sum())} départs des stands, {int(grids['penalite'].notna().sum())} pénalités")

    step("3/5 Modèle de pole (backtest mis en cache tant que l'historique ne change pas)")
    import config as cfg
    import weather
    forecast = None if args.offline else weather.forecast(cfg.TARGET_INFO)
    print("Prévision météo :", forecast or "aucune (piste sèche supposée)")
    out = run(best, forecast)
    pd.set_option("display.width", 200)
    print(out["res"][["moment", "variables", "methode", "log_loss_choix_2026_debut", "log_loss_test", "choisi"]]
          .to_string(index=False))

    step("4/5 Modèle de victoire en course")
    race = race_model.evaluate(best, results, grids=grids)
    gp = TARGET_GP.replace(" Grand Prix", "")
    quali = best[(best["season"] == TARGET_SEASON) & (best["grand_prix"] == gp) & (best["session"] == "Qualifying")]
    pred = out["pred"]
    col = "proba_pole_apres" if "proba_pole_apres" in pred else "proba_pole_avant"
    # hors ligne : pas d'appel à OpenF1, la grille reste celle de la qualif (provisoire)
    grid, grid_source = (grille.official(TARGET_SEASON, TARGET_GP, {} if args.offline else cfg.TARGET_INFO, quali)
                         if len(quali) else (None, "inconnue"))
    if grid is not None:
        moved = grid[grid["stands"] | (grid["penalite"] > 0)]
        print(f"Grille {grid_source} : " + (", ".join(f"{r.driver} {'stands' if r.stands else f'+{r.penalite}'}"
                                                      for r in moved.itertuples()) or "aucune pénalité"))
    win = race_model.predict_race(best, results, entry_list(best), quali if len(quali) else None,
                                  pred.set_index("driver")[col], race["feats"], race["weights"],
                                  rain=float(((forecast or {}).get("R") or {}).get("pluie") or 0.0),
                                  grid=grid if grid_source == "officielle" else None)

    # championnat : chances de titre (Grands Prix restants simulés avec les chances de victoire du modèle)
    import championnat
    from config import CALENDAR_FILE
    # un échec ici (fichier f1db inattendu...) ne doit jamais empêcher la publication des pronostics
    try:
        forced = bool(os.environ.get("F1_TARGET"))     # course passée rejouée : classement d'avant cette manche
        classement = f1db.championship(TARGET_SEASON, before_round=cfg.TARGET_INFO.get("round") if forced else None)
        entrants = entry_list(best)
        win_avant = win if not len(quali) else race_model.predict_race(
            best, results, entrants, None, pred.set_index("driver")["proba_pole_avant"], race["feats"], race["weights"])
        cal = json.loads(CALENDAR_FILE.read_text(encoding="utf-8")).get(str(TARGET_SEASON), []) if CALENDAR_FILE.exists() else []
        champ = championnat.calculer(TARGET_SEASON, classement, cal, championnat.equipes_engagees(entrants, classement),
                                     dict(zip(win["driver"], win["proba_victoire"])),
                                     dict(zip(win_avant["driver"], win_avant["proba_victoire"])), TARGET_GP)
    except Exception as e:  # noqa: BLE001
        print(f"Championnat : calcul impossible ({type(e).__name__}: {e}), bloc masqué")
        champ = None
    if champ:
        for k in ("pilotes", "constructeurs"):
            top = champ[k]["classement"][0]
            print(f"Championnat {k} après la manche {champ['apres_manche']} : "
                  + (f"joué ({top['id']})" if champ[k]["joue"] else
                     ", ".join(f"{d['id']} {d['titre']:.0%}" for d in champ[k]["classement"] if d["titre"] >= 0.005)))
    else:
        print("Championnat : classement f1db indisponible")

    step("5/5 Enregistrement, journal des prédictions et export du site")
    import config as cfg
    import export_site
    import journal
    from config import DATA_RAW
    col = "proba_pole_apres" if "proba_pole_apres" in pred else "proba_pole_avant"
    win_stage = f"après la qualif, grille {grid_source}" if len(quali) else f"avant la qualif ({out['status']})"
    added = journal.record(TARGET_SEASON, gp, cfg.TARGET_INFO, pred, col, out["status"],
                           out["chosen"]["après les essais libres" if col.endswith("apres") else "avant le week-end"]["label"],
                           win, win_stage, race["chosen"])
    print(f"Journal : {added} nouvelles lignes publiées")
    journal_eval = journal.evaluate(best, results)
    export_site.export(out, race, win, best, results, journal_eval, DATA_RAW, cfg, forecast,
                       grid=grid, grid_source=grid_source, championnat=champ)
    RESULTS.mkdir(parents=True, exist_ok=True)
    files = {
        "probabilites_pole.csv": pred, "backtest.csv": out["res"], "gains_vs_references.csv": out["gains"],
        "calibration.csv": out["calib"], "historique_pole.csv": out["history"],
        "probabilites_victoire.csv": win, "course_scores.csv": race["scores"], "course_gains.csv": race["gains"],
        "historique_course.csv": race["history"][["season", "date", "grand_prix", "race_idx", "driver", "team",
                                                  "grille", "finish", "p_win"]],
    }
    for name, df in files.items():
        df.to_csv(RESULTS / name, index=False)
    meta = {
        "calcule_le": datetime.now().strftime("%d/%m/%Y à %H h %M"),
        "grand_prix": gp, "saison": TARGET_SEASON, "statut": out["status"],
        "qualif_disputee": bool(len(quali)),
        "modele_pole": {k: v["label"] for k, v in out["chosen"].items()},
        "modele_course": race["chosen"],
    }
    (RESULTS / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    plots.pole_chances(pred, out["status"], out["res"])
    plots.backtest_chart(out["res"])
    plots.calibration_chart(out["calib"])
    plots.season_heatmap(best, pred)
    page = report.build(pred, out["status"], out["res"], out["chosen"])
    print(f"Terminé. Statut : {out['status']}. Rapport : {page}")
    if args.open:
        import webbrowser
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
