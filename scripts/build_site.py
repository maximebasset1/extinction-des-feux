"""Génère les pages HTML du site (même en-tête et même pied de page partout).

python scripts/build_site.py          écrit les pages dans site/
python scripts/build_site.py --check  vérifie seulement qu'elles sont à jour (utilisé par les tests)
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
POINTS_SRC = ROOT / "relais" / "points.js"
POINTS_DST = SITE / "assets" / "points.js"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; "
       "connect-src 'self' https://extinction-direct.maximebasset1.workers.dev; base-uri 'self'; form-action 'none'")
COMPETITIONS = [("E0", "premier-league", "Premier League"), ("D1", "bundesliga", "Bundesliga"), ("SP1", "liga", "Liga"),
                ("I1", "serie-a", "Serie A"), ("F1", "ligue-1", "Ligue 1"),
                ("LDC", "ligue-des-champions", "Ligue des champions"), ("LEC", "ligue-europa", "Ligue Europa")]
LIGHTS = '<span class="feux" aria-hidden="true">' + '<i></i>' * 5 + "</span>"


def empreinte(nom: str) -> str:
    """8 caractères tirés du contenu d'un fichier de site/assets : le lien change dès que le fichier change,
    un navigateur ne mélange donc jamais une page neuve et un script ou un style gardé en cache.
    Les fins de ligne sont normalisées en LF avant le calcul : l'empreinte est la même sur Windows
    (`core.autocrlf=true`, fichiers en CRLF sur le disque) et sur GitHub (Linux, LF). Réservé aux fichiers texte (CSS, JS)."""
    contenu = (SITE / "assets" / nom).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(contenu).hexdigest()[:8]


def page(path: str, title: str, description: str, body: str, scripts: list[str], section: str, sub: str = "",
         styles: tuple[str, ...] = (), common: bool = True, name: str = "", modules: tuple[str, ...] = ()) -> str:
    """`common=False` : page d'un module autonome (F1), sans les scripts communs du site."""
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
      <a href="{r}foot/en-direct.html" data-direct{' aria-current="page"' if sub == "en-direct" else ""}>En direct<span class="bande-live" hidden><i class="pastille" aria-hidden="true"></i><b></b><span class="cache"> matchs en cours</span></span></a>
      <a href="{r}foot/ligues.html"{' aria-current="page"' if sub == "ligues" else ""}>Ligues</a>
      {items}
    </div>
  </nav>'''
    # le compteur de l'onglet « En direct » (onglet-direct.js) est sur toutes les pages Football
    if section == "foot":
        scripts = [*scripts, "onglet-direct.js"]
    js_lines = [f'<script src="{r}assets/{s}?v={empreinte(s)}" defer></script>' for s in (["commun.js"] if common else []) + scripts]
    js_lines += [f'<script type="module" src="{r}assets/{m}?v={empreinte(m)}"></script>' for m in modules]
    js = "\n".join(js_lines)
    css = "".join(f'\n<link rel="stylesheet" href="{r}assets/{c}?v={empreinte(c)}">' for c in styles)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#0f1115">
<meta name="description" content="{description}">
<title>{title}</title>
<link rel="icon" href="{r}assets/favicon.svg" type="image/svg+xml">
<link rel="preload" href="{r}assets/fonts/titillium-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{r}assets/fonts/titillium-900.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{r}assets/style.css?v={empreinte("style.css")}">{css}
{js}
</head>
<body data-root="{r or './'}"{f' data-page="{name}"' if name else ""}>
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
      <p class="chapeau">Les chances de chaque Grand Prix de Formule 1 et de chaque match de sept compétitions de football, recalculées plusieurs fois par jour et comparées ensuite aux vrais résultats.</p>
      <div class="departs">
        <a class="dep" href="f1.html" id="dep-f1"><span class="dep-quoi">Formule 1</span><b id="dep-f1-titre">Chargement…</b><span id="dep-f1-quand"></span><span id="dep-f1-detail" class="dep-detail"></span></a>
        <a class="dep" href="foot.html" id="dep-foot"><span class="dep-quoi">Football</span><b id="dep-foot-titre">Chargement…</b><span id="dep-foot-quand"></span><span id="dep-foot-detail" class="dep-detail"></span></a>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" aria-labelledby="h-direct" id="direct" hidden>
      <div class="bloc-tete"><h2 id="h-direct">En direct</h2></div>
      <p class="note" id="direct-note">Les matchs en cours des sept compétitions, avec les chances recalculées à chaque but.</p>
      <ul class="matchs avec-comp" id="direct-liste"></ul>
    </section>

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
      <div class="bloc-tete"><h2 id="h-comp">Sept compétitions de football</h2></div>
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

  <div class="page f1">
    <div class="f1-haut">
      <section class="carte" aria-labelledby="grid-title">
        <h2 id="grid-title">Grille probable</h2>
        <p class="f1-source" id="grid-source"></p>
        <ol class="classement-f1" id="grid"></ol>
      </section>
      <div class="f1-favoris-cartes" id="favoris">
        <section class="carte" id="fav-pole" aria-label="Favoris pour la pole"></section>
        <section class="carte" id="fav-victoire" aria-label="Favoris pour la victoire"></section>
      </div>
    </div>

    <section class="bloc" aria-labelledby="h-seances">
      <div class="bloc-tete"><h2 id="h-seances">Week-end et météo</h2></div>
      <ul class="seances" id="sessions"></ul>
      <p class="note" id="sessions-note"></p>
    </section>

    <section class="bloc" id="championnat" aria-labelledby="h-champ" hidden>
      <div class="bloc-tete"><h2 id="h-champ">Championnat du monde</h2></div>
      <p class="note" id="champ-note"></p>
      <div class="f1-champ">
        <section class="carte" id="champ-pilotes" aria-label="Titre pilotes"></section>
        <section class="carte" id="champ-equipes" aria-label="Titre constructeurs"></section>
      </div>
    </section>

    <section class="bloc carte" id="reel" aria-labelledby="reel-titre">
      <h2 id="reel-titre">Prévu et réel</h2>
      <div id="reel-corps"></div>
    </section>

    <section class="bloc" id="drivers" aria-labelledby="h-pilotes">
      <div class="bloc-tete"><h2 id="h-pilotes">Tous les pilotes</h2></div>
      <p class="note" id="field-note"></p>
      <div class="defile"><table class="tableau" id="field"></table></div>
    </section>

    <section class="bloc" aria-labelledby="h-journal">
      <div class="bloc-tete"><h2 id="h-journal">Derniers pronostics jugés</h2><a href="f1-methode.html#h-journal-complet">Tout le journal</a></div>
      <div id="journal"></div>
      <p class="note"><a href="f1-methode.html">Méthode et bilan du modèle F1</a>. <span id="updated"></span></p>
    </section>
  </div>"""

FOOT = """  <section class="titre-page">
    <div class="titre-in">
      <h1>Football</h1>
      <p class="chapeau">Premier League, Bundesliga, Liga, Serie A, Ligue 1, Ligue des champions et Ligue Europa : les chances de chaque match à venir.</p>
      <div class="recherche">
        <label for="q">Chercher un club ou un match</label>
        <input id="q" type="search" autocomplete="off" spellcheck="false" role="combobox" aria-autocomplete="list" aria-controls="suggest" aria-expanded="false">
        <ul id="suggest" class="suggest" role="listbox" hidden></ul>
        <p class="club-favori" id="club-favori" hidden></p>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" id="favoris" aria-labelledby="h-favoris" hidden>
      <div class="bloc-tete"><h2 id="h-favoris">Mes clubs favoris</h2></div>
      <p class="note">Leurs matchs sont mis en valeur partout sur le site, et passent en tête de la section « En direct » de l'accueil. Ta liste reste dans ce navigateur : pas de compte, rien n'est envoyé.</p>
      <ul class="mes-favoris" id="favoris-liste"></ul>
    </section>

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

LIVE = """  <section class="titre-page">
    <div class="titre-in">
      <h1>En direct</h1>
      <p class="chapeau">Les matchs du jour des sept compétitions, de quinze minutes avant le coup d'envoi jusqu'au coup de sifflet final : le score, la minute et les chances de chaque camp, recalculées à chaque but.</p>
    </div>
  </section>

  <div class="page">
    <section class="bloc" aria-labelledby="h-live">
      <div class="bloc-tete"><h2 id="h-live">Matchs à suivre</h2></div>
      <p class="note" id="live-note" aria-live="polite">Chargement…</p>
      <div id="live-liste" class="live-groupes"></div>
    </section>

    <section class="bloc" id="prochains" aria-labelledby="h-prochains" hidden>
      <div class="bloc-tete"><h2 id="h-prochains">Prochains coups d'envoi</h2><a href="../foot.html">Tous les matchs</a></div>
      <p class="note">Heures à l'heure de ton appareil. Un match apparaît dans la liste du dessus quinze minutes avant son coup d'envoi.</p>
      <ul class="matchs avec-comp" id="prochains-liste"></ul>
    </section>
  </div>"""

LIGUES = """  <section class="titre-page">
    <div class="titre-in">
      <h1>Ligues de pronostics</h1>
      <p class="chapeau">Des pronostics de scores entre amis. Sans compte : l'accès est enregistré dans ce navigateur.</p>
      <div class="ligue-barre" id="ligue-barre" hidden>
        <label for="ligue-select">Ligue active</label>
        <select id="ligue-select"></select>
        <button type="button" class="btn-secondaire" id="btn-nouvelle">Créer ou rejoindre</button>
      </div>
    </div>
  </section>

  <div class="page">
    <section class="bloc" id="ligue-entree" aria-label="Créer ou rejoindre une ligue">
      <div class="ligue-entree-grille">
        <form class="carte ligue-form" id="form-creer" novalidate>
          <h2>Créer une ligue</h2>
          <div class="champ">
            <label for="c-nom">Nom de la ligue</label>
            <input id="c-nom" name="nom" type="text" minlength="3" maxlength="40" required>
          </div>
          <div class="champ">
            <label for="c-pseudo">Pseudo</label>
            <input id="c-pseudo" name="pseudo" type="text" minlength="2" maxlength="20" required>
          </div>
          <fieldset class="champ champ-comps">
            <div class="champ-comps-tete">
              <legend>Compétitions</legend>
              <div class="champ-comps-raccourcis">
                <button type="button" class="btn-lien" id="btn-comp-toutes">Tout sélectionner</button>
                <button type="button" class="btn-lien" id="btn-comp-aucune">Aucune</button>
              </div>
            </div>
            <div class="comp-grille" id="c-comps">
              <label class="comp-pilule"><input type="checkbox" name="comp" value="E0" checked><span>Premier League</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="D1" checked><span>Bundesliga</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="SP1" checked><span>Liga</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="I1" checked><span>Serie A</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="F1" checked><span>Ligue 1</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="LDC" checked><span>Ligue des champions</span></label>
              <label class="comp-pilule"><input type="checkbox" name="comp" value="LEC" checked><span>Ligue Europa</span></label>
            </div>
          </fieldset>
          <button type="submit" class="btn-primaire" id="btn-creer">Créer la ligue</button>
          <p class="form-msg" id="msg-creer" aria-live="polite"></p>
        </form>

        <form class="carte ligue-form" id="form-rejoindre" novalidate>
          <h2>Rejoindre une ligue</h2>
          <div class="champ">
            <label for="r-code">Code de la ligue</label>
            <input id="r-code" name="code" type="text" maxlength="10" required autocomplete="off" autocapitalize="characters" spellcheck="false">
          </div>
          <div class="champ">
            <label for="r-pseudo">Pseudo</label>
            <input id="r-pseudo" name="pseudo" type="text" minlength="2" maxlength="20" required>
          </div>
          <button type="submit" class="btn-primaire" id="btn-rejoindre">Rejoindre la ligue</button>
          <p class="form-msg" id="msg-rejoindre" aria-live="polite"></p>
        </form>
      </div>
      <p class="plus" id="retour-ligue-wrap" hidden><button type="button" id="btn-retour-ligue">Revenir à ma ligue active</button></p>
    </section>

    <div id="ligue-vue" hidden>
      <section class="bloc carte ligue-entete" aria-labelledby="l-nom">
        <div class="ligue-entete-haut">
          <div>
            <p class="dep-quoi">Ligue active</p>
            <h2 id="l-nom">Chargement…</h2>
            <ul class="ligue-comps" id="l-comps" aria-label="Compétitions de la ligue"></ul>
            <p class="note" id="l-moi"></p>
          </div>
          <div class="ligue-actions">
            <span class="ligue-code" id="l-code" aria-label="Code de la ligue"></span>
            <button type="button" class="btn-primaire" id="btn-inviter">Copier le lien d'invitation</button>
            <button type="button" class="btn-discret" id="btn-oublier">Quitter la ligue</button>
            <button type="button" class="btn-discret btn-danger" id="btn-supprimer" hidden>Supprimer la ligue</button>
          </div>
        </div>
        <p class="note" id="l-statut" aria-live="polite"></p>
        <details class="bareme">
          <summary>Barème des points</summary>
          <ul>
            <li><b>+3 points</b> pour la bonne issue (victoire domicile, match nul ou victoire extérieur).</li>
            <li><b>+2 points</b> supplémentaires pour le bon écart de buts si l'issue est juste (un match nul juste rapporte donc au moins 5 points).</li>
            <li><b>+5 points</b> supplémentaires pour le score exact (<b>10 points</b> au total).</li>
            <li><b>Coup de poker (×1,5)</b> : si l'issue trouvée avait strictement moins de 25&#8239;% de chances avant le match, le total est multiplié par 1,5 et arrondi au supérieur (jusqu'à <b>15 points</b>).</li>
          </ul>
        </details>
      </section>

      <section class="bloc" id="sec-classement" aria-labelledby="h-l-classement">
        <div class="bloc-tete">
          <h2 id="h-l-classement">Classement</h2>
          <span class="note" id="l-maj"></span>
        </div>
        <p class="note" id="l-direct-note" hidden></p>
        <div class="defile"><table class="tableau" id="l-classement"></table></div>
      </section>

      <section class="bloc" id="sec-suivi" aria-labelledby="h-l-suivi" hidden>
        <div class="bloc-tete"><h2 id="h-l-suivi">Pronostics dévoilés et résultats</h2></div>
        <p class="note">Les pronostics des autres joueurs apparaissent au coup d'envoi. Pendant le match, les points sont provisoires.</p>
        <div id="l-suivi"></div>
      </section>

      <section class="bloc" id="sec-pronos" aria-labelledby="h-l-pronos">
        <div class="bloc-tete"><h2 id="h-l-pronos">Pronostiquer les prochains matchs</h2></div>
        <div class="pastilles" id="l-chips" role="group" aria-label="Filtrer par compétition"></div>
        <p class="note" id="l-pronos-note" aria-live="polite">Chargement du programme…</p>
        <div id="l-pronos"></div>
        <p class="plus"><button type="button" id="l-more" hidden>Voir plus de matchs</button></p>
      </section>
    </div>
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
      <p>Tous les clubs de 22 championnats européens et des coupes d'Europe sont notés ensemble : chacun a une force d'attaque et une force de défense estimées à deux échelles de temps — un niveau intrinsèque (demi-vie d'environ un an) complété par une composante de forme récente (demi-vie d'environ 40 jours) qui capte plus vite une série ou une crise — à partir des buts et des tirs cadrés. Les championnats ne se rencontrent qu'en coupe d'Europe : ce sont ces matchs, et les clubs qui montent ou descendent, qui permettent de comparer un club de Ligue 1 à un club de Bundesliga.</p>
      <p>De ces forces, le modèle tire la probabilité de chaque score (loi de Poisson, avec la correction de Dixon et Coles pour les petits scores), puis les chances de victoire, de nul et de défaite sur 90 minutes, ainsi que les probabilités « Les deux équipes marquent » et « Plus de 2,5 buts ». Prolongations et tirs au but ne sont pas comptés. Pour les matchs des trois prochains jours, les absents notables et changements d'entraîneur récents ajustent de façon bornée les buts attendus avant le mélange avec les cotes.</p>
      <p>Depuis le 25 novembre 2026, la fiche de match signale aussi les absents repérés dans la presse. Des flux RSS publics (RMC Sport, L'Équipe, BBC Sport, Sky Sports, Kicker, Marca, AS, Gazzetta dello Sport) sont relus sur les 72 dernières heures : un joueur n'est retenu que s'il figure dans l'effectif d'un club cité et qu'une phrase le désigne comme absent ou incertain. La détection est automatique et peut se tromper ou en oublier. Le joueur signalé est retiré des buteurs probables. <b>Les buts attendus et les chances de victoire, de nul et de défaite n'en tiennent pas compte</b> : un malus sur les buts attendus a été envisagé puis écarté. Faute d'archive de ces articles, aucun comparatif avant/après de log-loss ou de score de Brier n'est possible, et une nouvelle variable n'entre dans le modèle que si ce comparatif montre une amélioration. Les buteurs probables écartent aussi les joueurs qui n'ont pas joué au moins 60 % des matchs de leur équipe (ou, quand les compositions sont fournies, qui n'ont pas été titulaires dans cette proportion). Sans les compositions, un remplaçant qui entre à chaque match n'est pas repéré.</p>
      <p>Quand les cotes d'avant-match sont publiées, elles sont mélangées au modèle, car elles résument ce que les statistiques ne voient pas : blessures, compositions, actualité. <span id="m-part">Elles pèsent lourd dans le pronostic final</span>, mais nos statistiques gardent toujours une part, et les cotes ne sont jamais affichées.</p>
      <h3>Le modèle apprend-il ?</h3>
      <p>À chaque nouveau résultat, toutes les forces sont réestimées : une victoire, un nul ou une défaite déplace les chances des matchs suivants, d'autant plus que le résultat est récent. Une seule surprise ne bouge pourtant les choses que de peu, volontairement : un match tient beaucoup du hasard, et sur-réagir rendrait le modèle moins juste. Ses réglages, eux, ne changent pas d'un match à l'autre : ils ont été choisis une fois pour toutes sur la saison 2021-22, et le journal des pronostics sert à vérifier, saison après saison, qu'ils tiennent.</p>
      <h3>Est-ce fiable ?</h3>
      <p>Chaque semaine depuis 2022, le modèle est rejoué avec les seuls matchs joués avant, comme s'il avait tourné à l'époque. On le compare à deux références : les pourcentages habituels de victoire à domicile, de nul et de victoire à l'extérieur, et les cotes des bookmakers. Le score utilisé, le RPS, est d'autant plus bas que les probabilités annoncées étaient justes.</p>
      <div class="defile"><table class="tableau" id="m-table"></table></div>
      <p>Un pronostic de football se trompe souvent sur un match donné : même bien calibré, le favori ne gagne qu'un peu plus d'une fois sur deux. Ce qui compte, c'est qu'un événement annoncé à 30 % arrive à peu près trois fois sur dix.</p>
      <h3 id="multifacteur">Étude multi-facteurs : forme récente, fatigue et confiance</h3>
      <p id="m-etude-note">Avant d'ajouter une variable au moteur de probabilités, elle est jugée par backtest walk-forward sans fuite du futur (réglage sur 2021-22, évaluation sur 2022-2026) : seule une amélioration objective du RPS et de la log-loss est retenue. La fatigue brute (repos ≤ 3 jours) n'améliore pas les scores et reste donc affichée à titre purement informatif dans les facteurs clés du match.</p>
      <div class="defile"><table class="tableau" id="m-etude"></table></div>
      <div class="defile"><table class="tableau" id="m-confiance"></table></div>
      <h3 id="journal">Bilan réel du journal</h3>
      <p id="m-journal-note">Chaque pronostic est enregistré avant le coup d'envoi dans le journal, jamais réécrit, puis comparé au résultat réel.</p>
      <dl class="bilan-chiffres" id="m-journal-chiffres" hidden></dl>
      <div class="defile"><table class="tableau" id="m-journal"></table></div>
      <h3 id="direct">Les chances en direct</h3>
      <p id="m-direct-txt">Pendant un match, les chances sont recalculées dans ton navigateur à chaque but et à chaque minute qui passe.</p>
      <div class="defile"><table class="tableau" id="m-jugement"></table></div>
      <div class="calib">
        <figure id="m-calib"></figure>
        <div id="m-calib-txt"></div>
      </div>
    </section>

    <section class="bloc">
      <h2>Formule 1</h2>
      <p>Les temps au tour depuis 2018, la forme récente de chaque pilote, le rythme de la voiture, les essais du week-end et la météo prévue alimentent un modèle statistique réentraîné après chaque course. Il donne, pour chaque pilote, la probabilité de faire la pole et de gagner la course. Le détail et le bilan sont sur la page <a href="f1-methode.html">Méthode et bilan F1</a>.</p>
    </section>

    <section class="bloc">
      <h2>Sources</h2>
      <p>Football : <a href="https://www.football-data.co.uk/">football-data.co.uk</a> (résultats, tirs, cotes), <a href="https://www.football-data.org/">football-data.org</a> (calendriers, résultats récents, meilleurs buteurs), <a href="https://github.com/openfootball">openfootball</a> (coupes d'Europe passées, domaine public), <a href="https://the-odds-api.com/">The Odds API</a> (Ligue Europa, cotes des coupes), <a href="https://www.api-football.com/">API-Football</a> (scores en direct, blessures, entraîneurs), flux RSS de la presse sportive (absents signalés). Formule 1 : <a href="https://github.com/TracingInsights">TracingInsights</a>, <a href="https://docs.fastf1.dev/">FastF1</a>, <a href="https://jolpi.ca">Jolpica</a>, <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0).</p>
      <p>Logos : seuls ceux du domaine public sont utilisés (Wikimedia Commons) ; les autres clubs sont représentés par leur sigle. Les noms et logos des clubs appartiennent à leurs propriétaires.</p>
      <p class="note" id="m-maj"></p>
    </section>
  </div>"""

F1_METHODE = """  <section class="titre-page">
    <div class="titre-in">
      <h1>Méthode et bilan F1</h1>
      <p class="chapeau">Comment les chances de pole et de victoire sont calculées, et ce qu'elles valent face aux vrais résultats.</p>
    </div>
  </section>

  <div class="page f1 f1-texte">
    <section class="bloc" aria-labelledby="h-bilan">
      <div class="bloc-tete"><h2 id="h-bilan">Le bilan en bref</h2></div>
      <dl class="chiffres" id="tiles"></dl>
    </section>

    <section class="bloc" aria-labelledby="h-histo">
      <div class="bloc-tete"><h2 id="h-histo">Le modèle face à la réalité</h2><div class="pastilles" id="seasons" role="group" aria-label="Saison"></div></div>
      <p class="note">Pour chaque qualification, le modèle est rejoué avec les seules courses d'avant. Chaque barre montre la chance qu'il donnait au pilote qui a fait la pole ; la ligne pointillée correspond à un pilote tiré au hasard. Les manches 4 à 11 de 2026 ont servi à choisir le modèle : il y part avec un avantage.</p>
      <div class="graphe" id="chart"></div>
      <div class="defile"><table class="tableau" id="history-table"></table></div>
    </section>

    <section class="bloc" id="etude" aria-labelledby="h-etude">
      <div class="bloc-tete"><h2 id="h-etude">Novembre 2026 : grille officielle et rythme de course</h2></div>
      <p>Jusqu'au Grand Prix de Las Vegas 2026, la grille utilisée était l'ordre de la qualification : les pénalités moteur et les départs des stands étaient ignorés. Le modèle de victoire utilise désormais la grille officielle (f1db pour les courses passées, OpenF1 pour la course à venir), avec la place en qualif pour garder la vitesse d'un pilote pénalisé. Il est jugé sur le classement officiel, pénalités d'après course comprises.</p>
      <div class="defile"><table class="tableau" id="etude-grille"></table></div>
      <p>Nous avons ensuite testé le rythme des longs relais aux essais, l'usure des pneus et le rythme en course sprint. Tours écartés : sorties et entrées des stands, drapeaux, voiture de sécurité, tours supprimés, tours au-delà de 107 % du tour médian du relais. Règle fixée avant de voir les résultats : une variable n'entre que si elle améliore la log-loss et le score de Brier sur 2024-2025, puis se confirme sur 2026. Aucune n'a passé ce test : les écarts restent dans le bruit d'une vingtaine de courses par saison.</p>
      <div class="defile"><table class="tableau" id="etude-variables"></table></div>
      <p class="note">Log-loss : moins la chance donnée au vrai vainqueur est grande, plus le score monte. Brier : écart moyen entre les chances annoncées et ce qui s'est passé, pour tous les pilotes. Plus bas = mieux pour les deux.</p>
    </section>

    <section class="bloc" id="etude-sprint" aria-labelledby="h-sprint" hidden>
      <div class="bloc-tete"><h2 id="h-sprint">Novembre 2026 : week-ends sprint</h2></div>
      <p>Un week-end sprint n'a qu'une séance d'essais libres, mais deux séances disputées pour de vrai avant la qualification et la course du dimanche : la qualification sprint et la course sprint. Depuis 2024, elles ont lieu avant la qualification. En 2023, la qualification se courait le vendredi, avant la qualif sprint : on ne s'en sert pas pour prédire la pole de 2023, pour ne pas utiliser une information postérieure au pronostic (l'heure réelle de chaque séance est vérifiée).</p>
      <p>Même règle que pour le rythme de course, fixée avant de voir les résultats : une variable n'entre que si elle améliore la log-loss et le score de Brier sur les week-ends sprint de la période de choix, puis se confirme sur ceux de 2026. Chaque Grand Prix est prédit avec les seules courses d'avant. La dernière colonne donne la log-loss sur tous les Grands Prix des mêmes saisons : une variable sprint ne doit rien abîmer ailleurs. Limites : l'échantillon est petit (onze week-ends pour choisir, cinq pour tester), et trois des week-ends de test (Miami, Canada, Grande-Bretagne) font partie des manches 4 à 11 de 2026 qui servent à choisir le modèle de pole lui-même ; la comparaison avec et sans la variable porte sur ce même modèle.</p>
      <p id="sprint-conclusion"></p>
      <h3>Pole</h3>
      <p class="note" id="sprint-pole-note"></p>
      <div class="defile"><table class="tableau" id="sprint-pole"></table></div>
      <h3>Victoire</h3>
      <p class="note" id="sprint-victoire-note"></p>
      <div class="defile"><table class="tableau" id="sprint-victoire"></table></div>
      <p class="note">Log-loss et Brier : plus bas = mieux. Les deux valeurs sont « sans → avec » la variable.</p>
    </section>

    <section class="bloc" aria-labelledby="h-comment">
      <div class="bloc-tete"><h2 id="h-comment">Comment c'est calculé</h2></div>
      <ul>
        <li><b>Pole.</b> Les temps au tour depuis 2018, la forme récente de chaque pilote et de sa voiture, le type de circuit, la météo et les essais du week-end alimentent plusieurs modèles ; le meilleur, sur des courses jamais utilisées pour le régler, est retenu. Un week-end sprint, l'écart en qualification sprint s'ajoute aux essais dès que la séance est terminée.</li>
        <li><b>Victoire.</b> Avant la qualif, on tire au sort des milliers de grilles possibles selon les chances de pole. Après la qualif, on part de la grille de départ : officielle quand elle est publiée, sinon l'ordre de la qualif, annoncé comme provisoire.</li>
        <li><b>Championnat.</b> Tant qu'un titre n'est pas mathématiquement joué, 10 000 fins de saison sont tirées au sort à partir du classement officiel (f1db). Pour chaque Grand Prix restant, l'ordre d'arrivée complet est tiré selon les chances de victoire du modèle (premier tiré selon ces chances, deuxième parmi les autres, etc.), sprint compris le cas échéant, avec le barème de la saison et le départage officiel (nombre de victoires, puis de deuxièmes places...). Chaque pilote peut abandonner, avec le taux de non-classés de la saison en cours (18 % en 2026, 10 à 12 % de 2023 à 2025), et finit alors derrière ceux qui ont vu l'arrivée. Le prochain Grand Prix utilise ses chances du moment ; les suivants reprennent les chances d'avant la qualif du prochain, faute de mieux si loin à l'avance. Ce tirage ne connaît ni les pénalités moteur ni les consignes d'équipe : c'est un ordre de grandeur.</li>
        <li><b>Journal.</b> Chaque pronostic est enregistré avant la séance et jamais réécrit. Seule exception, signalée : le pronostic de Las Vegas 2026, publié sur une grille sans pénalités, a été recalculé après la course avec les seules données d'avant le départ.</li>
      </ul>
    </section>

    <section class="bloc" aria-labelledby="h-journal-complet">
      <div class="bloc-tete"><h2 id="h-journal-complet">Journal des pronostics publiés</h2></div>
      <div id="journal"></div>
      <p class="note">Sources : TracingInsights (temps au tour), f1db (grilles et classements officiels, CC BY 4.0), OpenF1 (grille de la course à venir), Jolpica (calendrier), Open-Meteo (météo, CC BY 4.0). <span id="updated"></span></p>
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
<script src="assets/redirection.js?v={version}" defer data-cible="{target}"></script>
</head>
<body>
<p>Cette page a déménagé : <a href="{target}">{label}</a>.</p>
</body>
</html>
"""


def pages() -> dict[str, str]:
    out = {
        "index.html": page("index.html", "Extinction des feux : pronostics F1 et football",
                           "Probabilités de chaque Grand Prix de Formule 1 et de chaque match de sept compétitions de football, mises à jour plusieurs fois par jour.",
                           HOME, ["favoris.js", "modele-direct.js", "direct.js", "fiche.js", "accueil.js"], "accueil"),
        "f1.html": page("f1.html", "Formule 1 : pole et victoire au prochain Grand Prix - Extinction des feux",
                        "Probabilités de pole et de victoire pour chaque pilote au prochain Grand Prix, comparées ensuite aux vrais résultats.",
                        F1, ["f1.js"], "f1", styles=("f1.css",), common=False, name="f1"),
        "f1-methode.html": page("f1-methode.html", "Méthode et bilan F1 - Extinction des feux",
                                "Comment les chances de pole et de victoire sont calculées, et ce qu'elles valent face aux vrais résultats.",
                                F1_METHODE, ["f1.js"], "f1", styles=("f1.css",), common=False, name="f1-methode"),
        "foot.html": page("foot.html", "Football : probabilités des prochains matchs - Extinction des feux",
                          "Chercher un club et voir les chances de ses prochains matchs : Premier League, Bundesliga, Liga, Serie A, Ligue 1, Ligue des champions, Ligue Europa.",
                          FOOT, ["favoris.js", "direct.js", "foot.js"], "foot", "hub"),
        "foot/en-direct.html": page("foot/en-direct.html", "Football en direct : scores et chances des matchs en cours - Extinction des feux",
                                    "Les matchs du jour de la Premier League, de la Bundesliga, de la Liga, de la Serie A, de la Ligue 1, de la Ligue des champions et de la Ligue Europa : score, minute et chances recalculées à chaque but.",
                                    LIVE, ["favoris.js", "modele-direct.js", "direct.js", "fiche.js", "en-direct.js"], "foot", "en-direct"),
        "foot/ligues.html": page("foot/ligues.html", "Ligues de pronostics entre amis - Extinction des feux",
                                 "Ligues de pronostics de football entre amis : scores à saisir avant le coup d'envoi, classement et points en direct.",
                                 LIGUES, ["favoris.js", "direct.js"], "foot", "ligues", modules=("ligues.js",)),
        "methode.html": page("methode.html", "Méthode - Extinction des feux",
                             "Comment les probabilités de Formule 1 et de football sont calculées, et ce qu'elles valent.",
                             METHODE, ["methode.js"], "methode"),
    }
    for _, slug, nom in COMPETITIONS:
        out[f"foot/{slug}.html"] = page(f"foot/{slug}.html", f"{nom} : pronostics, classement et fin de saison - Extinction des feux",
                                        f"{nom} : probabilités de chaque match, classement, fin de saison simulée, face-à-face et fiabilité du modèle.",
                                        COMP.replace("{nom}", nom), ["favoris.js", "modele-direct.js", "direct.js", "fiche.js", "competition.js"], "foot", slug).replace(
            '<body data-root="../">', f'<body data-root="../" data-competition="{slug}">')
    out["ligue1.html"] = REDIRECT.format(csp=CSP, target="foot/ligue-1.html", label="Ligue 1", version=empreinte("redirection.js"))
    out["recherche.html"] = REDIRECT.format(csp=CSP, target="foot.html", label="Football", version=empreinte("redirection.js"))
    return out


def sync_points(check: bool = False) -> bool:
    """Copie relais/points.js vers site/assets/points.js (ou vérifie qu'il est à jour en mode --check)."""
    src = POINTS_SRC.read_text(encoding="utf-8")
    if check:
        return POINTS_DST.exists() and POINTS_DST.read_text(encoding="utf-8") == src
    POINTS_DST.parent.mkdir(parents=True, exist_ok=True)
    POINTS_DST.write_text(src, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    stale = []
    if not sync_points(check=args.check):
        stale.append("assets/points.js")
    for rel, html in pages().items():
        f = SITE / rel
        if args.check:
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
