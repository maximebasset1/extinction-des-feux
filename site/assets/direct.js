/* Direct : scores du relais Cloudflare, rattachés à nos matchs, et chances recalculées dans le navigateur
   (modele-direct.js) à partir des buts attendus publiés. Rien n'est envoyé au relais. */
"use strict";

const RELAIS = "https://extinction-direct.maximebasset1.workers.dev/direct";
/* synchro : dernière réponse reçue du relais ; echec : dernier appel raté (remis à null au premier appel réussi) */
const D = { params: null, relais: null, suivis: [], minuteur: null, horloge: null, synchro: null, echec: null, relire: null, ecoute: false };
const DIRECT_EN_JEU = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
const DIRECT_FINI = new Set(["FT", "AET", "PEN", "FT?"]);
const DIRECT_COUPES = new Set(["LDC", "LEC"]);
const DIRECT_REPORTE = { PST: "reporté", CANC: "annulé", ABD: "arrêté", AWD: "sur tapis vert", WO: "forfait" };
const SUIVI_AVANT_MS = 15 * 6e4;         // on interroge le relais 15 min avant le coup d'envoi
const SUIVI_APRES_MS = 150 * 6e4;        // jusqu'à 2 h 30 après en championnat
const SUIVI_APRES_COUPE_MS = 180 * 6e4;  // jusqu'à 3 h en coupe (prolongations et tirs au but)
const SUIVI_MAX_MS = 240 * 6e4;          // filet de sécurité (4 h) si un statut en jeu reste figé
const TOUR_RELAIS_MS = 60e3;
const TOUR_HORLOGE_MS = 20e3;
const ECART_KO_MS = 20 * 6e4;          // un coup d'envoi déplacé de quelques minutes reste le même match
const PERIME_MS = 20 * 6e4;             // au-delà, un relevé du relais n'est plus annoncé comme du direct
const SCORE_ATTENDU_MS = 5 * 6e4;       // 5 min après le coup d'envoi, un score doit avoir été relevé
const DELAI_RELAIS_MS = 10e3;           // un relais qui ne répond pas ne bloque pas le bouton « Actualiser »
const PROCHAINS_MAX = 8;

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
  const perime = relaisPerime(D.relais);   // boucle arrêtée ou quota épuisé : le score reste, sans minute ni « DIRECT »
  const t = minuteMaintenant(f, D.relais?.maj_utc);
  const etiquette = f.st === "HT" ? "mi-temps" : ["1H", "2H"].includes(f.st) ? minuteTexte(t) : f.st === "P" ? "tirs au but" : f.st === "ET" ? "prolongation" : "interrompu";
  let barreDirect = "";
  if (!perime && m.lam && D.params && ["1H", "HT", "2H"].includes(f.st) && g[0] != null) {
    const mi = f.st === "1H" ? 1 : 2, minute = f.st === "HT" ? "45" : `${t.base}${t.plus ? `+${t.plus}` : ""}`;
    const { reste } = tempsRestant(minute, mi, D.params);
    const { p } = chancesEnDirect(m.lam[0], m.lam[1], g[0], g[1], mi, reste, D.params);
    const dom = clubs[m.home]?.nom || m.home, ext = clubs[m.away]?.nom || m.away;
    barreDirect = barre(p, dom, ext);
  }
  const releve = D.relais?.maj_utc ? heure(D.relais.maj_utc) : "";
  const badge = perime ? `<span class="badge-direct perime">relevé à ${esc(releve)}</span>`
    : `<span class="badge-direct"><i class="pastille" aria-hidden="true"></i><b>DIRECT</b> ${esc(etiquette)}</span>`;
  const info = perime ? `Dernier score relevé à ${releve}.` : `En direct.${releve ? ` Score relevé à ${releve}.` : ""}`;
  return `<span class="m-direct" title="${esc(info)}">${badge}<span class="m-score">${score}</span>${barreDirect}</span>`;
}

/* ---------- ce que le relais dit à cet instant ---------- */

/* un relevé périmé : plus de 20 min, ou plus de deux intervalles et 5 min quand le relais espace ses appels (quota) */
function relaisPerime(relais, maintenant = Date.now()) {
  if (!relais?.maj_utc) return false;
  const limite = Math.max(PERIME_MS, (2 * (relais.intervalle_min || 0) + 5) * 6e4);
  return maintenant - Date.parse(relais.maj_utc) > limite;
}
/* en cours d'après le relais, et encore plausible : 4 h au plus après le coup d'envoi ; sur un relevé périmé (boucle arrêtée
   en plein match, statut resté figé), pas au-delà de la durée d'un match */
function enJeuRecent(f, relais, t) {
  if (!DIRECT_EN_JEU.has(f.st)) return false;
  const limite = !relaisPerime(relais, t) ? SUIVI_MAX_MS : DIRECT_COUPES.has(f.c) ? SUIVI_APRES_COUPE_MS : SUIVI_APRES_MS;
  return t - Date.parse(f.ko) <= limite;
}

/* un match que le relais connaît sans qu'on ait pu le rattacher : montré avec les noms d'API-Football, sans pronostic */
function entreeRelais(f) {
  const home = `relais:${f.h}`, away = `relais:${f.a}`;
  const club = (n) => ({ nom: n, sigle: String(n).replace(/[^\p{L}\p{N}]/gu, "").slice(0, 3).toUpperCase() });
  return { m: { id: `relais|${f.id}`, c: f.c, kickoff: f.ko, home, away }, f, connu: false,
    clubs: { [home]: club(f.h), [away]: club(f.a) } };
}

/* les matchs à venir (recherche.json) et ceux du jour (index.json, qui portent les buts attendus), sans doublon */
function matchsSuivables(index, recherche) {
  const vus = new Set();
  const matchs = [...(index?.du_jour || []), ...(recherche?.matchs || [])].filter((m) => !vus.has(m.id) && vus.add(m.id));
  return { matchs, clubs: { ...(recherche?.clubs || {}), ...(index?.clubs || {}) } };
}

/* tous les matchs en cours d'après le relais : ceux rattachés aux nôtres (`suivis`), puis ceux qu'il est seul à connaître */
function enDirectMaintenant(relais, suivis, { comp = null, maintenant = Date.now() } = {}) {
  const rattaches = suivis.filter((x) => enJeuRecent(x.f, relais, maintenant)).map((x) => ({ ...x, connu: x.connu !== false }));
  const pris = new Set(suivis.map((x) => x.f.id));
  const seuls = (relais?.matchs || []).filter((f) => !pris.has(f.id) && enJeuRecent(f, relais, maintenant)).map(entreeRelais);
  return [...rattaches, ...seuls].filter((x) => !comp || x.m.c === comp).sort((x, y) => Date.parse(x.f.ko) - Date.parse(y.f.ko));
}

/* le reste de la journée (date de l'appareil), hors matchs en cours, et les coups d'envoi des jours suivants.
   `etat` : a_venir, attente (coup d'envoi passé, score pas encore relevé), reporte, fini, sans_score */
function repartirDuJour(matchs, clubs, relais, maintenant = Date.now()) {
  const jourDe = (t) => new Date(t).toLocaleDateString("sv-SE");
  const ceJour = jourDe(maintenant);
  const dates = matchs.filter((m) => m.kickoff);
  const lien = rattacher(dates, relais?.matchs || [], clubs);
  const pris = new Set([...lien.values()].map((f) => f.id));
  const nos = dates.map((m) => ({ m, f: lien.get(m) || null, clubs, connu: true }));
  const seuls = (relais?.matchs || []).filter((f) => !pris.has(f.id)).map(entreeRelais);
  const aVenir = [], termines = [], suivants = [];
  for (const x of [...nos, ...seuls].sort((a, b) => Date.parse(a.m.kickoff) - Date.parse(b.m.kickoff))) {
    const { m, f } = x, ko = Date.parse(m.kickoff);
    if (jourDe(ko) !== ceJour) {
      if (x.connu && ko > maintenant && m.etat !== "joue") suivants.push({ ...x, etat: "a_venir" });
      continue;
    }
    if (f && enJeuRecent(f, relais, maintenant)) continue;   // montré en tête, avec les matchs en cours
    let etat;
    if ((f && DIRECT_REPORTE[f.st]) || m.etat === "reporte") etat = "reporte";
    else if ((f && DIRECT_FINI.has(f.st)) || m.etat === "joue") etat = "fini";
    else if (ko > maintenant) etat = "a_venir";
    else etat = maintenant - ko < SUIVI_MAX_MS ? "attente" : "sans_score";
    (etat === "fini" || etat === "sans_score" ? termines : aVenir).push({ ...x, etat });
  }
  return { aVenir, termines, suivants: suivants.slice(0, PROCHAINS_MAX) };
}

/* heure seule le jour même, jour et heure sinon */
const momentTexte = (iso, maintenant = Date.now()) => (new Date(iso).toDateString() === new Date(maintenant).toDateString() ? heure(iso) : quand(iso));

/* ce qui empêche le direct de marcher, à dire en clair : relais injoignable, muet pendant un match, ou en erreur.
   Un vieux relevé n'est anormal que si un match devrait être suivi : hors match, le relais n'appelle pas l'API. */
function alerteDirect(relais, matchs, { echec = null, maintenant = Date.now() } = {}) {
  if (echec) return { type: "panne", texte: "Le relais du direct ne répond pas : les scores ne peuvent pas être actualisés pour le moment. Nouvel essai dans une minute." };
  if (!relais) return null;
  const aSuivreMaintenant = (ko) => { const age = maintenant - Date.parse(ko); return age > SCORE_ATTENDU_MS && age < SUIVI_APRES_MS; };
  const duRelais = relais.matchs || [];
  const couvert = (m) => duRelais.some((f) => f.c === m.c && Math.abs(Date.parse(f.ko) - Date.parse(m.kickoff)) <= ECART_KO_MS);
  const attendu = duRelais.some((f) => !DIRECT_FINI.has(f.st) && !DIRECT_REPORTE[f.st] && aSuivreMaintenant(f.ko))
    || matchs.some((m) => m.kickoff && m.etat !== "joue" && m.etat !== "reporte" && aSuivreMaintenant(m.kickoff) && !couvert(m));
  if (attendu && relaisPerime(relais, maintenant)) {
    return { type: "muet", texte: `Des matchs ont commencé, mais le relais n'a relevé aucun score depuis ${momentTexte(relais.maj_utc, maintenant)} : le direct est en retard ou arrêté.` };
  }
  // le message technique du relais reste dans /direct : il n'aide pas le lecteur
  if (relais.erreur) return { type: "erreur", texte: `Le relais a signalé un problème${relais.erreur.utc ? ` à ${momentTexte(relais.erreur.utc, maintenant)}` : ""} : les scores peuvent être en retard.` };
  return null;
}

/* bloc « En direct » en tête de liste (page Football, pages des compétitions). La liste n'est refaite que quand un match y
   entre, en sort ou change de place (favoris), pour ne pas fermer ce que l'on regarde ; appliquer() tient les centres à jour. */
function rendreBlocDirect(section, entrees, ligne) {
  const aFavori = (x) => (typeof Favoris === "undefined" ? 0 : Favoris.matchFavori(x.m));
  const triees = [...entrees].sort((x, y) => aFavori(y) - aFavori(x));
  const cle = triees.map((x) => cleId(x.m.id)).join("|");
  if (section.dataset.cle === cle) return;
  section.dataset.cle = cle;
  section.hidden = !triees.length;
  section.querySelector("[data-compte]").textContent = triees.length > 1 ? `${triees.length} matchs` : "1 match";
  section.querySelector("ul").innerHTML = triees.map(ligne).join("");
  if (typeof Favoris !== "undefined") Favoris.marquer(section);
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

function suiviEnJeu(m) {
  const cle = cleId(m.id);
  return D.suivis.some((x) => cleId(x.m.id) === cle && DIRECT_EN_JEU.has(x.f?.st));
}
function aSuivre(m, t, comp = m.c) {
  if (!m.kickoff) return false;
  const ko = Date.parse(m.kickoff);
  if (t < ko - SUIVI_AVANT_MS || t > ko + SUIVI_MAX_MS) return false;
  const apres = DIRECT_COUPES.has(comp) ? SUIVI_APRES_COUPE_MS : SUIVI_APRES_MS;
  return t <= ko + apres || suiviEnJeu(m);
}

/* une page peut demander le relais depuis plusieurs endroits (suivi des matchs, compteur de l'onglet « En direct ») :
   une même lecture sert pendant 15 secondes (le relais lui-même garde sa réponse 20 secondes) */
let relaisLu = { t: 0, p: null };
function lireRelais({ force = false } = {}) {
  if (!force && relaisLu.p && Date.now() - relaisLu.t < 15e3) return relaisLu.p;
  const p = (async () => {
    const signal = typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(DELAI_RELAIS_MS) : undefined;
    const r = await fetch(`${RELAIS}?t=${force ? Date.now() : Math.floor(Date.now() / 6e4)}`, { cache: "no-cache", signal });
    if (!r.ok) throw new Error(`relais du direct : réponse ${r.status}`);
    const corps = await r.json();
    if (!Array.isArray(corps?.matchs)) throw new Error("relais du direct : réponse illisible");
    D.synchro = Date.now();
    return corps;
  })();
  relaisLu = { t: Date.now(), p };
  p.catch(() => { if (relaisLu.p === p) relaisLu = { t: 0, p: null }; });   // un échec n'est pas gardé : le tour suivant réessaie
  return p;
}

/* suit les matchs donnés ; `listes` : [{ matchs, clubs, comp }] (comp : compétition commune quand les matchs n'ont pas de champ c) ;
   `apresTour` est appelé après chaque lecture du relais, réussie ou non, avant la mise à jour des lignes ;
   `inclureDuJourSansScore` : rattache aussi les matchs du jour déjà finis dans le relais mais sans score publié dans le JSON statique ;
   `toujours` : lit le relais même sans match à suivre (heure de synchronisation, matchs absents de nos données) ;
   `inconnus` ({ comp }) : suit aussi les matchs en cours que le relais est seul à connaître.
   D.relire({ force: true }) relit tout de suite (bouton « Actualiser »). Un onglet caché ne relit pas ; il relit dès qu'il
   redevient visible. */
async function suivreDirect(listes, { apresTour = null, inclureDuJourSansScore = false, toujours = false, inconnus = null } = {}) {
  const tous = listes.flatMap(({ matchs, clubs, comp }) => matchs.map((m) => ({ m: comp && !m.c ? { ...m, c: comp } : m, orig: m, clubs })));
  const aRattacher = (m, t) => {
    if (aSuivre(m, t)) return true;
    if (!inclureDuJourSansScore || !m.kickoff || (m.etat === "joue" && m.score)) return false;
    const ko = Date.parse(m.kickoff);
    return t >= ko - SUIVI_AVANT_MS && t <= ko + 12 * 36e5;
  };
  const tour = async ({ force = false } = {}) => {
    const t = Date.now(), enCours = tous.filter(({ m }) => aRattacher(m, t));
    if (!enCours.length && !toujours) return;
    if (!D.params) {
      // sans les réglages du modèle, le score et la minute s'affichent quand même ; seules les chances en direct manquent
      try { D.params = await donnees("foot/direct"); } catch (err) { console.warn("Réglages du direct indisponibles", err); }
    }
    try {
      D.relais = await lireRelais({ force });
      D.echec = null;
    } catch (err) {
      // le direct est un plus : en cas d'échec, les lignes gardent leur dernier état et l'on réessaie au tour suivant
      D.echec = Date.now();
      console.warn("Direct indisponible", err);
      if (apresTour) apresTour();
      return;
    }
    D.suivis = [];
    for (const { clubs } of listes) {
      const lot = enCours.filter((x) => x.clubs === clubs);
      const lien = rattacher(lot.map((x) => x.m), D.relais.matchs || [], clubs);
      for (const [m, f] of lien) if (f.st !== "NS") D.suivis.push({ m: { ...m, id: lot.find((x) => x.m === m).orig.id }, f, clubs });
    }
    if (inconnus) D.suivis.push(...enDirectMaintenant(D.relais, D.suivis, inconnus).filter((x) => !x.connu));
    if (apresTour) apresTour();
    appliquer();
  };
  D.relire = tour;
  if (!D.ecoute) {
    D.ecoute = true;
    document.addEventListener("visibilitychange", () => { if (!document.hidden) D.relire(); });
  }
  await tour();
  clearInterval(D.minuteur); clearInterval(D.horloge);
  D.minuteur = setInterval(() => { if (!document.hidden) tour(); }, TOUR_RELAIS_MS);
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
    note.textContent = `Les matchs en cours des sept compétitions, avec les chances recalculées à chaque but. Clique un match pour sa fiche : courbe des chances, scores probables.${typeof Favoris !== "undefined" && Favoris.liste().length ? " Les matchs de tes clubs favoris passent en tête." : ""}${n ? ` Scores relevés toutes les ${n === 1 ? "minutes" : `${n} minutes`} ; la minute avance entre deux relevés.` : ""}`;
  };
  rendre();
  setInterval(rendre, TOUR_RELAIS_MS);
  // un favori ajouté ou retiré réordonne la liste tout de suite
  document.addEventListener("favoris", () => { montres = ""; rendre(); appliquer(); });
  return rendre;
}

if (typeof module !== "undefined") module.exports = { rattacher, ressemblance, minuteMaintenant };
