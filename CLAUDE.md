# CLAUDE.md : extinction-des-feux

Mémoire permanente du projet. À lire avant toute modification.

## Présentation

Plateforme statique multi-sport (**Formule 1 + Football**) de pronostics probabilistes, publiée sur GitHub Pages : <https://maximebasset1.github.io/extinction-des-feux/>.

- Calcul : pipelines Python exécutés par **GitHub Actions** (`.github/workflows/mise-a-jour.yml`, toutes les 1 à 3 h). Ils réentraînent les modèles, recalculent les pronostics et republient le site.
- Direct Football : relais Edge **Cloudflare Worker** (`extinction-direct.maximebasset1.workers.dev`, code dans `relais/`). La boucle d'appels tourne dans GitHub Actions (`direct.yml`), le Worker ne fait que servir.
- Site 100 % statique : pas de serveur, pas de base de données. CSP stricte, aucun CDN ni traceur.

Carte du dépôt :

| Dossier / fichier | Rôle |
| --- | --- |
| `src/` | moteur F1 (modèles, features, journal, export JSON) |
| `football/` | moteur Football (ligues, coupes, direct, journal) |
| `scripts/build_site.py` | génère les pages HTML de `site/` |
| `site/` | pages et `assets/` (CSS, JS, polices Titillium Web) |
| `data/journal/` | journaux de pronostics (`predictions.csv` F1, `foot.csv` Football) |
| `docs/contrat-f1.md` | contrat de données F1 |
| `relais/` | Cloudflare Worker + boucle du direct |
| `integration/` | patch d'intégration dans PitLane Insider |
| `tests/` | `pytest` (Python) et tests Node `*.test.mjs` (relais, direct) |

## Règle d'architecture critique : découplage strict F1 / Football

- La partie **F1** (`src/`, JSON F1 dans `data/`, `f1.css`, `f1.js`, pages F1) et la partie **Football** (`football/`, `foot.js`, `direct.js`, relais) restent **strictement découplées**.
- Aucune dépendance croisée : pas d'import de l'une dans l'autre, pas de fichier de données ou de style partagé qui ferait tomber l'autre en cas de panne. Une panne Football ne doit jamais casser F1, et inversement.
- Le code commun reste dans les assets génériques (`commun.js`, `style.css`) et ne doit dépendre d'aucun des deux sports.
- **Contrat de données F1** (`docs/contrat-f1.md`) : on peut **ajouter** des champs, jamais **renommer ni supprimer** un champ existant, et l'adresse des fichiers JSON ne change pas. Raison : la partie F1 sera intégrée plus tard dans un site externe Node.js/EJS (*PitLane Insider*). Toute évolution est documentée dans le contrat, avec la date d'ajout.

## Charte graphique (design system)

- Thème sombre unifié inspiré de *PitLane Insider* : fonds `#0f1115` et `#161920`.
- Accent : vert d'eau `#058785`.
- Police libre **Titillium Web**, hébergée dans `site/assets/fonts/` (aucun CDN).
- Chiffres tabulaires alignés partout (`font-variant-numeric: tabular-nums`) : classements, probabilités, cotes.
- Couleurs officielles des écuries, avec un contraste suffisant sur fond sombre.
- Pas de texte gris sur gris, pas de look « généré par IA » (dégradés gratuits, emojis décoratifs, cartes interchangeables).
- Toute modification d'interface est vérifiée en mobile **et** en desktop.

## Data science et modélisation

- **Backtest sans fuite du futur** : séparation stricte entre la période où l'on choisit (variables, hyperparamètres) et la période de test. Aucune information postérieure à la date du pronostic ne peut entrer dans une variable.
- **Une nouvelle variable n'est gardée que si elle améliore objectivement** la log-loss et le score de Brier sur la période de test. Tout comparatif avant/après est documenté dans la section **Méthode** du site (`methode.html`, `f1-methode.html`), y compris quand la variable est rejetée.
- **Le journal des pronostics publiés n'est jamais réécrit silencieusement** (`data/journal/*.csv`). Un pronostic est enregistré avant la séance ou le coup d'envoi. Toute correction passe par un script dédié (voir `src/corriger_journal.py`), est explicite et tracée.
- Versions des bibliothèques figées dans `requirements-ci.txt` : une mise à jour ne doit pas changer les pronostics publiés sans décision explicite.

## Workflow Git et qualité

- Toujours travailler sur une branche dédiée (`feat/...` ou `fix/...`). Jamais de commit direct sur `main` sans validation explicite de Maxime.
- Avant de proposer une fusion :
  1. lancer `python -m pytest` (état de référence sur GitHub : tout passe ; en local, 3 tests sont ignorés car Node est absent, et avec Node installé les tests `relais` et `live` s'exécutent) ;
  2. vérifier les empreintes de cache des fichiers statiques (`?v=...`) : `build_site.py` les calcule (sha256 du fichier, 8 premiers caractères) et les écrit dans les pages. Après tout changement d'un CSS/JS de `site/assets/`, relancer `python scripts/build_site.py` et commiter les pages régénérées. `python scripts/build_site.py --check` (appelé par `pytest`) échoue si une page est périmée. Les JSON de `data/` ne portent pas d'empreinte : ils sont demandés avec `?t=<minute>` ;
  3. lancer `/review` (relecture indépendante du `git diff main`).
- Le site se régénère avec `scripts/build_site.py`. Ne jamais éditer à la main les pages HTML générées.
- **Piège Windows (fins de ligne)** : `empreinte()` hache les octets du fichier. Avec `core.autocrlf=true`, les assets sont en CRLF sur le disque, donc le hash local diffère de celui calculé sur GitHub (Linux, LF). Conséquence connue : `test_site_pages_are_up_to_date` échoue en local alors que `main` est correct. Ne pas régénérer les pages sur ce PC pour « corriger » : on commiterait de fausses empreintes. Pour régénérer ou valider proprement, passer par GitHub Actions ou normaliser les fins de ligne en LF (`.gitattributes` avec `* text=auto eol=lf`, ou hacher en normalisant `\r\n` dans `empreinte()`).

## Environnement local

- Windows, PowerShell. Python 3.12 en local, 3.13 sur GitHub Actions.
- Installation : `pip install -r requirements-ci.txt` (tests et calcul) ; `requirements-local.txt` ajoute Streamlit pour l'application locale.
