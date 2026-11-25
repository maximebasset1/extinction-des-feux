/* Page Football : recherche d'un club ou d'un match dans les sept compétitions, clubs favoris en tête, prochains matchs
   filtrés par une seule ligne de boutons (posée dans la page par build_site.py), compétitions, fiabilité. */
"use strict";

const PAGE = 30;
const MATCHS_FAVORIS = 6;        // dans la section du haut ; les suivants par le filtre « Mes favoris »
const F = { r: null, i: null, idx: {}, comp: "", q: "", club: null, montres: PAGE };
const lienMatch = (m) => `${ROOT}foot/${F.r.competitions[m.c].slug}.html#match=${encodeURIComponent(m.id)}`;

const etoile = (k, n, texte = false) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, n, { texte }));
const mesClubs = () => (typeof Favoris === "undefined" ? [] : Favoris.liste());
/* un club suivi absent des données de la saison reste listé, pour pouvoir le retirer (un compte en garde vingt au plus) */
const clubSuivi = (k) => F.r.clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };
const ligne = (m) => ligneMatch(m, F.r.clubs, { lien: lienMatch(m), comp: F.r.competitions[m.c].nom });

function aVenir() {
  const now = new Date(), today = aujourdhui();
  return F.r.matchs.filter((m) => (m.kickoff ? new Date(m.kickoff) > now : (m.jour || "9999") >= today));
}
const matchsDe = (clubs) => { const s = new Set(clubs); return (m) => s.has(m.home) || s.has(m.away); };
function filtre() {
  const req = F.club ? { un: new Set([F.club]) } : lireRequete(F.idx, F.q);
  const garde = F.comp === "FAV" ? matchsDe(mesClubs()) : (m) => !F.comp || m.c === F.comp;
  return aVenir().filter((m) => garde(m) && correspond(req, m));
}
function rendre() {
  const liste = filtre(), montres = liste.slice(0, F.montres), cherche = F.club || F.q.trim();
  $("#note").textContent = !liste.length
    ? (cherche ? "Aucun match à venir pour cette recherche. Vérifie l'orthographe, ou essaie un seul club." : "Aucun match à venir.")
    : cherche ? `${liste.length} match${liste.length > 1 ? "s" : ""} à venir. Clique sur un match pour le détail.`
      : "Heures à l'heure de ton appareil. Clique sur un match pour le détail.";
  // la page d'une compétition (classement, calendrier, face-à-face) reste à un clic quand son filtre est choisi
  const comp = F.r.competitions[F.comp], lien = $("#lien-comp");
  lien.hidden = !comp;
  if (comp) lien.innerHTML = `<a href="${esc(`${ROOT}foot/${comp.slug}.html`)}">${esc(comp.nom)} : classement, calendrier et face-à-face</a>`;
  const cf = $("#club-favori");
  cf.hidden = !F.club;
  if (F.club) cf.innerHTML = etoile(F.club, F.r.clubs[F.club].nom, true);
  $("#results").innerHTML = parJour(montres, ligne);
  $("#more").hidden = liste.length <= F.montres;
}
/* le bouton « Mes favoris » apparaît avec le premier club suivi ; une compétition sans match à venir est grisée */
function rendreFiltres() {
  const present = new Set(F.r.matchs.map((m) => m.c));
  if (F.comp === "FAV" && !mesClubs().length) F.comp = "";
  for (const b of document.querySelectorAll("#chips button")) {
    const c = b.dataset.comp;
    if (c === "FAV") b.hidden = !mesClubs().length;
    else b.disabled = Boolean(c) && !present.has(c);
    b.setAttribute("aria-pressed", String(c === F.comp));
  }
}
function choisirFiltre(comp) {
  F.comp = comp; F.montres = PAGE;
  rendreFiltres(); rendreFavoris(); rendre();
}
/* section du haut : les clubs suivis, de quoi les retirer ou chercher leurs matchs, et leurs prochains matchs.
   Demandée par l'adresse (menu du compte, « Mes favoris ») elle s'affiche même vide. */
function rendreFavoris() {
  if (typeof Favoris === "undefined") return;
  const clubs = mesClubs();
  $("#favoris").hidden = !clubs.length && location.hash !== "#favoris";
  $("#favoris-liste").innerHTML = clubs.map((k) => `<li><button type="button" class="puce" data-club="${esc(k)}">${ecusson(clubSuivi(k))}${esc(clubSuivi(k).nom)}</button>${etoile(k, clubSuivi(k).nom)}</li>`).join("");
  // avec le filtre « Mes favoris », la liste du dessous montre déjà ces matchs
  const matchs = F.comp === "FAV" ? [] : aVenir().filter(matchsDe(clubs));
  const connecte = typeof Compte !== "undefined" && Compte.lire();
  const garde = connecte ? "Enregistrés sur ton compte." : "Gardés dans ce navigateur. Avec un compte, tu les retrouves sur tous tes appareils.";
  $("#favoris-note").textContent = !clubs.length ? "Aucun club suivi. L'étoile à côté d'une équipe l'ajoute ici."
    : F.comp !== "FAV" && !matchs.length ? `Aucun match à venir pour ces clubs. ${garde}` : garde;
  $("#favoris-matchs").innerHTML = parJour(matchs.slice(0, MATCHS_FAVORIS), ligne);
  $("#favoris-tous").hidden = matchs.length <= MATCHS_FAVORIS;
}
function surFavoris() {
  const actif = document.activeElement?.closest?.("#favoris button[data-favori]")?.dataset.favori;
  const filtreFavoris = F.comp === "FAV";
  rendreFiltres(); rendreFavoris();
  // la liste principale n'est refaite que si son contenu change : les étoiles sont mises à jour par favoris.js
  if (filtreFavoris) rendre();
  if (actif) $(`#favoris button[data-favori="${CSS.escape(actif)}"]`)?.focus();
}
function montrerSectionDemandee() {
  if (location.hash !== "#favoris") return;
  rendreFavoris();
  $("#favoris").scrollIntoView({ block: "start" });
}
function chercherClub(k) {
  if (!F.r.clubs[k]) return;
  const q = $("#q");
  q.value = F.r.clubs[k].nom; F.q = q.value; F.club = k; F.montres = PAGE;
  $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); rendre();
}
function suggerer() {
  const ws = mots(F.q), boite = $("#suggest");
  const hits = ws.length && !F.club ? clubsPour(F.idx, ws).slice(0, 8) : [];
  boite.innerHTML = hits.map((k, i) => `<li role="option" id="sg-${i}" data-club="${esc(k)}" tabindex="-1">${ecusson(F.r.clubs[k])}<span>${esc(F.r.clubs[k].nom)}</span>
    <small>${esc(F.r.clubs[k].competitions.map((c) => F.r.competitions[c].nom).join(", "))}</small></li>`).join("");
  boite.hidden = !hits.length;
  $("#q").setAttribute("aria-expanded", String(!boite.hidden));
}
function rendreFiabilite() {
  const t = F.i.fiabilite;
  $("#f-note").textContent = `Chaque semaine depuis ${F.i.saisons_test[0]}, le modèle est rejoué avec les seuls matchs joués avant. Score RPS : plus il est bas, plus les probabilités étaient justes. « Habitudes » : donner à chaque match les pourcentages habituels domicile, nul, extérieur.`;
  $("#f-table").innerHTML = `<thead><tr><th>Compétition</th><th class="num">Matchs</th><th class="num">Nos statistiques</th><th class="num">Avec les cotes</th><th class="num">Cotes seules</th><th class="num">Habitudes</th><th class="num">Le favori gagne</th></tr></thead><tbody>${t.map((r) => `<tr>
    <td>${esc(r.nom)}</td><td class="num">${nombre(r.matchs).toLocaleString("fr-FR")}</td><td class="num">${virgule(r.modele.rps, 3)}</td>
    <td class="num">${r.avec_cotes ? virgule(r.avec_cotes.rps, 3) : "–"}</td><td class="num">${r.marche ? virgule(r.marche.rps, 3) : "–"}</td>
    <td class="num">${virgule(r.habitudes.rps, 3)}</td><td class="num">${pct((r.avec_cotes || r.modele).bons_favoris)}</td></tr>`).join("")}</tbody>
    <caption>En coupe d'Europe, pas d'historique de cotes gratuit : seules nos statistiques sont jugées.</caption>`;
}
async function main() {
  // ancien lien de la page Recherche (recherche.html#match=...) : on suit jusqu'à la page de la compétition
  try {
    [F.r, F.i] = await Promise.all([donnees("foot/recherche"), donnees("foot/index")]);
  } catch (err) {
    erreur($("#results"), err);
    return;
  }
  if (location.hash.startsWith("#match=")) {
    try {
      let id = decodeURIComponent(location.hash.slice(7)), comp = id.split("|")[0];
      if (!F.r.competitions[comp]) {
        // ancien lien de la page Recherche, sans la compétition : on la retrouve
        const m = F.r.matchs.find((x) => x.id.endsWith(`|${id}`));
        const [h, a] = id.split("|");
        const communes = m ? [m.c] : ((F.r.clubs[h] || {}).competitions || []).filter((c) => ((F.r.clubs[a] || {}).competitions || []).includes(c));
        comp = communes[0];
        if (comp) id = `${comp}|${id}`;
      }
      if (F.r.competitions[comp]) { location.replace(`${ROOT}foot/${F.r.competitions[comp].slug}.html#match=${encodeURIComponent(id)}`); return; }
    } catch { /* lien abîmé : on reste sur la page */ }
  }
  F.idx = indexClubs(F.r.clubs);
  listeCompetitions($("#competitions"), F.i.competitions);
  rendreFiltres(); rendre(); rendreFiabilite(); rendreFavoris();
  montrerSectionDemandee();
  window.addEventListener("hashchange", montrerSectionDemandee);
  document.addEventListener("favoris", surFavoris);
  document.addEventListener("compte", rendreFavoris);
  $("#favoris-liste").addEventListener("click", (e) => { const b = e.target.closest("button.puce"); if (b) { chercherClub(b.dataset.club); $("#q").focus(); } });
  $("#favoris-tous").addEventListener("click", () => { choisirFiltre("FAV"); $("#h-matchs").scrollIntoView({ block: "start" }); });
  const q = $("#q");
  q.addEventListener("input", () => { F.q = q.value; F.club = null; F.montres = PAGE; rendre(); suggerer(); });
  q.addEventListener("keydown", (e) => {
    const items = [...document.querySelectorAll("#suggest li")];
    if (e.key === "ArrowDown" && items.length && !$("#suggest").hidden) { e.preventDefault(); items[0].focus(); }
    if (e.key === "Escape") { $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); }
  });
  $("#suggest").addEventListener("keydown", (e) => {
    const items = [...document.querySelectorAll("#suggest li")], i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[Math.min(i + 1, items.length - 1)].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); if (i <= 0) q.focus(); else items[i - 1].focus(); }
    if (e.key === "Enter") document.activeElement.click();
    if (e.key === "Escape") { $("#suggest").hidden = true; q.focus(); }
  });
  $("#suggest").addEventListener("click", (e) => {
    const li = e.target.closest("li[data-club]");
    if (!li) return;
    q.value = F.r.clubs[li.dataset.club].nom; F.q = q.value; F.club = li.dataset.club; F.montres = PAGE;
    $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); rendre(); q.focus();
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".recherche")) { $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); } });
  $("#chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-comp]");
    if (b && !b.disabled) choisirFiltre(b.dataset.comp);
  });
  $("#more").addEventListener("click", () => { F.montres += PAGE; rendre(); });
}
main();
