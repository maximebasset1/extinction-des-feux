-- Bases D1 créées avant l'ajout d'une colonne. Un ordre par ligne, rejoués à chaque déploiement (relais.yml) :
-- « duplicate column name » est attendu et ignoré, toute autre erreur arrête le déploiement.
ALTER TABLE ligues ADD COLUMN competitions TEXT
ALTER TABLE ligues ADD COLUMN createur_id TEXT
-- le créateur est le joueur inscrit au même instant que la ligue
UPDATE ligues SET createur_id = (SELECT id FROM membres WHERE ligue_code = ligues.code AND est_bot = 0 AND membres.cree_le = ligues.cree_le LIMIT 1) WHERE createur_id IS NULL
