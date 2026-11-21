"""Génère les pages HTML du site (même en-tête et même pied de page partout).

python scripts/build_site.py          écrit les pages dans site/
python scripts/build_site.py --check  vérifie seulement qu'elles sont à jour (utilisé par les tests)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; "
       "connect-src 'self'; base-uri 'self'; form-action 'none'")
COMPETITIONS = [("E0", "premier-league", "Premier League"), ("D1", "bundesliga", "Bundesliga"), ("SP1", "liga", "Liga"),
                ("F1", "ligue-1", "Ligue 1"), ("LDC", "ligue-des-champions", "Ligue des champions"),
                ("LEC", "ligue-europa", "Ligue Europa")]
LIGHTS = '<span class="feux" aria-hidden="true">' + '<i></i>' * 5 + "</span>"


def page(path: str, title: str, description: str, body: str, scripts: list[str], section: str, sub: str = "") -> str:
    depth = path.count("/")
    r = "../" * depth or ""
    def link(href: str, label: str, key: str) -> str:
        cur = ' aria-current="page"' if key == section else ""
        return f'<a href="{r}{href}"{cur}>{label}</a>'
    nav = "\n    ".join([link("f1.html", "Formule 1", "f1"), link("foot.html", "Football", "foot"),
                         link("methode.html", "Méthode", "methode")])
    strip = ""
    if section == "foot":
        items = "\n      ".join(
            f'<a href="{r}foot/{slug}.html"{" aria-current=\"page\"" if slug == sub else ""}>{nom}</a>' for _, slug, nom in COMPETITIONS)
        strip = f'''
  <nav class="bande" aria-label="Compétitions">
    <div class="bande-in">
      <a href="{r}foot.html"{' aria-current="page"' if sub == "hub" else ""}>Tous les matchs</a>
      {items}
    </div>
  </nav>'''
    js = "\n".join(f'<script src="{r}assets/{s}" defer></script>' for s in ["commun.js", *scripts])
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#26292e">
<meta name="description" content="{description}">
<title>{title}</title>
<link rel="icon" href="{r}assets/favicon.svg" type="image/svg+xml">
<link rel="preload" href="{r}assets/fonts/signal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{r}assets/style.css">
{js}
</head>
<body data-root="{r or './'}">
<a class="evitement" href="#contenu">Aller au contenu</a>
<header class="tete">
  <div class="tete-in">
    <a class="marque" href="{r}index.html">{LIGHTS}<span>Extinction des feux</span></a>
    <nav class="menu" aria-label="Sections">
    {nav}
    </nav>
  </div>{strip}
</header>
<main id="contenu">
{body}
</main>
<footer class="pied">
  <div class="pied-in">
    <p>Projet étudiant de Maxime Basset. Pronostics automatiques, sans lien avec la Formule 1, la FIA, l'UEFA, les ligues ni les clubs.</p>
    <p>Ce n'est pas un outil de paris. Les jeux d'argent et de hasard peuvent être dangereux : pertes d'argent, conflits familiaux, addiction. Retrouvez nos conseils sur joueurs-info-service.fr (09 74 75 13 13, appel non surtaxé).</p>
    <p><a href="https://github.com/maximebasset1/extinction-des-feux">Code source</a></p>
  </div>
</footer>
</body>
</html>
"""


HOME = """  <section class="depart" aria-labelledby="h-depart">
    <div class="depart-in">
      <div class="feux-grands" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
      <h1 id="h-depart">Les prochains départs</h1>
      <p class="chapeau">Les chances de chaque Grand Prix de Formule 1 et de chaque match de six compétitions de football, recalculées plusieurs fois par jour et comparées ensuite aux vrais résultats.</p>
      <div class="departs">
        <a class="dep" href="f1.html" id="dep-f1"><span class="dep-quoi">Formule 1</span><b id="dep-f1-titre">Chargement…</b><span id="dep-f1-quand"></span><span id="dep-f1-detail" class="dep-detail"></span></a>
        <a class="dep" href="foot.html" id="dep-foot"><span class="dep-quoi">Football</span><b id="dep-foot-titre">Chargement…</b><span id="dep-foot-quand"></span><span id="dep-foot-detail" class="dep-detail"></span></a>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" aria-labelledby="h-une">
      <div class="bloc-tete"><h2 id="h-une">À la une cette semaine</h2><a href="foot.html">Tous les matchs</a></div>
      <p class="note">Les affiches de la semaine : coupes d'Europe, grands clubs et matchs à l'issue la plus ouverte.</p>
      <ul class="matchs avec-comp" id="une"></ul>
    </section>

    <section class="bloc" aria-labelledby="h-surprises">
      <div class="bloc-tete"><h2 id="h-surprises">Surprises récentes</h2></div>
      <p class="note">Le modèle se trompe aussi. Voici les résultats des deux dernières semaines auxquels il donnait moins de 20&#8239;% de chances.</p>
      <ul class="matchs avec-comp" id="surprises"></ul>
    </section>

    <section class="bloc" aria-labelledby="h-grille">
      <div class="bloc-tete"><h2 id="h-grille">Formule 1, la grille la plus probable</h2><a href="f1.html">Page Formule 1</a></div>
      <p class="note" id="grille-note"></p>
      <ol class="classement-f1" id="grille"></ol>
    </section>

    <section class="bloc" aria-labelledby="h-comp">
      <div class="bloc-tete"><h2 id="h-comp">Six compétitions de football</h2></div>
      <ul class="competitions" id="competitions"></ul>
    </section>

    <section class="bloc encadre" aria-labelledby="h-fiable">
      <h2 id="h-fiable">Peut-on s'y fier ?</h2>
      <p id="fiable"></p>
      <p><a href="methode.html">Comment c'est calculé, et à quel point c'est juste</a></p>
    </section>
  </div>"""

F1 = """  <section class="depart depart-f1" aria-labelledby="gp-name">
    <div class="depart-in">
      <p class="dep-quoi" id="question">Qui partira en pole ?</p>
      <h1 id="gp-name">Chargement…</h1>
      <p class="chapeau" id="status"></p>
      <div class="compte" id="countdown" aria-live="off">
        <p id="session-next"></p>
        <div class="compte-chiffres"><span><b id="cd-d">00</b> j</span><span><b id="cd-h">00</b> h</span><span><b id="cd-m">00</b> min</span><span><b id="cd-s">00</b> s</span></div>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" aria-labelledby="grid-title">
      <div class="bloc-tete"><h2 id="grid-title">La grille la plus probable</h2></div>
      <ol class="classement-f1" id="grid"></ol>
      <p class="note">Un pronostic, pas un résultat : un tour raté et tout change.</p>
    </section>

    <section class="bloc" aria-labelledby="h-seances">
      <div class="bloc-tete"><h2 id="h-seances">Programme du week-end</h2></div>
      <ul class="seances" id="sessions"></ul>
      <p class="note" id="sessions-note"></p>
    </section>

    <section class="bloc" id="drivers" aria-labelledby="h-pilotes">
      <div class="bloc-tete"><h2 id="h-pilotes">Tous les pilotes</h2></div>
      <p class="note" id="field-note"></p>
      <div class="defile"><table class="tableau" id="field"></table></div>
    </section>

    <section class="bloc" id="history" aria-labelledby="h-histo">
      <div class="bloc-tete"><h2 id="h-histo">Le modèle face à la réalité</h2><div class="pastilles" id="seasons" role="group" aria-label="Saison"></div></div>
      <p class="note">Pour chaque qualification, le modèle est rejoué avec les seules courses d'avant, comme s'il avait tourné à l'époque. Chaque barre montre la chance qu'il donnait au pilote qui a fait la pole. La ligne pointillée correspond à un pilote tiré au hasard.</p>
      <p class="note">Les manches 4 à 11 de 2026 ont servi à choisir le modèle : il y part avec un avantage. Les pronostics vraiment publiés à l'avance sont dans le journal plus bas.</p>
      <div class="graphe" id="chart"></div>
      <div class="defile"><table class="tableau" id="history-table"></table></div>
    </section>

    <section class="bloc" id="record" aria-labelledby="h-bilan">
      <div class="bloc-tete"><h2 id="h-bilan">Bilan</h2></div>
      <dl class="chiffres" id="tiles"></dl>
      <h3>Journal des pronostics publiés</h3>
      <p class="note">Chaque pronostic est enregistré avant la séance, jamais réécrit, puis comparé au résultat.</p>
      <div id="journal"></div>
    </section>

    <section class="bloc encadre" id="method" aria-labelledby="h-meth">
      <h2 id="h-meth">Comment ça marche</h2>
      <p>Les temps au tour depuis 2018, la forme récente de chaque pilote, le rythme de la voiture, les essais du week-end et la météo prévue alimentent un modèle statistique réentraîné après chaque course. Le calcul tourne tout seul sur GitHub plusieurs fois par jour.</p>
      <p id="updated" class="note"></p>
      <p class="note">Données : chronométrage officiel via <a href="https://github.com/TracingInsights">TracingInsights</a> et <a href="https://docs.fastf1.dev/">FastF1</a>, calendrier <a href="https://jolpi.ca">Jolpica</a>, météo <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0).</p>
    </section>
  </div>"""

FOOT = """  <section class="titre-page">
    <div class="titre-in">
      <h1>Football</h1>
      <p class="chapeau">Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions et Ligue Europa : les chances de chaque match à venir.</p>
      <div class="recherche">
        <label for="q">Chercher un club ou un match</label>
        <input id="q" type="search" autocomplete="off" spellcheck="false" placeholder="Lille, ou Lille Bayern" role="combobox" aria-autocomplete="list" aria-controls="suggest" aria-expanded="false">
        <ul id="suggest" class="suggest" role="listbox" hidden></ul>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" aria-labelledby="h-matchs">
      <div class="bloc-tete"><h2 id="h-matchs">Prochains matchs</h2></div>
      <div class="pastilles" id="chips" role="group" aria-label="Compétition"></div>
      <p class="note" id="note" aria-live="polite"></p>
      <div id="results" class="avec-comp"></div>
      <p class="plus"><button type="button" id="more" hidden>Voir plus de matchs</button></p>
    </section>

    <section class="bloc" aria-labelledby="h-comp">
      <div class="bloc-tete"><h2 id="h-comp">Les compétitions</h2></div>
      <ul class="competitions" id="competitions"></ul>
    </section>

    <section class="bloc" aria-labelledby="h-fiab">
      <div class="bloc-tete"><h2 id="h-fiab">Fiabilité par compétition</h2><a href="methode.html">Méthode</a></div>
      <p class="note" id="f-note"></p>
      <div class="defile"><table class="tableau" id="f-table"></table></div>
    </section>
  </div>"""

COMP = """  <section class="titre-page">
    <div class="titre-in">
      <h1 id="c-titre">{nom}</h1>
      <p class="chapeau" id="c-chapeau"></p>
      <nav class="sommaire" aria-label="Dans cette page">
        <a href="#matchs">Matchs</a><a href="#classement" id="lien-classement">Classement</a><a href="#club">Clubs</a><a href="#face">Face-à-face</a><a href="#fiabilite">Fiabilité</a>
      </nav>
    </div>
  </section>

  <div class="page">
    <section class="bloc" id="matchs" aria-labelledby="j-titre">
      <div class="bloc-tete">
        <h2 id="j-titre">Matchs</h2>
        <div class="pager">
          <button type="button" id="j-prev" aria-label="Journée précédente">‹</button>
          <label class="cache" for="j-select">Journée</label>
          <select id="j-select"></select>
          <button type="button" id="j-next" aria-label="Journée suivante">›</button>
        </div>
      </div>
      <p class="note" id="j-note"></p>
      <div id="j-liste"></div>
    </section>

    <section class="bloc" id="classement" aria-labelledby="h-classement">
      <div class="bloc-tete"><h2 id="h-classement">Classement et fin de saison prévue</h2></div>
      <p class="note" id="t-note"></p>
      <div class="defile"><table class="tableau" id="t-table"></table></div>
    </section>

    <section class="bloc" id="club" aria-labelledby="h-club">
      <div class="bloc-tete"><h2 id="h-club">Calendrier d'un club</h2><label class="cache" for="club-select">Club</label><select id="club-select"></select></div>
      <div id="club-resume"></div>
      <div id="club-liste"></div>
    </section>

    <section class="bloc" id="face" aria-labelledby="h-face">
      <div class="bloc-tete"><h2 id="h-face">Face-à-face</h2>
        <div class="pager"><label class="cache" for="f-a">Premier club</label><select id="f-a"></select><span>contre</span><label class="cache" for="f-b">Second club</label><select id="f-b"></select></div>
      </div>
      <p id="f-resume"></p>
      <div class="defile"><table class="tableau" id="f-liste"></table></div>
    </section>

    <section class="bloc" id="fiabilite" aria-labelledby="h-fiab">
      <div class="bloc-tete"><h2 id="h-fiab">Fiabilité</h2><a href="../methode.html">Méthode</a></div>
      <p class="note" id="b-note"></p>
      <div class="defile"><table class="tableau" id="b-table"></table></div>
      <h3>Journal des pronostics publiés</h3>
      <p class="note">Chaque pronostic est enregistré avant le coup d'envoi, jamais réécrit, puis comparé au résultat.</p>
      <div id="journal"></div>
    </section>
  </div>"""

METHODE = """  <section class="titre-page">
    <div class="titre-in">
      <h1>Méthode</h1>
      <p class="chapeau">Comment les probabilités sont calculées, et ce qu'elles valent vraiment.</p>
    </div>
  </section>

  <div class="page texte">
    <section class="bloc">
      <h2>Football</h2>
      <p>Tous les clubs de 22 championnats européens et des coupes d'Europe sont notés ensemble : chacun a une force d'attaque et une force de défense, estimées sur ses matchs récents (les plus récents comptent plus) à partir des buts et des tirs cadrés. Les championnats ne se rencontrent qu'en coupe d'Europe : ce sont ces matchs, et les clubs qui montent ou descendent, qui permettent de comparer un club de Ligue 1 à un club de Bundesliga.</p>
      <p>De ces forces, le modèle tire la probabilité de chaque score (loi de Poisson, avec la correction de Dixon et Coles pour les petits scores), puis les chances de victoire, de nul et de défaite sur 90 minutes. Prolongations et tirs au but ne sont pas comptés.</p>
      <p>Quand les cotes d'avant-match sont publiées, elles sont mélangées au modèle, car elles résument ce que les statistiques ne voient pas : blessures, compositions, actualité. <span id="m-part">Elles pèsent lourd dans le pronostic final</span>, mais nos statistiques gardent toujours une part, et les cotes ne sont jamais affichées.</p>
      <h3>Le modèle apprend-il ?</h3>
      <p>À chaque nouveau résultat, toutes les forces sont réestimées : une victoire, un nul ou une défaite déplace les chances des matchs suivants, d'autant plus que le résultat est récent. Une seule surprise ne bouge pourtant les choses que de peu, volontairement : un match tient beaucoup du hasard, et sur-réagir rendrait le modèle moins juste. Ses réglages, eux, ne changent pas d'un match à l'autre : ils ont été choisis une fois pour toutes sur la saison 2021-22, et le journal des pronostics sert à vérifier, saison après saison, qu'ils tiennent.</p>
      <h3>Est-ce fiable ?</h3>
      <p>Chaque semaine depuis 2022, le modèle est rejoué avec les seuls matchs joués avant, comme s'il avait tourné à l'époque. On le compare à deux références : les pourcentages habituels de victoire à domicile, de nul et de victoire à l'extérieur, et les cotes des bookmakers. Le score utilisé, le RPS, est d'autant plus bas que les probabilités annoncées étaient justes.</p>
      <div class="defile"><table class="tableau" id="m-table"></table></div>
      <p>Un pronostic de football se trompe souvent sur un match donné : même bien calibré, le favori ne gagne qu'un peu plus d'une fois sur deux. Ce qui compte, c'est qu'un événement annoncé à 30 % arrive à peu près trois fois sur dix.</p>
    </section>

    <section class="bloc">
      <h2>Formule 1</h2>
      <p>Les temps au tour depuis 2018, la forme récente de chaque pilote, le rythme de la voiture, les essais du week-end et la météo prévue alimentent un modèle statistique réentraîné après chaque course. Il donne, pour chaque pilote, la probabilité de faire la pole et de gagner la course. Le détail et le bilan sont sur la <a href="f1.html">page Formule 1</a>.</p>
    </section>

    <section class="bloc">
      <h2>Sources</h2>
      <p>Football : <a href="https://www.football-data.co.uk/">football-data.co.uk</a> (résultats, tirs, cotes), <a href="https://www.football-data.org/">football-data.org</a> (calendriers, résultats récents), <a href="https://github.com/openfootball">openfootball</a> (coupes d'Europe passées, domaine public), <a href="https://the-odds-api.com/">The Odds API</a> (Ligue Europa, cotes des coupes). Formule 1 : <a href="https://github.com/TracingInsights">TracingInsights</a>, <a href="https://docs.fastf1.dev/">FastF1</a>, <a href="https://jolpi.ca">Jolpica</a>, <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0).</p>
      <p>Logos : seuls ceux du domaine public sont utilisés (Wikimedia Commons) ; les autres clubs sont représentés par leur sigle. Les noms et logos des clubs appartiennent à leurs propriétaires.</p>
      <p class="note" id="m-maj"></p>
    </section>
  </div>"""

REDIRECT = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta http-equiv="refresh" content="0; url={target}">
<link rel="canonical" href="{target}">
<title>Page déplacée</title>
<script src="assets/redirection.js" defer data-cible="{target}"></script>
</head>
<body>
<p>Cette page a déménagé : <a href="{target}">{label}</a>.</p>
</body>
</html>
"""


def pages() -> dict[str, str]:
    out = {
        "index.html": page("index.html", "Extinction des feux : pronostics F1 et football",
                           "Probabilités de chaque Grand Prix de Formule 1 et de chaque match de six compétitions de football, mises à jour plusieurs fois par jour.",
                           HOME, ["accueil.js"], "accueil"),
        "f1.html": page("f1.html", "Formule 1 : pole et victoire au prochain Grand Prix - Extinction des feux",
                        "Probabilités de pole et de victoire pour chaque pilote au prochain Grand Prix, comparées ensuite aux vrais résultats.",
                        F1, ["f1.js"], "f1"),
        "foot.html": page("foot.html", "Football : probabilités des prochains matchs - Extinction des feux",
                          "Chercher un club et voir les chances de ses prochains matchs : Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions, Ligue Europa.",
                          FOOT, ["foot.js"], "foot", "hub"),
        "methode.html": page("methode.html", "Méthode - Extinction des feux",
                             "Comment les probabilités de Formule 1 et de football sont calculées, et ce qu'elles valent.",
                             METHODE, ["methode.js"], "methode"),
    }
    for _, slug, nom in COMPETITIONS:
        out[f"foot/{slug}.html"] = page(f"foot/{slug}.html", f"{nom} : pronostics, classement et fin de saison - Extinction des feux",
                                        f"{nom} : probabilités de chaque match, classement, fin de saison simulée, face-à-face et fiabilité du modèle.",
                                        COMP.replace("{nom}", nom), ["competition.js"], "foot", slug).replace(
            '<body data-root="../">', f'<body data-root="../" data-competition="{slug}">')
    out["ligue1.html"] = REDIRECT.format(csp=CSP, target="foot/ligue-1.html", label="Ligue 1")
    out["recherche.html"] = REDIRECT.format(csp=CSP, target="foot.html", label="Football")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    stale = []
    for rel, html in pages().items():
        f = SITE / rel
        if ap.parse_args().check:
            if not f.exists() or f.read_text(encoding="utf-8") != html:
                stale.append(rel)
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html, encoding="utf-8")
    if stale:
        print("Pages à regénérer (python scripts/build_site.py) :", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
