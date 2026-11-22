"""Simulation du championnat : barème, départage, titre mathématiquement joué."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import championnat as C  # noqa: E402


def _pilotes(points, teams=None, wins=None):
    codes = [f"D{i}" for i in range(len(points))]
    d = pd.DataFrame({"driver": codes, "team": teams or [f"T{i // 2}" for i in range(len(points))], "points": points})
    d["p1"] = wins or [0] * len(points)
    return d


def _equipes(d):
    return d.groupby("team", as_index=False).agg(points=("points", "sum"), p1=("p1", "sum"))


def test_points_max_restants_respecte_le_bareme_de_la_saison():
    gp, sprint = {"sprint": False}, {"sprint": True}
    assert C.points_max_restants([gp, sprint], 2026) == 25 + 25 + 8
    assert C.points_max_restants([gp], 2024) == 26                   # meilleur tour jusqu'en 2024
    assert C.points_max_restants([gp, sprint], 2026, par_equipe=2) == 43 + 43 + 15


def test_titre_joue_seulement_si_le_second_ne_peut_plus_egaliser():
    pts = pd.Series({"A": 100, "B": 75, "C": 40})
    s = C.statut_titre(pts, 25)
    assert not s["joue"] and s["elimines"] == {"C"}                  # 75 + 25 = 100 : égalité encore possible
    s = C.statut_titre(pd.Series({"A": 101, "B": 75}), 25)
    assert s["joue"] and s["champion"] == "A"


def test_sans_course_restante_le_leader_est_champion_et_les_chances_somment_a_un():
    d = _pilotes([50, 60, 10, 0])
    r = C.simuler(d, _equipes(d), [], 2026, n=200)
    assert r["pilotes"]["D1"] == 1.0
    assert abs(sum(r["pilotes"].values()) - 1) < 1e-9
    assert r["constructeurs"]["T0"] == 1.0                           # 110 contre 10


def test_egalite_de_points_departagee_au_nombre_de_victoires():
    d = _pilotes([50, 50], teams=["T0", "T1"], wins=[1, 2])
    r = C.simuler(d, _equipes(d), [], 2026, n=50)
    assert r["pilotes"]["D1"] == 1.0


def test_un_pilote_elimine_n_a_jamais_le_titre_et_le_favori_gagne_plus_souvent():
    d = _pilotes([100, 95, 40, 0])
    course = {"poids": {"D0": 0.2, "D1": 0.6, "D2": 0.1, "D3": 0.1}, "sprint": False}
    r = C.simuler(d, _equipes(d), [course], 2026, n=4000, seed=1)
    assert r["pilotes"]["D2"] == 0 and r["pilotes"]["D3"] == 0      # 40 + 25 < 100
    # D1 doit finir au moins 6 points devant D0 sur cette seule course : plausible mais pas acquis
    assert 0.2 < r["pilotes"]["D1"] < 0.8
    assert abs(sum(r["pilotes"].values()) - 1) < 1e-9


def test_points_moyens_et_sprint():
    d = _pilotes([0, 0], teams=["T0", "T1"])
    egal = {"poids": {"D0": 0.5, "D1": 0.5}}
    r = C.simuler(d, _equipes(d), [egal | {"sprint": True}], 2026, n=20000, seed=2)
    # deux pilotes, chances égales : (25 + 18) / 2 en course, (8 + 7) / 2 en sprint
    assert np.isclose(r["points_moyens"]["D0"], 21.5 + 7.5, atol=0.3)
    assert np.isclose(sum(r["points_moyens"].values()), 43 + 15)


def test_un_pilote_absent_ne_marque_pas_mais_garde_ses_points_pour_son_ecurie():
    d = _pilotes([30, 0, 20], teams=["T0", "T0", "T1"])
    course = {"poids": {"D1": 0.5, "D2": 0.5}, "sprint": False}      # D0 remplacé par D1
    r = C.simuler(d, _equipes(d), [course], 2026, n=3000, seed=3)
    assert np.isclose(r["points_moyens"]["D0"], 30)
    assert np.isclose(r["points_moyens_equipes"]["T0"] + r["points_moyens_equipes"]["T1"], 50 + 43)


# ---------------------------------------------------------------- lecture des classements officiels (f1db)
import f1db  # noqa: E402


def _course(root: Path, rnd: int, slug: str, resultats: list, pilotes: list, equipes: list, sprint: list | None = None):
    d = root / f"src/data/seasons/2026/races/{rnd:02d}-{slug}"
    d.mkdir(parents=True)
    (d / "race.yml").write_text(f"round: {rnd}\ndate: 2026-0{rnd}-10\n", encoding="utf-8")
    (d / "race-results.yml").write_text("".join(f"- position: {p}\n  driverId: {i}\n  constructorId: {c}\n"
                                                for p, i, c in resultats), encoding="utf-8")
    (d / "driver-standings.yml").write_text("".join(f"- position: {k}\n  driverId: {i}\n  points: {p}\n"
                                                    for k, (i, p) in enumerate(pilotes, 1)), encoding="utf-8")
    (d / "constructor-standings.yml").write_text("".join(f"- position: {k}\n  constructorId: {i}\n  points: {p}\n"
                                                         for k, (i, p) in enumerate(equipes, 1)), encoding="utf-8")
    if sprint:
        (d / "sprint-race-results.yml").write_text("".join(f"- position: {p}\n  driverId: {i}\n" for p, i in sprint),
                                                   encoding="utf-8")


def test_classements_lus_apres_la_derniere_manche_et_avant_une_manche_donnee(tmp_path, monkeypatch):
    (tmp_path / "src/data/drivers").mkdir(parents=True)
    for code, i in [("ANT", "kimi-antonelli"), ("VER", "max-verstappen"), ("RUS", "george-russell")]:
        (tmp_path / f"src/data/drivers/{i}.yml").write_text(f"id: {i}\nabbreviation: {code}\n", encoding="utf-8")
    _course(tmp_path, 1, "a", [(1, "max-verstappen", "red-bull"), (2, "kimi-antonelli", "mercedes"),
                               ("DNF", "george-russell", "mercedes")],
            [("max-verstappen", 25), ("kimi-antonelli", 18), ("george-russell", 0)], [("red-bull", 25), ("mercedes", 18)])
    _course(tmp_path, 2, "b", [(1, "kimi-antonelli", "mercedes"), (2, "george-russell", "mercedes"),
                               (3, "max-verstappen", "red-bull")],
            [("kimi-antonelli", 51), ("max-verstappen", 40), ("george-russell", 25)], [("mercedes", 76), ("red-bull", 40)],
            sprint=[(1, "kimi-antonelli"), (2, "max-verstappen"), ("DNF", "george-russell")])
    (tmp_path / "src/data/seasons/2026/races/03-c").mkdir(parents=True)     # manche à venir : pas de résultat
    (tmp_path / "src/data/seasons/2026/races/03-c/race.yml").write_text("round: 3\ndate: 2026-03-10\n", encoding="utf-8")
    monkeypatch.setenv("F1DB_DIR", str(tmp_path))
    c = f1db.championship(2026)
    assert c["manche"] == 2
    p = c["pilotes"].set_index("driver")
    assert p.loc["ANT", "points"] == 51 and p.loc["ANT", "p1"] == 1 and p.loc["VER", "p1"] == 1
    assert p.loc["RUS", "team"] == "mercedes" and p.loc["RUS", "p2"] == 1
    assert c["constructeurs"].set_index("team").loc["mercedes", "p1"] == 1
    avant = f1db.championship(2026, before_round=2)                       # rejouer la saison : avant la manche 2
    assert avant["manche"] == 1 and avant["pilotes"].set_index("driver").loc["VER", "points"] == 25
    s = f1db.sprint_results()
    assert list(s.sort_values("sprint")["driver"]) == ["ANT", "VER", "RUS"]


def test_calcul_complet_titre_joue_et_titre_ouvert():
    pil = pd.DataFrame({"driver": ["ANT", "VER", "RUS"], "points": [402.0, 304.0, 264.0], "team": "x",
                        **{f"p{j}": 0 for j in range(1, 7)}})
    eq = pd.DataFrame({"team": ["mercedes", "red-bull"], "points": [666.0, 304.0], **{f"p{j}": 0 for j in range(1, 7)}})
    cal = [{"round": 21, "gp": "Las Vegas Grand Prix", "sessions": {}},
           {"round": 22, "gp": "Qatar Grand Prix", "sessions": {"Q": "x", "R": "y"}},
           {"round": 23, "gp": "Abu Dhabi Grand Prix", "sessions": {"Q": "x", "R": "y"}}]
    equipes = {"ANT": "mercedes", "RUS": "mercedes", "VER": "red-bull", "HAD": "red-bull"}
    poids = {"ANT": 0.4, "VER": 0.3, "RUS": 0.2, "HAD": 0.1}
    r = C.calculer(2026, {"manche": 21, "pilotes": pil, "constructeurs": eq}, cal, equipes, poids, poids,
                   "Qatar Grand Prix", n=500)
    assert [g["gp"] for g in r["gp_restants"]] == ["Qatar Grand Prix", "Abu Dhabi Grand Prix"]
    assert r["pilotes"]["joue"] and r["pilotes"]["champion"] == "ANT"          # 98 points d'avance, 50 en jeu
    assert r["pilotes"]["points_max_restants"] == 50
    assert {d["id"] for d in r["pilotes"]["classement"]} == {"ANT", "VER", "RUS", "HAD"}   # remplaçant ajouté à 0
    # titre ouvert : 10 points d'avance seulement (4 pilotes : le dernier marque encore 12 points)
    pil["points"] = [314.0, 304.0, 250.0]
    r = C.calculer(2026, {"manche": 21, "pilotes": pil, "constructeurs": eq}, cal, equipes, poids, poids,
                   "Qatar Grand Prix", n=2000)
    t = {d["id"]: d for d in r["pilotes"]["classement"]}
    assert not r["pilotes"]["joue"] and t["RUS"]["elimine"] and t["RUS"]["titre"] == 0
    assert 0.5 < t["ANT"]["titre"] < 1 and abs(sum(d["titre"] for d in t.values()) - 1) < 1e-9


def test_les_abandons_rendent_le_titre_moins_certain():
    d = _pilotes([60, 40] + [0] * 8)
    poids = {f"D{i}": w for i, w in enumerate([0.5, 0.3] + [0.025] * 8)}
    courses = [{"poids": poids, "sprint": False}] * 2
    sans = C.simuler(d, _equipes(d), courses, 2026, n=6000, seed=4)["pilotes"]["D1"]
    avec = C.simuler(d, _equipes(d), courses, 2026, n=6000, seed=4, abandon=0.1)["pilotes"]["D1"]
    assert avec > sans


def test_fin_de_saison_a_egalite_le_departage_attribue_le_titre():
    pil = pd.DataFrame({"driver": ["A", "B"], "points": [100.0, 100.0], "team": ["x", "y"], "p1": [3, 4],
                        **{f"p{j}": 0 for j in range(2, 7)}})
    eq = pd.DataFrame({"team": ["x", "y"], "points": [100.0, 100.0], "p1": [3, 4], **{f"p{j}": 0 for j in range(2, 7)}})
    r = C.calculer(2026, {"manche": 24, "pilotes": pil, "constructeurs": eq}, [], {}, {}, {}, "", n=10)
    assert r["pilotes"]["joue"] and r["pilotes"]["champion"] == "B"


def test_un_non_partant_finit_derriere_les_abandons():
    rng = np.random.default_rng(0)
    places = C._ordres(rng, np.array([0.5, 0.5, 0.0]), 2000, abandon=0.5)
    assert (places[:, 2] == 2).all()
