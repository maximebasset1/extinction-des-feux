"""Ligue 1 : réglages, noms d'équipes, couleurs."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(os.environ.get("L1_DATA_DIR", ROOT / "data" / "football" / "raw"))
PROCESSED = ROOT / "data" / "football"
SITE_DATA = ROOT / "site" / "data" / "ligue1"
JOURNAL = ROOT / "data" / "journal" / "ligue1.csv"

FD_URL = "https://www.football-data.co.uk/mmz4281/{code}/F1.csv"
FD_FIXTURES = "https://www.football-data.co.uk/fixtures.csv"
MIRROR_URL = "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/ligue-1/season-{code}.csv"
OPENFOOTBALL_URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/fr.1.json"
USER_AGENT = "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"

FIRST_ODDS_SEASON = 2000   # football-data : cotes à partir de 2000-01
FIRST_MIRROR_SEASON = 1993 # historique des face-à-face
CURRENT_SEASON = 2026      # 2026-27

# saisons du backtest : CHOIX des réglages, puis TEST (jamais utilisé pour choisir)
CHOICE_SEASONS = [2015, 2016, 2017, 2018, 2019]
TEST_SEASONS = [2021, 2022, 2023, 2024, 2025, 2026]
# 2020-21 (huis clos, calendrier chamboulé) : ni choix ni test, mais sert à l'apprentissage

# openfootball -> football-data
OPENFOOTBALL_NAMES = {
    "AJ Auxerre": "Auxerre", "AS Monaco FC": "Monaco", "Angers SCO": "Angers", "ES Troyes AC": "Troyes",
    "FC Lorient": "Lorient", "Le Havre AC": "Le Havre", "Le Mans FC": "Le Mans", "Lille OSC": "Lille",
    "OGC Nice": "Nice", "Olympique Lyonnais": "Lyon", "Olympique de Marseille": "Marseille", "Paris FC": "Paris FC",
    "Paris Saint-Germain FC": "Paris SG", "RC Strasbourg Alsace": "Strasbourg", "Racing Club de Lens": "Lens",
    "Stade Brestois 29": "Brest", "Stade Rennais FC 1901": "Rennes", "Toulouse FC": "Toulouse",
}
# nom affiché, sigle, couleur principale, couleur secondaire (pastille)
CLUBS = {
    "Auxerre": ("AJ Auxerre", "AJA", "#0055a4", "#ffffff"), "Monaco": ("AS Monaco", "ASM", "#e2001a", "#ffffff"),
    "Angers": ("Angers SCO", "SCO", "#111111", "#ffffff"), "Troyes": ("ES Troyes AC", "ESTAC", "#0056a7", "#ffffff"),
    "Lorient": ("FC Lorient", "FCL", "#f58025", "#111111"), "Le Havre": ("Le Havre AC", "HAC", "#7ab8e6", "#0b2a4a"),
    "Le Mans": ("Le Mans FC", "LMFC", "#e30613", "#f6d000"), "Lille": ("LOSC Lille", "LOSC", "#d71920", "#1d2b58"),
    "Nice": ("OGC Nice", "OGCN", "#d0021b", "#111111"), "Lyon": ("Olympique lyonnais", "OL", "#ffffff", "#1c3f94"),
    "Marseille": ("Olympique de Marseille", "OM", "#2faee0", "#ffffff"), "Paris FC": ("Paris FC", "PFC", "#0b1f3a", "#9fc5e8"),
    "Paris SG": ("Paris Saint-Germain", "PSG", "#004170", "#da291c"), "Strasbourg": ("RC Strasbourg", "RCSA", "#009fe3", "#ffffff"),
    "Lens": ("RC Lens", "RCL", "#fde100", "#d0021b"), "Brest": ("Stade brestois", "SB29", "#e30613", "#ffffff"),
    "Rennes": ("Stade rennais", "SRFC", "#e30613", "#111111"), "Toulouse": ("Toulouse FC", "TFC", "#5b2a86", "#ffffff"),
}
