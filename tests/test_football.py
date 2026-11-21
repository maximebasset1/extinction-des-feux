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
