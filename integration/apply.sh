#!/usr/bin/env bash
# Crée la branche feat/predictions sur PitLane Insider, y applique le patch et la pousse. main n'est pas modifié.
set -euo pipefail
URL=https://raw.githubusercontent.com/maximebasset1/extinction-des-feux/main/integration/pli-predictions.patch
EXPECTED=bdd3aab346e0cea7
git fetch -q origin main
git checkout -q -b feat/predictions origin/main
curl -fsSL "$URL" -o /tmp/pli-predictions.patch
test "$(sha256sum /tmp/pli-predictions.patch | cut -c1-16)" = "$EXPECTED" || { echo "PATCH INATTENDU, ARRET"; exit 1; }
git am /tmp/pli-predictions.patch
git push -u origin feat/predictions
echo "=== TERMINE ==="
git log --oneline -2
git status -sb | head -1
