/* Page « En direct » du football : les matchs du jour des sept compétitions entre 15 min avant le coup d'envoi et la fin du suivi,
   groupés par compétition, les clubs favoris en tête. Même suivi (direct.js) et même fiche de match (fiche.js) que l'accueil
   et les pages de compétition ; cette page ne fait que présenter la liste. Sans match à suivre : les prochains coups d'envoi. */
"use strict";

const L = { index: null, recherche: null, montres: "", prochains: "" };
const PROCHAINS_MAX = 8;

const aFavori = (m) => (typeof Favoris === "undefined" ? 0 : Favoris.matchFavori(m));
const lienLive = (m) => `${ROOT}foot/${L.index.slugs[m.c]}.html#match=${encodeURIComponent(m.id)}`;
const rangComp = (c) => { const i = Object.keys(L.index.noms).indexOf(c); return i < 0 ? 99 : i; };

/* les matchs à suivre à cet instant, par compétition : une compétition qui compte un match de club favori passe en tête,
   et dans chaque compétition ces matchs-là passent d'abord (l'ordre des coups d'envoi reste le même ensuite) */
function groupes(t) {
  const matchs = (L.index.du_jour || []).filter((m) => aSuivre(m, t)).sort((x, y) => Date.parse(x.kickoff) - Date.parse(y.kickoff));
  const par = new Map();
  for (const m of matchs) par.set(m.c, [...(par.get(m.c) || []), m]);
  for (const liste of par.values()) liste.sort((x, y) => aFavori(y) - aFavori(x));
  const poids = (liste) => Math.max(...liste.map(aFavori));
  return [...par.entries()].sort(([a, x], [b, y]) => poids(y) - poids(x) || rangComp(a) - rangComp(b));
}

function rendreNote(gr, t) {
  const matchs = gr.flatMap(([, l]) => l), n = matchs.length;
  if (!n) { $("#live-note").textContent = "Aucun match en direct pour le moment."; return; }
  const maj = D.relais?.intervalle_min, commence = matchs.some((m) => Date.parse(m.kickoff) <= t);
  $("#live-note").textContent = `${n} match${n > 1 ? "s" : ""} à suivre. Clique un match pour sa fiche : courbe des chances, scores les plus probables.`
    + `${typeof Favoris !== "undefined" && Favoris.liste().length ? " Les matchs de tes clubs favoris passent en tête." : ""}`
    + `${maj ? ` Scores relevés toutes les ${maj === 1 ? "minutes" : `${maj} minutes`} ; la minute avance entre deux relevés.` : ""}`
    + `${commence && !D.relais ? " Les scores en direct ne sont pas disponibles pour l'instant : les chances d'avant-match sont affichées." : ""}`;
}

function rendre() {
  const t = Date.now(), gr = groupes(t);
  const cle = gr.map(([c, l]) => `${c}:${l.map((m) => m.id).join(",")}`).join("|");
  if (cle !== L.montres) {
    L.montres = cle;
    $("#live-liste").innerHTML = gr.map(([c, liste]) => `<h3 class="jour-titre">${esc(L.index.noms[c] || c)}</h3><ul class="matchs">${
      liste.map((m) => ligneMatch(m, L.index.clubs, { lien: lienLive(m) })).join("")}</ul>`).join("");
    if (typeof Favoris !== "undefined") Favoris.marquer($("#live-liste"));
    appliquer();
  }
  rendreNote(gr, t);
  rendreProchains(t);
}

/* prochains coups d'envoi : ceux qui ne sont pas encore dans la liste du dessus (plus de 15 min avant le coup d'envoi) */
function rendreProchains(t) {
  const bloc = $("#prochains");
  if (!L.recherche) { bloc.hidden = true; return; }
  const liste = L.recherche.matchs.filter((m) => m.kickoff && Date.parse(m.kickoff) - SUIVI_AVANT_MS > t && m.etat !== "joue")
    .sort((x, y) => Date.parse(x.kickoff) - Date.parse(y.kickoff)).slice(0, PROCHAINS_MAX);
  const cle = liste.map((m) => m.id).join("|");
  bloc.hidden = !liste.length;
  if (cle === L.prochains) return;
  L.prochains = cle;
  const r = L.recherche;
  $("#prochains-liste").innerHTML = liste.map((m) => ligneMatch(m, r.clubs, {
    lien: `${ROOT}foot/${r.competitions[m.c].slug}.html#match=${encodeURIComponent(m.id)}`, comp: r.competitions[m.c].nom, jourDansHeure: true })).join("");
  if (typeof Favoris !== "undefined") Favoris.marquer($("#prochains-liste"));
}

async function main() {
  const [index, recherche] = await Promise.allSettled([donnees("foot/index"), donnees("foot/recherche")]);
  if (index.status !== "fulfilled") {
    $("#live-note").textContent = "";
    erreur($("#live-liste"), index.reason);
    return;
  }
  L.index = index.value;
  L.recherche = recherche.status === "fulfilled" ? recherche.value : null;   // sans lui : pas de « prochains coups d'envoi », le reste marche
  rendre();
  suivreDirect([{ matchs: L.index.du_jour || [], clubs: L.index.clubs }], { apresTour: rendre });
  setInterval(rendre, TOUR_RELAIS_MS);   // un match entre dans la liste 15 min avant son coup d'envoi, en sort 2 h 30 après (3 h en coupe, ou à la fin du direct)
  document.addEventListener("favoris", () => { L.montres = ""; rendre(); });   // un favori ajouté ou retiré réordonne la liste tout de suite
}
main();
