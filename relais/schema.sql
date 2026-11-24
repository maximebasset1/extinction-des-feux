-- Ligues de pronostics (Cloudflare D1). Appliqué à chaque déploiement par .github/workflows/relais.yml :
-- tout doit rester relançable sans effacer les données (IF NOT EXISTS). Ajouter une colonne à une table existante
-- demande en plus un ordre dans migrations.sql, ce fichier ne la ferait pas.

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
  UNIQUE (ligue_code, pseudo_cle)
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
