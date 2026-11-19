"""Tests : python -m pytest tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features import ewm_mean, features_for_race, qualifying_table  # noqa: E402
from model import pole_probabilities  # noqa: E402


def test_probabilities_sum_to_one_and_are_fair():
    p = pole_probabilities(np.array([0.3, 0.3, 0.3, 1.0]), sigma=0.3)
    assert p.sum() == pytest.approx(1.0)
    assert p[0] == pytest.approx(p[1]) == pytest.approx(p[2])
    assert p[3] < p[0]


def test_probabilities_match_monte_carlo():
    mu, sigma = np.array([0.0, 0.2, 0.5, 0.9]), 0.3
    rng = np.random.default_rng(0)
    draws = mu + sigma * rng.standard_normal((200_000, len(mu)))
    mc = np.bincount(draws.argmin(axis=1), minlength=len(mu)) / len(draws)
    assert np.allclose(pole_probabilities(mu, sigma), mc, atol=0.005)


def test_ewm_gives_more_weight_to_recent_races():
    assert ewm_mean(np.array([1.0, 0.0])) < 0.5          # la dernière course (0.0) pèse plus
    assert ewm_mean(np.array([np.nan, 0.4])) == pytest.approx(0.4)


def fake_season():
    rows = []
    for k in range(1, 7):
        for drv, team, d in [("AAA", "T1", 0.0), ("BBB", "T1", 0.5), ("CCC", "T2", 1.0)]:
            rows.append(dict(season=2026, date=f"2026-0{k}-01", grand_prix=f"GP{k}", session="Qualifying",
                             driver=drv, team=team, best_lap=90 * (1 + d / 100), deficit_pct=d,
                             wet=False, downforce="low", street=False))
    return pd.DataFrame(rows)


def test_features_do_not_use_the_race_being_predicted():
    best = fake_season()
    q = qualifying_table(best, 4.0)
    drivers = pd.DataFrame({"driver": ["AAA", "BBB", "CCC"], "team": ["T1", "T1", "T2"]})
    before = features_for_race(q, 2026, 6, "GP6", "low", drivers)
    best.loc[best["grand_prix"] == "GP6", "deficit_pct"] = [3.0, 0.0, 0.0]   # on change la course 6
    after = features_for_race(qualifying_table(best, 4.0), 2026, 6, "GP6", "low", drivers)
    pd.testing.assert_frame_equal(before, after)
    assert before.set_index("driver").loc["AAA", "forme_pilote"] == pytest.approx(0.0)


def test_grid_version_matches_single_sigma():
    from model import pole_probabilities_grid
    mu = np.array([0.0, 0.2, 0.5, 0.9])
    grid = pole_probabilities_grid(mu, np.array([0.2, 0.4]), 4)
    assert np.allclose(grid[0], pole_probabilities(mu, 0.2, 4), atol=1e-3)
    assert np.allclose(grid[1], pole_probabilities(mu, 0.4, 4), atol=1e-3)


def test_logit_learns_that_faster_drivers_take_pole():
    from model import fit_logit, logit_probabilities
    rng = np.random.default_rng(0)
    rows = []
    for race in range(60):
        pace = rng.normal(0, 0.3, 10)
        actual = pace + rng.normal(0, 0.1, 10)
        for i in range(10):
            rows.append(dict(season=2026, grand_prix=f"R{race}", forme=pace[i], is_pole=actual[i] == actual.min()))
    t = pd.DataFrame(rows)
    w = fit_logit(t, ["forme"])
    assert w[0] > 0                                   # plus d'écart = moins de chances
    p = logit_probabilities(t[t["grand_prix"] == "R0"], ["forme"], w)
    assert p.sum() == pytest.approx(1.0)


def test_race_prediction_without_grid_sums_to_one():
    from race_model import predict_race
    entrants = pd.DataFrame({"driver": ["AAA", "BBB", "CCC"], "team": ["T1", "T1", "T2"]})
    results = pd.DataFrame(columns=["season", "date", "driver", "finish"])
    poles = pd.Series({"AAA": 0.7, "BBB": 0.2, "CCC": 0.1})
    out = predict_race(None, results, entrants, None, poles, ["log_grille"], np.array([1.9]), n_sim=500)
    assert out["proba_victoire"].sum() == pytest.approx(1.0)
    assert out.iloc[0]["driver"] == "AAA"


def test_journal_records_only_before_the_session_and_only_once(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import journal
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "predictions.csv")
    info = {"sessions": {"Q": "2026-11-21T04:00:00Z", "R": "2026-11-22T04:00:00Z"}}
    pole = pd.DataFrame({"driver": ["AAA", "BBB"], "team": ["T1", "T2"], "p": [0.7, 0.3]})
    win = pd.DataFrame({"driver": ["AAA", "BBB"], "team": ["T1", "T2"], "proba_victoire": [0.6, 0.4]})
    before = datetime(2026, 11, 20, tzinfo=timezone.utc)
    after_q = datetime(2026, 11, 21, 6, tzinfo=timezone.utc)
    n1 = journal.record(2026, "Las Vegas", info, pole, "p", "avant", "m", win, "avant la qualif", "g", now=before)
    n2 = journal.record(2026, "Las Vegas", info, pole, "p", "avant", "m", win, "avant la qualif", "g", now=before)
    n3 = journal.record(2026, "Las Vegas", info, pole, "p", "après EL1", "m", win, "après la qualif", "g", now=after_q)
    assert n1 == 4          # 2 pilotes x (pole + victoire)
    assert n2 == 0          # même étape : déjà publiée, pas de réécriture
    assert n3 == 2          # après le début de la qualif : seulement la victoire
    assert set(journal.load()["type"]) == {"pole", "victoire"}


def test_target_is_next_race_in_calendar(monkeypatch):
    import importlib
    monkeypatch.setenv("F1_TARGET", "2026|Qatar Grand Prix")
    import config
    importlib.reload(config)
    assert config.TARGET_GP == "Qatar Grand Prix" and config.TARGET_SEASON == 2026
    monkeypatch.delenv("F1_TARGET")
    importlib.reload(config)


def test_journal_needs_margin_official_times_and_never_rewrites(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import journal
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "predictions.csv")
    info = {"sessions": {"Q": "2026-11-21T04:00:00Z", "R": "2026-11-22T04:00:00Z"}}
    pole = pd.DataFrame({"driver": ["AAA", "BBB"], "team": ["T1", "T2"], "p": [0.7, 0.3]})
    win = pd.DataFrame({"driver": ["AAA", "BBB"], "team": ["T1", "T2"], "proba_victoire": [0.6, 0.4]})
    args = (2026, "Las Vegas", info, pole, "p", "après EL3", "m", win, "avant la qualif", "g")
    # 20 minutes avant la qualif : trop tard (le site ne serait publié qu'après le départ)
    assert journal.record(*args, now=datetime(2026, 11, 21, 3, 40, tzinfo=timezone.utc)) == 2  # victoire seulement
    first = (tmp_path / "predictions.csv").read_text()
    # horaires estimés : rien n'est enregistré
    approx = {**info, "approx": True}
    assert journal.record(2026, "Las Vegas", approx, pole, "p", "avant", "m", win, "x", "g",
                          now=datetime(2026, 11, 19, tzinfo=timezone.utc)) == 0
    journal.record(2026, "Las Vegas", info, pole, "p", "avant", "m", win, "y", "g",
                   now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    assert (tmp_path / "predictions.csv").read_text().startswith(first)  # les lignes publiées restent intactes


def test_team_colours_from_data_are_sanitised(tmp_path):
    import json
    import export_site
    f = tmp_path / "2026" / "Monaco" / "Qualifying" / "drivers.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"drivers": [
        {"driver": "AAA", "fn": "A", "ln": "Aa", "team": "T", "tc": "red;position:fixed"},
        {"driver": "BBB", "fn": "B", "ln": "Bb", "team": "T", "tc": "#00D2BE"}]}), encoding="utf-8")
    d = export_site.driver_directory(tmp_path)
    assert d["AAA"]["couleur"] == "#888888" and d["BBB"]["couleur"] == "#00D2BE"


def test_first_race_of_a_new_season_uses_last_known_entry_list(monkeypatch):
    import predict
    monkeypatch.setattr(predict, "TARGET_SEASON", 2027)
    monkeypatch.setattr(predict, "TARGET_GP", "Australian Grand Prix")
    best = pd.DataFrame({"season": [2026] * 3, "grand_prix": ["Abu Dhabi"] * 3, "session": ["Qualifying"] * 3,
                         "driver": ["AAA", "BBB", "CCC"], "team": ["T1", "T1", "T2"], "date": ["2026-12-05"] * 3})
    assert set(predict.entry_list(best)["driver"]) == {"AAA", "BBB", "CCC"}
