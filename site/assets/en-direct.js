/* Page « En direct » du football. En tête, les matchs en cours d'après le relais, groupés par compétition, clubs favoris
   d'abord ; puis les matchs du jour encore à venir avec leur heure, les matchs terminés et, quand la journée n'en a plus, les
   prochains coups d'envoi : même sans match, la page montre que le direct répond. La synchronisation est datée et peut être
   relancée à la main. Même suivi (direct.js) et même fiche de match (fiche.js) que les autres pages du football. */
"use strict";

const L = { index: null, suivables: null, cles: {}, actualisation: false };

const aFavori = (m) => (typeof Favoris === "undefined" ? 0 : Favoris.matchFavori(m));
const lienLive = (m) => `${ROOT}foot/${L.index.slugs[m.c]}.html#match=${encodeURIComponent(m.id)}`;
const nomComp = (c) => L.index.noms[c] || c;
const rangComp = (c) => { const i = Object.keys(L.index.noms).indexOf(c); return i < 0 ? 99 : i; };

/* une compétition qui compte un match de club favori passe en tête, et ces matchs-là passent d'abord dans leur groupe
   (l'ordre des coups d'envoi reste le même ensuite) */
function groupes(entrees) {
  const par = new Map();
  for (const x of entrees) par.set(x.m.c, [...(par.get(x.m.c) || []), x]);
  for (const liste of par.values()) liste.sort((x, y) => aFavori(y.m) - aFavori(x.m));
  const poids = (liste) => Math.max(...liste.map((x) => aFavori(x.m)));
  return [...par.entries()].sort(([a, x], [b, y]) => poids(y) - poids(x) || rangComp(a) - rangComp(b));
}

const ligneEnCours = (x) => ligneMatch(x.m, x.clubs, { lien: x.connu ? lienLive(x.m) : null, etoiles: x.connu,
  centre: centreDirect(x.m, x.f, x.clubs) });

const ETATS = { attente: "coup d'envoi passé, score attendu", sans_score: "score pas encore relevé", reporte: "reporté" };
function ligneProgramme(x, { jour = false } = {}) {
  let centre = null;   // par défaut : les chances d'avant-match, ou le score publié
  if (x.etat === "fini" && x.f) centre = centreDirect(x.m, x.f, x.clubs);
  else if (x.etat === "reporte" && x.f && DIRECT_REPORTE[x.f.st]) centre = `<span class="m-etat">${DIRECT_REPORTE[x.f.st]}</span>`;
  else if (ETATS[x.etat]) centre = `<span class="m-etat">${ETATS[x.etat]}</span>`;
  else if (x.etat === "a_venir" && !x.m.p) centre = `<span class="m-etat">à venir</span>`;
  return ligneMatch(x.m, x.clubs, { lien: x.connu ? lienLive(x.m) : null, etoiles: x.connu, comp: nomComp(x.m.c), jourDansHeure: jour, centre });
}

/* une liste n'est refaite que quand son contenu change, pour ne pas fermer ce que l'on regarde */
function remplir(cle, el, entrees, rendu) {
  const contenu = entrees.map((x) => `${cleId(x.m.id)}:${x.etat || ""}:${x.f?.st || ""}:${(x.f?.g || []).join("-")}`).join("|");
  if (L.cles[cle] === contenu) return;
  L.cles[cle] = contenu;
  el.innerHTML = entrees.map(rendu).join("");
  if (typeof Favoris !== "undefined") Favoris.marquer(el);
}
function rendreEnCours(entrees) {
  const par = groupes(entrees);
  const contenu = par.map(([c, l]) => `${c}:${l.map((x) => cleId(x.m.id)).join(",")}`).join("|");
  if (L.cles.live === contenu) return;
  L.cles.live = contenu;
  $("#live-liste").innerHTML = par.map(([c, liste]) => `<h3 class="jour-titre">${esc(nomComp(c))}</h3><ul class="matchs">${
    liste.map(ligneEnCours).join("")}</ul>`).join("");
  if (typeof Favoris !== "undefined") Favoris.marquer($("#live-liste"));
}

function rendreSynchro(maintenant) {
  $("#live-synchro").textContent = D.synchro ? `Dernière synchronisation : ${new Date(D.synchro).toLocaleTimeString("fr-FR")}`
    : D.echec ? "Dernière synchronisation : aucune pour l'instant" : "Dernière synchronisation : en cours…";
  const r = D.relais;
  $("#live-releve").textContent = r?.maj_utc ? `Dernier relevé du relais : ${momentTexte(r.maj_utc, maintenant)}.${
    r.intervalle_min ? ` Pendant les matchs, un relevé toutes les ${r.intervalle_min === 1 ? "minutes" : `${r.intervalle_min} minutes`} ; la minute avance entre deux.` : ""}` : "";
}

function rendreNote(enCours, jour, alerte, maintenant) {
  let texte;
  if (enCours.length) {
    const dernier = relaisPerime(D.relais, maintenant) ? " au dernier relevé" : "";
    texte = `${accord(enCours.length, "match", "matchs")} en cours${dernier}. Clique un match pour sa fiche : courbe des chances, scores les plus probables.`;
  } else if (!D.relais && !D.echec) texte = "Vérification du direct…";
  else if (alerte && alerte.type !== "erreur") texte = "Aucun score en direct disponible pour le moment.";   // l'alerte dit pourquoi
  else if (jour.aVenir.some((x) => x.etat === "attente")) texte = "Aucun score en direct pour le moment : coup d'envoi passé, premier relevé attendu.";
  else {
    const prochain = jour.aVenir.find((x) => x.etat === "a_venir");
    texte = `Aucun match en cours actuellement.${prochain ? ` Prochain coup d'envoi à ${heure(prochain.m.kickoff)}, ${relatif(prochain.m.kickoff)}.` : ""}`;
  }
  const el = $("#live-note");
  if (el.textContent !== texte) el.textContent = texte;
}

function rendre() {
  const maintenant = Date.now();
  const enCours = enDirectMaintenant(D.relais, D.suivis, { maintenant });
  const jour = repartirDuJour(L.suivables.matchs, L.suivables.clubs, D.relais, maintenant);
  const alerte = alerteDirect(D.relais, L.suivables.matchs, { echec: D.echec, maintenant });
  rendreSynchro(maintenant);
  const boite = $("#live-alerte");
  boite.hidden = !alerte;
  if (alerte && boite.textContent !== alerte.texte) boite.textContent = alerte.texte;
  rendreEnCours(enCours);
  rendreNote(enCours, jour, alerte, maintenant);

  $("#du-jour").hidden = false;
  $("#jour-note").textContent = jour.aVenir.length ? "Heures à l'heure de ton appareil." : "Plus aucun match prévu aujourd'hui.";
  remplir("jour", $("#jour-liste"), jour.aVenir, (x) => ligneProgramme(x));
  $("#termines").hidden = !jour.termines.length;
  remplir("termines", $("#termines-liste"), jour.termines, (x) => ligneProgramme(x));
  const suivants = jour.aVenir.length ? [] : jour.suivants;
  $("#prochains").hidden = !suivants.length;
  remplir("prochains", $("#prochains-liste"), suivants, (x) => ligneProgramme(x, { jour: true }));
  appliquer();
}

/* « Actualiser » : lit le relais tout de suite ; le bouton reste atteignable au clavier pendant la lecture */
async function actualiser(bouton) {
  if (L.actualisation || !D.relire) return;
  L.actualisation = true;
  bouton.setAttribute("aria-disabled", "true");
  bouton.textContent = "Actualisation…";
  try {
    await D.relire({ force: true });
  } finally {
    L.actualisation = false;
    bouton.removeAttribute("aria-disabled");
    bouton.textContent = "Actualiser";
  }
}

async function main() {
  const [index, recherche] = await Promise.allSettled([donnees("foot/index"), donnees("foot/recherche")]);
  if (index.status !== "fulfilled") {
    $("#live-note").textContent = "";
    erreur($("#live-liste"), index.reason);
    return;
  }
  L.index = index.value;
  // sans la liste de recherche : les matchs du jour de l'accueil suffisent au direct
  L.suivables = matchsSuivables(L.index, recherche.status === "fulfilled" ? recherche.value : null);
  rendre();
  suivreDirect([{ matchs: L.suivables.matchs, clubs: L.suivables.clubs }],
    { apresTour: rendre, toujours: true, inconnus: {}, inclureDuJourSansScore: true });
  $("#live-actualiser").addEventListener("click", (e) => actualiser(e.currentTarget));
  setInterval(rendre, TOUR_RELAIS_MS);   // un coup d'envoi passe, la journée se vide : l'heure suffit à changer les listes
  document.addEventListener("favoris", () => { L.cles = {}; rendre(); });   // un favori ajouté ou retiré réordonne tout de suite
}
main();
