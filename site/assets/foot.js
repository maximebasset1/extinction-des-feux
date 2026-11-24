/* Page Football : recherche d'un club ou d'un match dans les sept compétitions, prochains matchs, compétitions, fiabilité. */
"use strict";

const PAGE = 30;
const F = { r: null, i: null, idx: {}, comp: "", q: "", club: null, montres: PAGE };
const lienMatch = (m) => `${ROOT}foot/${F.r.competitions[m.c].slug}.html#match=${encodeURIComponent(m.id)}`;

const etoile = (k, n, texte = false) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, n, { texte }));

function filtre() {
  const now = new Date(), today = aujourdhui();
  const req = F.club ? { un: new Set([F.club]) } : lireRequete(F.idx, F.q);
  return F.r.matchs.filter((m) => (m.kickoff ? new Date(m.kickoff) > now : (m.jour || "9999") >= today)
    && (!F.comp || m.c === F.comp) && correspond(req, m));
}
function rendre() {
  const liste = filtre(), montres = liste.slice(0, F.montres), cherche = F.club || F.q.trim();
  $("#note").textContent = !liste.length
    ? (cherche ? "Aucun match à venir pour cette recherche. Vérifie l'orthographe, ou essaie un seul club." : "Aucun match à venir.")
    : cherche ? `${liste.length} match${liste.length > 1 ? "s" : ""} à venir. Clique sur un match pour le détail.`
      : "Les prochains matchs des sept compétitions, à l'heure de ton appareil. Clique sur un match pour le détail.";
  const cf = $("#club-favori");
  cf.hidden = !F.club;
  if (F.club) cf.innerHTML = etoile(F.club, F.r.clubs[F.club].nom, true);
  $("#results").innerHTML = parJour(montres, (m) => ligneMatch(m, F.r.clubs, { lien: lienMatch(m), comp: F.r.competitions[m.c].nom }));
  $("#more").hidden = liste.length <= F.montres;
}
/* « Mes clubs favoris » : ceux de ce navigateur, avec de quoi les retirer et chercher leurs matchs */
function rendreFavoris() {
  if (typeof Favoris === "undefined") return;
  const liste = Favoris.liste().filter((k) => F.r.clubs[k]);
  $("#favoris").hidden = !liste.length;
  $("#favoris-liste").innerHTML = liste.map((k) => `<li><button type="button" class="puce" data-club="${esc(k)}">${ecusson(F.r.clubs[k])}${esc(F.r.clubs[k].nom)}</button>${etoile(k, F.r.clubs[k].nom)}</li>`).join("");
}
function chercherClub(k) {
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
  const present = new Set(F.r.matchs.map((m) => m.c));
  $("#chips").innerHTML = [["", "Toutes"], ...Object.entries(F.r.competitions).map(([c, v]) => [c, v.nom])].map(([c, l]) => {
    const on = !c || present.has(c);
    return `<button type="button" data-comp="${esc(c)}" aria-pressed="${c === "" ? "true" : "false"}"${on ? "" : " disabled"}>${esc(l)}</button>`;
  }).join("");
  listeCompetitions($("#competitions"), F.i.competitions);
  rendre(); rendreFiabilite(); rendreFavoris();
  document.addEventListener("favoris", rendreFavoris);
  $("#favoris-liste").addEventListener("click", (e) => { const b = e.target.closest("button.puce"); if (b) { chercherClub(b.dataset.club); $("#q").focus(); } });
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
    if (!b || b.disabled) return;
    F.comp = b.dataset.comp; F.montres = PAGE;
    document.querySelectorAll("#chips button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    rendre();
  });
  $("#more").addEventListener("click", () => { F.montres += PAGE; rendre(); });
}
main();
