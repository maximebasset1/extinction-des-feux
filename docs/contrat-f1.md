# Contrat de données du moteur F1

Le moteur F1 (`src/`) est indépendant du football. Il publie des fichiers JSON à l'adresse
`https://maximebasset1.github.io/extinction-des-feux/data/<nom>.json`. Le site (pages `f1.html` et
`f1-methode.html`, script `site/assets/f1.js`, styles `site/assets/f1.css`) et PitLane Insider les lisent.

Règle de compatibilité : on peut **ajouter** des champs ; on ne renomme ni ne supprime un champ existant,
et l'adresse des fichiers ne change pas.

## `next.json` : le prochain Grand Prix

| Champ | Type | Sens |
|---|---|---|
| `maj_utc` | texte ISO | heure du calcul |
| `saison`, `gp`, `gp_fr`, `manche` | | Grand Prix visé (`gp` : nom anglais court, ex. « Las Vegas ») |
| `sessions` | objet | `FP1`…`R` → heure UTC de début |
| `qualif_disputee` | booléen | la qualification a eu lieu |
| `poleman` | objet ou `null` | pilote le plus rapide en qualif (`code`, `nom`, `famille`, `couleur`) |
| `grille_source` | texte | `officielle` (pénalités comprises, OpenF1), `provisoire` (ordre de la qualif) ou `inconnue` (avant la qualif) — **ajouté en novembre 2026** |
| `pole[]` | liste | par pilote : `code`, `nom`, `famille`, `couleur`, `equipe`, `avant` (chance de pole avant les essais), `apres` (après les essais), `sec`, `pluie` |
| `victoire[]` | liste | par pilote : `code`, `nom`, `famille`, `couleur`, `equipe`, `proba` (chance de victoire), `grille` (place de départ réelle quand la grille est connue) |
| `victoire[].qualif` | entier | place en qualif — **ajouté** |
| `victoire[].penalite` | entier | places perdues par rapport à la qualif (0 sinon) — **ajouté** |
| `victoire[].stands` | booléen | départ des stands — **ajouté** |
| `meteo` | objet | par séance : `temperature`, `pluie` (risque) |
| `arrivee[]` | liste | six premiers une fois la course finie |
| `modeles`, `statut`, `debut_saison`, `saison_terminee`, `horaires_estimes` | | contexte |

## `history.json` : passé rejoué

`saisons.<année>[]` : un Grand Prix par entrée (`gp`, `gp_fr`, `date`, `pluie`, `poleman`, `vainqueur`,
`pilotes[]` avec `avant`, `apres`, `ref`, `qualif`, `victoire`, `arrivee`). `pilotes.<code>` : nom et couleur.

## `journal.json` : pronostics publiés et jugés

`evaluations[]` : `season`, `grand_prix`, `type` (`pole` ou `victoire`), `etape`, `publie_utc`, `reel`,
`proba_du_vainqueur`, `rang_du_vainqueur`, `favori`, `log_loss`, `log_loss_hasard`, `recalcule` (**ajouté** :
vrai pour le recalcul de Las Vegas 2026 sur la grille officielle).

## `performance.json`, `drivers.json`, `etude_f1.json`

Bilan du backtest, saison des pilotes, et étude de novembre 2026 (grille officielle et variables de rythme
testées), affichée sur la page « Méthode et bilan F1 ».
