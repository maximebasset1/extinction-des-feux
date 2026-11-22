"""Grille de départ réelle (pénalités, stands) et classement officiel."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import f1db  # noqa: E402
import grille  # noqa: E402
import journal  # noqa: E402
from race_model import predict_race  # noqa: E402


def _f1db_fixture(root: Path) -> Path:
    race = root / "src/data/seasons/2026/races/21-las-vegas"
    race.mkdir(parents=True)
    (root / "src/data/drivers").mkdir(parents=True)
    for i, (code, did) in enumerate([("VER", "max-verstappen"), ("ANT", "kimi-antonelli"), ("RUS", "george-russell"),
                                     ("LAW", "liam-lawson")]):
        (root / f"src/data/drivers/{did}.yml").write_text(f"id: {did}\nabbreviation: {code}\n", encoding="utf-8")
    (race / "race.yml").write_text("id: 1170\nround: 21\ndate: 2026-11-22\n", encoding="utf-8")
    (race / "starting-grid-positions.yml").write_text(
        "- position: 1\n  driverId: max-verstappen\n  gridPenalty:\n"
        "- position: 2\n  driverId: george-russell\n  gridPenalty:\n"
        "- position: 3\n  driverId: kimi-antonelli\n  gridPenalty: 5\n"
        "- position: PL\n  driverId: liam-lawson\n  gridPenalty:\n", encoding="utf-8")
    (race / "race-results.yml").write_text(
        "- position: 1\n  driverId: george-russell\n- position: 2\n  driverId: kimi-antonelli\n"
        "- position: DNF\n  driverId: liam-lawson\n- position: DSQ\n  driverId: max-verstappen\n", encoding="utf-8")
    return root


def test_official_grid_and_classification_come_from_f1db(tmp_path, monkeypatch):
    monkeypatch.setenv("F1DB_DIR", str(_f1db_fixture(tmp_path)))
    o = f1db.load()
    # nos données datent la course du 21 (fuseau horaire) : rattachée à un jour près
    results = pd.DataFrame({"season": 2026, "date": "2026-11-21", "grand_prix": "Las Vegas",
                            "driver": ["VER", "ANT", "RUS", "LAW"], "finish": [1, 2, 3, 4]})
    g = f1db.official_grids(results, o).set_index("driver")
    assert g.loc["ANT", "grille_officielle"] == 3 and g.loc["ANT", "penalite"] == 5
    assert bool(g.loc["LAW", "stands"]) and g.loc["LAW", "grille_officielle"] == 4
    r = f1db.official_results(results, o).set_index("driver")["finish"]
    assert r["RUS"] == 1 and r["VER"] == 4        # disqualifié : classé derrière tout le monde


def test_openf1_grid_maps_numbers_and_puts_missing_drivers_in_the_pit_lane():
    rows = [{"position": i + 1, "driver_number": n} for i, n in enumerate(range(1, 17))]
    numbers = {str(n): f"D{n:02d}" for n in range(1, 18)}
    g = grille.from_openf1(rows, numbers, [f"D{n:02d}" for n in range(1, 18)])
    assert len(g) == 17 and bool(g.iloc[-1]["stands"]) and g.iloc[-1]["driver"] == "D17"
    assert grille.from_openf1(rows[:5], numbers, list(numbers.values())) is None    # grille incomplète : ignorée


def test_qualifying_session_is_matched_on_the_calendar_time():
    sessions = [{"session_key": 1, "date_start": "2026-11-21T04:00:00+00:00"},
                {"session_key": 2, "date_start": "2026-12-05T17:00:00+00:00"}]
    assert grille.quali_session(sessions, "2026-11-21T04:00:00Z")["session_key"] == 1
    assert grille.quali_session(sessions, "2026-11-28T04:00:00Z") is None


def test_without_openf1_the_grid_is_the_qualifying_order_and_marked_provisional():
    quali = pd.DataFrame({"driver": ["ANT", "VER"], "quali_pos": [1, 2]})
    g, source = grille.official(2026, "Las Vegas Grand Prix", {}, quali)
    assert source == "provisoire" and list(g["grille"]) == [1, 2]


def test_a_grid_penalty_lowers_the_chance_of_winning():
    entrants = pd.DataFrame({"driver": ["AAA", "BBB", "CCC"], "team": ["T1", "T2", "T3"]})
    results = pd.DataFrame(columns=["season", "date", "driver", "finish"])
    quali = pd.DataFrame({"driver": ["AAA", "BBB", "CCC"], "quali_pos": [1, 2, 3], "deficit_pct": [0, 0.2, 0.4]})
    feats, w = ["log_grille"], np.array([1.9])
    raw = predict_race(None, results, entrants, quali, pd.Series(dtype=float), feats, w).set_index("driver")
    grid = pd.DataFrame({"driver": ["BBB", "CCC", "AAA"], "grille": [1, 2, 6]})
    pen = predict_race(None, results, entrants, quali, pd.Series(dtype=float), feats, w, grid=grid).set_index("driver")
    assert pen.loc["AAA", "proba_victoire"] < raw.loc["AAA", "proba_victoire"]
    assert pen.loc["AAA", "grille"] == 6 and pen.loc["BBB", "grille"] == 1


def test_a_forecast_redone_on_the_official_grid_replaces_the_wrong_one_in_the_record(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "predictions.csv")
    win = pd.DataFrame({"driver": ["ANT", "VER"], "team": ["Mercedes", "Red Bull"], "proba_victoire": [0.7, 0.3]})
    info = {"sessions": {"Q": "2026-11-21T04:00:00Z", "R": "2026-11-22T04:00:00Z"}}
    from datetime import datetime, timezone
    journal.record(2026, "Las Vegas", info, win.assign(p=0.5), "p", "x", "m", win, "après la qualif", "g",
                   now=datetime(2026, 11, 21, 12, tzinfo=timezone.utc))
    fixed = win.assign(proba_victoire=[0.44, 0.36])
    assert journal.record_correction(2026, "Las Vegas", fixed, "g2") == 2
    assert journal.record_correction(2026, "Las Vegas", fixed, "g2") == 0      # une seule fois
    best = pd.DataFrame({"season": [2026], "grand_prix": ["Las Vegas"], "session": ["Qualifying"], "pole": [True], "driver": ["ANT"]})
    results = pd.DataFrame({"season": [2026], "grand_prix": ["Las Vegas"], "driver": ["VER"], "finish": [1]})
    ev = journal.evaluate(best, results)
    v = ev[ev["type"] == "victoire"]
    assert len(v) == 1 and bool(v.iloc[0]["recalcule"]) and v.iloc[0]["proba_du_vainqueur"] == pytest.approx(0.36)
    assert len(journal.load()) == 4                                            # la ligne d'origine reste dans le fichier
