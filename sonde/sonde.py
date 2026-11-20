"""Sonde (accord de Maxime) : vérifie depuis GitHub les sources Ligue 1 : résultats, cotes, calendrier, licences des logos."""
import csv, io, json, urllib.parse, urllib.request
OUT = {}
UA = {"User-Agent": "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()

def probe_csv(name, url):
    try:
        rows = list(csv.DictReader(io.StringIO(get(url).decode("latin-1"))))
        OUT[name] = {"ok": True, "rows": len(rows), "columns": list(rows[0].keys()) if rows else [],
                     "first": rows[0] if rows else None, "last": rows[-1] if rows else None}
    except Exception as e:
        OUT[name] = {"ok": False, "error": repr(e)}

for s in ["2627", "2526", "0506"]:
    probe_csv(f"fd_{s}", f"https://www.football-data.co.uk/mmz4281/{s}/F1.csv")
try:
    rows = [r for r in csv.DictReader(io.StringIO(get("https://www.football-data.co.uk/fixtures.csv").decode("latin-1"))) if r.get("Div") == "F1"]
    OUT["fd_fixtures"] = {"ok": True, "rows_F1": len(rows), "sample": rows[:3]}
except Exception as e:
    OUT["fd_fixtures"] = {"ok": False, "error": repr(e)}

PAGES = {"AJ Auxerre": "AJ Auxerre", "AS Monaco FC": "AS Monaco FC", "Angers SCO": "Angers SCO", "ES Troyes AC": "ES Troyes AC",
         "FC Lorient": "FC Lorient", "Le Havre AC": "Le Havre AC", "Le Mans FC": "Le Mans FC", "Lille OSC": "Lille OSC",
         "OGC Nice": "OGC Nice", "Olympique Lyonnais": "Olympique lyonnais", "Olympique de Marseille": "Olympique de Marseille",
         "Paris FC": "Paris FC", "Paris Saint-Germain FC": "Paris Saint-Germain Football Club", "RC Strasbourg Alsace": "Racing Club de Strasbourg Alsace",
         "Racing Club de Lens": "Racing Club de Lens", "Stade Brestois 29": "Stade brestois 29",
         "Stade Rennais FC 1901": "Stade rennais football club", "Toulouse FC": "Toulouse Football Club"}
logos = {}
for club, page in PAGES.items():
    try:
        q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "pageimages", "piprop": "name", "titles": page, "redirects": 1})
        name = next(iter(json.loads(get(f"https://fr.wikipedia.org/w/api.php?{q}"))["query"]["pages"].values())).get("pageimage")
        info = {"file": name}
        if name:
            q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata", "titles": f"File:{name}"})
            p = next(iter(json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))["query"]["pages"].values()))
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            info.update(on_commons="imageinfo" in p, url=ii.get("url"), license=meta.get("LicenseShortName", {}).get("value"),
                        copyrighted=meta.get("Copyrighted", {}).get("value"), restrictions=meta.get("Restrictions", {}).get("value"))
        logos[club] = info
    except Exception as e:
        logos[club] = {"error": repr(e)}
OUT["logos"] = logos
json.dump(OUT, open("sonde/resultat.json", "w"), ensure_ascii=False, indent=1)
