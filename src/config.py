"""Paramètres du projet « Probabilités de pole position »."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Les données brutes (des milliers de petits fichiers) peuvent être rangées ailleurs : variable F1_DATA_DIR
DATA_RAW = Path(os.environ["F1_DATA_DIR"]) if os.environ.get("F1_DATA_DIR") else ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"
RESULTS = ROOT / "reports" / "results"

BASE_URL = "https://raw.githubusercontent.com/TracingInsights/{season}/main"

CALENDAR_FILE = ROOT / "data" / "calendar.json"


def _resolve_target():
    """Course à prédire = la prochaine course du calendrier dont l'arrivée n'est pas passée depuis
    plus de 6 h. Forçable avec la variable F1_TARGET="2026|Las Vegas Grand Prix"."""
    import json
    from datetime import datetime, timedelta, timezone
    forced = os.environ.get("F1_TARGET")
    cal = json.loads(CALENDAR_FILE.read_text(encoding="utf-8")) if CALENDAR_FILE.exists() else {}
    races = [(int(s), r) for s, rs in cal.items() if s.isdigit() for r in rs]
    if forced:
        season, gp = forced.split("|")
        info = next((r for s, r in races if s == int(season) and r["gp"] == gp), {"gp": gp, "sessions": {}})
        return int(season), gp, info, False
    now = datetime.now(timezone.utc)
    upcoming = sorted((datetime.fromisoformat(r["sessions"]["R"].replace("Z", "+00:00")), s, r)
                      for s, r in races if "R" in r.get("sessions", {}))
    for race_time, s, r in upcoming:
        if race_time + timedelta(hours=6) > now:
            return s, r["gp"], r, False
    if upcoming:  # saison terminée : on garde la dernière course
        _, s, r = upcoming[-1]
        return s, r["gp"], r, True
    return 2026, "Las Vegas Grand Prix", {"gp": "Las Vegas Grand Prix", "sessions": {}}, False


# Course à prédire (déterminée automatiquement à partir du calendrier)
TARGET_SEASON, TARGET_GP, TARGET_INFO, SEASON_OVER = _resolve_target()

# Saisons complètes utilisées pour apprendre et tester le modèle
SEASONS = {
    # 2018-2022 : autre génération de voitures ; servent seulement à mieux apprendre les poids
    2018: ['Abu Dhabi Grand Prix', 'Australian Grand Prix', 'Austrian Grand Prix', 'Azerbaijan Grand Prix', 'Bahrain Grand Prix', 'Belgian Grand Prix', 'Brazilian Grand Prix', 'British Grand Prix', 'Canadian Grand Prix', 'Chinese Grand Prix', 'French Grand Prix', 'German Grand Prix', 'Hungarian Grand Prix', 'Italian Grand Prix', 'Japanese Grand Prix', 'Mexican Grand Prix', 'Monaco Grand Prix', 'Russian Grand Prix', 'Singapore Grand Prix', 'Spanish Grand Prix', 'United States Grand Prix'],
    2019: ['Abu Dhabi Grand Prix', 'Australian Grand Prix', 'Austrian Grand Prix', 'Azerbaijan Grand Prix', 'Bahrain Grand Prix', 'Belgian Grand Prix', 'Brazilian Grand Prix', 'British Grand Prix', 'Canadian Grand Prix', 'Chinese Grand Prix', 'French Grand Prix', 'German Grand Prix', 'Hungarian Grand Prix', 'Italian Grand Prix', 'Japanese Grand Prix', 'Mexican Grand Prix', 'Monaco Grand Prix', 'Russian Grand Prix', 'Singapore Grand Prix', 'Spanish Grand Prix', 'United States Grand Prix'],
    2020: ['70th Anniversary Grand Prix', 'Abu Dhabi Grand Prix', 'Austrian Grand Prix', 'Bahrain Grand Prix', 'Belgian Grand Prix', 'British Grand Prix', 'Eifel Grand Prix', 'Emilia Romagna Grand Prix', 'Hungarian Grand Prix', 'Italian Grand Prix', 'Portuguese Grand Prix', 'Russian Grand Prix', 'Sakhir Grand Prix', 'Spanish Grand Prix', 'Styrian Grand Prix', 'Turkish Grand Prix', 'Tuscan Grand Prix'],
    2021: ['Abu Dhabi Grand Prix', 'Austrian Grand Prix', 'Azerbaijan Grand Prix', 'Bahrain Grand Prix', 'Belgian Grand Prix', 'British Grand Prix', 'Dutch Grand Prix', 'Emilia Romagna Grand Prix', 'French Grand Prix', 'Hungarian Grand Prix', 'Italian Grand Prix', 'Mexico City Grand Prix', 'Monaco Grand Prix', 'Portuguese Grand Prix', 'Qatar Grand Prix', 'Russian Grand Prix', 'Saudi Arabian Grand Prix', 'Spanish Grand Prix', 'Styrian Grand Prix', 'São Paulo Grand Prix', 'Turkish Grand Prix', 'United States Grand Prix'],
    2022: ['Abu Dhabi Grand Prix', 'Australian Grand Prix', 'Austrian Grand Prix', 'Azerbaijan Grand Prix', 'Bahrain Grand Prix', 'Belgian Grand Prix', 'British Grand Prix', 'Canadian Grand Prix', 'Dutch Grand Prix', 'Emilia Romagna Grand Prix', 'French Grand Prix', 'Hungarian Grand Prix', 'Italian Grand Prix', 'Japanese Grand Prix', 'Mexico City Grand Prix', 'Miami Grand Prix', 'Monaco Grand Prix', 'Saudi Arabian Grand Prix', 'Singapore Grand Prix', 'Spanish Grand Prix', 'São Paulo Grand Prix', 'United States Grand Prix'],
    2023: [
        "Bahrain Grand Prix", "Saudi Arabian Grand Prix", "Australian Grand Prix", "Azerbaijan Grand Prix",
        "Miami Grand Prix", "Monaco Grand Prix", "Spanish Grand Prix", "Canadian Grand Prix",
        "Austrian Grand Prix", "British Grand Prix", "Hungarian Grand Prix", "Belgian Grand Prix",
        "Dutch Grand Prix", "Italian Grand Prix", "Singapore Grand Prix", "Japanese Grand Prix",
        "Qatar Grand Prix", "United States Grand Prix", "Mexico City Grand Prix", "São Paulo Grand Prix",
        "Las Vegas Grand Prix", "Abu Dhabi Grand Prix",
    ],
    2024: [
        "Bahrain Grand Prix", "Saudi Arabian Grand Prix", "Australian Grand Prix", "Japanese Grand Prix",
        "Chinese Grand Prix", "Miami Grand Prix", "Emilia Romagna Grand Prix", "Monaco Grand Prix",
        "Canadian Grand Prix", "Spanish Grand Prix", "Austrian Grand Prix", "British Grand Prix",
        "Hungarian Grand Prix", "Belgian Grand Prix", "Dutch Grand Prix", "Italian Grand Prix",
        "Azerbaijan Grand Prix", "Singapore Grand Prix", "United States Grand Prix", "Mexico City Grand Prix",
        "São Paulo Grand Prix", "Las Vegas Grand Prix", "Qatar Grand Prix", "Abu Dhabi Grand Prix",
    ],
    2025: [
        "Australian Grand Prix", "Chinese Grand Prix", "Japanese Grand Prix", "Bahrain Grand Prix",
        "Saudi Arabian Grand Prix", "Miami Grand Prix", "Emilia Romagna Grand Prix", "Monaco Grand Prix",
        "Spanish Grand Prix", "Canadian Grand Prix", "Austrian Grand Prix", "British Grand Prix",
        "Belgian Grand Prix", "Hungarian Grand Prix", "Dutch Grand Prix", "Italian Grand Prix",
        "Azerbaijan Grand Prix", "Singapore Grand Prix", "United States Grand Prix",
        "Mexico City Grand Prix", "São Paulo Grand Prix", "Las Vegas Grand Prix", "Qatar Grand Prix",
        "Abu Dhabi Grand Prix",
    ],
    # 2026 : courses déjà disputées (l'ordre réel est repris des dates de session)
    2026: [
        "Australian Grand Prix", "Chinese Grand Prix", "Japanese Grand Prix", "Bahrain Grand Prix",
        "Miami Grand Prix", "Canadian Grand Prix", "Monaco Grand Prix", "Barcelona Grand Prix",
        "Austrian Grand Prix", "British Grand Prix", "Belgian Grand Prix", "Hungarian Grand Prix",
        "Dutch Grand Prix", "Italian Grand Prix", "Spanish Grand Prix", "Azerbaijan Grand Prix",
        "Singapore Grand Prix", "United States Grand Prix", "Mexico City Grand Prix",
        "São Paulo Grand Prix", "Las Vegas Grand Prix", "Qatar Grand Prix", "Abu Dhabi Grand Prix",
    ],
}


def seasons_to_fetch() -> dict:
    """Saisons connues + saisons suivantes d'après le calendrier (2027...), jusqu'à la saison cible."""
    import json
    out = {s: list(g) for s, g in SEASONS.items()}
    if CALENDAR_FILE.exists():
        cal = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
        for s, races in cal.items():
            if s.isdigit() and int(s) <= TARGET_SEASON:
                names = out.setdefault(int(s), [])
                names += [r["gp"] for r in races if r["gp"] not in names]
    return out
TARGET_HISTORY: dict = {}  # l'historique complet 2023-2024 est maintenant dans SEASONS

# week-ends sprint : qualif sprint et sprint téléchargées aussi (rythme du week-end, étape 2)
SESSIONS = ["Qualifying", "Practice 1", "Practice 2", "Practice 3", "Sprint Qualifying", "Sprint", "Race"]

# Caractéristiques des circuits (hypothèse de l'équipe, d'après leur profil connu) :
# appui aérodynamique demandé (low / medium / high) et circuit urbain ou non.
CIRCUITS = {
    "Australian": ("medium", True), "Chinese": ("medium", False), "Japanese": ("high", False),
    "Bahrain": ("medium", False), "Saudi Arabian": ("low", True), "Miami": ("medium", True),
    "Emilia Romagna": ("high", False), "Monaco": ("high", True), "Spanish": ("high", False),
    "Barcelona": ("high", False), "Canadian": ("low", True), "Austrian": ("medium", False),
    "British": ("medium", False), "Belgian": ("low", False), "Hungarian": ("high", False),
    "Dutch": ("high", False), "Italian": ("low", False), "Azerbaijan": ("low", True),
    "Singapore": ("high", True), "United States": ("medium", False), "Mexico City": ("high", False),
    "São Paulo": ("medium", False), "Las Vegas": ("low", True), "Qatar": ("high", False),
    "Abu Dhabi": ("medium", False),
    # anciens Grands Prix (2018-2022)
    "French": ("medium", False), "German": ("medium", False), "Russian": ("medium", False),
    "Portuguese": ("medium", False), "Turkish": ("medium", False), "Styrian": ("medium", False),
    "70th Anniversary": ("medium", False), "Eifel": ("medium", False), "Tuscan": ("high", False),
    "Sakhir": ("low", False), "Brazilian": ("medium", False), "Mexican": ("high", False),
}

# Même nom de GP, circuit différent selon la saison
CIRCUIT_BY_SEASON = {(2026, "Spanish"): ("medium", True)}   # 2026 : nouveau circuit de Madrid
SAME_CIRCUIT_LAST_YEAR = {(2026, "Barcelona"): "Spanish", (2026, "Spanish"): None,
                          (2020, "Styrian"): "Austrian", (2020, "70th Anniversary"): "British",
                          (2020, "Sakhir"): None, (2022, "São Paulo"): "São Paulo"}


def circuit_type(season: int, gp: str) -> tuple:
    return CIRCUIT_BY_SEASON.get((season, gp), CIRCUITS.get(gp, ("medium", False)))


# Un écart au poleman supérieur à ce seuil (en %) est un incident (crash, pas de tour) : écarté
MAX_DEFICIT_PCT = 4.0
N_SIMULATIONS = 100_000
