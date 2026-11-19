"""Met à jour data/calendar.json depuis l'API publique Jolpica (successeur d'Ergast).

Lancé automatiquement par GitHub Actions avant chaque calcul. Si l'API ne répond pas,
le calendrier existant est conservé : le site continue de fonctionner.
Usage : python scripts/update_calendar.py [saison ...]
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "data" / "calendar.json"
API = "https://api.jolpi.ca/ergast/f1/{season}.json"
SESSION_KEYS = {"FirstPractice": "FP1", "SecondPractice": "FP2", "ThirdPractice": "FP3",
                "SprintQualifying": "SQ", "Sprint": "S", "Qualifying": "Q"}
# Noms Jolpica -> noms des dossiers de données TracingInsights, quand ils diffèrent
ALIASES = {"Spanish Grand Prix": "Spanish Grand Prix", "Barcelona-Catalunya Grand Prix": "Barcelona Grand Prix",
           "Brazilian Grand Prix": "São Paulo Grand Prix", "Mexican Grand Prix": "Mexico City Grand Prix"}
COUNTRY_FR = {"USA": "États-Unis", "United States": "États-Unis", "Qatar": "Qatar", "UAE": "Émirats arabes unis",
              "Bahrain": "Bahreïn", "Saudi Arabia": "Arabie saoudite", "Australia": "Australie", "Japan": "Japon",
              "China": "Chine", "Canada": "Canada", "Monaco": "Monaco", "Spain": "Espagne", "Austria": "Autriche",
              "UK": "Royaume-Uni", "Belgium": "Belgique", "Hungary": "Hongrie", "Netherlands": "Pays-Bas",
              "Italy": "Italie", "Azerbaijan": "Azerbaïdjan", "Singapore": "Singapour", "Mexico": "Mexique",
              "Brazil": "Brésil", "Portugal": "Portugal", "Turkey": "Turquie"}


def iso(d: dict) -> str | None:
    if not d or "date" not in d:
        return None
    t = d.get("time", "12:00:00Z")
    return f"{d['date']}T{t if t.endswith('Z') else t + 'Z'}"


def fetch(season: int) -> list[dict]:
    with urllib.request.urlopen(API.format(season=season), timeout=30) as r:
        races = json.load(r)["MRData"]["RaceTable"]["Races"]
    out = []
    for race in races:
        sessions = {v: iso(race.get(k)) for k, v in SESSION_KEYS.items() if race.get(k)}
        sessions["R"] = iso({"date": race["date"], "time": race.get("time", "12:00:00Z")})
        loc = race["Circuit"]["Location"]
        out.append({"round": int(race["round"]), "gp": ALIASES.get(race["raceName"], race["raceName"]),
                    "city": loc.get("locality"), "country": COUNTRY_FR.get(loc.get("country"), loc.get("country")),
                    "lat": float(loc["lat"]) if loc.get("lat") else None, "lon": float(loc["long"]) if loc.get("long") else None,
                    "sessions": {k: v for k, v in sessions.items() if v},
                    "approx": "time" not in race or any("time" not in race[k] for k in SESSION_KEYS if race.get(k))})
    return out


def main(seasons: list[int]) -> None:
    cal = json.loads(CAL.read_text(encoding="utf-8")) if CAL.exists() else {}
    for s in seasons:
        try:
            races = fetch(s)
            if races:
                cal[str(s)] = races
                print(f"Calendrier {s} : {len(races)} courses (API Jolpica)")
        except Exception as exc:
            print(f"Calendrier {s} : API injoignable ({exc}), calendrier existant conservé")
    CAL.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    year = datetime.now(timezone.utc).year
    main([int(a) for a in sys.argv[1:]] or [year, year + 1])
