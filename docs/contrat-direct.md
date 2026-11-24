# Contrat de données du direct Football

Le direct est indépendant de la F1 : le relais (`relais/`), les scripts `direct.js`, `fiche.js`, `modele-direct.js` et `favoris.js`
ne lisent aucun fichier F1, et la F1 ne lit rien du direct. Une panne du relais ne touche que les lignes « en direct » du football.

Règle de compatibilité (la même que pour la F1) : on peut **ajouter** des champs ; on ne renomme ni ne supprime un champ existant.

## `GET https://extinction-direct.maximebasset1.workers.dev/direct`

Réponse JSON, mise en cache 20 secondes. L'état est rangé dans le stockage KV par `relais/boucle.mjs` (GitHub Actions, un tour par minute) ;
le Worker ne fait que le servir.

| Champ | Type | Sens |
|---|---|---|
| `jour` | texte `AAAA-MM-JJ` (UTC) | jour du programme |
| `maj_utc` | texte ISO | dernier relevé des scores (ou du programme) |
| `intervalle_min` | entier ou `null` | minutes entre deux relevés en direct (quota d'appels de l'API) |
| `source`, `erreur` | | provenance ; dernière erreur du relais (`utc`, `message`) ou `null` |
| `matchs[]` | liste | matchs du jour de nos sept compétitions |
| `matchs[].id`, `c` | | identifiant API-Football ; code de la compétition du site (`E0`, `D1`, `SP1`, `I1`, `F1`, `LDC`, `LEC`) |
| `matchs[].ko`, `st` | | coup d'envoi (ISO) ; statut (`NS`, `1H`, `HT`, `2H`, `ET`, `BT`, `P`, `FT`, `FT?` : sorti du direct, score à confirmer, `AET`, `PEN`, `PST`, …) |
| `matchs[].min`, `plus` | entiers ou `null` | minute de jeu et arrêts de jeu |
| `matchs[].h`, `a` | texte | noms des équipes chez API-Football (le site les rattache à ses clubs) |
| `matchs[].g`, `mt` | `[domicile, extérieur]` | score du moment ; score à la mi-temps |
| `matchs[].ev` | liste de `[minute, arrêts, buts domicile, buts extérieur]` | chronologie des buts : un point à chaque changement de score vu par le relais — **ajouté le 22 novembre 2026** |

`ev` sert à la courbe des chances de la fiche d'un match (`fiche.js`). Sa précision est celle du relevé : la minute d'un but est
la minute du relevé qui l'a vu, au plus `intervalle_min` minutes après le but. Un score déjà acquis au premier relevé (relais lancé
en retard) apparaît à la minute de ce relevé ; une annulation par la VAR apparaît comme un point à score plus bas. La chronologie
survit à la relecture du programme (score final). Un relais plus ancien, sans `ev`, reste lisible : le site reconstruit alors une
courbe à deux marches avec `mt` et `g`.

## `data/foot/direct.json` : réglages du modèle du direct

Écrit par `football/pipeline.py` à partir de `football/live_params.json` (réglé par `football/live_fit.py`).

| Champ | Sens |
|---|---|
| `part_1re_mi_temps`, `rythme_selon_ecart`, `minutes_mi_temps`, `pas_par_mi_temps` | réglages du modèle (identiques en Python, `football/live.py`, et en JavaScript, `modele-direct.js`) |
| `periode_choix`, `periode_test`, `matchs_test` | réglage sur 2010-2021, jugement sur 2022 et après |
| `jugement_mi_temps[]` | log-loss, RPS, part de favoris justes de quatre méthodes, à la mi-temps |
| `fiabilite_mi_temps[]` | `issue`, `annonce` (chance moyenne annoncée à la pause), `observe` (fréquence observée en fin de match), `matchs` : le diagramme de calibration de la page Méthode (backtest, pas du suivi en direct) |

Les matchs du jour et à venir de `index.json` et des pages de compétition portent `lam` : les buts attendus de chaque équipe, calés pour
redonner `p` (chances publiées avant le match) au coup d'envoi. Les matchs joués la veille et aujourd'hui le gardent aussi, pour que la
fiche d'un match qui vient de se terminer reste lisible.
