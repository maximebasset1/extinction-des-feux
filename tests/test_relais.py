"""Tests du direct en JavaScript (relais Cloudflare et page) lancés avec node."""
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


def test_ligues():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    # la base D1 des tests est simulée avec node:sqlite (Node 22.13 ou plus récent)
    if subprocess.run([node, "-e", "require('node:sqlite')"], capture_output=True).returncode:
        pytest.skip("node:sqlite absent de cette version de node")
    r = subprocess.run([node, "--test", str(ICI / "ligues.test.mjs")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def test_direct_site():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    r = subprocess.run([node, "--test", str(ICI / "direct.test.mjs")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def test_navigation_football_et_branchement_du_direct():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    r = subprocess.run([node, "--test", str(ICI / "navigation.test.mjs")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
