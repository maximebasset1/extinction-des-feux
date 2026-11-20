"""Tests de la recherche multi-championnats : python -m pytest tests -q"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football import cups, joint, names, sources  # noqa: E402


def test_cup_scores_are_taken_after_90_minutes():
    assert cups.score90("2-1 (1-0)") == (2, 1)
    assert cups.score90("4-2 a.e.t. (2-2, 0-2)") == (2, 2)
    assert cups.score90("4-3 pen. 1-1 a.e.t. (1-1, 0-1)") == (1, 1)
    assert cups.score90("") is None


def test_cup_file_dates_follow_the_season(tmp_path):
    f = tmp_path / "cl.txt"
    f.write_text("""= UEFA Champions League 2024/25
▪ League, Matchday 1
  Tue Sep 17 2024
    18:45  Juventus FC (ITA)       v PSV (NED)       3-1 (1-0)
▪ Group B
  Wed Sep 18
    21:00  Lille OSC (FRA)         v Sporting Clube de Portugal (POR)  0-2 (0-1)
▪ Finals, Final
  Sat May 31
    21:00  Paris Saint-Germain FC (FRA) v FC Internazionale Milano (ITA)  5-0 (2-0)
""", encoding="utf-8")
    d = cups.parse(f, "LDC", 2024)
    assert list(d["date"].dt.year) == [2024, 2024, 2025]
    assert list(d["neutral"]) == [False, False, True]
    assert d.loc[1, "home_cc"] == "FRA" and d.loc[1, "ag"] == 2


def test_names_are_matched_within_the_country():
    assert names.match("ITA", "Lazio Roma", ["Lazio", "Roma"]) == "Lazio"
    assert names.match("ENG", "Brentford FC", ["Brentford", "Brighton"]) == "Brentford"
    assert names.match("ESP", "Club Atlético de Madrid", ["Ath Madrid", "Real Madrid"]) == "Ath Madrid"
    assert names.match("FRA", "Club inconnu", ["Lille", "Lens"]) is None


def test_odds_api_name_without_country_is_resolved_only_if_unique():
    idx = sources.TeamIndex(["FRA:Lille", "ENG:Arsenal", "GER:Bayern Munich"])
    assert idx.resolve("Lille OSC") == "FRA:Lille"
    assert idx.resolve("Bayern München") == "GER:Bayern Munich"
    assert idx.resolve("Club Totalement Inconnu").startswith("?:")


def test_odds_frame_averages_bookmakers_and_never_needs_them():
    idx = sources.TeamIndex(["FRA:Lille", "GER:Bayern Munich"])
    ev = [{"id": "x", "commence_time": "2026-11-25T20:00:00Z", "home_team": "Lille OSC", "away_team": "Bayern Munich"}]
    od = [{"id": "x", "home_team": "Lille OSC", "away_team": "Bayern Munich", "bookmakers": [
        {"markets": [{"key": "h2h", "outcomes": [{"name": "Lille OSC", "price": 4.0}, {"name": "Draw", "price": 4.0}, {"name": "Bayern Munich", "price": 1.8}]}]},
        {"markets": [{"key": "h2h", "outcomes": [{"name": "Lille OSC", "price": 4.4}, {"name": "Draw", "price": 4.2}, {"name": "Bayern Munich", "price": 1.7}]}]}]}]
    f = sources.odds_frame(ev, od, "LEC", idx)
    assert f.loc[0, "home"] == "FRA:Lille" and f.loc[0, "oh"] == pytest.approx(4.2)
    assert np.isnan(sources.odds_frame(ev, [], "LEC", idx).loc[0, "oh"])


def test_football_data_org_uses_the_score_after_90_minutes():
    js = {"teams": [{"id": 1, "name": "Lille OSC", "area": {"code": "FRA"}}, {"id": 2, "name": "FC Bayern München", "area": {"code": "DEU"}}],
          "matches": [{"utcDate": "2027-03-10T20:00:00Z", "status": "FINISHED", "stage": "LAST_16",
                       "homeTeam": {"id": 1, "name": "Lille OSC"}, "awayTeam": {"id": 2, "name": "FC Bayern München"},
                       "score": {"fullTime": {"home": 3, "away": 2}, "regularTime": {"home": 2, "away": 2}}},
                      {"utcDate": "2027-03-17T20:00:00Z", "status": "TIMED", "stage": "LAST_16",
                       "homeTeam": {"id": None, "name": None}, "awayTeam": {"id": None, "name": None}, "score": {}}]}
    f = sources.fdorg_frame(js, "LDC", sources.TeamIndex(["FRA:Lille", "GER:Bayern Munich"]))
    assert len(f) == 1 and f.loc[0, "away"] == "GER:Bayern Munich" and (f.loc[0, "hg"], f.loc[0, "ag"]) == (2, 2)


def leagues_and_cup(seed=0):
    """Deux championnats fictifs ; le championnat X est bien plus fort, ce que seuls les matchs européens montrent."""
    rng = np.random.default_rng(seed)
    st = {"X:a": 0.9, "X:b": 0.7, "X:c": 0.5, "Y:a": -0.3, "Y:b": -0.5, "Y:c": -0.7}
    rows, d0 = [], pd.Timestamp("2024-08-01")
    for w in range(80):
        for lg in ("X", "Y"):
            t = [k for k in st if k.startswith(lg)]
            for h, a in ((t[w % 3], t[(w + 1) % 3]), (t[(w + 2) % 3], t[w % 3])):
                rows.append((d0 + pd.Timedelta(weeks=w), h, a, lg, False))
        h, a = ("X:a", "Y:a") if w % 2 else ("Y:b", "X:c")
        rows.append((d0 + pd.Timedelta(weeks=w, days=2), h, a, "LDC", True))
    m = pd.DataFrame(rows, columns=["date", "home", "away", "league", "is_cup"])
    m["hg"] = rng.poisson(np.exp(0.2 + m["home"].map(st) - m["away"].map(st)))
    m["ag"] = rng.poisson(np.exp(m["away"].map(st) - m["home"].map(st)))
    m["hst"] = m["ast"] = np.nan
    m["neutral"] = False
    return m


def test_cross_league_strength_comes_from_european_matches():
    m = leagues_and_cup()
    f = joint.fit(m, m["date"].max() + pd.Timedelta(days=1), 0.002, 0.0, 0.3)
    lh, la = joint.rates(f, "Y:a", "X:c", neutral=True)
    assert la > lh       # le 3e du championnat fort reste meilleur que le 1er du faible
    assert f["converged"]


def test_joint_fit_never_uses_the_future():
    m = leagues_and_cup()
    cutoff = m["date"].iloc[len(m) // 2]
    a = joint.fit(m, cutoff, 0.002, 0.0, 0.3)
    m2 = m.copy()
    m2.loc[m2["date"] >= cutoff, ["hg", "ag"]] = 9
    b = joint.fit(m2, cutoff, 0.002, 0.0, 0.3)
    assert np.allclose(a["att"], b["att"]) and np.allclose(a["def"], b["def"])


def test_odds_are_fetched_only_when_a_match_is_near(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sources, "_get_json", lambda url, h=None: (calls.append(url.split("?")[0]) or ([], {})))
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    sources.odds_api("LEC", "k", tmp_path, now, [datetime(2026, 12, 10, tzinfo=timezone.utc)])
    assert all(not u.endswith("/odds") for u in calls)          # match lointain : liste des matchs seulement (gratuite)
    sources.odds_api("LEC", "k", tmp_path, now, [datetime(2026, 11, 21, tzinfo=timezone.utc)])
    assert sum(u.endswith("/odds") for u in calls) == 1
    sources.odds_api("LEC", "k", tmp_path, now, [datetime(2026, 11, 21, tzinfo=timezone.utc)])
    assert sum(u.endswith("/odds") for u in calls) == 1        # déjà récupérées il y a moins de 3 h
