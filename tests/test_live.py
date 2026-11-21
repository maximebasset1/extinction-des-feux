"""Modèle du direct : départ sur le pronostic publié, cohérence dans le temps, même résultat en JavaScript."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from football import live as L

PARAMS = {"part_1re_mi_temps": 0.44, "rythme_selon_ecart": [1.15, 1.08, 1.0, 0.92, 0.9]}
JS = Path(__file__).resolve().parent.parent / "site" / "assets" / "modele-direct.js"


def test_kickoff_reproduces_the_published_forecast():
    p = np.array([[0.42, 0.28, 0.30], [0.70, 0.18, 0.12], [0.14, 0.18, 0.68], [0.33, 0.34, 0.33]])
    lam = L.calibrate(p, PARAMS)
    assert L.kickoff_outcome(lam[:, 0], lam[:, 1], PARAMS) == pytest.approx(p, abs=1e-5)


def test_probabilities_sum_to_one_and_the_final_whistle_decides():
    d = L.remaining(1.4, 1.1, 2, 2, 2, 0.4, PARAMS)
    assert d.sum() == pytest.approx(1)
    assert L.outcome_from(L.remaining(1.4, 1.1, 2, 1, 3, 0.0, PARAMS), 2, 1)[0] == pytest.approx([1, 0, 0])


def test_a_lead_is_worth_more_as_time_runs_out():
    chances = [L.outcome_from(L.remaining(1.3, 1.2, 1, 0, 2, f, PARAMS), 1, 0)[0, 0] for f in (1.0, 0.5, 0.1, 0.01)]
    assert chances == sorted(chances) and chances[-1] > 0.95


def test_the_browser_computes_the_same_thing():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    cases = [(1.3, 1.1, 0, 0, 0, 1.0), (1.3, 1.1, 1, 0, 1, 0.5), (0.9, 2.1, 1, 1, 2, 1.0), (1.7, 0.8, 0, 2, 2, 0.2)]
    script = (f"const D = require({json.dumps(str(JS))}); const P = {json.dumps(PARAMS)};"
              f"console.log(JSON.stringify({json.dumps(cases)}.map(c => D.chancesEnDirect(...c, P).p)));")
    js = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    for c, pj in zip(cases, js):
        lh, la, hg, ag, half, frac = c
        assert L.outcome_from(L.remaining(lh, la, hg, ag, half, frac, PARAMS), hg, ag)[0] == pytest.approx(pj, abs=1e-9)
