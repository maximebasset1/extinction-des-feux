/* Page Football. La barre en tête (« À la une », « Mes favoris », les compétitions) est posée par build_site.py ; les deux
   premières entrées sont des vues de cette page (adresse nue, ou #favoris). Les matchs en cours passent en tête (direct.js),
   puis les prochaines affiches ; « Mes favoris » ne montre que les clubs suivis. */
"use strict";

const PAGE = 30;
const F = { r: null, i: null, idx: {}, vue: "une", q: "", club: null, montres: PAGE, montresFav: PAGE, suivables: null, enCours: new Set() };
const nomComp = (c) => F.r.competitions[c]?.nom || F.i.noms[c] || c;
const lienMatch = (m) => `${ROOT}foot/${F.r.competitions[m.c]?.slug || F.i.slugs[m.c]}.html#match=${encodeURIComponent(m.id)}`;

const etoile = (k, n, texte = false) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, n, { texte }));
const mesClubs = () => (typeof Favoris === "undefined" ? [] : Favoris.liste());
/* un club suivi absent des données de la saison reste listé, pour pouvoir le retirer (un compte en garde vingt au plus) */
const clubSuivi = (k) => F.r.clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };
const ligne = (m) => ligneMatch(m, F.r.clubs, { lien: lienMatch(m), comp: nomComp(m.c) });
const matchsDe = (clubs) => { const s = new Set(clubs); return (m) => s.has(m.home) || s.has(m.away); };

/* les matchs en cours sont en tête de page : les listes du dessous ne les répètent pas */
function aVenir() {
  const now = new Date(), today = aujourdhui();
  return F.r.matchs.filter((m) => !F.enCours.has(m.id) && (m.kickoff ? new Date(m.kickoff) > now : (m.jour || "9999") >= today));
}
function rendreAffiches() {
  const now = Date.now();
  const liste = F.i.a_la_une.filter((m) => !F.enCours.has(m.id) && (!m.kickoff || Date.parse(m.kickoff) > now));
  $("#affiches-liste").innerHTML = liste.length
    ? liste.map((m) => ligneMatch(m, F.i.clubs, { lien: lienMatch(m), comp: nomComp(m.c), jourDansHeure: true })).join("")
    : `<li class="vide">Pas de grande affiche annoncée cette semaine.</li>`;
}
function rendre() {
  const req = F.club ? { un: new Set([F.club]) } : lireRequete(F.idx, F.q);
  const liste = aVenir().filter((m) => correspond(req, m)), montres = liste.slice(0, F.montres), cherche = F.club || F.q.trim();
  $("#note").textContent = !liste.length
    ? (cherche ? "Aucun match à venir pour cette recherche. Vérifie l'orthographe, ou essaie un seul club." : "Aucun match à venir.")
    : cherche ? `${liste.length} match${liste.length > 1 ? "s" : ""} à venir. Clique sur un match pour le détail.`
      : "Heures à l'heure de ton appareil. Clique sur un match pour le détail.";
  const cf = $("#club-favori");
  cf.hidden = !F.club;
  if (F.club) cf.innerHTML = etoile(F.club, F.r.clubs[F.club].nom, true);
  $("#results").innerHTML = parJour(montres, ligne);
  $("#more").hidden = liste.length <= F.montres;
}
/* vue « Mes favoris » : les clubs suivis, de quoi les retirer ou chercher leurs matchs, et tous leurs matchs à venir */
function rendreFavoris() {
  const clubs = mesClubs();
  $("#favoris-liste").innerHTML = clubs.map((k) => `<li><button type="button" class="puce" data-club="${esc(k)}">${ecusson(clubSuivi(k))}${esc(clubSuivi(k).nom)}</button>${etoile(k, clubSuivi(k).nom)}</li>`).join("");
  const matchs = aVenir().filter(matchsDe(clubs));
  const connecte = typeof Compte !== "undefined" && Compte.lire();
  const garde = connecte ? "Enregistrés sur ton compte." : "Gardés dans ce navigateur. Avec un compte, tu les retrouves sur tous tes appareils.";
  $("#favoris-note").textContent = !clubs.length ? "Aucun club suivi. L'étoile à côté d'une équipe l'ajoute ici."
    : !matchs.length ? `Aucun match à venir pour ces clubs. ${garde}` : garde;
  $("#favoris-chercher").textContent = clubs.length ? "Chercher un autre club" : "Chercher un club à suivre";
  $("#favoris-matchs").innerHTML = parJour(matchs.slice(0, F.montresFav), ligne);
  $("#favoris-plus").hidden = matchs.length <= F.montresFav;
}

/* ---------- direct : matchs en cours en tête, et une ligne qui dit où en est le direct quand il n'y en a pas */
const ligneDirect = (x) => ligneMatch(x.m, x.clubs, { lien: x.connu ? lienMatch(x.m) : null, comp: nomComp(x.m.c), etoiles: x.connu,
  centre: centreDirect(x.m, x.f, x.clubs) });

function rendreEtatDirect(tous, montres) {
  const maintenant = Date.now();
  const alerte = alerteDirect(D.relais, F.suivables.matchs, { echec: D.echec, maintenant });
  let texte = "";
  if (alerte) texte = alerte.texte;
  else if (!D.relais) texte = "Vérification du direct…";
  else if (!montres.length && tous.length) {
    texte = `Aucun de tes clubs ne joue en ce moment. ${accord(tous.length, "match", "matchs")} en cours dans les autres rencontres.`;
  } else if (!montres.length) {
    const garde = F.vue === "favoris" ? matchsDe(mesClubs()) : () => true;
    const prochain = F.suivables.matchs.filter((m) => m.kickoff && m.etat !== "joue" && Date.parse(m.kickoff) > maintenant && garde(m))
      .sort((x, y) => Date.parse(x.kickoff) - Date.parse(y.kickoff))[0];
    texte = `Aucun match en cours actuellement.${prochain ? ` Prochain coup d'envoi : ${momentTexte(prochain.kickoff)}.` : ""}`;
  }
  const boite = $("#direct-etat"), span = $("#direct-etat-texte");
  boite.hidden = !texte;
  boite.classList.toggle("alerte", Boolean(alerte));
  if (span.textContent !== texte) span.textContent = texte;   // réécrire un texte identique le ferait annoncer de nouveau
}
function majDirect() {
  if (!F.suivables) return;
  const tous = enDirectMaintenant(D.relais, D.suivis);
  const garde = matchsDe(mesClubs());
  const montres = F.vue === "favoris" ? tous.filter((x) => garde(x.m)) : tous;
  const ids = new Set(tous.map((x) => x.m.id));
  const change = ids.size !== F.enCours.size || [...ids].some((id) => !F.enCours.has(id));
  F.enCours = ids;
  rendreBlocDirect($("#bloc-direct"), montres, ligneDirect);
  rendreEtatDirect(tous, montres);
  if (change) { rendreAffiches(); rendre(); rendreFavoris(); }
}

/* ---------- vues */
const vueDemandee = () => (location.hash === "#favoris" ? "favoris" : "une");
function afficherVue() {
  F.vue = vueDemandee();
  $("#vue-une").hidden = F.vue !== "une";
  $("#vue-favoris").hidden = F.vue !== "favoris";
  for (const a of document.querySelectorAll("#nav-foot a[data-vue]")) {
    if (a.dataset.vue === F.vue) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  majDirect();
  appliquer();
}
function allerA(vue) {
  if (vueDemandee() !== vue) history.pushState(null, "", vue === "favoris" ? "#favoris" : location.pathname + location.search);
  afficherVue();
}
/* la recherche est dans « À la une » : on y revient pour chercher un club */
function chercherClub(k) {
  allerA("une");
  const q = $("#q");
  q.value = k && F.r.clubs[k] ? F.r.clubs[k].nom : "";
  F.q = q.value; F.club = k && F.r.clubs[k] ? k : null; F.montres = PAGE;
  $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); rendre();
  $("#h-matchs").scrollIntoView({ block: "start" });
  q.focus({ preventScroll: true });
}
function surFavoris() {
  const actif = document.activeElement?.closest?.("#vue-favoris button[data-favori]")?.dataset.favori;
  rendreFavoris(); majDirect(); appliquer();
  if (actif) $(`#vue-favoris button[data-favori="${CSS.escape(actif)}"]`)?.focus();
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
    erreur($("#results"), err); erreur($("#favoris-matchs"), err);
    $("#direct-etat").hidden = true;
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
  F.suivables = matchsSuivables(F.i, F.r);
  listeCompetitions($("#competitions"), F.i.competitions);
  rendreAffiches(); rendre(); rendreFiabilite(); rendreFavoris();
  afficherVue();
  window.addEventListener("hashchange", afficherVue);
  window.addEventListener("popstate", afficherVue);
  document.addEventListener("favoris", surFavoris);
  document.addEventListener("compte", rendreFavoris);
  $("#nav-foot").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-vue]");
    if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    allerA(a.dataset.vue);
  });
  $("#favoris-liste").addEventListener("click", (e) => { const b = e.target.closest("button.puce"); if (b) chercherClub(b.dataset.club); });
  $("#favoris-chercher").addEventListener("click", () => chercherClub(null));
  $("#favoris-plus").addEventListener("click", () => { F.montresFav += PAGE; rendreFavoris(); });
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
  $("#more").addEventListener("click", () => { F.montres += PAGE; rendre(); });
  suivreDirect([{ matchs: F.suivables.matchs, clubs: F.suivables.clubs }], { apresTour: majDirect, toujours: true, inconnus: {} });
}
main();
