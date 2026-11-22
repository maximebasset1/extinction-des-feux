"""Variables des week-ends sprint : jamais d'information postérieure à la séance prédite."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sprint  # noqa: E402


def _best(sq_start, q_start):
    rows = []
    for drv, sq, q in [("A", 0.0, 0.0), ("B", 0.4, 0.2), ("C", np.nan, 0.5)]:
        rows.append({"season": 2026, "grand_prix": "X", "session": "Sprint Qualifying", "driver": drv,
                     "deficit_pct": sq, "start": sq_start})
        if q_start:
            rows.append({"season": 2026, "grand_prix": "X", "session": "Qualifying", "driver": drv,
                         "deficit_pct": q, "start": q_start})
    return pd.DataFrame(rows)


def test_qualif_sprint_utilisee_seulement_si_elle_precede_la_qualification():
    avant = sprint.quali_sprint(_best("2026-10-09T12:30:00", "2026-10-10T13:00:00")).set_index("driver")
    assert avant.loc["B", "qualif_sprint"] == 0.4 and avant.loc["C", "qualif_sprint"] == sprint.CAP
    # 2023 : la qualification (vendredi) précédait le shootout (samedi) : rien n'est utilisable
    assert sprint.quali_sprint(_best("2023-10-07T13:00:00", "2023-10-06T17:00:00")).empty
    # week-end en cours, qualification pas encore disputée : la qualif sprint sert
    assert len(sprint.quali_sprint(_best("2026-11-27T12:30:00", None))) == 3


def test_forme_avec_sprint_compte_le_sprint_du_week_end_mais_jamais_la_course_visee():
    r = pd.DataFrame({"season": 2026, "grand_prix": ["G1", "G2"], "driver": "A", "race_idx": [1, 2],
                      "finish": [10, 1], "log_grille": np.log([5, 2]), "forme_course": [15.0, 10.0]})
    s = pd.DataFrame({"season": 2026, "grand_prix": ["G2"], "driver": ["A"], "sprint": [2]})
    out = sprint.add_race_sprint(r, s).set_index("grand_prix")
    assert out.loc["G1", "forme_course_sprint"] == 15.0          # rien de connu avant : forme sans sprint
    w = 0.5 ** (1 / 5.0)                                         # moyenne pondérée de 10 (course 1) puis 2 (sprint 2)
    assert np.isclose(out.loc["G2", "forme_course_sprint"], (10 * w + 2) / (w + 1))
    assert np.isclose(out.loc["G2", "sprint_vs_grille"], np.log(2) - np.log(2))
    assert out.loc["G1", "sprint_vs_grille"] == 0.0


def test_week_end_sprint_detecte_dans_le_calendrier():
    assert sprint.is_sprint_weekend({"sessions": {"FP1": "x", "SQ": "y", "S": "z", "Q": "q", "R": "r"}})
    assert not sprint.is_sprint_weekend({"sessions": {"FP1": "x", "FP2": "y", "FP3": "z", "Q": "q", "R": "r"}})


def test_ecart_en_qualif_sprint_nul_hors_week_end_sprint():
    t = pd.DataFrame({"season": 2026, "grand_prix": ["X", "X", "Y"], "driver": ["A", "B", "A"], "essais": [0.3, 0.1, 0.2]})
    out = sprint.add_quali_sprint(t, _best("2026-10-09T12:30:00", "2026-10-10T13:00:00"), ["essais"]).set_index(["grand_prix", "driver"])
    assert np.isclose(out.loc[("X", "A"), "ecart_qualif_sprint"], -0.3)        # 0,0 % en SQ contre 0,3 % aux essais
    assert np.isclose(out.loc[("X", "B"), "ecart_qualif_sprint"], 0.3)
    assert out.loc[("Y", "A"), "ecart_qualif_sprint"] == 0.0 and out.loc[("Y", "A"), "essais_sprint"] == 0.2
