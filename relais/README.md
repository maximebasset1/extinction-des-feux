# Relais : direct et ligues de pronostics

Le Worker `extinction-direct` a deux rôles indépendants : servir le direct (`GET /direct`, voir `docs/contrat-direct.md`)
et gérer les ligues de pronostics entre amis (`/ligues`).

| Fichier | Rôle |
|---|---|
| `relais.js` | direct (boucle et route `/direct`), aiguillage vers les ligues |
| `ligues.js` | routes `/ligues` |
| `points.js` | barème ; module ES sans dépendance, utilisable aussi par le site |
| `programme.js`, `publier-programme.mjs` | programme des matchs rangé dans KV (clé `programme`) |
| `schema.sql` | tables D1 `ligues`, `membres`, `pronos` |

## Programme des matchs

Les ligues utilisent les **identifiants de match du site** (`compétition|domicile|extérieur|jour`, champ `matchs[].id` des fichiers
`data/foot/*.json`). GitHub Actions (`relais.yml`) relit ces fichiers après chaque déploiement puis toutes les 30 minutes
(GitHub peut avoir du retard) et range dans KV, pour chaque match : coup d'envoi, état, probabilités, score n° 1 et résultat.
Les probabilités et le score n° 1 sont figés au dernier relevé d'avant-match.

- Seuls les matchs dont l'heure est connue sont pronosticables (en pratique, les deux prochaines semaines au moins).
- Match déplacé : le pronostic le suit (même affiche, jusqu'à 90 jours après en championnat, 40 en coupe).
- Les résultats arrivent avec ceux du site, donc parfois plusieurs heures après la fin du match.
- Les scores sont ceux des 90 minutes, **sauf peut-être en Ligue Europa à élimination directe** : la source de ces résultats
  (The Odds API) peut y inclure la prolongation (voir `football/sources.py`).

## Barème

Bonne issue (1, N, 2) : 3 points. Bon écart de buts, si l'issue est bonne : 2 de plus. Score exact : 5 de plus (10 au total).
« Coup de poker » : issue bonne qui avait moins de 25 % de chances avant le match : total × 1,5, arrondi au supérieur.
Un match nul bien annoncé vaut donc au moins 5 points (son écart, 0, est forcément juste).

## API

Réponses en JSON, sans cache, CORS ouvert. Erreur : `{ "erreur": { "code", "message" } }`.
Le jeton n'est remis qu'une fois (création ou inscription) : au navigateur de le garder. La base n'en conserve que l'empreinte.
Le code de la ligue suffit pour consulter et s'inscrire : il se partage entre amis seulement.

| Route | Corps | Réponse |
|---|---|---|
| `POST /ligues` | `{ nom, pseudo }` | 201 `{ code, membre_id, jeton }` ; le `Bot IA` est inscrit avec la ligue |
| `POST /ligues/:code/rejoindre` | `{ pseudo }` | 201 `{ membre_id, jeton }` |
| `POST /ligues/:code/pronos` | `{ match_id, buts_dom, buts_ext }` + `Authorization: Bearer <jeton>` | 200 `{ match_id, buts_dom, buts_ext, coup_envoi, maj_le }` |
| `GET /ligues/:code` | `Authorization` facultatif (sans lui, tous les pronostics à venir sont masqués) | 200, voir plus bas |

`nom` : 3 à 40 caractères ; `pseudo` : 2 à 20, unique dans la ligue sans tenir compte de la casse ; scores : entiers de 0 à 20 ;
30 joueurs au plus par ligue.

Codes d'erreur : `corps_invalide`, `nom_invalide`, `pseudo_invalide`, `match_invalide`, `score_invalide` (400) ;
`jeton_manquant`, `jeton_invalide` (401) ; `ligue_inconnue`, `match_inconnu`, `route_inconnue` (404) ;
`methode_non_permise` (405) ; `pseudo_pris`, `ligue_complete`, `match_verrouille` (409) ; `corps_trop_long` (413) ;
`erreur_interne` (500) ; `ligues_indisponibles`, `programme_indisponible` (503, ce dernier aussi pour un pronostic quand le
programme a plus de 48 h).

### `GET /ligues/:code`

| Champ | Sens |
|---|---|
| `code`, `nom`, `cree_le` | la ligue |
| `moi` | identifiant du joueur du jeton, ou `null` |
| `programme_maj_utc` | date du programme utilisé |
| `membres[]` | `id`, `pseudo`, `est_bot`, `pronos[]` |
| `pronos[]` | visible : `match_id`, `buts_dom`, `buts_ext` ; match jugé : en plus `points`, `bonne_issue`, `bon_ecart`, `score_exact`, `coup_de_poker`. Caché (autre joueur, match pas commencé) : `match_id`, `masque: true`. `hors_delai: true` : saisi après le coup d'envoi finalement retenu, ne compte pas |
| `matchs{}` | par identifiant : `coup_envoi`, `commence`, `score` (ou `null`), `probas` `[domicile, nul, extérieur]` (ou `null`) |
| `classement[]` | `rang`, `membre_id`, `pseudo`, `est_bot`, `points`, `scores_exacts`, `bonnes_issues`, `bons_ecarts`, `coups_de_poker`, `matchs_juges` ; départage : points, scores exacts, bonnes issues |

Le `Bot IA` joue le score n° 1 publié par le site, **seulement sur les matchs qu'au moins un joueur de la ligue a pronostiqués**.
Ses pronostics ne sont pas masqués (ce score est déjà public sur le site).

## Déploiement

`relais.yml` crée la base D1 `extinction-ligues` au premier déploiement et rejoue `schema.sql` à chaque fois.
Le jeton `CLOUDFLARE_API_TOKEN` doit avoir les droits « Workers Scripts : modification », « Workers KV Storage : modification »
et **« D1 : modification »**.
