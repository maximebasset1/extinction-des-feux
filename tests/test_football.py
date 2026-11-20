"""Tests du modèle Ligue 1 : python -m pytest tests -q"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import config as C  # noqa: E402
from football import main as F  # noqa: E402
from football import model as M  # noqa: E402
from football import season as S  # noqa: E402


def matches(n_weeks=60, seed=1):
    """Petit championnat fictif : A est nettement la meilleure équipe."""
    rng = np.random.default_rng(seed)
    teams, strength = ["A", "B", "C", "D"], {"A": 0.6, "B": 0.1, "C": -0.1, "D": -0.4}
    rows, d0 = [], pd.Timestamp("2020-01-04")
    for w in range(n_weeks):
        for k, (h, a) in enumerate([(teams[(w + i) % 4], teams[(w + i + 1 + w % 3) % 4]) for i in range(2)]):
            if h == a:
                continue
            lh, la = np.exp(0.25 + strength[h] - strength[a]), np.exp(strength[a] - strength[h])
            rows.append({"date": d0 + pd.Timedelta(weeks=w, days=k), "home": h, "away": a,
                         "hg": rng.poisson(lh), "ag": rng.poisson(la), "hst": np.nan, "ast": np.nan})
    return pd.DataFrame(rows)


def test_score_matrix_is_a_distribution():
    for rho in (0.0, -0.1, -0.2):
        mat = M.score_matrix(1.6, 1.1, rho)
        assert mat.min() >= 0
        assert mat.sum() == pytest.approx(1.0, abs=1e-6)
        assert M.outcome(mat).sum() == pytest.approx(1.0, abs=1e-6)


def test_stronger_attack_means_more_home_wins():
    assert M.outcome(M.score_matrix(2.2, 0.8, -0.1))[0] > M.outcome(M.score_matrix(1.2, 1.2, -0.1))[0]


def test_market_probabilities_remove_the_margin():
    p = M.market_probs(np.array([[2.0, 3.4, 3.8]]))
    assert p.sum() == pytest.approx(1.0)
    assert p[0, 0] > p[0, 1] > p[0, 2]


def test_blend_without_odds_keeps_the_model():
    pm = np.array([[0.5, 0.3, 0.2]])
    out = M.blend(pm, np.full((1, 3), np.nan), 0.3, 1.0)
    assert np.allclose(out, pm)
    mixed = M.blend(pm, np.array([[0.2, 0.3, 0.5]]), 1.0, 1.0)
    assert mixed.sum() == pytest.approx(1.0) and mixed[0, 0] < 0.5


def test_rps_rewards_the_right_favourite():
    good, bad = np.array([[0.7, 0.2, 0.1]]), np.array([[0.1, 0.2, 0.7]])
    y = np.array([0])
    assert M.rps(good, y)[0] < M.rps(bad, y)[0]
    assert M.rps(np.array([[1.0, 0.0, 0.0]]), y)[0] == pytest.approx(0.0)


def test_fit_never_uses_matches_after_the_cutoff():
    m = matches()
    cutoff = m["date"].iloc[len(m) // 2]
    a = M.fit(m, cutoff, xi=0.003, s=0.0, sot_ratio=0.3)
    changed = m.copy()
    changed.loc[changed["date"] >= cutoff, ["hg", "ag"]] = 9
    b = M.fit(changed, cutoff, xi=0.003, s=0.0, sot_ratio=0.3)
    assert np.allclose(a["att"], b["att"]) and np.allclose(a["def"], b["def"])


def test_fit_finds_the_best_team():
    m = matches(120)
    fit = M.fit(m, m["date"].max() + pd.Timedelta(days=1), xi=0.001, s=0.0, sot_ratio=0.3)
    lh, la = M.rates(fit, "A", "D")
    assert lh > la


def test_table_and_simulation_are_consistent():
    played = pd.DataFrame({"home": ["A", "C"], "away": ["B", "D"], "hg": [2, 0], "ag": [0, 0]})
    t = S.table(played, ["A", "B", "C", "D"])
    assert list(t.index[:1]) == ["A"] and t.loc["A", "pts"] == 3 and t.loc["C", "pts"] == 1
    upcoming = pd.DataFrame({"home": ["A", "B"], "away": ["C", "D"], "lam_h": [1.5, 1.2], "lam_a": [1.0, 1.1]})
    sim = S.simulate(played, upcoming, ["A", "B", "C", "D"], rho=-0.1)
    assert sim["titre"].sum() == pytest.approx(1.0)
    assert sim["relegation"].sum() == pytest.approx(2.0)
    for places in sim["places"]:
        assert sum(places) == pytest.approx(1.0, abs=1e-3)
    assert sim.iloc[0]["club"] == "A"


def test_journal_records_once_and_respects_the_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "JOURNAL", tmp_path / "ligue1.csv")
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    fx = pd.DataFrame({
        "played": [False, False, False, False],
        "kickoff": [iso(now + timedelta(hours=5)), iso(now + timedelta(minutes=10)), iso(now + timedelta(days=9)),
                    iso(now + timedelta(days=2))],
        "round": [11, 11, 12, 11], "home": ["A", "B", "C", "D"], "away": ["D", "C", "A", "B"],
        "p": [[0.5, 0.3, 0.2]] * 4, "with_market": [True, True, True, False]})
    # trop tard pour le 2e, trop tôt pour le 3e, le 4e attend encore ses cotes
    assert F.record_journal(fx, now) == 1
    assert F.record_journal(fx, now + timedelta(hours=1)) == 0   # jamais réécrit
    j = pd.read_csv(C.JOURNAL)
    assert list(j["domicile"]) == ["A"] and j.loc[0, "p_dom"] == pytest.approx(0.5)


def test_kickoff_times_are_converted_to_utc():
    assert S.kickoff_utc(pd.Timestamp("2026-11-21"), "20:45") == "2026-11-21T19:45:00Z"
    assert S.kickoff_utc(pd.Timestamp("2026-08-22"), "21:05") == "2026-08-22T19:05:00Z"
    assert S.kickoff_utc(pd.Timestamp("2026-11-21"), None) is None          # pas d'heure inventée
    assert S.kickoff_utc(pd.Timestamp("2026-11-20"), "19:45", S.LONDON) == "2026-11-20T19:45:00Z"
    assert S.kickoff_utc(pd.Timestamp("2026-08-21"), "19:45", S.LONDON) == "2026-08-21T18:45:00Z"


def test_promoted_team_keeps_its_prior_all_season():
    m = matches(120)
    m["season"] = np.where(m["date"] < pd.Timestamp("2021-07-01"), 2020, 2021)
    m = m[~((m["season"] == 2020) & ((m["home"] == "D") | (m["away"] == "D")))]   # D est promu en 2021
    cutoff = m.loc[m["season"] == 2021, "date"].sort_values().iloc[10]
    prior = M._prior(m[m["date"] < cutoff], ["A", "B", "C", "D"], cutoff, {"promoted": (-0.2, -0.1)})
    assert prior[3] == pytest.approx(-0.2) and prior[7] == pytest.approx(-0.1)
    assert prior[:3].tolist() == [0, 0, 0]


def test_published_probabilities_are_rounded_and_sum_to_one():
    q = S.round_probs([0.3333, 0.3333, 0.3334])
    assert sum(q) == pytest.approx(1.0) and all(round(x, 2) == x for x in q)
