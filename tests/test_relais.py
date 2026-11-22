"""Tests du relais du direct (Worker Cloudflare, JavaScript) lancés avec node."""
import shutil
import subprocess
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent


def test_relais():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    r = subprocess.run([node, "--test", str(ICI / "relais.test.mjs")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
