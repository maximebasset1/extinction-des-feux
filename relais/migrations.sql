-- Bases D1 créées avant l'ajout d'une colonne. Un ordre par ligne, rejoués à chaque déploiement (relais.yml) :
-- « duplicate column name » est attendu et ignoré, toute autre erreur arrête le déploiement.
ALTER TABLE ligues ADD COLUMN competitions TEXT
ALTER TABLE ligues ADD COLUMN createur_id TEXT
ALTER TABLE membres ADD COLUMN compte_id TEXT
-- un compte n'a qu'un joueur par ligue
CREATE UNIQUE INDEX IF NOT EXISTS membres_compte ON membres (ligue_code, compte_id) WHERE compte_id IS NOT NULL
-- le créateur est le joueur inscrit au même instant que la ligue
UPDATE ligues SET createur_id = (SELECT id FROM membres WHERE ligue_code = ligues.code AND est_bot = 0 AND membres.cree_le = ligues.cree_le LIMIT 1) WHERE createur_id IS NULL
