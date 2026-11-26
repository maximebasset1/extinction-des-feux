"""En-tête et filtres des pages générées : une barre principale (F1, Football, En direct, Ligues, Méthode), le compte à
droite sur les pages qui ne sont pas de Formule 1, et une seule ligne de filtres pour les compétitions de football."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site  # noqa: E402

MENU = ["F1", "Football", "En direct", "Ligues", "Méthode"]
BARRE_FOOT = ["À la une", "Mes favoris", "Ligue 1", "LDC", "LEC", "Premier League", "Liga", "Serie A", "Bundesliga"]
F1 = ("f1.html", "f1-methode.html")
REDIRECTIONS = ("ligue1.html", "recherche.html")
PAGES = {p: html for p, html in build_site.pages().items() if p not in REDIRECTIONS}


def textes(bloc: str, balise: str) -> list[str]:
    return [re.sub(r"<.*", "", t, flags=re.S).strip() for t in re.findall(rf"<{balise} [^>]*>(.*?)</{balise}>", bloc, re.S)]


def bloc(html: str, motif: str) -> str:
    trouve = re.search(motif, html, re.S)
    assert trouve, motif
    return trouve.group(0)


def menu(html: str) -> str:
    return bloc(html, r'<nav class="menu".*?</nav>')


def courant(html: str) -> list[str]:
    return textes("".join(re.findall(r'<a [^>]*aria-current="page"[^>]*>.*?</a>', html, re.S)), "a")


def scripts(html: str) -> list[str]:
    return re.findall(r'<script[^>]* src="[./]*assets/([\w-]+\.js)\?v=[0-9a-f]{8}"', html)


def test_barre_principale_identique_sur_toutes_les_pages_sans_seconde_rangee():
    assert len(PAGES) == 14
    for p, html in PAGES.items():
        assert textes(menu(html), "a") == MENU, p
        assert 'class="bande' not in html, p


def test_la_page_courante_est_marquee_dans_la_barre():
    for p, attendu in {"index.html": [], "f1.html": ["F1"], "f1-methode.html": ["F1"], "foot.html": ["Football"],
                       "foot/en-direct.html": ["En direct"], "foot/ligues.html": ["Ligues"], "methode.html": ["Méthode"],
                       "foot/serie-a.html": ["Football"]}.items():
        assert courant(menu(PAGES[p])) == attendu, p


def test_indicateur_de_match_en_direct_sur_les_pages_hors_formule_1():
    html = PAGES["foot/en-direct.html"]
    assert re.search(r'<a href="\.\./foot/en-direct\.html" data-direct aria-current="page">En direct<span class="menu-live" hidden>', html)
    for p, page in PAGES.items():
        if p in F1:
            assert "onglet-direct.js" not in page, p
            continue
        ordre = scripts(page)
        assert ordre.index("direct.js") < ordre.index("onglet-direct.js"), p


def test_compte_partout_sauf_en_formule_1_qui_reste_decouplee():
    for p, html in PAGES.items():
        if p in F1:
            assert not {"compte.js", "favoris.js", "commun.js"} & set(scripts(html)), p
            assert "btn-compte" not in html and "dlg-compte" not in html, p
            continue
        ordre = scripts(html)
        assert ordre.index("commun.js") < ordre.index("favoris.js") < ordre.index("compte.js"), p
        assert len(ordre) == len(set(ordre)), p
        assert re.search(r'<button type="button" class="btn-compte" id="btn-compte" hidden>Connexion</button>', html), p
        assert html.count('id="dlg-compte"') == 1, p
        liens = textes(bloc(html, r'<ul class="compte-menu" id="menu-compte" hidden>.*?</ul>'), "a")
        assert liens == ["Mes favoris", "Mes ligues"] and ">Déconnexion</button>" in html, p


def test_fenetre_de_compte_deux_champs_et_aucun_exemple_dans_les_saisies():
    html = PAGES["foot/ligues.html"]
    fenetre = bloc(html, r'<dialog class="compte-dlg" id="dlg-compte".*?</dialog>')
    assert re.findall(r"<label for=\"[\w-]+\">(.*?)</label>", fenetre) == ["Pseudo", "Mot de passe"]
    assert re.findall(r'<input [^>]*type="(\w+)"', fenetre) == ["text", "password"]
    for p, page in PAGES.items():
        assert "placeholder" not in page, p


def competitions() -> dict[str, str]:
    pages = {p: h for p, h in PAGES.items() if p.startswith("foot/") and p not in ("foot/en-direct.html", "foot/ligues.html")}
    assert len(pages) == 7
    return pages


def barre_foot(html: str) -> str:
    return bloc(html, r'<nav class="filtres" id="nav-foot" aria-label="Football">.*?</nav>')


def en_ordre(html: str, *reperes: str) -> None:
    """Chaque repère est présent, et dans cet ordre."""
    positions = [html.index(r) for r in reperes]
    assert positions == sorted(positions), reperes


def test_barre_football_en_tete_de_la_section_identique_sur_les_huit_pages():
    pages = {"foot.html": PAGES["foot.html"], **competitions()}
    for p, html in pages.items():
        assert textes(barre_foot(html), "a") == BARRE_FOOT, p
        assert len(courant(barre_foot(html))) == 1, p
        # tout en haut : rien entre l'en-tête du site et la barre
        assert html.split('<main id="contenu">')[1].lstrip().startswith('<div class="nav-foot">'), p
    assert courant(barre_foot(pages["foot.html"])) == ["À la une"]
    assert courant(barre_foot(pages["foot/ligue-des-champions.html"])) == ["LDC"]
    assert courant(barre_foot(pages["foot/ligue-1.html"])) == ["Ligue 1"]
    assert 'href="../foot.html#favoris"' in barre_foot(pages["foot/ligue-1.html"])
    for p in ("foot/en-direct.html", "foot/ligues.html", "index.html"):
        assert 'class="nav-foot"' not in PAGES[p], p


def test_accueil_football_direct_et_affiches_d_abord_les_favoris_dans_leur_vue():
    hub = PAGES["foot.html"]
    assert "titre-page" not in hub
    en_ordre(hub, 'id="nav-foot"', 'id="bloc-direct"', 'id="vue-une"', 'id="affiches-liste"', 'id="q"', 'id="results"',
             'id="competitions"', 'id="vue-favoris"', 'id="favoris-liste"', 'id="favoris-matchs"')
    assert re.search(r'<div id="vue-favoris" hidden>', hub)
    ordre = scripts(hub)
    for s in ("modele-direct.js", "direct.js", "fiche.js"):
        assert ordre.index(s) < ordre.index("foot.js"), s


def test_pages_de_competition_deux_vues_et_journees_sans_sous_onglet():
    for p, html in competitions().items():
        onglets = bloc(html, r'<div class="vues" role="tablist".*?</div>')
        assert textes(onglets, "button") == ["Matchs", "Classement"], p
        assert onglets.count('aria-selected="true"') == 1 and 'id="onglet-matchs" aria-controls="vue-matchs" aria-selected="true"' in onglets, p
        assert "sommaire" not in html and "j-select" not in html, p
        assert re.search(r'id="j-prev"[^>]*>.*?Journée précédente', html, re.S), p
        assert re.search(r'id="j-next"[^>]*>.*?Journée suivante', html, re.S), p
        en_ordre(html, 'id="nav-foot"', 'class="vues"', 'id="vue-matchs"', 'id="j-prev"', 'id="j-pilules"', 'id="j-next"',
                 'id="bloc-direct"', 'id="j-liste"', 'id="vue-classement"', 'id="classement"', 'id="face"', 'id="club"',
                 'id="fiabilite"')
        assert re.search(r'<div id="vue-classement" role="tabpanel" aria-labelledby="onglet-classement" hidden>', html), p
        ordre = scripts(html)
        assert ordre.index("journees.js") < ordre.index("competition.js"), p


def test_page_en_direct_synchronisation_visible_et_actualisation_a_la_main():
    html = PAGES["foot/en-direct.html"]
    assert re.search(r'<button type="button" class="btn-secondaire" id="live-actualiser">Actualiser</button>', html)
    en_ordre(html, 'id="live-synchro"', 'id="live-actualiser"', 'id="live-alerte"', 'id="live-note"', 'id="live-liste"',
             'id="jour-liste"', 'id="termines-liste"', 'id="prochains-liste"')


def test_page_ligues_charge_module_et_synchronise_points():
    html = PAGES["foot/ligues.html"]
    assert re.search(r'<script type="module" src="\.\./assets/ligues\.js\?v=[0-9a-f]{8}"></script>', html)
    assert 'id="c-comps"' in html and 'id="l-comps"' in html
    assert build_site.POINTS_DST.read_text(encoding="utf-8") == build_site.POINTS_SRC.read_text(encoding="utf-8")
