"""Journal des prédictions publiées : la vraie mesure de la précision.

Le backtest rejoue le passé ; le journal, lui, garde ce que le site a RÉELLEMENT affiché
AVANT chaque séance. Règles :
- une prédiction de pole n'est enregistrée qu'avant le début de la qualif, une prédiction
  de victoire qu'avant le départ de la course ;
- pour chaque étape (avant le week-end, après EL1, EL2, EL3, après la qualif), seule la
  PREMIÈRE version publiée est gardée : on ne peut pas la corriger après coup.
Exception, toujours visible : un pronostic publié sur une grille fausse (pénalités ignorées, bug corrigé
en novembre 2026) peut être recalculé après la course avec les seules données d'avant le départ.
La ligne d'origine reste dans le fichier ; le bilan utilise le recalcul, signalé comme tel.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "data" / "journal" / "predictions.csv"
MARGIN = timedelta(minutes=30)  # le site est publié quelques minutes après le calcul : on garde une marge
COLUMNS = ["publie_utc", "season", "grand_prix", "type", "etape", "driver", "team", "proba", "modele"]


def _time(info: dict, key: str):
    t = info.get("sessions", {}).get(key)
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def load() -> pd.DataFrame:
    if JOURNAL.exists():
        return pd.read_csv(JOURNAL)
    return pd.DataFrame(columns=COLUMNS)


def record(season: int, gp: str, info: dict, pole: pd.DataFrame, pole_col: str, stage: str, pole_model: str,
           win: pd.DataFrame, win_stage: str, win_model: str, now: datetime | None = None) -> int:
    """Ajoute les prédictions du moment si elles sont nouvelles et encore « avant » la séance."""
    now = now or datetime.now(timezone.utc)
    j = load()
    rows = []
    if info.get("approx"):  # horaires pas encore officiels : impossible de garantir « avant la séance »
        return 0
    q_start, r_start = _time(info, "Q"), _time(info, "R")

    def already(kind, st):
        return ((j["season"] == season) & (j["grand_prix"] == gp) & (j["type"] == kind) & (j["etape"] == st)).any()

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if q_start and now < q_start - MARGIN and not already("pole", stage):
        rows += [[stamp, season, gp, "pole", stage, r.driver, r.team, round(float(getattr(r, pole_col)), 5), pole_model]
                 for r in pole.itertuples()]
    if r_start and now < r_start - MARGIN and not already("victoire", win_stage):
        rows += [[stamp, season, gp, "victoire", win_stage, r.driver, r.team, round(float(r.proba_victoire), 5), win_model]
                 for r in win.itertuples()]
    if rows:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        # ajout en fin de fichier uniquement : les lignes déjà publiées ne sont jamais réécrites
        pd.DataFrame(rows, columns=COLUMNS).to_csv(JOURNAL, mode="a", header=not JOURNAL.exists(), index=False)
    return len(rows)


RECALCUL = "(recalculé après la course)"


def record_correction(season: int, gp: str, win: pd.DataFrame, win_model: str, now: datetime | None = None) -> int:
    """Ajoute le recalcul d'un pronostic de victoire publié sur une grille fausse (une seule fois)."""
    stage = f"après la qualif, grille officielle {RECALCUL}"
    j = load()
    if ((j["season"] == season) & (j["grand_prix"] == gp) & (j["etape"] == stage)).any():
        return 0
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [[stamp, season, gp, "victoire", stage, r.driver, r.team, round(float(r.proba_victoire), 5), win_model]
            for r in win.itertuples()]
    pd.DataFrame(rows, columns=COLUMNS).to_csv(JOURNAL, mode="a", header=not JOURNAL.exists(), index=False)
    return len(rows)


def superseded(j: pd.DataFrame) -> set:
    """Étapes « après la qualif » remplacées par un recalcul sur la grille officielle."""
    redone = j[j["etape"].str.endswith(RECALCUL)][["season", "grand_prix", "type"]].drop_duplicates()
    return {(r.season, r.grand_prix, r.type, "après la qualif") for r in redone.itertuples()}


def evaluate(best: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Pour chaque prédiction publiée dont le résultat est connu : probabilité donnée au vrai
    vainqueur, son rang, et la log-loss (comparée au hasard)."""
    j = load()
    if j.empty:
        return pd.DataFrame()
    q = best[(best["session"] == "Qualifying") & best["pole"]][["season", "grand_prix", "driver"]]
    q = q.rename(columns={"driver": "reel"}).assign(type="pole")
    w = results[results["finish"] == 1][["season", "grand_prix", "driver"]].rename(columns={"driver": "reel"})
    truth = pd.concat([q, w.assign(type="victoire")])
    out = []
    skip = superseded(j)
    for (season, gp, kind, stage), g in j.groupby(["season", "grand_prix", "type", "etape"], sort=False):
        if (season, gp, kind, stage) in skip:
            continue
        t = truth[(truth["season"] == season) & (truth["grand_prix"] == gp) & (truth["type"] == kind)]
        if t.empty:
            continue
        real = t["reel"].iloc[0]
        g = g.sort_values("proba", ascending=False).reset_index(drop=True)
        hit = g.index[g["driver"] == real]
        p = float(g.loc[hit[0], "proba"]) if len(hit) else 0.0
        out.append({"season": season, "grand_prix": gp, "type": kind, "etape": stage, "publie_utc": g["publie_utc"].iloc[0],
                    "reel": real, "proba_du_vainqueur": round(p, 4), "rang_du_vainqueur": int(hit[0]) + 1 if len(hit) else None,
                    "favori": g.loc[0, "driver"], "log_loss": round(float(-np.log(max(p, 1e-6))), 3),
                    "log_loss_hasard": round(float(np.log(len(g))), 3), "recalcule": stage.endswith(RECALCUL)})
    return pd.DataFrame(out)
