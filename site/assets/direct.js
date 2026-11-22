/* Direct : scores du relais Cloudflare, rattachés à nos matchs, et chances recalculées dans le navigateur
   (modele-direct.js) à partir des buts attendus publiés. Rien n'est envoyé au relais. */
"use strict";

const RELAIS = "https://extinction-direct.maximebasset1.workers.dev/direct";
const D = { params: null, relais: null, suivis: [], minuteur: null, horloge: null };
const DIRECT_EN_JEU = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
const DIRECT_FINI = new Set(["FT", "AET", "PEN", "FT?"]);
const DIRECT_REPORTE = { PST: "reporté", CANC: "annulé", ABD: "arrêté", AWD: "sur tapis vert", WO: "forfait" };
const SUIVI_AVANT_MS = 15 * 6e4;       // on interroge le relais 15 min avant le coup d'envoi
const SUIVI_APRES_MS = 150 * 6e4;      // et jusqu'à 2 h 30 après
const TOUR_RELAIS_MS = 60e3;
const TOUR_HORLOGE_MS = 20e3;
const ECART_KO_MS = 20 * 6e4;          // un coup d'envoi déplacé de quelques minutes reste le même match

/* noms comparables : sans accents, sans sigles de forme juridique */
const MOTS_VIDES = new Set(["fc", "cf", "afc", "sc", "ssc", "ac", "as", "sk", "fk", "club", "de", "del", "the", "sv", "vfl", "vfb", "tsg", "rc", "ud", "cd", "ca", "1"]);
const jetons = (s) => plier(s).split(" ").filter((w) => w && !MOTS_VIDES.has(w));
function bigrammes(s) {
  const t = jetons(s).join(" "), b = new Set();
  for (let i = 0; i < t.length - 1; i++) b.add(t.slice(i, i + 2));
  return b;
}
function ressemblance(a, b) {
  const x = bigrammes(a), y = bigrammes(b);
  if (!x.size || !y.size) return 0;
  let n = 0;
  for (const g of x) if (y.has(g)) n += 1;
  const dice = (2 * n) / (x.size + y.size);
  // « Rennes » et « Stade Rennais », « Man United » et « Manchester United » : un mot commencé suffit
  const debut = jetons(a).some((w) => w.length >= 4 && jetons(b).some((v) => v.startsWith(w.slice(0, 4))));
  return Math.max(dice, debut ? 0.6 : 0);
}
const nomsClub = (clubs, k) => [clubs[k]?.nom, String(k).split(":").pop()].filter(Boolean);
const proche = (clubs, k, nomApi) => Math.max(...nomsClub(clubs, k).map((n) => ressemblance(n, nomApi)));

/* rattache les matchs du relais aux nôtres : même compétition, coup d'envoi proche, puis les noms départagent */
function rattacher(nos, theirs, clubs) {
  const paires = [];
  for (const m of nos) {
    if (!m.kickoff) continue;
    const ko = Date.parse(m.kickoff);
    for (const f of theirs) {
      if (f.c !== m.c || Math.abs(Date.parse(f.ko) - ko) > ECART_KO_MS) continue;
      const s = proche(clubs, m.home, f.h) + proche(clubs, m.away, f.a);
      if (s >= 0.7) paires.push({ m, f, s });
    }
  }
  paires.sort((x, y) => y.s - x.s);
  const pris = new Set(), lien = new Map();
  for (const { m, f } of paires) {
    if (lien.has(m) || pris.has(f.id)) continue;
    lien.set(m, f); pris.add(f.id);
  }
  return lien;
}

/* minute de jeu à l'instant : celle relevée par le relais, avancée du temps écoulé depuis, sans dépasser la mi-temps */
function minuteMaintenant(f, majUtc) {
  if (!["1H", "2H"].includes(f.st) || f.min == null) return { base: f.min, plus: f.plus };
  const ecoule = majUtc ? Math.max(0, Math.floor((Date.now() - Date.parse(majUtc)) / 6e4)) : 0;
  const fin = f.st === "1H" ? 45 : 90, total = f.min + (f.plus || 0) + ecoule;
  return total > fin ? { base: fin, plus: total - fin } : { base: total, plus: null };
}
const minuteTexte = ({ base, plus }) => (base == null ? "" : `${base}${plus ? `+${plus}` : ""}′`);

/* ce que montre une ligne de match pendant et juste après le direct */
function centreDirect(m, f, clubs) {
  const g = f.g || [], score = `${nombre(g[0])} - ${nombre(g[1])}`;
  if (DIRECT_REPORTE[f.st]) return `<span class="m-etat">${DIRECT_REPORTE[f.st]}</span>`;
  if (DIRECT_FINI.has(f.st)) {
    const fin = f.st === "FT?" ? "terminé, score à confirmer" : f.st === "FT" ? "terminé" : f.st === "AET" ? "après prolongation" : "tirs au but";
    return `<span class="m-score">${score}<small>${fin}</small></span>`;
  }
  const releve = D.relais?.maj_utc ? ` Score relevé à ${heure(D.relais.maj_utc)}.` : "";
  const t = minuteMaintenant(f, D.relais?.maj_utc);
  const etiquette = f.st === "HT" ? "mi-temps" : ["1H", "2H"].includes(f.st) ? minuteTexte(t) : f.st === "P" ? "tirs au but" : f.st === "ET" ? "prolongation" : "interrompu";
  let barreDirect = "";
  if (m.lam && D.params && ["1H", "HT", "2H"].includes(f.st) && g[0] != null) {
    const mi = f.st === "1H" ? 1 : 2, minute = f.st === "HT" ? "45" : `${t.base}${t.plus ? `+${t.plus}` : ""}`;
    const { reste } = tempsRestant(minute, mi, D.params);
    const { p } = chancesEnDirect(m.lam[0], m.lam[1], g[0], g[1], mi, reste, D.params);
    const dom = clubs[m.home]?.nom || m.home, ext = clubs[m.away]?.nom || m.away;
    barreDirect = barre(p, dom, ext);
  }
  return `<span class="m-direct" title="En direct.${releve}"><span class="m-score">${score}<small><i class="pastille" aria-hidden="true"></i>${etiquette}</small></span>${barreDirect}</span>`;
}

/* remplace le centre des lignes suivies, là où elles sont affichées (une ligne refaite par la page est reprise au tour suivant) */
function appliquer() {
  for (const { m, f, clubs } of D.suivis) {
    for (const li of document.querySelectorAll(`li[data-match="${CSS.escape(cleId(m.id))}"]`)) {
      const c = li.querySelector(".m-centre");
      if (c) c.innerHTML = centreDirect(m, f, clubs);
    }
  }
  if (typeof majFiche === "function") majFiche();   // la fiche du match, si elle est ouverte (fiche.js)
}

const aSuivre = (m, t) => m.kickoff && t >= Date.parse(m.kickoff) - SUIVI_AVANT_MS && t <= Date.parse(m.kickoff) + SUIVI_APRES_MS;

async function lireRelais() {
  const r = await fetch(`${RELAIS}?t=${Math.floor(Date.now() / 6e4)}`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`relais du direct : réponse ${r.status}`);
  return r.json();
}

/* suit les matchs donnés ; `listes` : [{ matchs, clubs, comp }] (comp : compétition commune quand les matchs n'ont pas de champ c) ;
   `apresTour` est appelé après chaque lecture du relais, avant la mise à jour des lignes */
async function suivreDirect(listes, { apresTour = null } = {}) {
  const tous = listes.flatMap(({ matchs, clubs, comp }) => matchs.map((m) => ({ m: comp && !m.c ? { ...m, c: comp } : m, orig: m, clubs })));
  const tour = async () => {
    const t = Date.now(), enCours = tous.filter(({ m }) => aSuivre(m, t));
    if (!enCours.length) return;
    try {
      if (!D.params) D.params = await donnees("foot/direct");
      D.relais = await lireRelais();
    } catch (err) {
      // le direct est un plus : en cas d'échec, les lignes gardent le pronostic d'avant-match et l'on réessaie au tour suivant
      console.warn("Direct indisponible", err);
      return;
    }
    D.suivis = [];
    for (const { clubs } of listes) {
      const lot = enCours.filter((x) => x.clubs === clubs);
      const lien = rattacher(lot.map((x) => x.m), D.relais.matchs || [], clubs);
      for (const [m, f] of lien) if (f.st !== "NS") D.suivis.push({ m: { ...m, id: lot.find((x) => x.m === m).orig.id }, f, clubs });
    }
    if (apresTour) apresTour();
    appliquer();
  };
  await tour();
  clearInterval(D.minuteur); clearInterval(D.horloge);
  D.minuteur = setInterval(tour, TOUR_RELAIS_MS);
  D.horloge = setInterval(appliquer, TOUR_HORLOGE_MS);
}

/* section « En direct » de l'accueil : les matchs du jour entre 15 min avant le coup d'envoi et la fin du suivi ;
   la liste n'est refaite que quand un match y entre ou en sort (ou qu'un favori change), pour ne pas fermer ce que l'on regarde ;
   les matchs d'un club favori passent en tête */
function sectionDirect(index, lien) {
  const section = $("#direct"), liste = $("#direct-liste"), note = $("#direct-note");
  if (!section) return () => {};
  let montres = "";
  const rendre = () => {
    const t = Date.now(), matchs = (index.du_jour || []).filter((m) => aSuivre(m, t));
    // les matchs d'un club favori d'abord (le tri est stable : l'ordre du jour reste le même ensuite)
    if (typeof Favoris !== "undefined") matchs.sort((x, y) => Favoris.matchFavori(y) - Favoris.matchFavori(x));
    const cle = matchs.map((m) => m.id).join("|");
    if (cle !== montres) {
      montres = cle;
      liste.innerHTML = matchs.map((m) => ligneMatch(m, index.clubs, { lien: lien(m, m.c), comp: index.noms[m.c] })).join("");
      section.hidden = !matchs.length;
      if (typeof Favoris !== "undefined") Favoris.marquer(liste);
    }
    const n = D.relais?.intervalle_min;
    note.textContent = `Les matchs en cours des six compétitions, avec les chances recalculées à chaque but. Clique un match pour sa fiche : courbe des chances, scores probables.${typeof Favoris !== "undefined" && Favoris.liste().length ? " Les matchs de tes clubs favoris passent en tête." : ""}${n ? ` Scores relevés toutes les ${n === 1 ? "minutes" : `${n} minutes`} ; la minute avance entre deux relevés.` : ""}`;
  };
  rendre();
  setInterval(rendre, TOUR_RELAIS_MS);
  // un favori ajouté ou retiré réordonne la liste tout de suite
  document.addEventListener("favoris", () => { montres = ""; rendre(); appliquer(); });
  return rendre;
}

if (typeof module !== "undefined") module.exports = { rattacher, ressemblance, minuteMaintenant };
