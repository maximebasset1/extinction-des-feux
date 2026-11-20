# Extinction des feux : qui partira en pole ?

Un site public sur la Formule 1 qui estime, pour chaque pilote, la probabilité de faire la **pole position** et de **gagner la course** au prochain Grand Prix. Il compare aussi, course par course depuis 2024, **ce que le modèle annonçait et ce qui s'est réellement passé**, et tient un journal des pronostics publiés avant chaque séance.

Le site se met à jour tout seul : toutes les 3 heures, GitHub télécharge les nouvelles séances, réentraîne les modèles, recalcule les pronostics et republie la page. Rien à faire sur ton PC.

## Le site en ligne (GitHub Pages)

| Élément | Rôle |
| --- | --- |
| `site/` | le site : `index.html`, `assets/` (style, script, polices, icône) et `data/*.json` (les chiffres) |
| `.github/workflows/mise-a-jour.yml` | le calcul automatique, toutes les 3 heures et à chaque modification du code |
| `data/calendar.json` | les horaires des séances (mis à jour par `scripts/update_calendar.py`) |
| `data/journal/predictions.csv` | le journal des pronostics : chaque pronostic est enregistré **avant** la séance, jamais réécrit |

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

## Les rubriques du site

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

## Ligue 1

Le site a aussi une page **Ligue 1** (`ligue1.html`) : pour chaque match, la probabilité de victoire à domicile, de nul et de victoire à l'extérieur, les scores les plus probables et les buts attendus. On peut choisir la journée, afficher le calendrier d'un club avec ses chances match par match, comparer deux clubs (tous leurs matchs de Ligue 1 depuis 1993) et voir la fin de saison simulée 10 000 fois (titre, top 4, barrage, relégation).

Comment c'est calculé :
- chaque équipe a une force d'attaque et de défense, estimée sur ses matchs récents (les plus récents comptent plus), avec les buts et les tirs cadrés ;
- les cotes d'avant-match servent de variable : elles résument les blessures, suspensions et l'actualité que les statistiques ne voient pas. Elles ne sont jamais affichées ;
- les réglages sont choisis sur 2015-2019, puis le modèle est jugé sur 2021-2026, semaine par semaine, sans jamais voir le futur.

Résultat sur 1 768 matchs (2021-2026) : avec les seules statistiques, le modèle fait nettement mieux que les habitudes (« l'équipe à domicile gagne 45 % du temps ») ; avec les cotes, il est au niveau du marché des paris, qui reste la référence la plus difficile à battre. Le favori du pronostic gagne environ un match sur deux : au foot, ce sont les probabilités qui doivent être justes, pas chaque pronostic.

Sources, gratuites : résultats, tirs et cotes de [football-data.co.uk](https://www.football-data.co.uk/), calendrier complet d'[openfootball](https://github.com/openfootball/football.json) (domaine public), anciennes saisons de [datasets/football-datasets](https://github.com/datasets/football-datasets). Seuls les logos du domaine public sur Wikimedia Commons sont utilisés ; les autres clubs ont une pastille à leurs couleurs.

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
football/               page Ligue 1 : téléchargement, modèle, backtest, saison simulée, export
data/journal/ligue1.csv journal des pronostics Ligue 1 publiés
app.py, lancer.py       plateforme locale (Streamlit), facultative
tests/                  tests automatiques
```

---

*Projet étudiant de Maxime Basset, non affilié à la Formule 1, à la FIA ni à la LFP. Ce n'est pas un outil de pari.*
