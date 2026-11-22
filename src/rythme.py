"""Rythme de course vu aux essais : longs relais et usure des pneus (étape 2, novembre 2026).

Pour chaque relais d'essais libres, on ne garde que les tours représentatifs : pas de tour de sortie ou
d'entrée aux stands, pas de drapeau (jaune, voiture de sécurité, VSC : statut de piste différent de « 1 »),
pas de tour supprimé, et rien au-delà de 107 % du tour médian du relais (tours de refroidissement, trafic).
Un relais d'au moins MIN_LAPS tours ainsi filtrés est un « long relais ».

Variables par pilote et par week-end (toutes connues avant la course) :
- rythme_relais : écart (%) entre son meilleur long relais et le meilleur long relais du week-end,
  à gomme égale et séance égale ;
- usure : pente de ses temps au tour sur un long relais (s/tour), comparée à la médiane de la séance ;
- rythme_sprint : écart (%) de son tour médian en course sprint au meilleur, hors 1er tour et neutralisations.
Une variable n'est gardée dans le modèle que si elle améliore le backtest (voir race_model.evaluate).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

MIN_LAPS = 5
CUT = 1.07                 # au-delà de 107 % du tour médian du relais : tour non représentatif
MIN_DRIVERS = 3            # comparaison seulement si au moins 3 pilotes ont un long relais sur la gomme
PRACTICE = ("Practice 1", "Practice 2", "Practice 3")
COLUMNS = ["season", "grand_prix", "driver", "rythme_relais", "usure", "rythme_sprint", "longs_relais"]


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) else np.nan


def clean_laps(lt: dict) -> pd.DataFrame:
    """Tours représentatifs d'un fichier laptimes.json (TracingInsights)."""
    n = len(lt.get("lap", []))
    get = lambda k, d=None: lt.get(k, [d] * n)  # noqa: E731
    d = pd.DataFrame({"lap": get("lap"), "time": [_num(t) for t in get("time")], "compound": get("compound"),
                      "stint": get("stint"), "status": [str(s) for s in get("status", "1")],
                      "pin": [_num(t) for t in get("pin")], "pout": [_num(t) for t in get("pout")],
                      "deleted": [bool(x) for x in get("del", False)]})
    ok = d["time"].notna() & (d["status"] == "1") & d["pin"].isna() & d["pout"].isna() & ~d["deleted"]
    d = d[ok & d["compound"].isin(["SOFT", "MEDIUM", "HARD"])]
    if d.empty:
        return d
    med = d.groupby("stint")["time"].transform("median")
    return d[d["time"] <= CUT * med]


def stints(d: pd.DataFrame) -> pd.DataFrame:
    """Longs relais : tour médian et pente (s/tour)."""
    out = []
    for (stint, comp), g in d.groupby(["stint", "compound"]):
        if len(g) < MIN_LAPS:
            continue
        slope = np.polyfit(g["lap"].astype(float), g["time"], 1)[0] if g["lap"].nunique() > 2 else np.nan
        out.append({"compound": comp, "median": float(g["time"].median()), "slope": float(slope), "laps": len(g)})
    return pd.DataFrame(out)


def weekend(folder: Path) -> pd.DataFrame:
    """Variables de rythme pour tous les pilotes d'un week-end (dossier du Grand Prix)."""
    rows = []
    for ses in PRACTICE:
        for f in sorted((folder / ses).glob("*/laptimes.json")):
            st = stints(clean_laps(json.loads(f.read_text(encoding="utf-8"))))
            for r in st.itertuples():
                rows.append({"session": ses, "driver": f.parent.name, **r._asdict()})
    per = pd.DataFrame(rows)
    out = pd.DataFrame(columns=["driver", "rythme_relais", "usure", "longs_relais"])
    if len(per):
        per = per.drop(columns="Index")
        key = ["session", "compound"]
        n = per.groupby(key)["driver"].transform("nunique")
        per = per[n >= MIN_DRIVERS]
        if len(per):
            best = per.groupby(key)["median"].transform("min")
            per["ecart"] = 100 * (per["median"] / best - 1)
            per["usure_rel"] = per["slope"] - per.groupby(key)["slope"].transform("median")
            out = per.groupby("driver").agg(rythme_relais=("ecart", "min"), usure=("usure_rel", "median"),
                                            longs_relais=("laps", "size")).reset_index()
    sprint = []
    for f in sorted((folder / "Sprint").glob("*/laptimes.json")):
        lt = json.loads(f.read_text(encoding="utf-8"))
        d = clean_laps(lt)
        d = d[d["lap"] > 1]
        if len(d) >= MIN_LAPS:
            sprint.append({"driver": f.parent.name, "sprint_med": float(d["time"].median())})
    if sprint:
        s = pd.DataFrame(sprint)
        s["rythme_sprint"] = 100 * (s["sprint_med"] / s["sprint_med"].min() - 1)
        out = out.merge(s[["driver", "rythme_sprint"]], on="driver", how="outer")
    for c in ("rythme_relais", "usure", "rythme_sprint", "longs_relais"):
        if c not in out:
            out[c] = np.nan
    return out


def build(raw: Path, seasons: list[int] | None = None) -> pd.DataFrame:
    """Toutes les saisons présentes dans `raw` (dossiers <saison>/<Grand Prix>/<séance>/<pilote>/laptimes.json)."""
    frames = []
    for sdir in sorted(p for p in raw.iterdir() if p.is_dir() and p.name.isdigit()):
        if seasons and int(sdir.name) not in seasons:
            continue
        for gdir in sorted(p for p in sdir.iterdir() if p.is_dir()):
            w = weekend(gdir)
            if len(w):
                frames.append(w.assign(season=int(sdir.name), grand_prix=gdir.name.replace(" Grand Prix", "")))
    return pd.concat(frames, ignore_index=True)[COLUMNS] if frames else pd.DataFrame(columns=COLUMNS)
