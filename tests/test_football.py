"""Tests des outils de match, des classements et du journal : python -m pytest tests -q"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import journal as JR  # noqa: E402
from football import model as M  # noqa: E402
from football import season as S  # noqa: E402


def test_score_matrix_is_a_distribution():
    for rho in (0.0, -0.1, -0.2):
        mat = M.score_matrix(1.6, 1.1, rho)
        assert mat.min() >= 0
        assert mat.sum() == pytest.approx(1.0, abs=1e-6)
        assert M.outcome(mat).sum() == pytest.approx(1.0, abs=1e-6)
    assert M.score_matrix(6.0, 5.0, -0.2).min() >= 0      # la correction ne crée jamais de probabilité négative


def test_stronger_attack_means_more_home_wins():
    assert M.outcome(M.score_matrix(2.2, 0.8, -0.1))[0] > M.outcome(M.score_matrix(1.2, 1.2, -0.1))[0]


def test_market_probabilities_remove_the_margin():
    p = M.market_probs(np.array([[2.0, 3.4, 3.8]]))
    assert p.sum() == pytest.approx(1.0)
    assert p[0, 0] > p[0, 1] > p[0, 2]


def test_blend_without_odds_keeps_the_model():
    pm = np.array([[0.5, 0.3, 0.2]])
    assert np.allclose(M.blend(pm, np.full((1, 3), np.nan), 0.3, 1.0), pm)
    mixed = M.blend(pm, np.array([[0.2, 0.3, 0.5]]), 1.0, 1.0)
    assert mixed.sum() == pytest.approx(1.0) and mixed[0, 0] < 0.5


def test_rps_rewards_the_right_favourite():
    y = np.array([0])
    assert M.rps(np.array([[0.7, 0.2, 0.1]]), y)[0] < M.rps(np.array([[0.1, 0.2, 0.7]]), y)[0]
    assert M.rps(np.array([[1.0, 0.0, 0.0]]), y)[0] == pytest.approx(0.0)


def test_table_and_simulation_are_consistent():
    played = pd.DataFrame({"home": ["A", "C"], "away": ["B", "D"], "hg": [2, 0], "ag": [0, 0]})
    t = S.table(played, ["A", "B", "C", "D"])
    assert list(t.index[:1]) == ["A"] and t.loc["A", "pts"] == 3 and t.loc["C", "pts"] == 1
    upcoming = pd.DataFrame({"home": ["A", "B"], "away": ["C", "D"], "lam_h": [1.5, 1.2], "lam_a": [1.0, 1.1]})
    pts, places = S.simulate_places(played, upcoming, ["A", "B", "C", "D"], rho=-0.1)
    assert places.shape == (4, 4)
    assert np.allclose(places.sum(axis=0), 1.0) and np.allclose(places.sum(axis=1), 1.0)
    assert places[0, 0] == places[:, 0].max()              # A, déjà en tête, finit le plus souvent premier
    assert pts[0] >= 3


def test_published_probabilities_are_rounded_and_sum_to_one():
    q = S.round_probs([0.3333, 0.3333, 0.3334])
    assert sum(q) == pytest.approx(1.0) and all(round(x, 2) == x for x in q)


def test_kickoff_times_are_converted_to_utc_and_to_the_paris_day():
    assert S.kickoff_utc(pd.Timestamp("2026-11-21"), "20:45") == "2026-11-21T19:45:00Z"
    assert S.kickoff_utc(pd.Timestamp("2026-08-22"), "21:05") == "2026-08-22T19:05:00Z"
    assert S.kickoff_utc(pd.Timestamp("2026-11-21"), None) is None          # pas d'heure inventée
    assert S.kickoff_utc(pd.Timestamp("2026-11-20"), "19:45", S.LONDON) == "2026-11-20T19:45:00Z"
    assert S.paris_day("2026-11-20T23:30:00Z") == "2026-11-21"               # 0 h 30 à Paris : le lendemain


def test_journal_records_once_respects_the_margin_and_waits_for_odds(tmp_path):
    path = tmp_path / "foot.csv"
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    rows = [{"competition": "F1", "journee": "Journée 11", "jour": "2026-11-20", "kickoff": iso(now + timedelta(hours=5)),
             "home": "FRA:A", "away": "FRA:D", "p": [0.6, 0.25, 0.15], "avec_cotes": True},
            {"competition": "F1", "journee": "Journée 11", "jour": "2026-11-20", "kickoff": iso(now + timedelta(minutes=10)),
             "home": "FRA:B", "away": "FRA:C", "p": [0.5, 0.3, 0.2], "avec_cotes": True},
            {"competition": "F1", "journee": "Journée 12", "jour": "2026-11-29", "kickoff": iso(now + timedelta(days=9)),
             "home": "FRA:C", "away": "FRA:A", "p": [0.5, 0.3, 0.2], "avec_cotes": True},
            {"competition": "LDC", "journee": "Journée 5", "jour": "2026-11-22", "kickoff": iso(now + timedelta(days=2)),
             "home": "FRA:D", "away": "GER:B", "p": [0.5, 0.3, 0.2], "avec_cotes": False},
            {"competition": "LDC", "journee": "Journée 5", "jour": "2026-11-21", "kickoff": None,
             "home": "FRA:E", "away": "GER:F", "p": [0.5, 0.3, 0.2], "avec_cotes": True}]
    # trop tard pour le 2e, trop tôt pour le 3e, le 4e attend ses cotes, le 5e son heure
    assert JR.record(rows, path, now) == 1
    assert JR.record(rows, path, now + timedelta(hours=1)) == 0              # jamais réécrit
    j = JR.read(path)
    assert list(j["domicile"]) == ["FRA:A"] and j.loc[0, "p_dom"] == pytest.approx(0.6)
    played = {j.loc[0, "match_id"]: ("2026-11-20", (0, 2))}
    e = JR.evaluate(path, played, JR.link(path, played))
    assert e[0]["resultat"] == 2 and e[0]["surprise"] and not e[0]["favori_juste"]


def test_a_postponed_match_is_recorded_once_and_judged_on_its_real_result(tmp_path):
    path = tmp_path / "foot.csv"
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    row = {"competition": "F1", "journee": "Journée 11", "jour": "2026-11-21", "kickoff": "2026-11-21T19:45:00Z",
           "home": "FRA:A", "away": "FRA:B", "p": [0.5, 0.3, 0.2], "avec_cotes": True}
    assert JR.record([row], path, now) == 1
    moved = {**row, "jour": "2026-12-16", "kickoff": "2026-12-16T19:45:00Z"}
    assert JR.record([moved], path, datetime(2026, 12, 15, 12, tzinfo=timezone.utc)) == 0      # reporté : pas de second pronostic
    played = {JR.match_id("F1", "FRA:A", "FRA:B", "2026-12-16"): ("2026-12-16", (1, 1))}
    links = JR.link(path, played)
    assert list(links.values()) == [JR.match_id("F1", "FRA:A", "FRA:B", "2026-12-16")]
    # la saison suivante, la même affiche n'est pas jugée avec le vieux pronostic
    later = {JR.match_id("F1", "FRA:A", "FRA:B", "2027-10-02"): ("2027-10-02", (3, 0))}
    assert JR.link(path, later) == {}


def test_matchs_du_jour():
    from football import pipeline as P
    slug = next(iter(P.COMPS.values()))["slug"]
    code = next(iter(P.COMPS))
    files = {slug: {"matchs": [
        {"id": "a", "jour": "2026-11-22", "kickoff": "2026-11-22T19:45:00Z", "home": "X", "away": "Y", "etat": "a_venir", "p": [0.5, 0.3, 0.2], "lam": [1.5, 1.0]},
        {"id": "b", "jour": "2026-11-22", "kickoff": "2026-11-22T14:00:00Z", "home": "Z", "away": "W", "etat": "joue", "score": [1, 0]},
        {"id": "c", "jour": "2026-11-23", "kickoff": "2026-11-23T14:00:00Z", "home": "X", "away": "W", "etat": "a_venir"},
        {"id": "d", "jour": "2026-11-22", "kickoff": None, "home": "Z", "away": "Y", "etat": "reporte"},
    ]}}
    du = P.matchs_du_jour(files, "2026-11-22")
    assert [m["id"] for m in du] == ["b", "a"]
    assert du[1] == {"c": code, "id": "a", "jour": "2026-11-22", "kickoff": "2026-11-22T19:45:00Z", "home": "X", "away": "Y",
                     "etat": "a_venir", "p": [0.5, 0.3, 0.2], "lam": [1.5, 1.0]}
    assert "score" not in du[0] and "lam" not in du[0]


def test_matchs_a_caler():
    """Les buts attendus du direct couvrent les matchs à venir et ceux joués depuis la veille, pas les anciens."""
    from football import pipeline as P
    p = [0.5, 0.3, 0.2]
    files = {"x": {"matchs": [
        {"id": "futur", "jour": "2026-11-25", "etat": "a_venir", "p": p},
        {"id": "sans_date", "jour": None, "etat": "a_venir", "p": p},
        {"id": "sans_pronostic", "jour": "2026-11-25", "etat": "a_venir"},
        {"id": "aujourdhui", "jour": "2026-11-22", "etat": "joue", "p": p},
        {"id": "veille", "jour": "2026-11-21", "etat": "joue", "p": p},
        {"id": "ancien", "jour": "2026-11-10", "etat": "joue", "p": p},
    ]}, "index": {"clubs": {}}}
    assert [m["id"] for m in P.matchs_a_caler(files, "2026-11-21")] == ["futur", "sans_date", "aujourdhui", "veille"]


def test_serie_a_is_enabled_across_pipeline_and_sources():
    from football import joint_backtest as JB
    from football import leagues as L
    from football import names as N
    from football import pipeline as P
    from football import sources as SRC
    assert L.MAIN["I1"] == ("ITA", "Serie A", True)
    assert SRC.FDORG_CODES["I1"] == "SA"
    assert "I1" in JB.TARGET_LEAGUES
    assert P.COMPS["I1"]["slug"] == "serie-a" and P.COMPS["I1"]["of"] == "it.1"
    assert list(P.COMPS).index("SP1") < list(P.COMPS).index("I1") < list(P.COMPS).index("F1")
    assert N.match("ITA", "Hellas Verona FC", ["Verona", "Inter"]) == "Verona"
    assert N.match("ITA", "Parma Calcio 1913", ["Parma", "Milan"]) == "Parma"
    assert P.display("SSC Napoli") == "Napoli"


def test_journal_summary_aggregates_rps_market_habits_and_favourites():
    evals = [
        {"joue_id": "F1|FRA:A|FRA:B|2026-11-21", "competition": "F1", "coup_envoi": "2026-11-21T19:45:00Z",
         "p": [0.7, 0.2, 0.1], "resultat": 0, "favori_juste": True, "surprise": False, "rps": 0.05},
        {"joue_id": "I1|ITA:Inter|ITA:Napoli|2026-11-22", "competition": "I1", "coup_envoi": "2026-11-22T19:45:00Z",
         "p": [0.5, 0.3, 0.2], "resultat": 2, "favori_juste": False, "surprise": False, "rps": 0.445},
    ]
    habits = {"F1": np.array([0.45, 0.27, 0.28]), "I1": np.array([0.44, 0.27, 0.29])}
    market = {"F1|FRA:A|FRA:B|2026-11-21": np.array([0.6, 0.25, 0.15])}
    s = JR.summary(evals, habits, market, pending_count=3, names={"I1": "Serie A", "F1": "Ligue 1"})
    assert s["matchs"] == 2 and s["en_attente"] == 3
    assert s["favoris_justes"] == 1 and s["taux_favori"] == pytest.approx(0.5)
    assert s["premier"] == "2026-11-21" and s["dernier"] == "2026-11-22"
    assert s["matchs_cotes"] == 1 and s["rps_marche"] is not None
    assert s["rps"] < s["rps_habitudes"] or np.isfinite(s["rps_habitudes"])
    assert [c["code"] for c in s["par_competition"]] == ["I1", "F1"]
    assert s["par_competition"][0]["rps_marche"] is None
    assert s["par_competition"][1]["rps_marche"] is not None
    empty = JR.summary([], habits, {}, pending_count=4)
    assert empty == {"matchs": 0, "en_attente": 4, "par_competition": []}


def test_double_horizon_captures_recent_form_without_future_leak():
    from football import joint as J
    rng = np.random.default_rng(7)
    d0 = pd.Timestamp("2025-08-01")
    teams = ["FRA:A", "FRA:B", "FRA:C", "FRA:D"]
    rows = []
    for w in range(30):
        dt = d0 + pd.Timedelta(weeks=w)
        # Sur les 4 dernières semaines, FRA:A marque beaucoup (série de forme)
        hg_a = 4 if w >= 26 else int(rng.poisson(1.2))
        rows.append((dt, "FRA:A", "FRA:B", hg_a, 1, "F1", False, False))
        rows.append((dt, "FRA:C", "FRA:D", 1, 1, "F1", False, False))
    m = pd.DataFrame(rows, columns=["date", "home", "away", "hg", "ag", "league", "is_cup", "neutral"])
    m["hst"] = m["ast"] = np.nan
    cutoff = d0 + pd.Timedelta(weeks=29)
    fit1 = J.fit(m, cutoff, 0.002, 0.0, 0.3)
    m2 = m.copy()
    m2.loc[m2["date"] >= cutoff, ["hg", "ag"]] = 9
    fit2 = J.fit(m2, cutoff, 0.002, 0.0, 0.3)
    assert np.allclose(fit1["att"], fit2["att"]) and np.allclose(fit1["def"], fit2["def"])
    assert fit1["form_att"][fit1["teams"]["FRA:A"]] > 0.01


def test_rest_days_and_last_match_info_are_causal():
    from football import joint as J
    m = pd.DataFrame([
        {"date": pd.Timestamp("2026-11-18"), "home": "FRA:A", "away": "GER:B", "hg": 2, "ag": 1, "league": "LDC"},
        {"date": pd.Timestamp("2026-11-21"), "home": "FRA:A", "away": "FRA:C", "hg": 1, "ag": 0, "league": "F1"},
    ])
    r = J.rest_days(m)
    assert r.loc[0, "repos_dom"] == 14.0
    assert r.loc[1, "repos_dom"] == 3.0 and r.loc[1, "repos_ext"] == 14.0
    info = J.last_match_info(m, pd.Timestamp("2026-11-21"))
    assert info["FRA:A"] == (pd.Timestamp("2026-11-18"), "LDC")
    assert "FRA:C" not in info


def test_confidence_label_uses_volatility_probability_and_new_coach():
    from football import joint_backtest as JB
    assert JB.confidence_label([0.65, 0.20, 0.15], 1.05, 1.10, vol_thresh=1.237) == "elevee"
    assert JB.confidence_label([0.42, 0.30, 0.28], 1.05, 1.10, vol_thresh=1.237) == "indecis"
    assert JB.confidence_label([0.65, 0.20, 0.15], 1.30, 1.25, vol_thresh=1.237) == "imprevisible"
    assert JB.confidence_label([0.58, 0.24, 0.18], 1.05, 1.10, vol_thresh=1.237, new_coach=True) == "imprevisible"


def test_context_scorers_adjustments_and_api_budget(tmp_path, monkeypatch):
    from football import context as CTX
    from football import sources as SRC

    assert CTX.same_player("Kylian Mbappé", "K. Mbappé")
    assert not CTX.same_player("Kylian Mbappé", "Ousmane Dembélé")

    scorers_map = {"FRA:Paris SG": [
        {"nom": "Ousmane Dembélé", "buts": 10, "matchs": 12, "penalties": 1},
        {"nom": "Bradley Barcola", "buts": 7, "matchs": 12, "penalties": 0},
        {"nom": "Vitinha", "buts": 4, "matchs": 12, "penalties": 1},
    ]}
    # Dembélé absent -> Barcola et Vitinha ressortent (2 buteurs max, probas Poisson valides)
    buts = CTX.probable_scorers("FRA:Paris SG", 2.0, scorers_map, {"FRA:Paris SG": 30}, absent_names=["O. Dembélé"])
    assert [b["nom"] for b in buts] == ["Bradley Barcola", "Vitinha"]
    assert all(0.05 <= b["p"] < 1.0 for b in buts)

    # Ajustements bornés et facteurs clés
    adj = CTX.apply_context_adjustments(
        2.0, 1.0, "FRA:Paris SG", "FRA:Lyon", "Paris Saint-Germain", "Lyon",
        [{"nom": "O. Dembélé", "statut": "absent"}, {"nom": "Marquinhos", "statut": "absent"},
         {"nom": "Hakimi", "statut": "absent"}, {"nom": "Mendes", "statut": "absent"}],
        [], {"nom": "Coach A", "recent": False}, {"nom": "Coach B", "recent": True},
        scorers_map, {"FRA:Paris SG": 30, "FRA:Lyon": 18},
        rest_h=3.0, rest_a=7.0, rest_comp_h="Ligue des champions", rest_comp_a="Ligue 1",
    )
    assert 2.0 * (1 + CTX.MAX_LAM_MALUS) - 1e-9 <= adj["lh"] < 2.0
    assert 1.0 <= adj["la"] <= 1.0 * (1 + CTX.MAX_LAM_BONUS) + 1e-9
    assert adj["variance_temp"] == CTX.COACH_VARIANCE_TEMP and adj["new_coach"]
    assert any("Repos court" in f and "Ligue des champions" in f for f in adj["facteurs"])
    assert any("Nouvel entraîneur" in f for f in adj["facteurs"])
    assert any("Absents notables" in f for f in adj["facteurs"])

    # Respect strict de la réserve direct (<= 25 -> arrêt immédiat) et du plafond 15 req/j
    calls = []
    def fake_get(url, headers=None, tries=2):
        calls.append(url)
        return {"errors": [], "response": []}, {"x-ratelimit-requests-remaining": str(CTX.APIFOOT_RESERVE_DIRECT)}
    monkeypatch.setattr(SRC, "_get_json", fake_get)
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    idx = SRC.TeamIndex(["FRA:Paris SG"])
    CTX.fetch_injuries(["2026-11-24", "2026-11-25", "2026-11-26"], "k", tmp_path, now, idx)
    # 1er appel ramène restant == APIFOOT_RESERVE_DIRECT -> les 2 dates suivantes sont sautées
    assert len(calls) == 1
    # Plafond dur 15 req/jour
    SRC.write_json(tmp_path / "apifoot_quota.json", {"jour": "2026-11-24", "appels": CTX.APIFOOT_MAX_JOUR, "restant": 80})
    CTX.fetch_coaches(["FRA:Paris SG"], {"FRA:Paris SG": 85}, "k", tmp_path, now)
    assert len(calls) == 1


def test_predict_includes_btts_and_confidence():
    from football import pipeline as P
    fit = {"teams": {"FRA:A": 0, "FRA:B": 1}, "att": np.array([0.3, -0.1]), "def": np.array([0.1, -0.2]),
           "league": {"FRA:A": "F1", "FRA:B": "F1"}, "league_level": {"F1": (0.0, 0.0)},
           "mu": 0.2, "home": 0.25, "home_cup": 0.2, "converged": True}
    bt = {"a": 0.3, "b": 0.8, "volatility": {"FRA:A": 1.0, "FRA:B": 1.05}, "vol_thresh": 1.237}
    r = {"competition": "F1", "home": "FRA:A", "away": "FRA:B", "neutral": False, "oh": np.nan, "od": np.nan, "oa": np.nan, "jour": "2026-11-25"}
    pr = P.predict(fit, r, bt)
    assert 0.0 < pr["btts"] < 1.0 and 0.0 < pr["plus25"] < 1.0
    assert pr["confiance"] in ("elevee", "indecis", "imprevisible")


# ---------------------------------------------------------------- buteurs : titulaires réguliers

def _buteur(nom, buts, matchs, comp="LDC"):
    return {"nom": nom, "buts": buts, "matchs": matchs, "penalties": 0, "comp": comp}


def test_scorer_who_misses_too_many_matches_is_not_a_probable_scorer():
    from football import context as CTX
    scorers = {"FRA:Lille": [_buteur("Remplaçant Rare", 5, 2), _buteur("Titulaire Habituel", 4, 5),
                             _buteur("Sans Compteur", 3, 0)]}
    marque = CTX.mark_regular_starters(scorers, {("FRA:Lille", "LDC"): 5}, {})
    buts = CTX.probable_scorers("FRA:Lille", 2.0, marque, {"FRA:Lille": 20}, top=3)
    # 2 matchs sur 5 : écarté ; compteur absent : pas de jugement
    assert [b["nom"] for b in buts] == ["Titulaire Habituel", "Sans Compteur"]


def test_too_few_team_matches_means_no_judgement():
    from football import context as CTX
    scorers = {"FRA:Lille": [_buteur("Début De Saison", 3, 1)]}
    marque = CTX.mark_regular_starters(scorers, {("FRA:Lille", "LDC"): 2}, {})
    assert CTX.probable_scorers("FRA:Lille", 2.0, marque, {"FRA:Lille": 10})


def test_lineups_override_appearances_and_drop_a_regular_substitute():
    from football import context as CTX
    scorers = {"FRA:Lille": [_buteur("Olivier Giroud", 5, 5), _buteur("Jonathan David", 4, 5)]}
    compos = {"FRA:Lille": [["J. David", "X Un"], ["Jonathan David"], ["Jonathan David"],
                            ["Jonathan David", "Olivier Giroud"], ["Jonathan David"]]}
    marque = CTX.mark_regular_starters(scorers, {("FRA:Lille", "LDC"): 5}, compos)
    assert [b["nom"] for b in CTX.probable_scorers("FRA:Lille", 2.0, marque, {"FRA:Lille": 20})] == ["Jonathan David"]


def test_scorers_keep_their_competition_and_team_matches_ignore_qualifiers():
    from football import context as CTX
    from football import sources as SRC
    js = {"LDC": {"scorers": [{"player": {"name": "A Buteur"}, "team": {"name": "Lille", "area": {"code": "FRA"}},
                               "goals": 3, "playedMatches": 4}]}}
    assert CTX.scorers_by_team(js, SRC.TeamIndex(["FRA:Lille"]))["FRA:Lille"][0]["comp"] == "LDC"
    cal = {"LDC": pd.DataFrame([
        {"home": "FRA:Lille", "away": "GER:Bayern", "played": True, "stage": "LEAGUE_STAGE"},
        {"home": "FRA:Lille", "away": "AUT:LASK", "played": True, "stage": "QUALIFICATION_ROUND_3"},
        {"home": "ITA:Inter", "away": "FRA:Lille", "played": False, "stage": "LEAGUE_STAGE"},
    ]), "LEC": pd.DataFrame()}
    assert CTX.team_match_counts(cal)[("FRA:Lille", "LDC")] == 1


def test_lineups_are_read_when_the_plan_returns_them(tmp_path, monkeypatch):
    from football import context as CTX
    from football import sources as SRC
    monkeypatch.setattr(CTX.time, "sleep", lambda s: None)
    appels = []

    def faux(url, headers=None, tries=3):
        appels.append((url, headers))
        m = {"utcDate": "2026-11-20T20:00:00Z", "homeTeam": {"id": 5, "lineup": [{"name": "Harry Kane"}]},
             "awayTeam": {"id": 9, "lineup": [{"name": "Autre"}]}}
        return {"matches": [m]}, {}

    monkeypatch.setattr(SRC, "_get_json", faux)
    now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    assert CTX.fetch_lineups({"GER:Bayern": 5}, "jeton", tmp_path, now) == {"GER:Bayern": [["Harry Kane"]]}
    assert appels[0][1]["X-Unfold-Lineups"] == "true"
    CTX.fetch_lineups({"GER:Bayern": 5}, "jeton", tmp_path, now + timedelta(hours=1))
    assert len(appels) == 1                       # cache


def test_lineups_absent_from_the_free_plan_stop_after_one_call(tmp_path, monkeypatch):
    from football import context as CTX
    from football import sources as SRC
    monkeypatch.setattr(CTX.time, "sleep", lambda s: None)
    appels = []

    def faux(url, headers=None, tries=3):
        appels.append(url)
        return {"matches": [{"utcDate": "2026-11-20T20:00:00Z", "homeTeam": {"id": 5}, "awayTeam": {"id": 9}}]}, {}

    monkeypatch.setattr(SRC, "_get_json", faux)
    now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    clubs = {"GER:Bayern": 5, "FRA:Lille": 9}
    assert CTX.fetch_lineups(clubs, "jeton", tmp_path, now) == {}
    assert CTX.fetch_lineups(clubs, "jeton", tmp_path, now + timedelta(days=2)) == {}
    assert len(appels) == 1


# ---------------------------------------------------------------- presse : flux RSS

def _rss(*items):
    corps = "".join(f"<item><title>{t}</title><description><![CDATA[{d}]]></description><pubDate>{p}</pubDate></item>"
                    for t, d, p in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>{corps}</channel></rss>'.encode("utf-8")


SQUADS = {"GER:Bayern Munich": ["Harry Kane", "Michael Olise", "Jamal Musiala", "Manuel Neuer"],
          "FRA:Lille": ["Olivier Giroud", "Hákon Haraldsson"],
          "ENG:Man United": ["Rasmus Højlund", "Leny Yoro"]}


def _alias():
    from football import context as CTX
    return {"GER:Bayern Munich": CTX.club_aliases("Bayern Munich", "FC Bayern München"),
            "FRA:Lille": CTX.club_aliases("Lille", "Lille OSC"),
            "ENG:Man United": CTX.club_aliases("Manchester United", "Man United")}


def _signales(titre, resume=""):
    from football import context as CTX
    trouve = CTX.detect_press_absences([{"titre": titre, "resume": resume, "date": 0}], SQUADS, _alias())
    return {(t, x["nom"], x["statut"]) for t, xs in trouve.items() for x in xs}


def test_rss_parser_reads_titles_summaries_and_dates_and_strips_html():
    from football import context as CTX
    items = CTX.parse_rss(_rss(("Kane forfait", "<p>Le <b>Bayern</b> sans son buteur&nbsp;</p>", "Tue, 24 Nov 2026 20:00:00 +0100"),
                               ("Sans date", "x", "")))
    assert len(items) == 1                                    # sans date : impossible de dire si c'est récent
    assert items[0]["titre"] == "Kane forfait"
    assert items[0]["resume"] == "Le Bayern sans son buteur"
    assert items[0]["date"] == datetime(2026, 11, 24, 19, tzinfo=timezone.utc).timestamp()


@pytest.mark.parametrize("mauvais", [b"", b"<html>404</html", b"pas du xml",
                                     b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>'])
def test_rss_parser_returns_nothing_for_broken_or_unsafe_documents(mauvais):
    from football import context as CTX
    assert CTX.parse_rss(mauvais) == []


@pytest.mark.parametrize("titre,nom", [
    ("Bayern : Harry Kane forfait contre Lille", "Harry Kane"),
    ("Blessé, Kane manquera le déplacement du Bayern", "Harry Kane"),
    ("Bayern's Kane ruled out of Lille trip", "Harry Kane"),
    ("Kane is out for Bayern", "Harry Kane"),
    ("FC Bayern: Kane verletzt", "Harry Kane"),
    ("El Bayern pierde a Kane: baja ante el Lille", "Harry Kane"),
    ("Bayern, infortunio per Kane", "Harry Kane"),
    ("Hojlund injured as Man United count the cost", "Rasmus Højlund"),
])
def test_press_absence_in_each_language(titre, nom):
    assert any(n == nom for _, n, _ in _signales(titre)), titre


def test_press_lists_several_absentees_and_flags_doubts():
    assert _signales("Bayern : Kane et Olise forfaits à Lille") == {
        ("GER:Bayern Munich", "Harry Kane", "absent"), ("GER:Bayern Munich", "Michael Olise", "absent")}
    assert _signales("Lille : Giroud incertain face au Bayern") == {("FRA:Lille", "Olivier Giroud", "incertain")}


@pytest.mark.parametrize("titre", [
    "Bayern : Kane de retour après sa blessure",
    "Kane is back from injury for Bayern",
    "Bayern: Kane nach Verletzung zurück",
    "Kane scores in injury time for Bayern",
    "Bayern knocked out despite Kane double",
    "Bayern: Kane n'est pas blessé",
    "Harry Kane forfait",                                     # aucun club cité
    "Bayern : un supporter blessé avant le match, Kane marque un triplé magnifique et offre la victoire",
    "Bayern: Tuchel injured",                                 # hors effectif
    "Bayern forfait pour le kane",                            # nom sans majuscule
    "El Bayern, en baja forma sin Kane",
])
def test_press_ignores_returns_unrelated_keywords_and_unknown_people(titre):
    assert _signales(titre) == set(), titre


def test_press_attaches_the_keyword_to_the_nearest_player_only():
    assert {n for _, n, _ in _signales("Bayern: Kane scores twice past injured Neuer")} == {"Manuel Neuer"}
    assert {n for _, n, _ in _signales("Bayern: Kane scores as Olise ruled out")} == {"Michael Olise"}


def test_press_reads_the_summary_with_the_club_named_in_the_title():
    assert _signales("Le Bayern inquiet", "Jamal Musiala, blessé à la cheville, ne fera pas le voyage.") == {
        ("GER:Bayern Munich", "Jamal Musiala", "absent")}


def test_shared_surname_needs_the_first_name_or_initial():
    from football import context as CTX
    squads = {"ESP:Barcelona": ["Eric Garcia", "Joan Garcia"]}
    alias = {"ESP:Barcelona": CTX.club_aliases("Barcelona")}

    def item(t):
        return [{"titre": t, "resume": "", "date": 0}]

    assert CTX.detect_press_absences(item("Barcelona: Garcia injured"), squads, alias) == {}
    got = CTX.detect_press_absences(item("Barcelona: Joan Garcia injured"), squads, alias)
    assert [x["nom"] for x in got["ESP:Barcelona"]] == ["Joan Garcia"]


def test_press_fetch_keeps_7_days_caches_6_hours_and_fails_silently(tmp_path):
    from football import context as CTX
    now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    appels = []

    def flux(url, timeout):
        appels.append((url, timeout))
        if "bbc" in url:
            raise TimeoutError("trop long")
        return _rss(("Kane forfait Bayern", "", "Fri, 20 Nov 2026 22:00:00 +0100"),     # 5 jours : gardé
                    ("Vieille nouvelle", "", "Tue, 17 Nov 2026 20:00:00 +0100"))          # plus de 7 jours

    items = CTX.fetch_press(tmp_path, now, fetch=flux)
    assert {i["titre"] for i in items} == {"Kane forfait Bayern"}
    assert CTX.RSS_TIMEOUT_S == 5 and all(t == 5 for _, t in appels)
    n = len(appels)
    CTX.fetch_press(tmp_path, now + timedelta(hours=5), fetch=flux)
    assert len(appels) == n + 1                  # seul le flux en panne est réessayé

    def panne(url, timeout):
        raise OSError("réseau coupé")

    assert CTX.fetch_press(tmp_path, now + timedelta(hours=7), fetch=panne)      # le cache reste servi
    assert CTX.fetch_press(tmp_path, now + timedelta(days=3), fetch=panne) == []   # puis il vieillit
    assert CTX.fetch_press(tmp_path / "vide", now, fetch=panne) == []


def test_offline_press_uses_the_cache_only(tmp_path):
    from football import context as CTX

    def interdit(url, timeout):
        raise AssertionError("aucun réseau hors ligne")

    assert CTX.fetch_press(tmp_path, datetime(2026, 11, 25, tzinfo=timezone.utc), offline=True, fetch=interdit) == []


def test_squads_come_from_the_teams_file_or_the_team_endpoint(tmp_path, monkeypatch):
    from football import context as CTX
    from football import sources as SRC
    monkeypatch.setattr(CTX.time, "sleep", lambda s: None)
    appels = []

    def faux(url, headers=None, tries=3):
        appels.append(url)
        return {"squad": [{"name": "Harry Kane"}]}, {}

    monkeypatch.setattr(SRC, "_get_json", faux)
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    teams = {"FRA:Lille": {"id": 521, "squad": [{"name": "Olivier Giroud"}]}, "GER:Bayern Munich": {"id": 5}}
    scorers = {"ITA:Inter": [_buteur("Lautaro Martínez", 4, 5)]}
    got = CTX.squad_names(["FRA:Lille", "GER:Bayern Munich", "ITA:Inter"], teams, scorers, "jeton", tmp_path, now)
    assert got == {"FRA:Lille": ["Olivier Giroud"], "GER:Bayern Munich": ["Harry Kane"], "ITA:Inter": ["Lautaro Martínez"]}
    assert appels == ["https://api.football-data.org/v4/teams/5"]
    CTX.squad_names(["GER:Bayern Munich"], teams, scorers, "jeton", tmp_path, now + timedelta(days=1))
    assert len(appels) == 1


def test_press_absentee_leaves_scorers_and_appears_in_factors_without_touching_lambda():
    from football import context as CTX
    scorers = {"GER:Bayern": [_buteur("Harry Kane", 12, 5), _buteur("Michael Olise", 5, 5), _buteur("Luis Díaz", 4, 5)]}
    base = dict(lh=1.0, la=2.0, home_id="FRA:Lille", away_id="GER:Bayern", home_nom="Lille", away_nom="Bayern Munich",
                injuries_h=[], injuries_a=[], coach_h=None, coach_a=None, scorers_map=scorers, team_goals={"GER:Bayern": 25})
    presse = [{"nom": "Harry Kane", "statut": "absent"}, {"nom": "Michael Olise", "statut": "incertain"}]
    adj = CTX.apply_context_adjustments(**base, presse_a=presse)
    assert "Absents signalés (presse, Bayern Munich) : Harry Kane, Michael Olise (incertain)" in adj["facteurs"]
    assert [b["nom"] for b in adj["buteurs"]["ext"]] == ["Luis Díaz"]
    assert adj["exclus"]["ext"] == ["Harry Kane", "Michael Olise"]
    # variable non validable par backtest (CLAUDE.md) : elle ne modifie aucun nombre du modèle
    for injuries in ([], [{"nom": "H. Kane", "statut": "absent"}]):
        sans = CTX.apply_context_adjustments(**{**base, "injuries_a": injuries})
        avec = CTX.apply_context_adjustments(**{**base, "injuries_a": injuries}, presse_a=presse, presse_h=presse)
        assert (avec["lh"], avec["la"], avec["variance_temp"]) == (sans["lh"], sans["la"], sans["variance_temp"])


def test_predict_drops_press_absentees_from_the_final_scorers():
    from football import pipeline as P
    fit = {"teams": {"FRA:A": 0, "FRA:B": 1}, "att": np.array([0.3, 0.2]), "def": np.array([0.0, 0.0]),
           "league": {"FRA:A": "F1", "FRA:B": "F1"}, "league_level": {"F1": (0.0, 0.0)},
           "mu": 0.2, "home": 0.25, "home_cup": 0.2, "converged": True}
    bt = {"a": 0.3, "b": 0.8, "volatility": {}, "vol_thresh": 1.237}
    r = {"competition": "F1", "home": "FRA:A", "away": "FRA:B", "neutral": False,
         "oh": 2.0, "od": 3.4, "oa": 3.8, "jour": "2026-11-26"}     # avec cotes : les buteurs sont recalculés
    ctx = {"rest_for": lambda t, j: (None, None), "injuries": {}, "coaches": {}, "team_goals": {},
           "scorers": {"FRA:A": [_buteur("Premier Buteur", 8, 5, "F1"), _buteur("Second Buteur", 5, 5, "F1")]},
           "presse": {"FRA:A": [{"nom": "Premier Buteur", "statut": "incertain"}]}, "nom": lambda t: t[4:]}
    pr = P.predict(fit, r, bt, ctx)
    assert [b["nom"] for b in pr["buteurs"]["dom"]] == ["Second Buteur"]
    # mêmes probabilités publiées (celles du journal) avec ou sans la presse, avec ou sans cotes
    for match in (r, {**r, "oh": np.nan, "od": np.nan, "oa": np.nan}):
        avec, sans = P.predict(fit, match, bt, ctx), P.predict(fit, match, bt, {**ctx, "presse": {}})
        for cle in ("p", "lam", "xg", "scores", "plus25", "btts", "confiance"):
            assert np.array_equal(avec[cle], sans[cle]), cle


@pytest.mark.parametrize("titre", [
    "Bayern: Kane is without a doubt the best striker",
    "Bayern: Kane is out to prove his critics wrong",
    "Bayern's Kane out for revenge against Lille",
    "El Bayern: Kane puso en duda el arbitraje",
])
def test_press_ignores_common_idioms(titre):
    assert _signales(titre) == set(), titre


def test_press_comma_after_the_absentee_does_not_catch_the_next_subject():
    assert {n for _, n, _ in _signales("Bayern : en l'absence de Kane, Olise a brillé")} == {"Harry Kane"}
    assert {n for _, n, _ in _signales("Bayern, les forfaits : Kane, Olise")} == {"Harry Kane", "Michael Olise"}
    assert {n for _, n, _ in _signales("Bayern, forfaits de Kane, Olise et Musiala")} == {
        "Harry Kane", "Michael Olise", "Jamal Musiala"}


def test_barcelona_nicknames_do_not_designate_espanyol():
    from football import context as CTX
    squads = {"ESP:Espanol": ["Pere Garcia"]}
    alias = {"ESP:Espanol": CTX.club_aliases("RCD Espanyol de Barcelona", "Espanyol")}
    item = [{"titre": "Barça : Garcia forfait", "resume": "", "date": 0}]
    assert CTX.detect_press_absences(item, squads, alias) == {}


def test_press_fetch_remembers_articles_that_left_the_feed_for_7_days(tmp_path):
    """Un flux chargé ne montre que ses derniers articles : sans mémoire, la fenêtre de 7 jours ne servirait à rien."""
    from football import context as CTX
    now = datetime(2026, 11, 21, 8, tzinfo=timezone.utc)
    contenu = {"corps": _rss(("Kane forfait Bayern", "", "Fri, 20 Nov 2026 22:00:00 +0100"))}

    def flux(url, timeout):
        return contenu["corps"]

    CTX.fetch_press(tmp_path, now, fetch=flux)
    contenu["corps"] = _rss(("Autre nouvelle", "", "Wed, 25 Nov 2026 08:00:00 +0100"))
    titres = [i["titre"] for i in CTX.fetch_press(tmp_path, now + timedelta(days=4, hours=2), fetch=flux)]
    assert sorted(titres) == ["Autre nouvelle", "Kane forfait Bayern"]          # une seule fois chacun
    contenu["corps"] = _rss(("Nouvelle du 28", "", "Sat, 28 Nov 2026 08:00:00 +0100"))
    titres = [i["titre"] for i in CTX.fetch_press(tmp_path, datetime(2026, 11, 28, 12, tzinfo=timezone.utc), fetch=flux)]
    assert "Kane forfait Bayern" not in titres


def test_press_feeds_include_international_champions_league_coverage():
    from football import context as CTX
    urls = " ".join(CTX.RSS_FEEDS.values())
    assert "theguardian.com/football/rss" in urls and "theguardian.com/football/championsleague/rss" in urls
    assert "skysports.com" in urls and "espn.com" in urls


# ---------------------------------------------------------------- API-Football : noms de clubs en coupe d'Europe

def _blessure(equipe, team_id, joueur, ligue, motif="Ankle Injury", genre="Missing Fixture"):
    return {"league": {"id": ligue}, "team": {"id": team_id, "name": equipe},
            "player": {"name": joueur, "type": genre, "reason": motif}}


def _blessures_lues(tmp_path, items):
    from football import context as CTX
    from football import sources as SRC
    now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    SRC.write_json(tmp_path / "injuries_2026-11-25.json", {"fetched": now.timestamp(), "items": items})
    idx = SRC.TeamIndex(["GER:Bayern Munich", "FRA:Lille"])
    return CTX.fetch_injuries(["2026-11-25"], None, tmp_path, now, idx)


def test_cup_injuries_are_kept_when_api_football_uses_the_local_club_name(tmp_path):
    """Cas réel du 25 novembre 2026 : « Bayern München » en Ligue des champions (pays inconnu) était jeté."""
    injuries, team_ids = _blessures_lues(tmp_path, [_blessure("Bayern München", 157, "H. Kane", 2),
                                                    _blessure("Lille", 79, "H. Igamane", 2)])
    kane = injuries[("2026-11-25", "GER:Bayern Munich")]
    assert [(x["nom"], x["statut"], x.get("hors_modele")) for x in kane] == [("H. Kane", "absent", True)]
    assert "hors_modele" not in injuries[("2026-11-25", "FRA:Lille")][0]     # reconnu directement : inchangé
    # club récupéré : pas ajouté au suivi des entraîneurs, qui peut modifier les probabilités
    assert team_ids == {"FRA:Lille": 79}


def test_unknown_cup_club_is_reported_in_the_log(tmp_path, capsys):
    injuries, _ = _blessures_lues(tmp_path, [_blessure("Club Inconnu", 1, "X. Joueur", 2)])
    assert injuries == {}
    assert "Club Inconnu" in capsys.readouterr().out


def test_recovered_cup_absentees_leave_scorers_and_appear_without_touching_lambda():
    from football import context as CTX
    scorers = {"GER:Bayern": [_buteur("Harry Kane", 12, 5), _buteur("Michael Olise", 5, 5), _buteur("Luis Díaz", 4, 5)]}
    base = dict(lh=1.0, la=2.0, home_id="FRA:Lille", away_id="GER:Bayern", home_nom="Lille", away_nom="Bayern Munich",
                injuries_h=[], injuries_a=[], coach_h=None, coach_a=None, scorers_map=scorers, team_goals={"GER:Bayern": 25})
    recuperes = [{"nom": n, "statut": "absent", "hors_modele": True}
                 for n in ("H. Kane", "M. Olise", "S. Gnabry", "M. Neuer")]
    sans = CTX.apply_context_adjustments(**base)
    avec = CTX.apply_context_adjustments(**{**base, "injuries_a": recuperes})
    assert (avec["lh"], avec["la"], avec["variance_temp"]) == (sans["lh"], sans["la"], sans["variance_temp"])
    assert "Absents notables (Bayern Munich) : Harry Kane, Michael Olise (+2)" in avec["facteurs"]
    assert [b["nom"] for b in avec["buteurs"]["ext"]] == ["Luis Díaz"]


@pytest.mark.parametrize("titre", [
    "El Bayern ha perdido 130 goles por las lesiones de Kane y Olise",      # titre réel d'AS, 25 novembre 2026
    "El Bayern, sin los lesionados Kane y Olise",
    "Bayern : les blessures de Kane et Olise changent tout",
    "Bayern count the cost of injuries to Kane and Olise",
    "Bayern, gli infortuni di Kane e Olise",
])
def test_press_reads_plural_injury_words(titre):
    assert {n for _, n, _ in _signales(titre)} == {"Harry Kane", "Michael Olise"}, titre


@pytest.mark.parametrize("titre", [
    "Bayern report no injuries to Kane and Olise",
    "Bayern: no new injuries, Kane says",
    "Bayern : pas de blessures pour Kane et Olise",
    "Bayern : Kane et Olise sortent sans blessures",
    "El Bayern, sin lesiones para Kane y Olise",
    "Bayern, nessun infortunio per Kane",
    "Bayern, senza infortuni Kane e Olise",
])
def test_press_ignores_plural_denials(titre):
    assert _signales(titre) == set(), titre


# noms lus dans le journal du calcul du 25 novembre 2026 ; identifiants lus dans les données publiées
@pytest.mark.parametrize("nom_apifoot,club", [
    ("Ararat-Armenia", "ARM:FC Ararat-Armenia"),
    ("Celje", "SVN:NK Celje"),
    ("Levski Sofia", "BUL:PFC Levski Sofia"),
    ("Omonia Nicosia", "CYP:Omonia Nikosia"),
    ("Plzen", "CZE:Viktoria Plzeň"),
    ("Sabah FA", "AZE:Sabah FK"),
    ("Union St. Gilloise", "BEL:St. Gilloise"),
])
def test_cup_injuries_are_recovered_for_api_football_spellings(tmp_path, capsys, nom_apifoot, club):
    injuries, team_ids = _blessures_lues(tmp_path, [_blessure(nom_apifoot, 1, "X. Joueur", 3)])
    assert [(x["nom"], x.get("hors_modele")) for x in injuries[("2026-11-25", club)]] == [("X. Joueur", True)]
    assert team_ids == {}                                   # ni buts attendus, ni suivi des entraîneurs
    assert "non reconnus" not in capsys.readouterr().out


def test_api_football_cup_spellings_stay_out_of_the_shared_name_tables():
    """`names.py` sert aussi à rapprocher les cotes : y ajouter ces noms pourrait changer des probabilités."""
    from football import context as CTX
    from football import names as N
    assert not set(CTX.APIFOOT_NOMS_COUPE) & (set(N.NO_COUNTRY) | {source for _, source in N.MANUAL})
