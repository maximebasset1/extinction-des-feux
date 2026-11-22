"""Championnat du monde : chances de titre pilotes et constructeurs (simulation de Monte-Carlo).

Principe :
1. points actuels = classement officiel après la dernière course connue (f1db : Grands Prix et sprints,
   point du meilleur tour compris quand il existait) ;
2. pour chaque Grand Prix restant, on tire au sort l'ordre d'arrivée complet selon les chances de victoire
   du modèle de course (modèle de Plackett-Luce : le premier est tiré selon les chances de victoire, le
   deuxième parmi les autres avec les mêmes poids, etc.). Un week-end sprint ajoute un sprint tiré de la
   même façon. Sans abandons, ce tirage ne fait presque jamais finir un favori loin : chaque pilote abandonne
   donc au hasard avec le taux d'abandon de la saison (non classés dans f1db) et finit alors sans point ;
3. barème officiel de la saison, départage au nombre de victoires, puis de deuxièmes places, etc.
4. N_TIRAGES saisons simulées : la chance de titre est la part des saisons gagnées.

Un titre est « mathématiquement joué » quand le leader a plus de points que ce que tout autre concurrent
peut encore atteindre (égalité possible = pas encore joué). Le bloc du site disparaît alors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

N_TIRAGES = 10_000
POINTS_GP = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
POINTS_SPRINT = [8, 7, 6, 5, 4, 3, 2, 1]
# point du meilleur tour (pilote classé dans les 10 premiers) : de 2019 à 2024, supprimé en 2025
SAISONS_MEILLEUR_TOUR = range(2019, 2025)
NIVEAUX_DEPARTAGE = 6      # victoires, 2es places... 6es places (au-delà, égalité parfaite quasi impossible)


def meilleur_tour(saison: int) -> bool:
    return saison in SAISONS_MEILLEUR_TOUR


def points_max_restants(courses: list[dict], saison: int, par_equipe: int = 1) -> int:
    """Points qu'un pilote (par_equipe=1) ou une écurie (2 voitures) peut encore marquer au maximum."""
    gp = sum(POINTS_GP[:par_equipe]) + (1 if meilleur_tour(saison) else 0)
    sprint = sum(POINTS_SPRINT[:par_equipe])
    return int(sum(gp + (sprint if c.get("sprint") else 0) for c in courses))


def statut_titre(points: pd.Series, max_restant: int) -> dict:
    """Leader, titre joué ou non, concurrents éliminés (ne peuvent plus atteindre le leader)."""
    pts = points.sort_values(ascending=False)
    if pts.empty:
        return {"joue": True, "champion": None, "elimines": set()}
    leader, top = pts.index[0], pts.iloc[0]
    second = pts.iloc[1] if len(pts) > 1 else -np.inf
    joue = bool(top > second + max_restant)
    elimines = {k for k, v in pts.items() if v + max_restant < top}
    return {"joue": joue, "champion": leader if joue else None, "elimines": elimines}


TAUX_ABANDON = 0.11       # par défaut, si la saison ne permet pas de le mesurer (10 à 12 % de 2023 à 2025)


def _ordres(rng: np.random.Generator, poids: np.ndarray, n: int, abandon: float = 0.0) -> np.ndarray:
    """n ordres d'arrivée (Plackett-Luce) : place (0 = vainqueur) de chaque pilote, tableau (n, pilotes).
    Un pilote qui abandonne (probabilité `abandon`) passe derrière tous ceux qui ont fini."""
    w = np.clip(np.asarray(poids, dtype=float), 0, None)
    cles = rng.exponential(size=(n, len(w))) / (w + 1e-9)      # plus petite clé = devant
    if abandon > 0:
        cles = np.where(rng.random(cles.shape) < abandon, cles + 1e12, cles)
    cles = np.where(w > 0, cles, cles + 2e12)       # non partant : derrière tout le monde, abandons compris
    return cles.argsort(axis=1).argsort(axis=1)


def _bareme(places: np.ndarray, bareme: list[int]) -> np.ndarray:
    table = np.zeros(max(places.shape[1], len(bareme)))
    table[:len(bareme)] = bareme
    return table[places]


def simuler(pilotes: pd.DataFrame, equipes: pd.DataFrame, courses: list[dict], saison: int,
            n: int = N_TIRAGES, seed: int = 0, abandon: float = 0.0) -> dict:
    """`pilotes` : une ligne par pilote du championnat (driver, team, points, p1...p6 = nombre de victoires,
    de 2es places... en Grand Prix ; team = écurie pour les courses restantes, vide s'il ne court plus).
    `equipes` : une ligne par écurie (team, points, p1...p6), classement officiel des constructeurs.
    `courses` : Grands Prix restants, dans l'ordre : {"poids": {pilote: chance de victoire}, "sprint": bool}.
    Renvoie les chances de titre des pilotes et des écuries, et les points moyens en fin de saison."""
    rng = np.random.default_rng(seed)
    d, e = pilotes.reset_index(drop=True), equipes.reset_index(drop=True)
    k = len(d)
    gain = np.zeros((n, k))                     # points marqués d'ici la fin de saison
    places_gp = np.zeros((n, k, NIVEAUX_DEPARTAGE))
    fl = meilleur_tour(saison)
    for c in courses:
        w = d["driver"].map(c["poids"]).fillna(0.0).to_numpy(float)
        partants = w > 0
        if not partants.any():
            continue
        if c.get("sprint"):
            gain += np.where(partants, _bareme(_ordres(rng, w, n, abandon), POINTS_SPRINT), 0)
        places = _ordres(rng, w, n, abandon)
        gain += np.where(partants, _bareme(places, POINTS_GP), 0)
        for j in range(NIVEAUX_DEPARTAGE):
            places_gp[:, :, j] += (places == j) & partants
        if fl:  # meilleur tour : un pilote du top 10, tiré selon les mêmes poids
            u = rng.random((n, k)) * np.where((places < 10) & partants, w + 1e-9, 0)
            ok = u.max(axis=1) > 0
            gain[np.flatnonzero(ok), u.argmax(axis=1)[ok]] += 1
    deja = lambda t: np.stack([t.get(f"p{j + 1}", pd.Series(0, index=t.index)).to_numpy(float)  # noqa: E731
                               for j in range(NIVEAUX_DEPARTAGE)], axis=-1)
    pts = d["points"].to_numpy(float) + gain
    rangs = deja(d)[None] + places_gp
    m = (d["team"].to_numpy()[:, None] == e["team"].to_numpy()[None, :]).astype(float)   # pilote -> écurie
    pts_e = e["points"].to_numpy(float) + gain @ m
    rangs_e = deja(e)[None] + np.einsum("nkj,ke->nej", places_gp, m)
    return {"pilotes": _titres(pts, rangs, d["driver"].tolist()),
            "constructeurs": _titres(pts_e, rangs_e, e["team"].tolist()),
            "points_moyens": dict(zip(d["driver"], pts.mean(axis=0))),
            "points_moyens_equipes": dict(zip(e["team"], pts_e.mean(axis=0)))}


def _cle(pts: np.ndarray, rangs: np.ndarray) -> np.ndarray:
    """Clé entière de classement : points, puis victoires, 2es places... (départage officiel)."""
    cle = np.rint(np.broadcast_to(pts, rangs.shape[:2])).astype(np.int64)
    for j in range(rangs.shape[2]):
        cle = cle * 100 + np.minimum(rangs[:, :, j], 99).astype(np.int64)
    return cle


def _titres(pts: np.ndarray, rangs: np.ndarray, noms: list) -> dict:
    gagnant = _cle(pts, rangs).argmax(axis=1)
    return dict(zip(noms, np.bincount(gagnant, minlength=len(noms)) / len(gagnant)))


def courses_restantes(calendrier: list[dict], derniere_manche: int) -> list[dict]:
    """Grands Prix du calendrier (data/calendar.json) après la dernière manche classée."""
    return sorted((r for r in calendrier if int(r.get("round", 0)) > derniere_manche), key=lambda r: int(r["round"]))


def calculer(saison: int, classement: dict | None, calendrier: list[dict], equipes_actuelles: dict,
             poids_cible: dict, poids_suivants: dict, gp_cible: str, n: int = N_TIRAGES, seed: int = 0) -> dict | None:
    """Chances de titre à partir des classements officiels (f1db.championship).
    `equipes_actuelles` : pilote engagé -> écurie f1db pour les courses restantes ;
    `poids_cible` : chances de victoire au prochain Grand Prix (`gp_cible`) ;
    `poids_suivants` : chances de victoire avant la qualif, reprises pour les Grands Prix d'après
    (la forme actuelle est la meilleure estimation disponible si loin à l'avance)."""
    if not classement:
        return None
    restantes = courses_restantes(calendrier, classement["manche"])
    courses = [{"gp": r["gp"], "sprint": "S" in (r.get("sessions") or {}),
                "poids": poids_cible if r["gp"] == gp_cible else poids_suivants} for r in restantes]
    pil = classement["pilotes"].copy()
    eq = classement["constructeurs"].copy()
    # engagés pas encore classés (remplaçant) : 0 point ; pilotes partis : gardent leurs points, ne courent plus
    nouveaux = [d for d in equipes_actuelles if d not in set(pil["driver"])]
    if nouveaux:
        pil = pd.concat([pil, pd.DataFrame({"driver": nouveaux, "points": 0.0})], ignore_index=True)
    pil["team"] = pil["driver"].map(equipes_actuelles)
    pil = pil.fillna({f"p{j}": 0 for j in range(1, 7)})
    for t in [e for e in pil["team"].dropna().unique() if e not in set(eq["team"])]:
        eq = pd.concat([eq, pd.DataFrame({"team": [t], "points": [0.0]})], ignore_index=True)
    eq = eq.fillna({f"p{j}": 0 for j in range(1, 7)})
    abandon = classement.get("abandons")
    abandon = TAUX_ABANDON if abandon is None or not np.isfinite(abandon) else float(abandon)
    sim = simuler(pil, eq, courses, saison, n=n, seed=seed, abandon=abandon)

    def bloc(points: pd.Series, chances: dict, moyens: dict, par_equipe: int, equipe: dict) -> dict:
        maxi = points_max_restants(courses, saison, par_equipe)
        st = statut_titre(points, maxi)
        if maxi == 0 and not st["joue"]:     # plus rien à courir, égalité de points : le départage a tranché
            champion = max(chances, key=chances.get)
            st = {"joue": True, "champion": champion, "elimines": set(points.index) - {champion}}
        lignes = [{"id": k, "team": equipe.get(k), "points": float(v), "points_moyens": float(moyens.get(k, v)),
                   "titre": (1.0 if k == st["champion"] else 0.0) if st["joue"] else
                   (0.0 if k in st["elimines"] else float(chances.get(k, 0.0))),
                   "elimine": k in st["elimines"]} for k, v in points.sort_values(ascending=False).items()]
        return {"joue": st["joue"], "champion": st["champion"], "points_max_restants": maxi, "classement": lignes}

    return {"saison": saison, "apres_manche": int(classement["manche"]), "tirages": n, "taux_abandon": abandon,
            "meilleur_tour": meilleur_tour(saison),
            "gp_restants": [{"gp": c["gp"], "sprint": c["sprint"]} for c in courses],
            "pilotes": bloc(pil.set_index("driver")["points"], sim["pilotes"], sim["points_moyens"], 1,
                            {d: (t if isinstance(t, str) else None) for d, t in zip(pil["driver"], pil["team"])}),
            "constructeurs": bloc(eq.set_index("team")["points"], sim["constructeurs"], sim["points_moyens_equipes"], 2,
                                  dict(zip(eq["team"], eq["team"])))}


def equipes_engagees(entrants: pd.DataFrame, classement: dict | None) -> dict:
    """Écurie f1db de chaque engagé du prochain Grand Prix. Les noms d'écurie de TracingInsights et de f1db
    diffèrent : on passe par les pilotes présents dans les deux (un remplaçant prend l'écurie de son coéquipier)."""
    if not classement:
        return {}
    f1db_team = {d: t for d, t in zip(classement["pilotes"]["driver"], classement["pilotes"]["team"]) if isinstance(t, str)}
    par_nom = {}
    for r in entrants.itertuples():
        if r.driver in f1db_team:
            par_nom.setdefault(r.team, f1db_team[r.driver])
    out = {}
    for r in entrants.itertuples():
        t = par_nom.get(r.team) or f1db_team.get(r.driver)
        if t:
            out[r.driver] = t
    return out
