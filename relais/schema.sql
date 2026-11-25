-- Ligues de pronostics (Cloudflare D1). Appliqué à chaque déploiement par .github/workflows/relais.yml :
-- tout doit rester relançable sans effacer les données (IF NOT EXISTS). Ajouter une colonne à une table existante
-- demande en plus un ordre dans migrations.sql, ce fichier ne la ferait pas. Un index sur une colonne ajoutée ainsi
-- va lui aussi dans migrations.sql : ce fichier passe avant, sur une base qui n'a pas encore la colonne.

CREATE TABLE IF NOT EXISTS ligues (
  code         TEXT PRIMARY KEY,               -- ex. EDF-742
  nom          TEXT NOT NULL,
  cree_le      TEXT NOT NULL,
  competitions TEXT,                           -- tableau JSON de codes (ex. '["F1","LDC"]'), NULL = toutes
  createur_id  TEXT                            -- membres.id du créateur, seul autorisé à supprimer la ligue
);

CREATE TABLE IF NOT EXISTS membres (
  id         TEXT PRIMARY KEY,
  ligue_code TEXT NOT NULL REFERENCES ligues(code),
  pseudo     TEXT NOT NULL,
  pseudo_cle TEXT NOT NULL,                    -- pseudo en minuscules (accents compris) : unicité dans la ligue
  jeton_hash TEXT NOT NULL,                    -- SHA-256 du jeton ; vide pour le Bot IA, qui ne peut pas se connecter
  est_bot    INTEGER NOT NULL DEFAULT 0,
  cree_le    TEXT NOT NULL,
  compte_id  TEXT,                             -- comptes.id du joueur connecté, NULL sans compte (index : migrations.sql)
  UNIQUE (ligue_code, pseudo_cle)
);

CREATE TABLE IF NOT EXISTS comptes (
  id         TEXT PRIMARY KEY,
  pseudo     TEXT NOT NULL,
  pseudo_cle TEXT NOT NULL UNIQUE,             -- pseudo en minuscules : unique sur tout le site
  mdp_hash   TEXT NOT NULL,                    -- SHA-256 de « sel:mot de passe »
  sel        TEXT NOT NULL,                    -- 16 octets au hasard, propres à chaque compte
  favoris    TEXT NOT NULL DEFAULT '[]',       -- tableau JSON de clubs (ex. '["FRA:Brest"]'), 20 au plus
  cree_le    TEXT NOT NULL,
  maj_le     TEXT NOT NULL
);

-- une ligne par appareil connecté : le jeton de compte n'est jamais gardé, seulement son empreinte
CREATE TABLE IF NOT EXISTS sessions (
  jeton_hash TEXT PRIMARY KEY,
  compte_id  TEXT NOT NULL REFERENCES comptes(id),
  cree_le    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pronos (
  ligue_code TEXT NOT NULL REFERENCES ligues(code),
  membre_id  TEXT NOT NULL REFERENCES membres(id),
  match_id   TEXT NOT NULL,                    -- identifiant du match sur le site : compétition|domicile|extérieur|jour
  buts_dom   INTEGER NOT NULL,
  buts_ext   INTEGER NOT NULL,
  maj_le     TEXT NOT NULL,
  PRIMARY KEY (ligue_code, membre_id, match_id)
);
