"""Sonde 4 (accord de Maxime) : fichiers gratuits de football-data.co.uk pour les championnats européens."""
import json, time, urllib.request
from pathlib import Path

UA = {"User-Agent": "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"}
OUT = Path("sonde/data"); OUT.mkdir(parents=True, exist_ok=True)
MAIN = ["E0", "E1", "D1", "SP1", "I1", "F1", "N1", "P1", "B1", "SC0", "T1", "G1"]
NEW = ["AUT", "DNK", "SWZ", "NOR", "SWE", "POL", "ROU", "RUS", "IRL", "FIN"]
log = {}

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = str(e); time.sleep(5 * (i + 1))
    raise RuntimeError(err)

for y in range(2010, 2027):
    code = f"{y % 100:02d}{(y + 1) % 100:02d}"
    for lg in MAIN:
        try:
            b = get(f"https://www.football-data.co.uk/mmz4281/{code}/{lg}.csv")
            (OUT / f"{lg}_{y}.csv").write_bytes(b); log[f"{lg}_{y}"] = len(b)
        except Exception as e:  # noqa: BLE001
            log[f"{lg}_{y}"] = f"erreur {e}"
        time.sleep(0.5)
for lg in NEW:
    try:
        b = get(f"https://www.football-data.co.uk/new/{lg}.csv")
        (OUT / f"new_{lg}.csv").write_bytes(b); log[f"new_{lg}"] = len(b)
    except Exception as e:  # noqa: BLE001
        log[f"new_{lg}"] = f"erreur {e}"
    time.sleep(0.5)
for f in ["fixtures.csv", "new_league_fixtures.csv"]:
    try:
        b = get(f"https://www.football-data.co.uk/{f}"); (OUT / f).write_bytes(b); log[f] = len(b)
    except Exception as e:  # noqa: BLE001
        log[f] = f"erreur {e}"
json.dump(log, open("sonde/resultat4.json", "w"), indent=1)
