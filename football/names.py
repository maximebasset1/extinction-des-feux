"""Relie les noms de clubs des différentes sources aux noms de football-data.co.uk."""
import difflib
import re
import unicodedata

# mots qui n'aident pas à reconnaître un club
NOISE = {"fc", "cf", "afc", "sc", "ssc", "ac", "as", "sk", "kv", "osc", "club", "de", "del", "da", "do", "the", "fk", "nk", "sv",
         "vfl", "vfb", "tsg", "rcd", "cd", "ud", "sd", "ca", "rc", "us", "ogc", "aj", "ss", "bc", "calcio", "1899", "1900", "1901",
         "1904", "1907", "1909", "1913", "04", "05", "96", "e", "v", "spor", "kulubu", "futbol", "football", "sport", "sporting",
         "royale", "royal", "krc", "rsc", "pae", "sfp", "sad", "fsv", "bsc", "hsc", "losc", "stade", "olympique", "real", "atletico",
         "atlético", "athletic", "borussia", "eintracht", "bayer", "1", "s", "a", "ff", "if", "bk", "ik"}
# cas que la ressemblance des noms ne suffit pas à trancher : (pays, nom source) -> nom football-data
MANUAL = {
    ("ENG", "Manchester United FC"): "Man United", ("ENG", "Manchester United"): "Man United", ("ENG", "Manchester City FC"): "Man City",
    ("ENG", "Manchester City"): "Man City", ("ENG", "Tottenham Hotspur FC"): "Tottenham", ("ENG", "Tottenham Hotspur"): "Tottenham",
    ("ENG", "Wolverhampton Wanderers FC"): "Wolves", ("ENG", "Wolverhampton Wanderers"): "Wolves", ("ENG", "Newcastle United FC"): "Newcastle",
    ("ENG", "Nottingham Forest FC"): "Nott'm Forest", ("ENG", "West Ham United FC"): "West Ham", ("ENG", "Brighton & Hove Albion FC"): "Brighton",
    ("ENG", "Sheffield United FC"): "Sheffield United", ("ENG", "Leicester City FC"): "Leicester", ("ENG", "Leeds United FC"): "Leeds",
    ("GER", "FC Bayern München"): "Bayern Munich", ("GER", "Bayern München"): "Bayern Munich", ("GER", "Borussia Mönchengladbach"): "M'gladbach",
    ("GER", "Bayer 04 Leverkusen"): "Leverkusen", ("GER", "Bayer Leverkusen"): "Leverkusen", ("GER", "Borussia Dortmund"): "Dortmund",
    ("GER", "Eintracht Frankfurt"): "Ein Frankfurt", ("GER", "1. FC Köln"): "FC Koln", ("GER", "1. FSV Mainz 05"): "Mainz",
    ("GER", "TSG 1899 Hoffenheim"): "Hoffenheim", ("GER", "RB Leipzig"): "RB Leipzig", ("GER", "1. FC Union Berlin"): "Union Berlin",
    ("GER", "VfB Stuttgart"): "Stuttgart", ("GER", "VfL Wolfsburg"): "Wolfsburg", ("GER", "Hertha BSC"): "Hertha", ("GER", "FC Schalke 04"): "Schalke 04",
    ("GER", "SC Freiburg"): "Freiburg", ("GER", "Hamburger SV"): "Hamburg", ("GER", "Werder Bremen"): "Werder Bremen", ("GER", "SV Werder Bremen"): "Werder Bremen",
    ("GER", "1. FC Heidenheim 1846"): "Heidenheim", ("GER", "FC St. Pauli"): "St Pauli", ("GER", "FC Augsburg"): "Augsburg",
    ("ESP", "Club Atlético de Madrid"): "Ath Madrid", ("ESP", "Atlético Madrid"): "Ath Madrid", ("ESP", "Athletic Club"): "Ath Bilbao",
    ("ESP", "Athletic Bilbao"): "Ath Bilbao", ("ESP", "Real Madrid CF"): "Real Madrid", ("ESP", "Real Madrid"): "Real Madrid",
    ("ESP", "FC Barcelona"): "Barcelona", ("ESP", "Real Sociedad de Fútbol"): "Sociedad", ("ESP", "Real Sociedad"): "Sociedad",
    ("ESP", "Real Betis Balompié"): "Betis", ("ESP", "Real Betis"): "Betis", ("ESP", "RCD Espanyol de Barcelona"): "Espanol",
    ("ESP", "Espanyol"): "Espanol", ("ESP", "Celta de Vigo"): "Celta", ("ESP", "RC Celta de Vigo"): "Celta", ("ESP", "RC Celta"): "Celta",
    ("ESP", "Rayo Vallecano de Madrid"): "Vallecano", ("ESP", "Deportivo Alavés"): "Alaves", ("ESP", "CA Osasuna"): "Osasuna",
    ("ESP", "Villarreal CF"): "Villarreal", ("ESP", "Sevilla FC"): "Sevilla", ("ESP", "Valencia CF"): "Valencia", ("ESP", "Getafe CF"): "Getafe",
    ("ESP", "RCD Mallorca"): "Mallorca", ("ESP", "Girona FC"): "Girona", ("ESP", "Real Oviedo"): "Oviedo", ("ESP", "Levante UD"): "Levante",
    ("ESP", "Elche CF"): "Elche", ("ESP", "Deportivo La Coruña"): "La Coruna", ("ESP", "RC Deportivo La Coruña"): "La Coruna", ("ESP", "Málaga CF"): "Malaga",
    ("ITA", "FC Internazionale Milano"): "Inter", ("ITA", "Internazionale"): "Inter", ("ITA", "Inter"): "Inter", ("ITA", "AC Milan"): "Milan",
    ("ITA", "Milan"): "Milan", ("ITA", "SSC Napoli"): "Napoli", ("ITA", "Juventus FC"): "Juventus", ("ITA", "Juventus"): "Juventus",
    ("ITA", "AS Roma"): "Roma", ("ITA", "SS Lazio"): "Lazio", ("ITA", "Atalanta BC"): "Atalanta", ("ITA", "ACF Fiorentina"): "Fiorentina",
    ("ITA", "Bologna FC 1909"): "Bologna", ("ITA", "Torino FC"): "Torino", ("ITA", "Udinese Calcio"): "Udinese", ("ITA", "Como 1907"): "Como",
    ("FRA", "Paris Saint-Germain FC"): "Paris SG", ("FRA", "Paris Saint-Germain"): "Paris SG", ("FRA", "Olympique de Marseille"): "Marseille",
    ("FRA", "Olympique Lyonnais"): "Lyon", ("FRA", "Lille OSC"): "Lille", ("FRA", "LOSC Lille"): "Lille", ("FRA", "AS Monaco FC"): "Monaco",
    ("MCO", "AS Monaco FC"): "Monaco", ("MCO", "AS Monaco"): "Monaco", ("MCO", "Monaco"): "Monaco", ("FRA", "AS Monaco"): "Monaco",
    ("FRA", "Stade Rennais FC 1901"): "Rennes", ("FRA", "Stade Rennais FC"): "Rennes", ("FRA", "Stade Rennais"): "Rennes",
    ("FRA", "OGC Nice"): "Nice", ("FRA", "RC Lens"): "Lens", ("FRA", "Racing Club de Lens"): "Lens", ("FRA", "Stade Brestois 29"): "Brest",
    ("FRA", "RC Strasbourg Alsace"): "Strasbourg", ("FRA", "Girondins de Bordeaux"): "Bordeaux", ("FRA", "FC Girondins de Bordeaux"): "Bordeaux",
    ("FRA", "AS Saint-Étienne"): "St Etienne", ("FRA", "Montpellier HSC"): "Montpellier", ("FRA", "Toulouse FC"): "Toulouse",
    ("FRA", "FC Nantes"): "Nantes", ("FRA", "Stade de Reims"): "Reims", ("FRA", "Angers SCO"): "Angers", ("FRA", "Paris FC"): "Paris FC",
    ("POR", "Sport Lisboa e Benfica"): "Benfica", ("POR", "SL Benfica"): "Benfica", ("POR", "Benfica"): "Benfica",
    ("POR", "Sporting Clube de Portugal"): "Sp Lisbon", ("POR", "Sporting CP"): "Sp Lisbon", ("POR", "Sporting Lisbon"): "Sp Lisbon",
    ("POR", "FC Porto"): "Porto", ("POR", "SC Braga"): "Sp Braga", ("POR", "Sporting Braga"): "Sp Braga", ("POR", "Vitória Guimarães"): "Guimaraes",
    ("POR", "Vitória SC"): "Guimaraes", ("NED", "PSV"): "PSV Eindhoven", ("NED", "PSV Eindhoven"): "PSV Eindhoven", ("NED", "AFC Ajax"): "Ajax",
    ("NED", "Ajax Amsterdam"): "Ajax", ("NED", "Feyenoord Rotterdam"): "Feyenoord", ("NED", "AZ Alkmaar"): "AZ Alkmaar", ("NED", "AZ"): "AZ Alkmaar",
    ("NED", "FC Twente"): "Twente", ("NED", "FC Utrecht"): "Utrecht", ("NED", "Go Ahead Eagles"): "Go Ahead Eagles",
    ("BEL", "Club Brugge KV"): "Club Brugge", ("BEL", "Club Brugge"): "Club Brugge", ("BEL", "Royale Union Saint-Gilloise"): "St. Gilloise",
    ("BEL", "Union Saint-Gilloise"): "St. Gilloise", ("BEL", "RSC Anderlecht"): "Anderlecht", ("BEL", "KRC Genk"): "Genk",
    ("BEL", "KAA Gent"): "Gent", ("BEL", "Royal Antwerp FC"): "Antwerp", ("BEL", "Standard Liège"): "Standard",
    ("SCO", "Celtic FC"): "Celtic", ("SCO", "Celtic"): "Celtic", ("SCO", "Rangers FC"): "Rangers", ("SCO", "Rangers"): "Rangers",
    ("SCO", "Aberdeen FC"): "Aberdeen", ("SCO", "Heart of Midlothian FC"): "Hearts",
    ("TUR", "Galatasaray SK"): "Galatasaray", ("TUR", "Galatasaray"): "Galatasaray", ("TUR", "Fenerbahçe SK"): "Fenerbahce",
    ("TUR", "Fenerbahçe"): "Fenerbahce", ("TUR", "Beşiktaş JK"): "Besiktas", ("TUR", "Beşiktaş"): "Besiktas", ("TUR", "Trabzonspor"): "Trabzonspor",
    ("TUR", "İstanbul Başakşehir FK"): "Buyuksehyr", ("TUR", "Başakşehir"): "Buyuksehyr",
    ("GRE", "PAE Olympiakos SFP"): "Olympiakos", ("GRE", "Olympiakos Piräus"): "Olympiakos", ("GRE", "Olympiacos"): "Olympiakos",
    ("GRE", "Panathinaikos FC"): "Panathinaikos", ("GRE", "PAOK FC"): "PAOK", ("GRE", "PAOK Thessaloniki"): "PAOK", ("GRE", "AEK Athens FC"): "AEK",
    ("GRE", "AEK Athens"): "AEK", ("GRE", "AEK Athen"): "AEK",
    ("AUT", "FC Red Bull Salzburg"): "Salzburg", ("AUT", "Red Bull Salzburg"): "Salzburg", ("AUT", "SK Sturm Graz"): "Sturm Graz",
    ("AUT", "SK Rapid Wien"): "SK Rapid", ("AUT", "Rapid Wien"): "SK Rapid", ("ITA", "Lazio Roma"): "Lazio",
    ("ENG", "West Ham United"): "West Ham", ("GER", "Bor. Mönchengladbach"): "M'gladbach", ("POR", "Sporting Clube de Braga"): "Sp Braga",
    ("ROU", "FC Steaua Bucureşti"): "FCSB", ("ROU", "Steaua Bucureşti"): "FCSB", ("RUS", "CSKA Moskva"): "CSKA Moscow",
    ("RUS", "Spartak Moskva"): "Spartak Moscow", ("TUR", "İstanbul Başakşehir"): "Buyuksehyr", ("AUT", "LASK"): "LASK", ("AUT", "LASK Linz"): "LASK",
    ("SUI", "BSC Young Boys"): "Young Boys", ("SUI", "FC Basel 1893"): "Basel", ("SUI", "FC Basel"): "Basel", ("SUI", "FC Zürich"): "Zurich",
    ("DEN", "FC København"): "FC Copenhagen", ("DEN", "FC Copenhagen"): "FC Copenhagen", ("DEN", "FC Midtjylland"): "Midtjylland",
    ("NOR", "FK Bodø/Glimt"): "Bodo/Glimt", ("NOR", "Bodø/Glimt"): "Bodo/Glimt", ("NOR", "Molde FK"): "Molde",
    ("SWE", "Malmö FF"): "Malmo FF", ("POL", "Legia Warszawa"): "Legia", ("ROU", "FCSB"): "FCSB",
    ("RUS", "FK Zenit St. Petersburg"): "Zenit", ("RUS", "Zenit St. Petersburg"): "Zenit", ("RUS", "PFC CSKA Moskva"): "CSKA Moscow",
    ("RUS", "FK Spartak Moskva"): "Spartak Moscow", ("RUS", "FK Lokomotiv Moskva"): "Lokomotiv Moscow", ("RUS", "FK Krasnodar"): "Krasnodar",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("'", ""))
    words = [w for w in s.split() if w not in NOISE]
    return " ".join(words) or s.strip()


def match(country: str, name: str, candidates: list[str]) -> str | None:
    """Nom football-data correspondant, ou None si aucun n'est assez proche."""
    if (country, name) in MANUAL:
        return MANUAL[(country, name)]
    if name in candidates:
        return name
    n = norm(name)
    by_norm = {norm(c): c for c in candidates}
    if n in by_norm:
        return by_norm[n]
    # un nom contient l'autre (« Brentford » / « Brentford FC ») ; ambigu (« Lazio Roma ») : on ne choisit pas
    hits = [c for k, c in by_norm.items() if k and n and (k in n.split() or n in k.split() or k == n.replace(" ", ""))]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return None
    best = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.8)
    return by_norm[best[0]] if best else None
