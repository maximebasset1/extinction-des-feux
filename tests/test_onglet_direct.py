"""Barre des compétitions du football : l'onglet « En direct » vient juste après « Tous les matchs »."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site  # noqa: E402

ORDRE = ["Tous les matchs", "En direct", "Premier League", "Bundesliga", "Liga", "Serie A", "Ligue 1", "Ligue des champions", "Ligue Europa"]


def onglets(html: str) -> list[str]:
    bande = re.search(r'<nav class="bande".*?</nav>', html, re.S).group(0)
    return [re.sub(r"<span.*", "", t).strip() for t in re.findall(r"<a [^>]*>(.*?)</a>", bande, re.S)]


def test_onglets_football_dans_l_ordre_sur_toutes_les_pages():
    pages = build_site.pages()
    foot = [p for p in pages if p == "foot.html" or p.startswith("foot/")]
    assert "foot/en-direct.html" in foot and "foot/serie-a.html" in foot and len(foot) == 9
    for p in foot:
        assert onglets(pages[p]) == ORDRE, p
        # le compteur et son script sont sur chaque page Football, rien de tel côté F1
        assert "onglet-direct.js" in pages[p], p
        assert "direct.js" in re.findall(r'assets/([\w-]+\.js)', pages[p]), p
    for p in ("f1.html", "f1-methode.html"):
        assert "onglet-direct.js" not in pages[p] and "bande" not in pages[p]


def test_page_en_direct_marque_son_onglet_et_cache_la_pastille():
    html = build_site.pages()["foot/en-direct.html"]
    assert html.count('aria-current="page"') == 2   # « Football » (menu) et « En direct » (barre)
    assert re.search(r'<a href="\.\./foot/en-direct\.html" data-direct aria-current="page">En direct<span class="bande-live" hidden>', html)
