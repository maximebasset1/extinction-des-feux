"""Journal des pronostics publiés, toutes compétitions de football.

Chaque match est enregistré une seule fois, au moins 30 minutes avant le coup d'envoi, et jamais réécrit.
On attend les cotes d'avant-match (blessures, actualité) ; sans elles, on fige quand même à 6 h du match.
Les calculs tournent au moins toutes les 3 h : un match est donc toujours figé à temps.
"""
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from football import model as M
except ImportError:  # lancé comme script
    import model as M  # type: ignore

MARGIN = timedelta(minutes=30)
LAST_CALL = timedelta(hours=6)
HORIZON = timedelta(days=7)
SURPRISE = 0.2          # un résultat qui avait moins de 20 % de chances est signalé comme une surprise
COLUMNS = ["publie_utc", "match_id", "competition", "journee", "domicile", "exterieur", "coup_envoi",
           "p_dom", "p_nul", "p_ext", "avec_cotes"]


def match_id(comp: str, home: str, away: str, jour: str | None) -> str:
    return f"{comp}|{home}|{away}|{jour or ''}"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def read(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"journee": str})


def record(rows: list[dict], path: Path, now: datetime) -> int:
    """`rows` : matchs à venir (competition, journee, jour, kickoff, home, away, p, avec_cotes)."""
    done = set(read(path)["match_id"])
    new = []
    for r in rows:
        if not isinstance(r.get("kickoff"), str):
            continue   # heure pas encore connue : on attend
        ko = datetime.fromisoformat(r["kickoff"].replace("Z", "+00:00"))
        mid = match_id(r["competition"], r["home"], r["away"], r.get("jour"))
        is_ready = bool(r.get("avec_cotes")) or ko - now < LAST_CALL
        if mid in done or not (now < ko - MARGIN and ko - now < HORIZON and is_ready):
            continue
        new.append([_iso(now), mid, r["competition"], r.get("journee", ""), r["home"], r["away"], r["kickoff"],
                    *r["p"], bool(r.get("avec_cotes"))])
        done.add(mid)
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(new, columns=COLUMNS).to_csv(path, mode="a", header=not path.exists() or not path.stat().st_size,
                                                  index=False)
    return len(new)


def outcome(hg: int, ag: int) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2


def evaluate(path: Path, results: dict) -> list[dict]:
    """`results` : match_id -> (buts domicile, buts extérieur). Une ligne par pronostic dont le match est joué."""
    out = []
    for r in read(path).itertuples():
        if r.match_id not in results:
            continue
        hg, ag = results[r.match_id]
        y = outcome(hg, ag)
        p = np.array([r.p_dom, r.p_nul, r.p_ext], float)
        out.append({"match_id": r.match_id, "competition": r.competition, "journee": str(r.journee),
                    "home": r.domicile, "away": r.exterieur, "coup_envoi": r.coup_envoi, "publie_utc": r.publie_utc,
                    "p": [float(x) for x in p], "score": [int(hg), int(ag)], "resultat": y,
                    "favori_juste": bool(p.argmax() == y), "surprise": bool(p[y] < SURPRISE),
                    "rps": round(float(M.rps(p[None], np.array([y]))[0]), 4)})
    return out
