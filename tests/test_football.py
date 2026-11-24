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
