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


def full_index():
    from football import leagues
    ids = []
    for cc, names_ in {"FRA": ["Paris SG", "Paris FC", "Lille", "Monaco"], "ESP": ["Real Madrid", "Ath Madrid", "Betis"],
                       "ITA": ["Inter", "Milan", "Lazio", "Roma"], "GER": ["Bayern Munich"], "RUS": ["Arsenal Tula"],
                       "ENG": ["Arsenal"], "POR": ["Sp Braga", "Sp Lisbon"]}.items():
        ids += [f"{cc}:{x}" for x in names_]
    return sources.TeamIndex(ids)


def test_odds_api_names_never_jump_to_the_wrong_club():
    idx = full_index()
    assert idx.resolve("Atletico Madrid") == "ESP:Ath Madrid"
    assert idx.resolve("Paris Saint Germain") == "FRA:Paris SG"
    assert idx.resolve("Paris FC") == "FRA:Paris FC"
    assert idx.resolve("Monaco") == "FRA:Monaco"
    assert idx.resolve("Inter Milan") == "ITA:Inter"
    assert idx.resolve("Arsenal") == "ENG:Arsenal"
    assert idx.resolve("Club Totalement Inconnu").startswith("?:")


def test_clubs_of_countries_without_league_keep_one_identity():
    idx = full_index()
    a = idx.resolve("Qarabağ FK", "AZE")
    assert idx.resolve("Qarabağ Ağdam FK", "AZE") == a
    assert idx.resolve("FK Crvena Zvezda", "SRB") == idx.resolve("Crvena Zvezda", "SRB")


def test_odds_frame_averages_bookmakers_and_drops_live_odds():
    idx = full_index()
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    ev = [{"id": "x", "commence_time": "2026-11-25T20:00:00Z", "home_team": "Lille OSC", "away_team": "Bayern Munich"},
          {"id": "y", "commence_time": "2026-11-20T11:00:00Z", "home_team": "Lille OSC", "away_team": "Inter Milan"}]
    book = lambda h, d, a: {"markets": [{"key": "h2h", "outcomes": [{"name": "Lille OSC", "price": h}, {"name": "Draw", "price": d},  # noqa: E731
                                                                     {"name": "Bayern Munich", "price": a}]}]}
    od = {"fetched": now.timestamp(), "data": [{"id": "x", "commence_time": ev[0]["commence_time"], "home_team": "Lille OSC",
                                                "away_team": "Bayern Munich", "bookmakers": [book(4.0, 4.0, 1.8), book(4.4, 4.2, 1.7)]}]}
    f = sources.odds_frame(ev, od, "LEC", idx, now)
    assert len(f) == 1                                        # le match déjà commencé disparaît
    assert f.loc[0, "home"] == "FRA:Lille" and f.loc[0, "oh"] == pytest.approx(4.2)
    late = {**od, "fetched": datetime(2026, 11, 25, 20, 30, tzinfo=timezone.utc).timestamp()}
    assert np.isnan(sources.odds_frame(ev, late, "LEC", idx, now).loc[0, "oh"])   # cote relevée pendant le match


def test_cup_odds_are_attached_by_kickoff_and_one_known_club():
    fx = pd.DataFrame({"kickoff": ["2026-11-25T20:00:00Z", "2026-11-25T20:00:00Z"], "home": ["FRA:Lille", "ESP:Betis"],
                       "away": ["GER:Bayern Munich", "ITA:Roma"]})
    od = pd.DataFrame({"kickoff": ["2026-11-25T20:00:00Z"], "home": ["FRA:Lille"], "away": ["?:Bayern"],
                       "oh": [4.0], "od": [3.8], "oa": [1.8]})
    out, lost = sources.attach_odds(fx, od)
    assert lost == 0 and out.loc[0, "oh"] == 4.0 and np.isnan(out.loc[1, "oh"])


def test_football_data_org_uses_the_score_after_90_minutes():
    js = {"teams": [{"id": 1, "name": "Lille OSC", "area": {"code": "FRA"}}, {"id": 2, "name": "FC Bayern München", "area": {"code": "DEU"}}],
          "matches": [{"utcDate": "2027-03-10T20:00:00Z", "status": "FINISHED", "stage": "LAST_16",
                       "homeTeam": {"id": 1, "name": "Lille OSC"}, "awayTeam": {"id": 2, "name": "FC Bayern München"},
                       "score": {"fullTime": {"home": 3, "away": 2}, "regularTime": {"home": 2, "away": 2}}},
                      {"utcDate": "2026-11-24T20:00:00Z", "status": "FINISHED", "stage": "LEAGUE_STAGE", "matchday": 5,
                       "homeTeam": {"id": 2, "name": "FC Bayern München"}, "awayTeam": {"id": 1, "name": "Lille OSC"},
                       "score": {"fullTime": {"home": 2, "away": 1}, "regularTime": {"home": None, "away": None}}},
                      {"utcDate": "2027-03-17T20:00:00Z", "status": "TIMED", "stage": "LAST_16",
                       "homeTeam": {"id": None, "name": None}, "awayTeam": {"id": None, "name": None}, "score": {}}]}
    f = sources.fdorg_frame(js, "LDC", sources.TeamIndex(["FRA:Lille", "GER:Bayern Munich"]))
    assert len(f) == 2 and f.loc[0, "away"] == "GER:Bayern Munich" and (f.loc[0, "hg"], f.loc[0, "ag"]) == (2, 2)
    assert (f.loc[1, "hg"], f.loc[1, "ag"]) == (2, 1) and bool(f.loc[1, "played"])


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
    calls, events = [], []
    def fake(url, h=None):
        calls.append(url.split("?")[0])
        return (events if url.split("?")[0].endswith("/events") else []), {"x-requests-remaining": "400"}
    monkeypatch.setattr(sources, "_get_json", fake)
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    odds_calls = lambda: sum(u.endswith("/odds") for u in calls)  # noqa: E731
    events[:] = [{"id": "a", "commence_time": "2026-12-10T20:00:00Z", "home_team": "x", "away_team": "y"}]
    sources.odds_api("LEC", "k", tmp_path, now)
    assert odds_calls() == 0                      # match lointain : liste des matchs seulement (gratuite)
    events[:] = [{"id": "a", "commence_time": "2026-11-21T20:00:00Z", "home_team": "x", "away_team": "y"}]
    sources.odds_api("LEC", "k", tmp_path, now)
    assert odds_calls() == 1
    sources.odds_api("LEC", "k", tmp_path, now)
    assert odds_calls() == 1                      # déjà récupérées il y a moins de 3 h
    (tmp_path / "quota.json").write_text('{"month": "2026-11", "remaining": 20}')
    sources.odds_api("LEC", "k", tmp_path, datetime(2026, 11, 20, 18, tzinfo=timezone.utc))
    assert odds_calls() == 1                      # réserve atteinte : plus d'appel payant ce mois-ci


def test_european_matches_of_one_week_form_one_matchday():
    from football import pipeline as P
    idx = sources.TeamIndex(["FRA:Lille", "FRA:Lyon", "ESP:Betis", "GER:Stuttgart"])
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    ev = [{"id": "a", "commence_time": "2026-11-26T17:45:00Z", "home_team": "Lille OSC", "away_team": "Real Betis"},
          {"id": "b", "commence_time": "2026-11-26T20:00:00Z", "home_team": "Lyon", "away_team": "VfB Stuttgart"},
          {"id": "c", "commence_time": "2026-12-10T20:00:00Z", "home_team": "Lyon", "away_team": "Lille OSC"}]
    f = P.europa_calendar(ev, {}, pd.DataFrame(), idx, now)
    assert list(f["journee"]) == ["Semaine du 26 novembre", "Semaine du 26 novembre", "Semaine du 10 décembre"]
    assert list(f["ordre"]) == [1, 1, 2]


def test_display_names_stay_unambiguous():
    from football import pipeline as P
    assert P.display("Paris FC") == "Paris FC"                 # sinon on le confondrait avec le PSG
    assert P.display("Arsenal FC") == "Arsenal"
    assert P.display("Paris Saint-Germain FC") == "Paris Saint-Germain"
    assert P.display("FC Bayern München") == "Bayern Munich"


def test_site_pages_are_up_to_date():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "scripts" / "build_site.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_asset_fingerprint_ignores_line_endings(tmp_path, monkeypatch):
    """Sous Windows (autocrlf) les assets sont en CRLF : l'empreinte doit rester celle de GitHub (LF)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import build_site
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "lf.js").write_bytes(b"a();\nb();\n")
    (tmp_path / "assets" / "crlf.js").write_bytes(b"a();\r\nb();\r\n")
    (tmp_path / "assets" / "autre.js").write_bytes(b"a();\nc();\n")
    monkeypatch.setattr(build_site, "SITE", tmp_path)
    assert build_site.empreinte("lf.js") == build_site.empreinte("crlf.js")
    assert build_site.empreinte("lf.js") != build_site.empreinte("autre.js")


def test_default_matchday_ignores_a_single_late_match():
    from football import pipeline as P
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    ahead = [{"journee": "Journée 6", "jour": "2026-11-21", "ordre": 6}] + \
            [{"journee": "Journée 13", "jour": "2026-11-22", "ordre": 13} for _ in range(9)]
    assert P.choose_matchday(ahead, now) == "Journée 13"
    assert P.choose_matchday([], now) is None


def test_match_states():
    from football import pipeline as P
    now = datetime(2026, 11, 20, 21, tzinfo=timezone.utc)
    base = {"played": False, "status": "TIMED", "kickoff": "2026-11-20T19:45:00Z"}
    assert P.etat(pd.Series(base), now) == "en_cours"
    assert P.etat(pd.Series({**base, "kickoff": "2026-11-19T19:45:00Z"}), now) == "en_attente"
    assert P.etat(pd.Series({**base, "status": "POSTPONED"}), now) == "reporte"
    assert P.etat(pd.Series({**base, "kickoff": "2026-11-21T19:45:00Z"}), now) == "a_venir"
    assert P.etat(pd.Series({**base, "played": True}), now) == "joue"


def test_europa_league_match_stays_listed_until_its_result_arrives():
    from football import pipeline as P
    idx = sources.TeamIndex(["FRA:Lille", "ESP:Betis"])
    now = datetime(2026, 11, 26, 21, 30, tzinfo=timezone.utc)
    seen = {"a": {"id": "a", "commence_time": "2026-11-26T20:00:00Z", "home_team": "Lille OSC", "away_team": "Real Betis"}}
    f = P.europa_calendar([], {}, pd.DataFrame(), idx, now, seen)
    assert len(f) == 1 and not f.loc[0, "played"] and P.etat(f.iloc[0], now) == "en_cours"
    done = pd.DataFrame([
        {"id": "old", "competition": "LEC", "kickoff": "2025-11-26T20:00:00Z", "home_name": "Lille OSC",
         "away_name": "Real Betis", "hg": 0, "ag": 0},
        {"id": "a", "competition": "LEC", "kickoff": "2026-11-26T20:00:00Z", "home_name": "Lille OSC",
         "away_name": "Real Betis", "hg": 2, "ag": 1},
    ])
    f = P.europa_calendar([], {}, done, idx, now, seen)
    assert len(f) == 1 and bool(f.loc[0, "played"]) and (f.loc[0, "hg"], f.loc[0, "ag"]) == (2, 1)


def test_europa_scores_are_fetched_only_after_a_match_and_twice_a_day_at_most(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sources, "_get_json", lambda url, h=None: (calls.append(url.split("?")[0]) or ([
        {"id": "a", "completed": True, "commence_time": "2026-11-26T20:00:00Z", "home_team": "Lille OSC", "away_team": "Real Betis",
         "scores": [{"name": "Lille OSC", "score": "2"}, {"name": "Real Betis", "score": "1"}]}], {"x-requests-remaining": "300"})))
    sources.write_json(tmp_path / "seen_LEC.json", {"a": {"id": "a", "commence_time": "2026-11-26T20:00:00Z",
                                                         "home_team": "Lille OSC", "away_team": "Real Betis"}})
    csv = tmp_path / "res.csv"
    assert sources.odds_scores("LEC", "k", tmp_path, datetime(2026, 11, 26, 21, tzinfo=timezone.utc), csv) == 0   # trop tôt
    assert calls == []
    assert sources.odds_scores("LEC", "k", tmp_path, datetime(2026, 11, 27, 8, tzinfo=timezone.utc), csv) == 1
    assert sources.odds_scores("LEC", "k", tmp_path, datetime(2026, 11, 27, 9, tzinfo=timezone.utc), csv) == 0   # déjà relevé
    assert len(calls) == 1 and pd.read_csv(csv).loc[0, "hg"] == 2
