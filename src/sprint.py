"""Week-ends sprint : la qualification sprint et la course sprint comme variables (étude de novembre 2026).

Un week-end sprint n'a qu'une séance d'essais libres. En échange, deux séances « pour de vrai » ont lieu
avant la qualification et la course du dimanche :
- la qualification sprint (SQ1 à SQ3, « Sprint Shootout » en 2023) ;
- la course sprint (environ 100 km), dont le classement officiel vient de f1db.

Ordre des séances : depuis 2024, qualif sprint (vendredi) et sprint (samedi) PRÉCÈDENT la qualification.
En 2023, la qualification avait lieu le vendredi, avant le shootout : la qualif sprint ne peut alors pas
servir à prédire la pole (fuite du futur). On le vérifie avec l'heure réelle de début des séances.

Variables (une variable n'est gardée que si elle améliore le backtest, voir etude_sprint.py) :
- qualif_sprint      : écart (%) au plus rapide de la qualif sprint (SQ3), plafonné à 3 % ;
- sprint_vs_grille   : log(place au sprint) - log(place sur la grille du Grand Prix) ; 0 hors sprint ;
- forme_course_sprint: forme en course (moyenne pondérée des places d'arrivée) qui compte aussi les sprints.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features import ewm_mean

SQ = "Sprint Qualifying"
CAP = 3.0                  # même plafond que les essais libres (features.practice_deficit)
KEY = ["season", "grand_prix", "driver"]


def is_sprint_weekend(info: dict) -> bool:
    s = (info or {}).get("sessions") or {}
    return "SQ" in s or "S" in s


def quali_sprint(best: pd.DataFrame) -> pd.DataFrame:
    """Écart en qualif sprint de chaque pilote, pour les seuls week-ends où elle a eu lieu AVANT la
    qualification (ou quand la qualification n'a pas encore eu lieu : week-end en cours)."""
    cols = KEY + ["qualif_sprint"]
    sq = best[best["session"] == SQ]
    if sq.empty or "start" not in best:
        return pd.DataFrame(columns=cols)
    week = ["season", "grand_prix"]
    q_start = best[best["session"] == "Qualifying"].groupby(week)["start"].min()
    sq_start = sq.groupby(week)["start"].min()
    before = sq_start.index[[not isinstance(q_start.get(k), str) or str(s) < q_start[k]
                             for k, s in sq_start.items()]]
    sq = sq.set_index(week).loc[lambda d: d.index.isin(before)].reset_index()
    # pas de temps valide (accident, abandon) : traité comme un incident, au plafond
    sq = sq.assign(qualif_sprint=sq["deficit_pct"].clip(upper=CAP).fillna(CAP))
    return sq.drop_duplicates(KEY)[cols]


def add_quali_sprint(t: pd.DataFrame, best: pd.DataFrame, fp_cols: list[str]) -> pd.DataFrame:
    """Ajoute, pour chaque colonne d'essais c, la colonne c + '_sprint' (qualif sprint quand elle est connue
    avant la qualification, essais sinon) et l'écart qualif sprint - essais (0 hors sprint)."""
    t = t.drop(columns=[c for c in t if c.endswith("_sprint") or c == "ecart_qualif_sprint"])
    t = t.merge(quali_sprint(best), on=KEY, how="left")
    known = t["qualif_sprint"].notna()
    for c in fp_cols:
        t[c + "_sprint"] = t["qualif_sprint"].where(known, t[c])
    t["ecart_qualif_sprint"] = (t["qualif_sprint"] - t[fp_cols[0]]).where(known, 0.0)
    t["sprint_connu"] = known
    return t.drop(columns="qualif_sprint")


def add_race_sprint(r: pd.DataFrame, sprints: pd.DataFrame | None) -> pd.DataFrame:
    """Variables sprint du modèle de victoire. `sprints` : season, grand_prix, driver, sprint (place).
    Le sprint d'un week-end a lieu avant la course : il compte pour cette course et les suivantes."""
    r = r.drop(columns=[c for c in ("sprint", "sprint_vs_grille", "forme_course_sprint", "sprint_connu") if c in r])
    if sprints is None or not len(sprints):
        return r.assign(sprint_vs_grille=0.0, forme_course_sprint=r["forme_course"], sprint_connu=False)
    r = r.merge(sprints[KEY + ["sprint"]].drop_duplicates(KEY), on=KEY, how="left")
    week = ["season", "grand_prix"]
    known = r.groupby(week)["sprint"].transform("count") > 0
    # pilote sans place au sprint (pas parti) : dernier du sprint
    place = r["sprint"].fillna(r.groupby(week)["sprint"].transform("max") + 1)
    r["sprint_vs_grille"] = (np.log(place) - r["log_grille"]).where(known, 0.0)
    r["sprint_connu"] = known
    form = []
    for (season, gp, idx), g in r.groupby(["season", "grand_prix", "race_idx"]):
        past = r[(r["season"] == season) & (r["race_idx"] <= idx)].sort_values("race_idx")
        for drv in g["driver"]:
            mine = past[past["driver"] == drv]
            seq = []
            for row in mine.itertuples():   # chronologie : sprint du week-end, puis course (sauf la course visée)
                if pd.notna(row.sprint):
                    seq.append(row.sprint)
                if row.race_idx < idx:
                    seq.append(row.finish)
            form.append((season, gp, drv, ewm_mean(np.array(seq, dtype=float))))
    f = pd.DataFrame(form, columns=KEY + ["forme_course_sprint"])
    r = r.merge(f, on=KEY, how="left")
    r["forme_course_sprint"] = r["forme_course_sprint"].fillna(r["forme_course"])
    return r.drop(columns="sprint")
