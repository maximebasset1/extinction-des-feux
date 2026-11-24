/* Programme des ligues : la liste compacte des matchs pronosticables, rangée dans KV sous la clé « programme ».
   Elle est construite depuis les JSON publiés par le site (relais/publier-programme.mjs, lancé par GitHub Actions) et lue par
   le Worker. Le site retire le score probable d'un match dès le coup d'envoi : on fige donc ici, au dernier relevé d'avant
   match, les probabilités (coup de poker) et le score n° 1 (pronostic du Bot IA). Module ES pur. */

export const CLE_PROGRAMME = "programme";
/* codes des compétitions du site et nom de leur fichier dans data/foot/ */
export const FICHIERS = { E0: "premier-league", D1: "bundesliga", SP1: "liga", I1: "serie-a", F1: "ligue-1",
  LDC: "ligue-des-champions", LEC: "ligue-europa" };
const JOUR_MS = 86400000;
const GARDE_JOURS = 400;                   // au-delà, un match sort du programme (une saison entière reste jugée)
/* match déplacé : même affiche, entre 3 jours avant et N jours après (mêmes ordres de grandeur que football/journal.py ;
   en coupe l'affiche peut revenir dans la saison, la fenêtre est donc plus courte) */
const AVANCE_MAX_JOURS = 3;
const REPORT_MAX_JOURS = { coupe: 40, ligue: 90 };

const score = (texte) => {
  const m = /^(\d+)-(\d+)$/.exec(texte || "");
  return m ? [Number(m[1]), Number(m[2])] : null;
};
export const competition = (id) => (id.includes("|") ? id.slice(0, id.indexOf("|")) : "");
const affiche = (id) => id.slice(0, id.lastIndexOf("|"));
const jour = (id) => Date.parse(id.slice(id.lastIndexOf("|") + 1));

/* nouveau programme à partir de l'ancien et des fichiers du site ({ code: contenu ou null s'il n'a pas pu être lu }) */
export function fusionner(ancien, fichiers, maintenant) {
  const avant = ancien?.matchs || {};
  const lus = new Set(Object.entries(fichiers)
    .filter(([code, f]) => f?.code === code && Array.isArray(f.matchs) && f.matchs.length)
    .map(([code]) => code));
  const matchs = {};
  // un match absent d'un fichier bien lu a été déplacé ou retiré : on ne le garde que s'il a déjà un résultat
  for (const [id, m] of Object.entries(avant)) {
    if (!lus.has(competition(id)) || m.res) matchs[id] = m;
  }
  for (const code of lus) {
    for (const f of fichiers[code].matchs) {
      const vu = Object.hasOwn(avant, f.id) ? avant[f.id] : null;
      const ko = f.kickoff || vu?.ko;
      if (!ko) continue;                    // heure inconnue : impossible de verrouiller, donc pas de pronostic
      const avantMatch = f.etat === "a_venir" && Date.parse(ko) > maintenant;
      matchs[f.id] = {
        ko, et: f.etat,
        p: (avantMatch ? f.p : vu?.p ?? f.p) ?? null,
        bot: avantMatch ? score(f.scores?.[0]?.score) : vu?.bot ?? null,
        res: f.etat === "joue" && Array.isArray(f.score) ? [f.score[0], f.score[1]] : vu?.res ?? null,
      };
    }
  }
  for (const [id, m] of Object.entries(matchs)) {
    if (maintenant - Date.parse(m.ko) > GARDE_JOURS * JOUR_MS) delete matchs[id];
  }
  return { maj_ms: maintenant, maj_utc: new Date(maintenant).toISOString(), matchs };
}

/* index des affiches, calculé une fois par programme lu */
const index = new WeakMap();
function parAffiche(programme) {
  let i = index.get(programme);
  if (!i) {
    i = new Map();
    for (const id of Object.keys(programme.matchs)) {
      const cle = affiche(id);
      if (!i.has(cle)) i.set(cle, []);
      i.get(cle).push(id);
    }
    index.set(programme, i);
  }
  return i;
}

/* le match d'un pronostic : même identifiant, sinon la même affiche à une date voisine (match déplacé) ; null s'il est inconnu */
export function trouver(programme, id) {
  if (Object.hasOwn(programme.matchs, id)) return { id, match: programme.matchs[id] };
  const depart = jour(id);
  const max = REPORT_MAX_JOURS[["LDC", "LEC"].includes(competition(id)) ? "coupe" : "ligue"];
  const [choix] = (parAffiche(programme).get(affiche(id)) || [])
    .filter((autre) => {
      const ecart = (jour(autre) - depart) / JOUR_MS;
      return ecart >= -AVANCE_MAX_JOURS && ecart <= max;
    })
    .sort((x, y) => jour(x) - jour(y));
  return choix ? { id: choix, match: programme.matchs[choix] } : null;
}
