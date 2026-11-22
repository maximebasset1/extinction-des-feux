"""Étape 2 (data engineer) : un meilleur tour par pilote et par session.

Sortie : data/processed/best_laps.csv avec, pour chaque session (qualif ou essai libre) :
saison, Grand Prix, date, session, pilote, équipe, meilleur tour valide (s),
écart au plus rapide de la session (%), session sous la pluie ou non.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import DATA_PROCESSED, DATA_RAW, circuit_type  # noqa: E402

WET = {"INTERMEDIATE", "WET"}


def _num(values) -> np.ndarray:
    return pd.to_numeric(pd.Series(values).replace("None", np.nan), errors="coerce").to_numpy()


SEGMENTS = ["Q1", "Q2", "Q3"]
# qualification sprint : SQ1 à SQ3 (« Sprint Shootout » en 2023, rangée sous le nom « Sprint Qualifying »)
SPRINT_QUALI = ("Sprint Qualifying", "Sprint Shootout")
SESSION_NAMES = {"Sprint Shootout": "Sprint Qualifying"}


def best_valid(t: np.ndarray, valid: np.ndarray) -> float:
    return float(t[valid].min()) if valid.any() else np.nan


def read_session(folder: Path) -> list[dict]:
    info = folder / "session_info.json"
    if not info.exists():
        return []
    t0 = (json.loads(info.read_text(encoding="utf-8")) or {}).get("t0_date")
    if t0 in (None, "None", ""):
        t0 = None
    if not t0:  # quelques séances anciennes n'ont pas d'heure de départ : date du premier tour enregistré
        for f in sorted(folder.glob("*/laptimes.json")):
            t0 = next((x for x in json.loads(f.read_text(encoding="utf-8")).get("lSD", []) if x not in (None, "None")), None)
            if t0:
                break
    if not t0:
        return []
    date, start = str(t0)[:10], str(t0)[:19]   # start : heure de début, pour savoir quelle séance précède l'autre
    rows, wet_laps, all_laps = [], 0, 0
    rain, track_t, air_t = [], [], []  # météo relevée à chaque tour (pluie oui/non, températures)
    for f in sorted(folder.glob("*/laptimes.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        t = _num(d.get("time", []))
        dl = d.get("del") or []
        deleted = np.array([x is True for x in dl], dtype=bool) if len(dl) == len(t) else np.zeros(len(t), dtype=bool)
        comp = d.get("compound") or []
        comp = comp if len(comp) == len(t) else [None] * len(t)
        valid = ~np.isnan(t) & ~deleted
        wet_laps += sum(c in WET for c in comp)
        rain += [x is True for x in d.get("wR", [])]
        track_t += list(_num(d.get("wTT", [])))
        air_t += list(_num(d.get("wAT", [])))
        all_laps += len(comp)
        teams = [x for x in d.get("team", []) if x not in (None, "None")]
        segment, lap, set_at = None, best_valid(t, valid), np.nan
        qs = np.array(d.get("qs", []))
        if (folder.name == "Qualifying" or folder.name in SPRINT_QUALI) and len(qs) == len(t):
            # en qualif, on garde le meilleur tour de la DERNIÈRE partie (Q1, Q2 ou Q3) où le
            # pilote a signé un temps : la pole se joue en Q3, pas sur un tour plus rapide en Q2
            # (même règle en qualif sprint, SQ1 à SQ3 rangées sous Q1 à Q3)
            ses_t = _num(d.get("sesT", [np.nan] * len(t)))
            prefix = "" if folder.name == "Qualifying" else "S"
            for seg in reversed(SEGMENTS):
                in_seg = valid & (qs == prefix + seg)
                if in_seg.any():
                    segment, lap = seg, best_valid(t, in_seg)
                    set_at = float(np.nanmin(np.where(in_seg & (t == lap), ses_t, np.nan)))
                    break
        row = {
            "driver": f.parent.name,
            "team": teams[0] if teams else None,
            "best_lap": lap,
            "segment": segment,
            "set_at": set_at,  # heure de la session où le tour a été bouclé (départage les égalités)
            "n_laps": int(valid.sum()),
        }
        if folder.name.startswith("Practice"):
            # tours en pneus tendres = simulations de qualif ; tour idéal = somme des meilleurs secteurs
            soft = valid & np.array([c == "SOFT" for c in comp])
            row["best_soft"] = best_valid(t, soft)
            secs = [_num(d.get(k, [])) for k in ("s1", "s2", "s3")]
            if all(len(x) == len(t) for x in secs):
                row["ideal_lap"] = float(sum(np.nanmin(np.where(valid, x, np.nan)) for x in secs)) if valid.any() else np.nan
        if folder.name == "Race":
            pos = _num(d.get("pos", []))
            laps = _num(d.get("lap", []))
            row["race_laps"] = int(np.nanmax(laps)) if len(laps) and not np.all(np.isnan(laps)) else 0
            ok = ~np.isnan(pos)
            row["race_last_pos"] = float(pos[ok][-1]) if ok.any() else np.nan
        rows.append(row)
    wet = all_laps > 0 and wet_laps / all_laps > 0.3
    weather = {"rain_share": float(np.mean(rain)) if rain else np.nan,
               "track_temp": float(np.nanmedian(track_t)) if np.isfinite(track_t).any() else np.nan,
               "air_temp": float(np.nanmedian(air_t)) if np.isfinite(air_t).any() else np.nan}
    for r in rows:
        r.update(date=date, start=start, wet=wet, **weather)
    return rows


def race_results(df: pd.DataFrame) -> pd.DataFrame:
    """Classement final : plus de tours d'abord, puis position au dernier tour."""
    r = df[df["session"] == "Race"].copy()
    r = r.sort_values(["season", "grand_prix", "race_laps", "race_last_pos"], ascending=[True, True, False, True])
    r["finish"] = r.groupby(["season", "grand_prix"]).cumcount() + 1
    return r[["season", "date", "grand_prix", "driver", "team", "finish", "race_laps", "wet", "rain_share"]]


def build() -> pd.DataFrame:
    rows = []
    for season_dir in sorted(p for p in DATA_RAW.iterdir() if p.is_dir()):
        for gp_dir in sorted(p for p in season_dir.iterdir() if p.is_dir()):
            for ses_dir in sorted(p for p in gp_dir.iterdir() if p.is_dir()):
                for r in read_session(ses_dir):
                    r.update(season=int(season_dir.name), grand_prix=gp_dir.name.replace(" Grand Prix", ""),
                             session=SESSION_NAMES.get(ses_dir.name, ses_dir.name))
                    rows.append(r)
    df = pd.DataFrame(rows)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    race_results(df).to_csv(DATA_PROCESSED / "race_results.csv", index=False)
    df = df[df["session"] != "Race"].copy()
    key = ["season", "grand_prix", "session"]
    # référence = pole (plus rapide en Q3) en qualif, plus rapide de la séance sinon
    q3 = df["best_lap"].where(df["segment"] == "Q3")
    ref = q3.groupby([df[k] for k in key]).transform("min").fillna(
        df.groupby(key)["best_lap"].transform("min"))
    # égalité au millième (Canada 2024) : la pole revient à celui qui a signé le temps en premier
    tied = (df["session"] == "Qualifying") & (df["best_lap"] == ref)
    first = df["set_at"].where(tied).groupby([df[k] for k in key]).transform("min")
    df["pole"] = tied & ((df["set_at"] == first) | first.isna())
    # un pilote éliminé ne peut pas être devant le poleman : écart ramené à 0 au minimum
    # un pilote sans aucun tour valide garde un écart vide (traité comme un incident)
    df["deficit_pct"] = (100 * (df["best_lap"] / ref - 1)).clip(lower=0)
    # place en qualif : d'abord la partie atteinte (Q3 > Q2 > Q1), puis le temps, puis l'heure du tour
    seg_rank = df["segment"].map({"Q3": 0, "Q2": 1, "Q1": 2}).fillna(3)
    order = df.assign(_seg=seg_rank, _lap=df["best_lap"].fillna(1e9), _t=df["set_at"].fillna(1e9)) \
        .sort_values(["_seg", "_lap", "_t"])
    df["quali_pos"] = np.nan
    is_q = order["session"] == "Qualifying"
    df.loc[order.index[is_q], "quali_pos"] = order[is_q].groupby(["season", "grand_prix"]).cumcount() + 1
    kind = [circuit_type(s_, g) for s_, g in zip(df["season"], df["grand_prix"])]
    df["downforce"] = [k[0] for k in kind]
    df["street"] = [k[1] for k in kind]
    cols = ["season", "date", "grand_prix", "session", "driver", "team", "segment", "best_lap",
            "deficit_pct", "pole", "quali_pos", "set_at", "n_laps", "wet", "rain_share", "track_temp", "air_temp", "downforce", "street", "best_soft", "ideal_lap",
            "start"]
    return df[cols].sort_values(["date", "session", "deficit_pct"]).reset_index(drop=True)


def main() -> None:
    df = build()
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out = DATA_PROCESSED / "best_laps.csv"
    df.to_csv(out, index=False)
    q = df[df["session"] == "Qualifying"]
    assert (q.groupby(["season", "grand_prix"])["pole"].sum() == 1).all(), "une qualif sans poleman unique"
    print(f"{len(df):,} meilleurs tours ; {q.groupby(['season', 'grand_prix']).ngroups} qualifications -> {out.name}")


if __name__ == "__main__":
    main()
