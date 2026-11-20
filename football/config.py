"""Football : réglages communs et couleurs des clubs de Ligue 1 (pour leur écusson)."""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"
# la saison commence en août : de juillet à décembre c'est l'année de début, ensuite l'année d'avant
_TODAY = date.today()
CURRENT_SEASON = _TODAY.year if _TODAY.month >= 7 else _TODAY.year - 1
MIN_MODEL_WEIGHT = 0.3     # le pronostic garde toujours une part de nos statistiques : ce n'est jamais la cote recopiée

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
