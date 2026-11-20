"""Sonde 3 (accord de Maxime) : licences des logos restants (Troyes, Lens, Rennes), lentement."""
import json, time, urllib.parse, urllib.request
from pathlib import Path
UA = {"User-Agent": "extinction-des-feux/1.0 (projet etudiant; github.com/maximebasset1/extinction-des-feux)"}
def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == 4:
                raise
            time.sleep(30 * (i + 1))
Path("sonde/logos").mkdir(parents=True, exist_ok=True)
OUT = {}
FILES = {"Troyes": ["ESTAC_Troyes_Logo.svg"]}
PAGES = {"Lens": ("en", "RC Lens"), "Rennes": ("en", "Stade Rennais F.C."), "Troyes": ("en", "ES Troyes AC")}
for club, (wiki, page) in PAGES.items():
    q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "pageimages", "piprop": "name", "titles": page, "redirects": 1})
    name = next(iter(json.loads(get(f"https://{wiki}.wikipedia.org/w/api.php?{q}"))["query"]["pages"].values())).get("pageimage")
    FILES.setdefault(club, []).append(name)
    time.sleep(5)
for club, names in FILES.items():
    OUT[club] = []
    for name in [n for n in names if n]:
        q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata", "titles": f"File:{name}"})
        p = next(iter(json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))["query"]["pages"].values()))
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value")
        OUT[club].append({"file": name, "on_commons": "imageinfo" in p, "license": lic, "url": ii.get("url")})
        if lic and lic.lower().startswith(("public domain", "cc0", "cc by")) and ii.get("url"):
            Path(f"sonde/logos/{club.lower()}.svg").write_bytes(get(ii["url"]))
        time.sleep(5)
json.dump(OUT, open("sonde/resultat3.json", "w"), ensure_ascii=False, indent=1)
