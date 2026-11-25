# CLAUDE.md : extinction-des-feux

Mémoire permanente du projet. À lire avant toute modification.

## Présentation

Plateforme statique multi-sport (**Formule 1 + Football**) de pronostics probabilistes, publiée sur GitHub Pages : <https://maximebasset1.github.io/extinction-des-feux/>.

- Calcul : pipelines Python exécutés par **GitHub Actions** (`.github/workflows/mise-a-jour.yml`, toutes les 1 à 3 h). Ils réentraînent les modèles, recalculent les pronostics et republient le site.
- Direct Football : relais Edge **Cloudflare Worker** (`extinction-direct.maximebasset1.workers.dev`, code dans `relais/`). La boucle d'appels tourne dans GitHub Actions (`direct.yml`), le Worker ne fait que servir.
- Ligues de pronostics entre amis (Football uniquement) : routes `/ligues` sur le même Worker Cloudflare, stockant ligues, pseudos et pronostics sur **Cloudflare D1** (`extinction-ligues`, schéma dans `relais/schema.sql`, barème partagé dans `relais/points.js` copié vers `site/assets/points.js` par `build_site.py`). Sans compte : le navigateur conserve le code de ligue et le jeton dans `localStorage`.
- Comptes personnels **facultatifs** (Football) : routes `/comptes` sur le même Worker (`relais/ligues.js`), clubs favoris et ligues retrouvés sur tous les appareils. Côté site : `site/assets/compte.js` (voir « Comptes et favoris »).
- Pages publiées sur GitHub Pages : 100 % statiques (la partie F1 n'a ni serveur ni base de données). CSP stricte, aucun CDN ni traceur.

Carte du dépôt :

| Dossier / fichier | Rôle |
| --- | --- |
| `src/` | moteur F1 (modèles, features, journal, export JSON) |
| `football/` | moteur Football (ligues, coupes, direct, journal) |
| `scripts/build_site.py` | génère les pages HTML de `site/` |
| `site/` | pages et `assets/` (CSS, JS, polices Titillium Web) |
| `data/journal/` | journaux de pronostics (`predictions.csv` F1, `foot.csv` Football) |
| `docs/contrat-f1.md` | contrat de données F1 |
| `docs/contrat-direct.md` | contrat de données du direct Football (relais, `ev`, `lam`) |
| `relais/` | Cloudflare Worker + boucle du direct |
| `integration/` | patch d'intégration dans PitLane Insider |
| `tests/` | `pytest` (Python) et tests Node `*.test.mjs` (relais, direct) |

## Règle d'architecture critique : découplage strict F1 / Football

- La partie **F1** (`src/`, JSON F1 dans `data/`, `f1.css`, `f1.js`, pages F1) et la partie **Football** (`football/`, `foot.js`, `direct.js`, relais) restent **strictement découplées**.
- Aucune dépendance croisée : pas d'import de l'une dans l'autre, pas de fichier de données ou de style partagé qui ferait tomber l'autre en cas de panne. Une panne Football ne doit jamais casser F1, et inversement.
- Le code commun reste dans les assets génériques (`commun.js`, `style.css`) et ne doit dépendre d'aucun des deux sports.
- **Contrat de données F1** (`docs/contrat-f1.md`) : on peut **ajouter** des champs, jamais **renommer ni supprimer** un champ existant, et l'adresse des fichiers JSON ne change pas. Raison : la partie F1 sera intégrée plus tard dans un site externe Node.js/EJS (*PitLane Insider*). Toute évolution est documentée dans le contrat, avec la date d'ajout.

## Comptes et favoris (Football)

- **Tout doit marcher sans compte.** Créer, rejoindre et pronostiquer sans en-tête de compte répondent comme avant (test « sans compte »). Les comptes ne font qu'ajouter.
- Base D1 : tables `comptes` et `sessions`, colonne `membres.compte_id`. `schema.sql` passe avant `migrations.sql` au déploiement : **un index sur une colonne ajoutée va dans `migrations.sql`**, sinon le déploiement échoue sur la base en ligne. Un ordre par ligne.
- Aucun secret en clair : mot de passe en SHA-256 salé (sel propre à chaque compte), jetons gardés en empreinte seulement. `compte_id` ne sort jamais de `GET /ligues/:code`.
- Limites connues : SHA-256 est rapide (faible si la base fuit) et **les essais de mot de passe ne sont pas limités**. Pas d'adresse e-mail, donc pas de récupération de mot de passe.
- Une ligne de `sessions` par appareil connecté (10 au plus par compte). Le jeton de compte ouvre aussi les joueurs rattachés au compte ; les jetons de joueur d'origine restent valables. Vingt clubs favoris au plus par compte.
- Navigateur : `localStorage` `extinction.compte.v1` (compte), `extinction.favoris.v1` (favoris : source de vérité sans compte, copie avec compte), `extinction_ligues_v1` (ligues ; `compte` marque celles du compte). La déconnexion retire du navigateur ce qui est sur le compte.
- `compte.js` et `favoris.js` sont chargés par `build_site.py` sur toutes les pages **sauf F1** (découplage). Partout où une étoile peut être touchée, `compte.js` doit être là, sinon le favori n'est pas envoyé au compte.

## Navigation

- Une seule barre principale : `F1`, `Football`, `En direct` (pastille quand un match est en cours), `Ligues`, `Méthode`, puis le bouton du compte. Pas de seconde rangée dans l'en-tête.
- Une seule ligne de filtres : `Mes favoris` (dès un club suivi), `Tout`, puis les compétitions dans l'ordre de `FILTRES` (`scripts/build_site.py`). Les pages de compétition ont la même ligne en liens.
- Une ligne de match cliquable est un `div` recouvert par un lien (`.m-lien`) : ne jamais remettre les étoiles à l'intérieur d'un `<a>`.

## Charte éditoriale

- **Aucun exemple fictif dans les `placeholder`** : champs vides, avec un `<label>` court (vérifié par `pytest`).
- Textes concis et directs.

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
  1. lancer `python -m pytest` et `node --test tests/*.test.mjs` (état de référence : tout passe ; sans Node, `pytest` ignore les tests JavaScript ; les tests des ligues et des comptes demandent Node 22.13 ou plus récent, pour `node:sqlite`) ;
  2. vérifier les empreintes de cache des fichiers statiques (`?v=...`) : `build_site.py` les calcule (sha256 du fichier, 8 premiers caractères) et les écrit dans les pages. Après tout changement d'un CSS/JS de `site/assets/`, relancer `python scripts/build_site.py` et commiter les pages régénérées. `python scripts/build_site.py --check` (appelé par `pytest`) échoue si une page est périmée. Les JSON de `data/` ne portent pas d'empreinte : ils sont demandés avec `?t=<minute>` ;
  3. lancer `/review` (relecture indépendante du `git diff main`).
- Le site se régénère avec `scripts/build_site.py`. Ne jamais éditer à la main les pages HTML générées.
- **Fins de ligne (Windows)** : `empreinte()` normalise `\r\n` en `\n` avant de hacher, donc l'empreinte est identique sur ce PC (`core.autocrlf=true`) et sur GitHub. Le test `test_asset_fingerprint_ignores_line_endings` protège ce comportement : ne pas le retirer.

## Environnement local

- Windows, PowerShell. Python 3.12 en local, 3.13 sur GitHub Actions.
- Installation : `pip install -r requirements-ci.txt` (tests et calcul) ; `requirements-local.txt` ajoute Streamlit pour l'application locale.
