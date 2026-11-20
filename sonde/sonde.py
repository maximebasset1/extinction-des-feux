"""Sonde 2 (accord de Maxime) : récupère les fichiers Ligue 1 de football-data.co.uk et les logos réellement libres."""
import csv, io, json, time, urllib.parse, urllib.request
from pathlib import Path
UA = {"User-Agent": "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"}
OUT = {"fichiers": {}, "logos": {}}
Path("sonde/data").mkdir(parents=True, exist_ok=True)
Path("sonde/logos").mkdir(parents=True, exist_ok=True)

def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(10 * (i + 1))

for y in range(2000, 2027):
    s = f"{y % 100:02d}{(y + 1) % 100:02d}"
    try:
        b = get(f"https://www.football-data.co.uk/mmz4281/{s}/F1.csv")
        Path(f"sonde/data/F1_{s}.csv").write_bytes(b)
        OUT["fichiers"][s] = len(b)
    except Exception as e:
        OUT["fichiers"][s] = repr(e)
    time.sleep(1)
try:
    Path("sonde/data/fixtures.csv").write_bytes(get("https://www.football-data.co.uk/fixtures.csv"))
except Exception as e:
    OUT["fichiers"]["fixtures"] = repr(e)

PAGES = {"AJ Auxerre": "AJ Auxerre", "AS Monaco FC": "AS Monaco FC", "Angers SCO": "Angers SCO", "ES Troyes AC": "ES Troyes AC",
         "FC Lorient": "FC Lorient", "Le Havre AC": "Le Havre AC", "Le Mans FC": "Le Mans FC", "Lille OSC": "Lille OSC",
         "OGC Nice": "OGC Nice", "Olympique Lyonnais": "Olympique Lyonnais", "Olympique de Marseille": "Olympique de Marseille",
         "Paris FC": "Paris FC", "Paris Saint-Germain FC": "Paris Saint-Germain F.C.", "RC Strasbourg Alsace": "RC Strasbourg Alsace",
         "Racing Club de Lens": "RC Lens", "Stade Brestois 29": "Stade Brestois 29", "Stade Rennais FC 1901": "Stade Rennais F.C.",
         "Toulouse FC": "Toulouse FC"}
FREE = ("public domain", "pd", "cc0", "cc by", "cc-by")
for club, page in PAGES.items():
    info = {}
    for wiki in ("en", "fr"):
        try:
            q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "pageimages", "piprop": "name", "titles": page, "redirects": 1})
            name = next(iter(json.loads(get(f"https://{wiki}.wikipedia.org/w/api.php?{q}"))["query"]["pages"].values())).get("pageimage")
            time.sleep(2)
            if not name:
                continue
            q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata", "titles": f"File:{name}"})
            p = next(iter(json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))["query"]["pages"].values()))
            time.sleep(2)
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = meta.get("LicenseShortName", {}).get("value")
            info[wiki] = {"file": name, "on_commons": "imageinfo" in p, "url": ii.get("url"), "license": lic,
                          "artist": meta.get("Artist", {}).get("value"), "restrictions": meta.get("Restrictions", {}).get("value")}
            if lic and lic.lower().startswith(FREE) and ii.get("url") and "logo" not in info:
                ext = ii["url"].rsplit(".", 1)[-1].lower()
                fn = f"sonde/logos/{club.replace(' ', '_')}.{ext}"
                Path(fn).write_bytes(get(ii["url"]))
                info["logo"] = fn
                time.sleep(2)
        except Exception as e:
            info[wiki] = {"error": repr(e)}
    OUT["logos"][club] = info
json.dump(OUT, open("sonde/resultat.json", "w"), ensure_ascii=False, indent=1)
