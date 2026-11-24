"""Journal des pronostics publiés, toutes compétitions de football.

Chaque match est enregistré une seule fois, au moins 30 minutes avant le coup d'envoi, et jamais réécrit.
On attend les cotes d'avant-match (blessures, actualité) ; sans elles, on fige quand même à 12 h du match.
GitHub lance parfois le calcul avec plusieurs heures de retard : d'où cette marge large. Un match qui n'a pas
pu être figé à temps n'entre pas dans le journal et reste affiché comme une reconstitution.
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
# une même affiche ne se rejoue pas avant longtemps en championnat (aller et retour sont deux affiches différentes) ;
# en coupe, elle peut revenir dans la saison (phase de ligue puis élimination)
SAME_MATCH_DAYS = {"ligue": 200, "coupe": 45}
RESULT_WINDOW_DAYS = 90   # un pronostic n'est jugé que sur un résultat arrivé dans les 90 jours (report compris)
LAST_CALL = timedelta(hours=12)
HORIZON = timedelta(days=7)
SURPRISE = 0.2          # un résultat qui avait moins de 20 % de chances est signalé comme une surprise
COLUMNS = ["publie_utc", "match_id", "competition", "journee", "domicile", "exterieur", "coup_envoi",
           "p_dom", "p_nul", "p_ext", "avec_cotes"]


def match_id(comp: str, home: str, away: str, jour: str | None) -> str:
    return f"{comp}|{home}|{away}|{jour or ''}"


def pair_key(mid: str) -> str:
    return mid.rsplit("|", 1)[0]


def kind(comp: str) -> str:
    return "coupe" if comp in ("LDC", "LEC") else "ligue"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def read(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"journee": str})


def _when(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def record(rows: list[dict], path: Path, now: datetime) -> int:
    """`rows` : matchs à venir (competition, journee, jour, kickoff, home, away, p, avec_cotes).
    Un match déjà enregistré ne l'est jamais une seconde fois, même reporté à une autre date."""
    old = read(path)
    seen: dict[str, list[datetime]] = {}
    for r in old.itertuples():
        seen.setdefault(pair_key(r.match_id), []).append(_when(r.coup_envoi))
    new = []
    for r in rows:
        if not isinstance(r.get("kickoff"), str):
            continue   # heure pas encore connue : on attend
        if str(r["home"]).startswith("?:") or str(r["away"]).startswith("?:"):
            continue   # club pas reconnu : pas de pronostic publié
        ko = _when(r["kickoff"])
        mid = match_id(r["competition"], r["home"], r["away"], r.get("jour"))
        days = SAME_MATCH_DAYS[kind(r["competition"])]
        if any(abs((ko - t).days) < days for t in seen.get(pair_key(mid), [])):
            continue
        is_ready = bool(r.get("avec_cotes")) or ko - now < LAST_CALL
        if not (now < ko - MARGIN and ko - now < HORIZON and is_ready):
            continue
        new.append([_iso(now), mid, r["competition"], r.get("journee", ""), r["home"], r["away"], r["kickoff"],
                    *r["p"], bool(r.get("avec_cotes"))])
        seen.setdefault(pair_key(mid), []).append(ko)
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(new, columns=COLUMNS).to_csv(path, mode="a", header=not path.exists() or not path.stat().st_size,
                                                  index=False)
    return len(new)


def outcome(hg: int, ag: int) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2


def link(path: Path, played: dict) -> dict:
    """Relie chaque pronostic publié au match joué correspondant : même identifiant, ou même affiche jouée
    entre 3 jours avant et 90 jours après le coup d'envoi prévu (match reporté). Seul le premier pronostic
    publié pour un match compte. `played` : identifiant du match joué -> (jour, score).
    Renvoie identifiant du pronostic -> identifiant du match joué."""
    by_pair: dict[str, list[tuple[str, str]]] = {}
    for mid, (jour, _) in played.items():
        by_pair.setdefault(pair_key(mid), []).append((jour, mid))
    out, used = {}, set()
    for r in read(path).sort_values("publie_utc").itertuples():
        target = r.match_id if r.match_id in played else None
        if target is None:
            ko = _when(r.coup_envoi).date()
            cand = sorted(j_m for j_m in by_pair.get(pair_key(r.match_id), [])
                          if -3 <= (datetime.fromisoformat(j_m[0]).date() - ko).days <= RESULT_WINDOW_DAYS)
            target = cand[0][1] if cand else None
        if target and target not in used:
            out[r.match_id] = target
            used.add(target)
    return out


def evaluate(path: Path, played: dict, links: dict) -> list[dict]:
    """Une ligne par pronostic publié dont le match est joué (voir `link`)."""
    out = []
    for r in read(path).itertuples():
        if r.match_id not in links:
            continue
        target = links[r.match_id]
        hg, ag = played[target][1]
        y = outcome(hg, ag)
        p = np.array([r.p_dom, r.p_nul, r.p_ext], float)
        out.append({"match_id": r.match_id, "joue_id": target, "competition": r.competition, "journee": str(r.journee),
                    "home": r.domicile, "away": r.exterieur, "coup_envoi": r.coup_envoi, "publie_utc": r.publie_utc,
                    "p": [float(x) for x in p], "avec_cotes": bool(r.avec_cotes), "score": [int(hg), int(ag)], "resultat": y,
                    "favori_juste": bool(p.argmax() == y), "surprise": bool(p[y] < SURPRISE),
                    "rps": round(float(M.rps(p[None], np.array([y]))[0]), 4)})
    return out


def summary(evals: list[dict], habits: dict[str, np.ndarray], market: dict[str, np.ndarray] | None = None,
            pending_count: int = 0, names: dict[str, str] | None = None) -> dict:
    """Bilan agrégé des pronostics réellement publiés et jugés, global et par compétition."""
    if not evals:
        return {"matchs": 0, "en_attente": int(pending_count), "par_competition": []}
    fallback = np.mean(list(habits.values()), axis=0) if habits else np.array([0.45, 0.27, 0.28])
    rows = []
    for e in evals:
        y = np.array([e["resultat"]])
        p = np.array([e["p"]], float)
        hab = np.asarray(habits.get(e["competition"], fallback), float)
        mk = (market or {}).get(e["joue_id"])
        rps_mk = float(M.rps(np.asarray(mk, float)[None], y)[0]) if mk is not None and np.isfinite(mk).all() else None
        rows.append({"competition": e["competition"], "rps": float(M.rps(p, y)[0]),
                     "rps_hab": float(M.rps(hab[None], y)[0]), "rps_marche": rps_mk,
                     "favori_juste": bool(e["favori_juste"]), "surprise": bool(e["surprise"])})

    def _agg(items: list[dict]) -> dict:
        n = len(items)
        fav = sum(1 for x in items if x["favori_juste"])
        surp = sum(1 for x in items if x["surprise"])
        with_mk = [x for x in items if x["rps_marche"] is not None]
        return {
            "matchs": n,
            "rps": round(float(np.mean([x["rps"] for x in items])), 4),
            "rps_habitudes": round(float(np.mean([x["rps_hab"] for x in items])), 4),
            "rps_marche": round(float(np.mean([x["rps_marche"] for x in with_mk])), 4) if with_mk else None,
            "rps_sur_cotes": round(float(np.mean([x["rps"] for x in with_mk])), 4) if with_mk else None,
            "matchs_cotes": len(with_mk),
            "favoris_justes": fav,
            "taux_favori": round(fav / n, 4),
            "surprises": surp,
        }

    order = list(names) if names else sorted({r["competition"] for r in rows})
    extra = sorted({r["competition"] for r in rows} - set(order))
    by_comp = []
    for comp in order + extra:
        sub = [r for r in rows if r["competition"] == comp]
        if sub:
            by_comp.append({"code": comp, "nom": (names or {}).get(comp, comp), **_agg(sub)})
    dates = [str(e["coup_envoi"])[:10] for e in evals if e.get("coup_envoi")]
    return {
        **_agg(rows),
        "en_attente": int(pending_count),
        "premier": min(dates) if dates else None,
        "dernier": max(dates) if dates else None,
        "par_competition": by_comp,
    }
