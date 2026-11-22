# Extinction des feux : pronostics de Formule 1 et de football

Un site public qui estime, avant chaque Grand Prix de Formule 1, la probabilité de chaque pilote de faire la **pole position** et de **gagner la course**, et, avant chaque match de six compétitions de football, les chances de **victoire, de nul et de défaite**. Les pronostics sont ensuite comparés aux vrais résultats : un journal enregistre chaque pronostic avant le départ, sans jamais le réécrire.

Le site se met à jour tout seul : toutes les 1 à 3 heures, GitHub télécharge les nouveaux résultats, réentraîne les modèles, recalcule les pronostics et republie les pages. Rien à faire sur ton PC.

Pages : accueil (prochains départs, matchs à la une, surprises récentes), Formule 1, Football (recherche d'un club ou d'un match), une page par compétition (Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions, Ligue Europa) et Méthode.

## Le site en ligne (GitHub Pages)

| Élément | Rôle |
| --- | --- |
| `site/` | le site : pages HTML (générées par `scripts/build_site.py`), `assets/` (style, scripts, polices, icône) et `data/` (les chiffres) |
| `.github/workflows/mise-a-jour.yml` | le calcul automatique : toutes les heures du vendredi au dimanche, toutes les 3 heures le reste de la semaine, et à chaque modification du code |
| `data/calendar.json` | les horaires des séances (mis à jour par `scripts/update_calendar.py`) |
| `data/journal/predictions.csv` | le journal des pronostics de F1 : chaque pronostic est enregistré **avant** la séance, jamais réécrit |
| `data/journal/foot.csv` | le journal des pronostics de football, au moins 30 minutes avant chaque coup d'envoi |
| `data/football/resultats_coupes.csv` | les résultats de Ligue Europa relevés au fil de la saison |

**Gratuit :** GitHub Actions et GitHub Pages sont gratuits pour un dépôt public.

**Sécurisé :**
- site 100 % statique : pas de serveur, pas de base de données, pas de formulaire, rien à pirater côté serveur ;
- aucun mot de passe ni jeton à stocker : la publication utilise le jeton temporaire fourni par GitHub à chaque exécution ;
- politique de sécurité du contenu (CSP) stricte : la page ne charge que ses propres fichiers (polices hébergées sur le site, aucun traceur, aucun CDN) ;
- Dependabot tient à jour les actions GitHub utilisées.

**Mise en route (déjà faite pour ce dépôt) :**
1. Dépôt **public** sur GitHub.
2. *Settings → Pages → Build and deployment → Source : GitHub Actions*, avant le premier envoi.
3. Envoyer le code (l'outil qui envoie doit avoir le droit de modifier les *workflows*).
4. Le premier calcul part tout seul (environ 20 minutes : tout l'historique est téléchargé une fois, puis gardé en cache). L'adresse du site s'affiche dans *Settings → Pages*.

À savoir :
- GitHub désactive les tâches planifiées d'un dépôt resté 60 jours sans modification. Si cela arrive pendant l'hiver : onglet *Actions → Mise à jour des pronostics → Enable workflow*, puis *Run workflow*.
- Les versions des bibliothèques utilisées en ligne sont figées dans `requirements-ci.txt`.
- Si un téléchargement échoue en partie, le calcul s'arrête sans publier : le site garde la version précédente, et la tentative suivante reprend là où elle s'est arrêtée.

## Un modèle qui apprend au fil des courses

- **À chaque mise à jour**, les poids des modèles sont réentraînés avec toutes les courses disponibles : chaque nouveau Grand Prix enrichit l'apprentissage.
- **La recette du modèle** (quelles variables, quelle famille de modèle) est choisie une fois, sur le début de saison 2026, puis figée. La choisir à nouveau à chaque course reviendrait à se noter soi-même : la période de test deviendrait une période d'entraînement. Elle sera revue une fois par saison.
- **Le journal des pronostics** est le vrai test : ce qui a été publié avant la séance, comparé au résultat. Un pronostic n'y entre que s'il est calculé au moins 30 minutes avant la séance, avec des horaires officiels, et les lignes ne sont jamais réécrites. Il démarre avec la mise en ligne du site.
- **L'historique affiché** (« ce que le modèle aurait prévu ») est une reconstitution : le modèle est rejoué course par course avec les seules données d'avant. Le site le dit.

## Météo et saisons anciennes

- **Saisons 2018 à 2022 ajoutées** (192 qualifications au total). Le site compare trois façons d'apprendre : seulement 2023 et après, tout depuis 2018, ou depuis 2018 avec un poids qui diminue avec l'ancienneté. Pour la pole, les trois font jeu égal sur la période de choix (log-loss moyenne 1,325 / 1,324 / 1,324) : la règle retient « depuis 2018, récent d'abord », mais la différence est du bruit. Pour la victoire, partir de 2018 aide nettement.
- **Météo des séances passées** : chaque tour enregistre la pluie, la température de l'air et de la piste.
- **Température** : nouvelle variable « forme par température proche » (qualifs de la saison disputées à ± 6 °C de la température attendue). La température attendue est celle des essais libres du week-end, ou la prévision avant le week-end, jamais celle de la qualif elle-même. Elle est retenue pour le pronostic d'avant week-end.
- **Pluie, modèle de pole** : deux réglages testés (le « talent sous la pluie » de chaque pilote, et une hiérarchie plus ou moins nette sous la pluie). Sur les 13 qualifs mouillées de 2018 à 2025, aucun ne fait mieux que le modèle de base : ils ne sont pas utilisés tant que ce sera le cas.
- **Pluie, modèle de victoire** : sous la pluie, la place de départ compte moins. Jugé à part sur les 9 courses mouillées de 2018 à 2025 (log-loss 1,685 sans, 1,661 avec) : retenu. Avant la course, il est pondéré par le risque de pluie prévu.
- **Prévision** : Open-Meteo (gratuit, sans clé, licence CC BY 4.0, cité sur le site) donne la température et le risque de pluie pour la qualif et la course. Ce risque compte toute pluie, même une petite averse : il surestime un peu le risque d'une séance vraiment mouillée.

| Modèle | Période | Avant | Après |
| --- | --- | --- | --- |
| Pole, avant le week-end, gain face au hasard | 2024-2025 | +1,28 | +1,23 |
| Pole, avant le week-end, gain face au hasard | fin 2026 | +0,19 | +0,27 |
| Pole, après les essais, gain face au hasard | 2024-2025 | +1,42 | +1,40 |
| Pole, après les essais, gain face au hasard | fin 2026 | +0,39 | +0,42 |
| Victoire, log-loss (plus bas = mieux) | 2026 | 1,194 | 1,103 |

En clair : la pole ne devient pas mesurablement plus précise (les écarts sont dans le bruit), la victoire oui.
Le calcul complet (88 variantes) prend environ 20 minutes ; il n'est refait que lorsqu'une nouvelle course entre dans l'historique.

## Sur ton PC (facultatif)

L'ancienne plateforme Streamlit reste disponible en local :
- **double-clic sur `Lancer_plateforme.bat`** (Windows), ou **`python lancer.py`** ;
- pour arrêter : bouton « ⏹ Arrêter la plateforme » dans le menu de gauche, ou ferme la fenêtre noire.

En ligne de commande :

```bash
pip install -r requirements.txt   # calcul seul (requirements-local.txt pour Streamlit)
python src/main.py                # télécharge ce qui manque, calcule, exporte le site
python -m http.server -d site     # voir le site sur http://localhost:8000
python -m pytest tests -q         # tests
```

Pour forcer un Grand Prix : `F1_TARGET="2026|Qatar Grand Prix" python src/main.py`.

## La page Formule 1

| Rubrique | Contenu |
| --- | --- |
| **Prochain GP** | Les cinq feux s'éteignent et révèlent la grille de départ la plus probable ; programme du week-end à l'heure locale. |
| **Les chances de chacun** | Probabilités de pole et de victoire pour tous les pilotes, avant ou après les essais libres. |
| **Ce qu'on avait prévu, et ce qui s'est passé** | Pour chaque qualif depuis 2024 : la probabilité donnée au vrai poleman, et le détail pilote par pilote. |
| **Notre bilan, sans maquillage** | Le modèle face au hasard, et le journal des pronostics publiés. |
| **La saison des pilotes** | Poles, victoires, podiums et proximité de la pole course après course. |
| **Comment ça marche** | La méthode en quatre étapes et ses limites. |

## Exemple : Las Vegas 2026, avant le week-end

| Pilote | Pole | Victoire |
| --- | --- | --- |
| Russell (Mercedes) | 20 % | 18 % |
| Hamilton (Ferrari) | 17 % | 16 % |
| Leclerc (Ferrari) | 16 % | 15 % |
| Verstappen (Red Bull) | 14 % | 14 % |
| Antonelli (Mercedes) | 13 % | 13 % |
| Norris (McLaren) | 8 % | 8 % |

La pole et la victoire sont très ouvertes : cinq pilotes ont entre 13 et 20 %. Ces chiffres changeront avec les essais libres. Hypothèse : piste sèche.

## Le modèle est-il fiable ?

**Méthode de test :** avant chaque qualif, le modèle ne voit que les courses précédentes, comme en vrai.
- Le modèle est **choisi** sur le début de saison 2026 (courses 4 à 11).
- Il est **jugé** sur deux périodes jamais utilisées pour ce choix : 2024-2025 (42 qualifs) et la fin 2026 (9 qualifs).

La mesure est la log-loss, −log(probabilité donnée au vrai poleman), et l'on regarde le **gain** par rapport à deux références. Un gain positif signifie que le modèle fait mieux.

| Modèle de pole | Période | Gain face au hasard | Gain face à « chances = poles déjà faites » |
| --- | --- | --- | --- |
| Avant le week-end | 2024-2025 | **+1,28** (IC 95 % : +1,05 à +1,51) | **+0,52** (+0,31 à +0,72) |
| Après les essais libres | 2024-2025 | **+1,42** (+1,16 à +1,68) | **+0,66** (+0,38 à +0,92) |
| Avant le week-end | fin 2026 | +0,19 (−1,18 à +0,99) | −0,18 (−1,40 à +0,80) |
| Après les essais libres | fin 2026 | +0,39 (−0,83 à +1,19) | +0,03 (−1,00 à +0,85) |

Ce qu'il faut en retenir :

- **Sur 2024-2025, le modèle bat nettement le hasard et la référence naïve :** les intervalles de confiance sont entièrement positifs.
- **Sur la fin de saison 2026, rien n'est démontré.** Seulement 9 qualifs, et une fin de saison très imprévisible (Gasly en pole à Monza, Hamilton au Mexique).
- **Les essais libres apportent le plus.** Sur la fin 2026, le meilleur modèle testé est le tour idéal en essais (somme des meilleurs secteurs), même s'il n'a pas été choisi : changer de modèle après avoir vu le test serait tricher.

**Course :** la place sur la grille explique l'essentiel. Le modèle retenu (logit sur la place de départ) fait à peine mieux que la fréquence historique de victoire selon la place : +0,04 de log-loss en 2026 (IC 95 % : −0,03 à +0,10), donc pas de différence démontrée. Sur 2024-2025, qui a servi à le choisir, le gain est de +0,21.

## Comment ça marche

1. **Données :** meilleurs tours de toutes les qualifications et essais libres, et classements des courses, de 2023 à 2026, soit 90 qualifications. Source : [TracingInsights](https://github.com/TracingInsights/2026) (données officielles extraites avec [FastF1](https://docs.fastf1.dev/)). Le poleman est le plus rapide en Q3 ; en cas d'égalité au millième, c'est celui qui a signé le temps en premier.
2. **Variables**, calculées uniquement avec les courses passées (un test le vérifie) :
   - forme récente du pilote et de l'équipe ;
   - forme sur les circuits du même type ;
   - affinité avec le Grand Prix ;
   - rythme en essais libres : meilleur tour, tours en pneus tendres, tour idéal.
3. **Deux familles de modèles comparées :**
   - *régression + aléa* : on prédit l'écart de chaque pilote au poleman, puis on ajoute un aléa de Student (σ recalé avant chaque qualif) ;
   - *logit conditionnel* : on apprend directement qui fait la pole parmi les pilotes de la course.
   - 22 modèles au total ; le meilleur est choisi automatiquement.
4. **Victoire :** logit conditionnel sur la place de départ. Avant la qualif, la grille est inconnue : on tire au sort 4 000 grilles possibles selon les probabilités de pole, puis on fait la moyenne.
5. **Grille officielle (correction de novembre 2026).** Jusqu'au GP de Las Vegas 2026, la « grille » était l'ordre de la qualif : les pénalités moteur et les départs des stands étaient ignorés, à l'entraînement comme pour la course à venir (Antonelli annoncé à 70 % depuis une pole qu'il n'occupait pas : il partait 6e). Désormais :
   - courses passées : grille réelle et classement officiel (pénalités après course, disqualifications) lus dans [f1db](https://github.com/f1db/f1db) (CC BY 4.0). 31 % des pilotes ne partent pas à leur place de qualif ; 2 vainqueurs changent (Canada 2019, Belgique 2024) ;
   - course à venir : grille publiée par [OpenF1](https://openf1.org) quelques minutes après le site officiel ; en attendant, l'ordre de la qualif, annoncé comme « grille provisoire » ;
   - nouvelle variable, la place en qualif, en plus de la place de départ : un pilote rapide pénalisé reste rapide. Jugée sur les mêmes courses (classement officiel) : log-loss 1,316 → 1,304 sur 2024-2025 (période de choix), 1,158 → 1,135 et score de Brier 0,572 → 0,538 sur 2026 (test) ; favori juste 10 → 11 fois sur 18. Sur 28 pilotes partis au moins 3 places derrière leur top 3 en qualif, le modèle donnait 11 % en moyenne ; 4 ont gagné (14 %) ;
   - le pronostic de Las Vegas publié sur la mauvaise grille reste dans le journal ; le bilan utilise son recalcul sur la grille officielle (données d'avant le départ seulement), signalé « recalculé après la course » (`src/corriger_journal.py`).
6. **Rythme de course (étude de novembre 2026, `src/rythme.py`, `src/etude_rythme.py`).** Testés : rythme des longs relais aux essais (tours de sortie/entrée, drapeaux, voiture de sécurité, VSC, tours supprimés et tours au-delà de 107 % du tour médian du relais écartés), usure des pneus (pente des temps sur un relais), rythme en course sprint. Règle fixée avant de voir les résultats : améliorer la log-loss **et** le score de Brier sur 2024-2025, puis le confirmer sur 2026. Aucune variable ne passe : les écarts restent dans le bruit (détail sur la page « Méthode et bilan F1 », données dans `data/processed/etude_f1.json`). Des chances de podium tirées du modèle de victoire ont aussi été essayées : elles ne battent pas la simple fréquence du podium selon la place de départ, elles ne sont donc pas publiées.

Le moteur F1 est un module autonome : `src/` (calcul), `site/f1.html` et `site/f1-methode.html`, `site/assets/f1.js` et `f1.css` (sans dépendance au reste du site). Le format des fichiers publiés est décrit dans [`docs/contrat-f1.md`](docs/contrat-f1.md) ; PitLane Insider les lit tels quels.

## Football : six compétitions, un seul modèle

Premier League, Bundesliga, Liga, Ligue 1, Ligue des champions et Ligue Europa. Pour chaque compétition : les matchs journée par journée (probabilités 1/N/2 sur 90 minutes, scores les plus probables, buts attendus), le classement et la fin de saison simulée 10 000 fois (titre, top 4, relégation ; top 8 et barrages en Ligue des champions), le calendrier de chaque club, les face-à-face depuis 2000 et la fiabilité. La page Football permet de chercher un club (« Lille ») ou un match (« Lille Bayern »).

Comment c'est calculé :
- un seul modèle note ensemble les clubs de 22 championnats européens (football-data.co.uk, depuis 2010) et des coupes d'Europe (openfootball, domaine public, puis football-data.org pour la saison en cours) ;
- chaque club a une force d'attaque et de défense, estimée sur ses matchs récents avec les buts et les tirs cadrés, et rappelée vers le niveau moyen de son championnat ; ce niveau n'est connu que grâce aux matchs européens et aux clubs qui montent ou descendent, ce qui permet de comparer Lille et le Bayern ;
- quand les cotes d'avant-match existent (football-data.co.uk pour les championnats, The Odds API pour les coupes), elles sont mélangées au modèle, car elles résument blessures et actualité ; elles ne sont jamais affichées et nos statistiques en gardent toujours une part (environ 30 % aujourd'hui, chiffre affiché sur la page Méthode).

**Le modèle apprend-il ?** À chaque lancement, toutes les forces sont réestimées avec les derniers résultats (football-data.org les donne dans l'heure) : une victoire ou une défaite déplace les chances des matchs suivants. Une surprise ne bouge pourtant les choses que de peu, volontairement : un match tient beaucoup du hasard. Les réglages (mémoire, part des tirs cadrés, poids des cotes) ont été choisis sur la saison 2021-22 et ne changent pas ; le journal sert à vérifier qu'ils tiennent.

Réglages choisis sur 2021-22, puis jugement semaine par semaine de 2022 à 2026. En coupe d'Europe, le modèle fait nettement mieux que les pourcentages habituels (score RPS d'environ 0,19 contre 0,24 en Ligue des champions, 0,20 contre 0,23 en Ligue Europa). En championnat, il est au niveau des bookmakers une fois les cotes ajoutées. Pour les matchs joués avant l'ouverture du journal, le site montre ce que le modèle aurait annoncé avant le match (reconstitution, faite sans connaître le résultat) : sous le score, « annoncé » désigne un pronostic publié, « estimé » une reconstitution.

**Chances en direct (en préparation).** `football/live.py` calcule, pendant un match, les chances de victoire, de nul et de défaite à partir du score et du temps restant. Chaque équipe marque à un rythme tiré de ses buts attendus, calés pour retrouver au coup d'envoi les chances publiées ; une équipe menée accélère un peu, une équipe qui mène ralentit un peu. Réglé sur 2010-2021 (`football/live_fit.py`, 48 000 matchs de 12 championnats), jugé à la mi-temps sur 17 400 matchs de 2022 à 2026 : log-loss 0,800 contre 0,967 en ignorant le score de la pause, et des chances annoncées proches des fréquences observées. Le même calcul existe en JavaScript (`site/assets/modele-direct.js`) pour tourner dans le navigateur ; un test vérifie que les deux donnent les mêmes chiffres.

Deux clés gratuites, rangées dans les secrets du dépôt (*Settings > Secrets and variables > Actions*) :
- `FOOTBALL_DATA_ORG_TOKEN` (football-data.org) : calendriers complets avec les heures, résultats récents, Ligue des champions ;
- `ODDS_API_KEY` (The Odds API, 500 crédits par mois) : Ligue Europa et cotes des coupes, demandées au plus toutes les 3 heures, seulement quand un match a lieu dans les 3 jours, avec une réserve de 50 crédits.

Sans ces clés, les quatre championnats fonctionnent avec le calendrier openfootball.

Essai sur un PC : `python football/pipeline.py --offline` réutilise les fichiers déjà téléchargés et n'utilise aucune clé. Hors de GitHub, le calcul travaille toujours sur une copie du journal et des résultats de coupe, dans un dossier temporaire : seul GitHub écrit les vrais. Variables utiles : `EU_DATA_DIR` (fichiers téléchargés), `ODDS_STATE_DIR` (suivi des crédits The Odds API), `FOOT_OUT_DIR` (fichiers JSON du site), `FOOT_JOURNAL` et `FOOT_CUP_RESULTS` (pour viser un journal ou un fichier de résultats précis).

## Limites

- Peu de courses par saison, et la réglementation 2026 change la hiérarchie : les données 2023-2025 n'aident qu'en partie.
- Pluie non modélisée (les séances humides sont exclues de la forme).
- Pénalités de grille et disqualifications après course non prises en compte.
- Aléa supposé indépendant entre pilotes, alors que deux coéquipiers partagent la voiture.
- Les données d'une séance sont publiées quelques heures après celle-ci.

## Relecture indépendante

Un relecteur a passé le code en revue avant la livraison. Ses remarques ont conduit à corriger :
- un plantage de la page Historique quand un pilote n'avait aucun temps en qualif ;
- l'ordre de la grille : il est maintenant calculé par partie atteinte (Q3, Q2, Q1), puis par temps ;
- le cache du backtest, désormais invalidé si le code change et recalculé s'il est illisible ;
- les accents du journal sous Windows, et un délai maximal pour la mise à jour ;
- deux libellés qui mélangeaient période de choix et période de test.

## Organisation

```
site/                   le site public (HTML, CSS, JavaScript, données JSON)
.github/workflows/      calcul et publication automatiques
scripts/update_calendar.py  horaires des séances (API Jolpica)
data/calendar.json      calendrier, heures UTC
data/journal/           journal des pronostics publiés
src/
  config.py             saisons, GP cible (choisi d'après le calendrier), type de circuit
  fetch_data.py         téléchargement (qualifs, essais, courses), avec réessais
  build_dataset.py      meilleurs tours, poleman, classements
  features.py           variables connues avant chaque qualif
  model.py              régression + aléa, logit conditionnel, métriques
  predict.py            backtest, choix du modèle, historique, prédiction
  race_model.py         modèle de victoire
  journal.py            enregistrement et évaluation des pronostics publiés
  export_site.py        fichiers JSON du site
  plots.py, report.py   graphiques et rapport HTML
  main.py               enchaîne tout
football/               les six compétitions de football
  pipeline.py           enchaîne tout : téléchargement, backtest, pronostics, journal, classements, fichiers du site
  joint.py, model.py    modèle commun aux championnats et coupes, grille des scores, mélange avec les cotes
  leagues.py, cups.py, sources.py, names.py  championnats, coupes passées, calendriers et cotes, noms des clubs
  season.py, journal.py classements et fins de saison simulées, journal des pronostics
scripts/build_site.py   génère les pages HTML (même en-tête et même pied partout)
app.py, lancer.py       plateforme locale (Streamlit), facultative
tests/                  tests automatiques
```

---

*Projet étudiant de Maxime Basset, non affilié à la Formule 1, à la FIA ni à la LFP, à l'UEFA ou aux clubs. Ce n'est pas un outil de pari.*
