# Relais : direct, ligues de pronostics et comptes

Le Worker `extinction-direct` a deux rôles indépendants : servir le direct (`GET /direct`, voir `docs/contrat-direct.md`)
et gérer les ligues de pronostics entre amis (`/ligues`), avec des comptes facultatifs (`/comptes`).

| Fichier | Rôle |
|---|---|
| `relais.js` | direct (boucle et route `/direct`), aiguillage vers les ligues et les comptes |
| `ligues.js` | routes `/ligues` et `/comptes` |
| `points.js` | barème ; module ES sans dépendance, utilisable aussi par le site |
| `programme.js`, `publier-programme.mjs` | programme des matchs rangé dans KV (clé `programme`) |
| `schema.sql` | tables D1 `ligues`, `membres`, `pronos`, `comptes`, `sessions`, `essais` |
| `migrations.sql` | colonnes ajoutées après la création de la base, et leurs index |

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
| `POST /ligues` | `{ nom, pseudo, competitions? }` (`competitions` facultatif : tableau non vide parmi `E0`, `D1`, `SP1`, `I1`, `F1`, `LDC`, `LEC` ou alias `PL`, `BL1`, `PD`, `SA`, `FL1`, `CL`, `EL` ; toutes par défaut) | 201 `{ code, membre_id, jeton, competitions }` ; le `Bot IA` est inscrit avec la ligue |
| `POST /ligues/:code/rejoindre` | `{ pseudo }` | 201 `{ membre_id, jeton }` |
| `POST /ligues/:code/pronos` | `{ match_id, buts_dom, buts_ext }` + `Authorization: Bearer <jeton>` | 200 `{ match_id, buts_dom, buts_ext, coup_envoi, maj_le }` (refuse `400` si la compétition du match n'appartient pas à la ligue) |
| `GET /ligues/:code` | `Authorization` facultatif (sans lui, tous les pronostics à venir sont masqués) | 200, voir plus bas |
| `DELETE /ligues/:code` | `Authorization: Bearer <jeton du créateur>` | 200 `{ code, supprimee: true }` : la ligue, ses membres et ses pronostics sont effacés définitivement |

`nom` : 3 à 40 caractères ; `pseudo` : 2 à 20, unique dans la ligue sans tenir compte de la casse ; scores : entiers de 0 à 20 ;
30 joueurs au plus par ligue.

Codes d'erreur : `corps_invalide`, `nom_invalide`, `pseudo_invalide`, `competitions_invalides`, `competition_non_autorisee`, `match_invalide`, `score_invalide` (400) ;
`jeton_manquant`, `jeton_invalide` (401) ; `pas_createur` (403) ; `ligue_inconnue`, `match_inconnu`, `route_inconnue` (404) ;
`methode_non_permise` (405) ; `pseudo_pris`, `ligue_complete`, `match_verrouille` (409) ; `corps_trop_long` (413) ;
`erreur_interne` (500) ; `ligues_indisponibles`, `programme_indisponible` (503, ce dernier aussi pour un pronostic quand le
programme a plus de 48 h).

### `GET /ligues/:code`

| Champ | Sens |
|---|---|
| `code`, `nom`, `cree_le` | la ligue |
| `competitions[]` | codes canoniques des compétitions jouées par la ligue (`E0`, `D1`, `SP1`, `I1`, `F1`, `LDC`, `LEC` ; toutes par défaut) |
| `moi` | identifiant du joueur du jeton, ou `null` |
| `createur_id` | identifiant du créateur de la ligue (ajouté le 2026-11-25) |
| `programme_maj_utc` | date du programme utilisé |
| `membres[]` | `id`, `pseudo`, `est_bot`, `pronos[]` |
| `pronos[]` | visible : `match_id`, `buts_dom`, `buts_ext` ; match jugé : en plus `points`, `bonne_issue`, `bon_ecart`, `score_exact`, `coup_de_poker`. Caché (autre joueur, match pas commencé) : `match_id`, `masque: true`. `hors_delai: true` : saisi après le coup d'envoi finalement retenu, ne compte pas |
| `matchs{}` | par identifiant : `coup_envoi`, `commence`, `score` (ou `null`), `probas` `[domicile, nul, extérieur]` (ou `null`) |
| `classement[]` | `rang`, `membre_id`, `pseudo`, `est_bot`, `points`, `scores_exacts`, `bonnes_issues`, `bons_ecarts`, `coups_de_poker`, `matchs_juges` ; départage : points, scores exacts, bonnes issues |

Le `Bot IA` joue le score n° 1 publié par le site, **seulement sur les matchs qu'au moins un joueur de la ligue a pronostiqués**.
Ses pronostics ne sont pas masqués (ce score est déjà public sur le site).

## Comptes (ajoutés le 2026-11-25)

Facultatifs : sans compte, les routes ci-dessus se comportent comme avant. `Authorization: Bearer <jeton_compte>` désigne
une session (un appareil connecté, 10 au plus par compte).

| Route | Corps | Réponse |
|---|---|---|
| `POST /comptes/inscription` | `{ pseudo, mot_de_passe }` | 201 `{ compte_id, pseudo, jeton_compte, favoris: [] }` |
| `POST /comptes/connexion` | `{ pseudo, mot_de_passe }` | 200 `{ compte_id, pseudo, jeton_compte, favoris, ligues }` |
| `GET /comptes/moi` | jeton de compte | 200 `{ compte_id, pseudo, favoris, ligues }` |
| `PUT /comptes/favoris` | `{ favoris }` + jeton de compte | 200 `{ favoris }` (doublons retirés, 20 au plus) |
| `POST /comptes/rattacher` | `{ ligues?: [{ code, jeton }], favoris? }` + jeton de compte | 200 `{ favoris, rattachees, ligues }` |
| `POST /comptes/detacher` | `{ code }` + jeton de compte | 200 `{ code, detachee: true }` : le joueur reste dans la ligue, hors du compte |
| `POST /comptes/deconnexion` | jeton de compte | 200 `{ deconnecte: true }` : cette session seulement est fermée |

- `pseudo` : 2 à 24 caractères, unique sur le site sans tenir compte de la casse. `mot_de_passe` : 4 à 128 caractères.
- `ligues[]` : `code`, `nom`, `membre_id`, `pseudo`, `jeton`. Ce `jeton` est le jeton de la session en cours : il ouvre ce
  joueur comme son jeton d'origine, qui reste valable. La base ne gardant que des empreintes, les jetons d'origine ne peuvent
  pas être rendus.
- `favoris` : identifiants de club du site (`FRA:Paris SG`).
- `rattacher` : 20 ligues et 100 favoris au plus par demande. Un joueur n'est rattaché que si son jeton est bon, s'il
  n'appartient pas à un autre compte et si le compte n'a pas déjà un joueur dans la ligue ; sinon il est ignoré. Favoris :
  ceux du compte d'abord, puis les nouveaux, coupés à 20.
- Avec un jeton de compte, `POST /ligues` et `POST /ligues/:code/rejoindre` rattachent le joueur au compte. Si le compte
  est déjà dans la ligue, `rejoindre` répond 200 `{ membre_id, jeton, pseudo, deja_membre: true }`. Un jeton de compte
  inconnu est refusé (401) plutôt qu'ignoré.

Codes d'erreur ajoutés : `mot_de_passe_invalide`, `favoris_invalides`, `rattachement_invalide`, `code_invalide` (400) ;
`identifiants_invalides` (pseudo inconnu et mot de passe faux répondent pareil), `session_invalide` (401) ;
`trop_d_essais` (429) ; `comptes_indisponibles` (503).

Sécurité : mot de passe gardé en SHA-256 de `sel:mot de passe`, sessions en SHA-256 du jeton.

Essais de mot de passe : **cinq par pseudo et par quart d'heure** (table `essais`). Au-delà, `POST /comptes/connexion`
répond 429 sans examiner le mot de passe, même s'il est bon, avec le temps restant dans le message. Le quart d'heure part
du premier essai et les essais refusés ne le repoussent pas ; une réussite remet le compteur à zéro. Un pseudo inconnu est
compté comme un autre. Les essais simultanés sont comptés un à un.

**Limites connues** :
- le compte porte sur le pseudo : quelqu'un qui le connaît peut empêcher son propriétaire de se connecter sur un nouvel
  appareil, tant qu'il recommence à chaque période (les appareils déjà connectés ne sont pas touchés) ;
- il reste 480 essais possibles par jour et par pseudo, assez pour trouver un mot de passe très courant ; rien ne limite un
  même mot de passe essayé sur beaucoup de pseudos ;
- SHA-256 se calcule vite : un mot de passe court se retrouve si la base fuit.

## Déploiement

`relais.yml` crée la base D1 `extinction-ligues` au premier déploiement, puis rejoue `schema.sql` et `migrations.sql` à chaque fois.
Le jeton `CLOUDFLARE_API_TOKEN` doit avoir les droits « Workers Scripts : modification », « Workers KV Storage : modification »
et **« D1 : modification »**.
