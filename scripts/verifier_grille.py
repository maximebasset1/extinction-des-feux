"""Vérifie, depuis GitHub, que la grille officielle d'une course passée est bien lue (OpenF1) et qu'elle
correspond à celle de f1db.

    python scripts/verifier_grille.py 2026 "Las Vegas Grand Prix"
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f1db  # noqa: E402
import grille  # noqa: E402
from config import CALENDAR_FILE, DATA_PROCESSED  # noqa: E402


def main(season: int, gp_folder: str) -> None:
    gp = gp_folder.replace(" Grand Prix", "")
    cal = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
    info = next(r for r in cal[str(season)] if r["gp"] == gp_folder)
    best = pd.read_csv(DATA_PROCESSED / "best_laps.csv")
    quali = best[(best["season"] == season) & (best["grand_prix"] == gp) & (best["session"] == "Qualifying")]
    g, source = grille.official(season, gp_folder, info, quali)
    print(f"Source : {source}")
    print(g.to_string(index=False))
    o = f1db.load()
    res = pd.read_csv(DATA_PROCESSED / "race_results.csv")
    ref = f1db.official_grids(res, o)
    ref = ref[(ref["season"] == season) & (ref["grand_prix"] == gp)].set_index("driver")["grille_officielle"]
    if len(ref):
        diff = [(d, int(x), int(ref[d])) for d, x in zip(g["driver"], g["grille"]) if d in ref and int(ref[d]) != int(x)]
        print("Identique à f1db" if not diff else f"Écarts avec f1db (pilote, OpenF1, f1db) : {diff}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
