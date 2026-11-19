"""Étape 3 (data scientist) : construire, pour chaque pilote et chaque qualification,
ce que l'on savait AVANT cette qualification.

Règle d'or : une variable ne doit utiliser que des courses antérieures (pas de fuite de données).

Variables (toutes en % d'écart au plus rapide, plus petit = plus rapide) :
- forme_pilote   : moyenne pondérée des écarts du pilote en qualif cette saison (les courses
                   récentes comptent plus : demi-vie de 5 courses) ;
- forme_equipe   : idem pour le meilleur pilote de l'équipe (= vitesse de la voiture) ;
- forme_type     : forme du pilote sur les circuits du même type d'appui aérodynamique ;
- affinite_gp    : écart du pilote sur ce Grand Prix l'an dernier, moins sa moyenne de l'an dernier ;
- essais         : écart du pilote dans les essais libres de ce week-end (meilleur tour des EL).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import SAME_CIRCUIT_LAST_YEAR  # noqa: E402

HALF_LIFE = 5.0  # choisi sur 2025 (2, 3 et 5 testés)
# Jeux de variables candidats ; le meilleur est choisi automatiquement sur la saison 2025
CANDIDATES_PRE = {
    "forme du pilote": ["forme_pilote"],
    "+ forme de l'équipe": ["forme_pilote", "forme_equipe"],
    "+ type de circuit": ["forme_pilote", "forme_equipe", "forme_type"],
    "+ affinité avec le GP": ["forme_pilote", "forme_equipe", "forme_type", "affinite_gp"],
}
FP_COLUMNS = ["essais", "essais_tendres", "essais_ideal"]
CANDIDATES_FP = {
    "essais libres seuls": ["essais"],
    "forme + essais": ["forme_pilote", "forme_equipe", "essais"],
    "forme + type + essais": ["forme_pilote", "forme_equipe", "forme_type", "essais"],
    "essais en pneus tendres": ["essais_tendres"],
    "forme + essais tendres": ["forme_pilote", "forme_equipe", "essais_tendres"],
    "tour idéal en essais": ["essais_ideal"],
    "forme + tendres + tour idéal": ["forme_pilote", "forme_equipe", "essais_tendres", "essais_ideal"],
}


def ewm_mean(values: np.ndarray) -> float:
    """Moyenne pondérée exponentielle : la dernière valeur a le poids 1, celle d'il y a HALF_LIFE courses 0,5."""
    v = values[~np.isnan(values)]
    if len(v) == 0:
        return np.nan
    w = 0.5 ** (np.arange(len(v))[::-1] / HALF_LIFE)
    return float((v * w).sum() / w.sum())


def qualifying_table(best: pd.DataFrame, max_deficit: float) -> pd.DataFrame:
    q = best[best["session"] == "Qualifying"].copy()
    # incident : écart énorme (crash, problème) ou aucun tour valide
    q["incident"] = q["deficit_pct"].isna() | (q["deficit_pct"] > max_deficit)
    q["target"] = q["deficit_pct"].fillna(max_deficit).clip(upper=max_deficit)
    # pour la FORME, on ignore les incidents et les qualifs sous la pluie (trop aléatoires)
    q["form_value"] = q["deficit_pct"].where(~q["incident"] & ~q["wet"])
    order = q.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    order["race_idx"] = order.groupby("season").cumcount() + 1
    return q.merge(order[["season", "grand_prix", "race_idx"]], on=["season", "grand_prix"])


def practice_deficit(best: pd.DataFrame) -> pd.DataFrame:
    """Rythme du week-end en essais libres (séances sèches), trois mesures en % du meilleur :
    - essais        : meilleur tour, tous pneus ;
    - essais_tendres: meilleur tour en pneus tendres (simulation de qualif) ;
    - essais_ideal  : tour idéal = somme des meilleurs secteurs du pilote."""
    fp = best[best["session"].str.startswith("Practice") & ~best["wet"]]
    key = ["season", "grand_prix", "driver"]
    agg = {"best_lap": "min"}
    for c in ["best_soft", "ideal_lap"]:
        if c in fp:
            agg[c] = "min"
    lap = fp.groupby(key).agg(agg).reset_index()
    out = lap[key].copy()
    for src, dst in [("best_lap", "essais"), ("best_soft", "essais_tendres"), ("ideal_lap", "essais_ideal")]:
        if src not in lap:
            out[dst] = np.nan
            continue
        ref = lap.groupby(["season", "grand_prix"])[src].transform("min")
        out[dst] = (100 * (lap[src] / ref - 1)).clip(upper=3.0)
    # pas de tour en tendres : on reprend le meilleur tour toutes gommes
    out["essais_tendres"] = out["essais_tendres"].fillna(out["essais"])
    out["essais_ideal"] = out["essais_ideal"].fillna(out["essais"])
    return out


def features_for_race(q: pd.DataFrame, season: int, race_idx: int, gp: str, downforce: str,
                      drivers: pd.DataFrame) -> pd.DataFrame:
    """Variables de chaque pilote de `drivers` (colonnes driver, team) avant la course race_idx."""
    past = q[(q["season"] == season) & (q["race_idx"] < race_idx)].sort_values("race_idx")
    team_best = past.groupby(["race_idx", "team"])["form_value"].min().reset_index()
    last_year = q[(q["season"] == season - 1)]
    gp_last_year = SAME_CIRCUIT_LAST_YEAR.get((season, gp), gp)
    rows = []
    for _, d in drivers.iterrows():
        mine = past[past["driver"] == d["driver"]]
        team = team_best[team_best["team"] == d["team"]].sort_values("race_idx")
        same_type = mine[mine["downforce"] == downforce]
        ly = last_year[last_year["driver"] == d["driver"]]
        ly_gp = ly[ly["grand_prix"] == gp_last_year]["form_value"]
        rows.append({
            "driver": d["driver"], "team": d["team"],
            "forme_pilote": ewm_mean(mine["form_value"].to_numpy()),
            "forme_equipe": ewm_mean(team["form_value"].to_numpy()),
            "forme_type": ewm_mean(same_type["form_value"].to_numpy()),
            "affinite_gp": (ly_gp.mean() - ly["form_value"].mean()) if len(ly_gp.dropna()) else np.nan,
            "n_qualifs": int(mine["form_value"].notna().sum()),
        })
    f = pd.DataFrame(rows)
    # valeurs manquantes : un nouveau pilote prend la forme de son équipe, etc.
    f["forme_pilote"] = f["forme_pilote"].fillna(f["forme_equipe"])
    f["forme_equipe"] = f["forme_equipe"].fillna(f["forme_pilote"])
    f["forme_type"] = f["forme_type"].fillna(f["forme_pilote"])
    f["affinite_gp"] = f["affinite_gp"].fillna(0.0)
    fallback = f["forme_pilote"].max() if f["forme_pilote"].notna().any() else 1.5
    for c in ["forme_pilote", "forme_equipe", "forme_type"]:
        f[c] = f[c].fillna(fallback)
    return f


def training_table(best: pd.DataFrame, max_deficit: float, min_prior_races: int = 3,
                   exclude: tuple | None = None) -> pd.DataFrame:
    """Une ligne par pilote et par qualification, avec les variables connues avant celle-ci.
    `exclude` = (saison, GP) à retirer : la course à prédire ne doit jamais servir à l'entraînement."""
    if exclude:
        best = best[~((best["season"] == exclude[0]) & (best["grand_prix"] == exclude[1]))]
    q = qualifying_table(best, max_deficit)
    fp = practice_deficit(best)
    out = []
    for (season, gp, idx), race in q.groupby(["season", "grand_prix", "race_idx"]):
        if idx <= min_prior_races:
            continue
        f = features_for_race(q, season, idx, gp, race["downforce"].iloc[0], race[["driver", "team"]])
        f = f.merge(race[["driver", "target", "deficit_pct", "pole", "incident", "wet", "date"]], on="driver")
        f["season"], f["grand_prix"], f["race_idx"] = season, gp, idx
        out.append(f)
    t = pd.concat(out, ignore_index=True).merge(fp, on=["season", "grand_prix", "driver"], how="left")
    # pas de temps en essais (pilote absent, etc.) : on suppose un écart moyen
    for c in FP_COLUMNS:
        t[c] = t[c].fillna(t.groupby(["season", "grand_prix"])[c].transform("median")).fillna(1.5)
    t["is_pole"] = t["pole"].astype(bool)
    return t.sort_values(["date", "target"]).reset_index(drop=True)
