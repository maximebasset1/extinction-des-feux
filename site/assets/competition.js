/* Page d'une compétition : lit data/foot/<compétition>.json et data/foot/h2h_<compétition>.json. */
"use strict";

const C = { d: null, h2h: [], journee: null, club: null, a: null, b: null };
const club = (k) => C.d.clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };
const nom = (k) => club(k).nom;
const COMPS = { E0: "Premier League", D1: "Bundesliga", SP1: "Liga", F1: "Ligue 1", I1: "Serie A", LDC: "Ligue des champions", LEC: "Ligue Europa" };
const compNom = (c) => COMPS[c] || "Championnat";

/* étoile des clubs favoris (favoris.js) ; rien si le script n'a pas pu se charger */
const etoile = (k, n, texte = false) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, n, { texte }));

function face(a, b) {
  return C.h2h.filter((g) => (g[1] === a && g[2] === b) || (g[1] === b && g[2] === a));
}

/* ---------- détail d'un match, montré quand on déplie sa ligne */
function detail(m) {
  const h = nom(m.home), a = nom(m.away);
  const trois = (p) => `<div class="m-trois">
      <p><b>${pct(p[0])}</b><span>victoire ${esc(h)}</span></p>
      <p><b>${pct(p[1])}</b><span>match nul</span></p>
      <p><b>${pct(p[2])}</b><span>victoire ${esc(a)}</span></p></div>`;
  let html = "";
  if (m.etat === "a_venir") {
    const sc = m.scores.map((s) => `${esc(s.score)} (${pct(s.p)})`).join(", ");
    html += trois(m.p);
    html += `<p>Scores les plus probables : ${sc}. Buts attendus : ${virgule(m.xg[0])} pour ${esc(h)}, ${virgule(m.xg[1])} pour ${esc(a)}. Plus de 2,5 buts : ${pct(m.plus25)}.</p>`;
    html += `<p class="note">${m.source === "publie" ? `Pronostic figé et enregistré dans le journal${m.publie ? ` (${esc(quand(m.publie))})` : ""} : c'est lui qui sera jugé. `
      : ""}${m.avec_cotes ? "Cotes d'avant-match comprises : les blessures et l'actualité connues sont prises en compte."
      : "Statistiques seules : les cotes d'avant-match ne sont pas encore publiées, les blessures et l'actualité récentes ne sont donc pas prises en compte."} Probabilités sur 90 minutes.</p>`;
  } else if (m.etat === "joue") {
    if (m.p) {
      const y = issue(m.score);
      html += `<p>${m.source === "publie" ? `Pronostic publié avant le match${m.publie ? ` (${esc(quand(m.publie))})` : ""} :`
        : "Ce que le modèle aurait annoncé avant le match (reconstitution : ce match n'a pas été enregistré dans le journal) :"}</p>`;
      html += trois(m.p);
      html += `<p>${m.surprise ? `<span class="tag-surprise">Surprise.</span> Le résultat n'avait que ${pct(m.p[y])} de chances.` : `Le résultat avait ${pct(m.p[y])} de chances.`}</p>`;
    } else {
      html += `<p class="note">Pas de pronostic enregistré pour ce match.</p>`;
    }
  } else if (m.p) {
    html += `<p>Pronostic publié avant le coup d'envoi :</p>${trois(m.p)}`;
  }
  const suivre = etoile(m.home, h, true) + etoile(m.away, a, true);
  if (suivre) html += `<div class="fiche-clubs">${suivre}</div>`;
  const g = face(m.home, m.away).slice(0, 8);
  html += `<h3>Derniers face-à-face</h3>`;
  html += g.length ? `<div class="defile"><table class="tableau"><thead><tr><th>Date</th><th>Compétition</th><th>Domicile</th><th class="num">Score</th><th>Extérieur</th></tr></thead><tbody>${g.map(([d, x, y, gx, gy, c]) => `<tr>
      <td class="nowrap">${esc(jourCourt(d))}</td><td>${esc(compNom(c))}</td><td><span class="club">${ecusson(club(x))}${esc(nom(x))}</span></td>
      <td class="num">${nombre(gx)} - ${nombre(gy)}</td><td><span class="club">${ecusson(club(y))}${esc(nom(y))}</span></td></tr>`).join("")}</tbody></table></div>`
    : `<p class="vide">Aucun match entre ces deux clubs dans nos données.</p>`;
  return html;
}
const ligne = (m) => ligneMatch(m, C.d.clubs, { detail: detail(m) });

/* ---------- matchs d'une journée */
function rendreJournee() {
  const j = C.journee, liste = C.d.matchs.filter((m) => m.journee === j)
    .sort((x, y) => String(x.kickoff || `${x.jour}T23:59`).localeCompare(String(y.kickoff || `${y.jour}T23:59`)));
  const i = C.d.journees.indexOf(j);
  $("#j-titre").textContent = j || "Matchs";
  $("#j-select").value = j;
  $("#j-prev").disabled = i <= 0;
  $("#j-next").disabled = i >= C.d.journees.length - 1;
  const aVenir = liste.filter((m) => m.etat === "a_venir");
  const legende = legendeJoues(liste);
  $("#j-note").textContent = !liste.length ? "" : !aVenir.length
    ? `Journée terminée. Sous chaque score, la chance que le modèle donnait au résultat avant le match. ${legende ? `${legende} ` : ""}Déplie un match pour le détail.`
    : `Chances de victoire à domicile, de nul et de victoire à l'extérieur${aVenir.some((m) => m.avec_cotes) ? ", cotes d'avant-match comprises quand elles sont publiées" : ""}. Heures à l'heure de ton appareil. ${legende ? `${legende} ` : ""}Déplie un match pour le détail.`;
  $("#j-liste").innerHTML = liste.length ? parJour(liste, ligne) : `<p class="vide">Aucun match pour l'instant.</p>`;
}

/* ---------- classement et fin de saison */
function rendreClassement() {
  const t = C.d.classement;
  if (!t.length) {
    if (C.d.type === "coupe") {   // pas de classement complet : la section et son lien disparaissent
      $("#classement").hidden = true;
      $("#lien-classement").hidden = true;
      return;
    }
    $("#t-note").textContent = "Le classement apparaîtra après la première journée.";
    $("#t-table").innerHTML = "";
    return;
  }
  const proj = new Map(C.d.projection.map((x) => [x.club, x]));
  const zones = C.d.zones;
  const zoneDe = (rang) => {
    const z = zones.find((x) => rang >= x.de && rang <= x.a && x.cle !== "titre");
    if (!z) return "";
    return ["relegation", "elimine"].includes(z.cle) ? "z-bas" : ["barrage", "barrages"].includes(z.cle) ? "z-barrage" : "z-haut";
  };
  $("#t-note").textContent = proj.size
    ? `Fin de saison simulée ${C.d.simulations.toLocaleString("fr-FR")} fois avec les pronostics de chaque match restant. Le filet à gauche du rang marque les zones${C.d.type === "ligue" ? " (le nombre de places européennes dépend des coupes : le top 4 est indicatif)" : ""}.`
    : "Classement actuel.";
  const zc = zones.map((z) => `<th class="num">${esc(z.nom)}</th>`).join("");
  $("#t-table").innerHTML = `<thead><tr><th>#</th><th>Club</th><th class="num">Pts</th><th class="num">J</th><th class="num">Diff.</th>${proj.size ? `<th class="num">Pts attendus</th>${zc}` : ""}</tr></thead><tbody>${t.map((r, i) => {
    const p = proj.get(r.club);
    return `<tr class="${zoneDe(i + 1)}"><td class="rang">${i + 1}</td><td><span class="club">${ecusson(club(r.club))}${esc(nom(r.club))}${etoile(r.club, nom(r.club))}</span></td>
      <td class="num"><b>${nombre(r.pts)}</b></td><td class="num">${nombre(r.j)}</td><td class="num">${r.diff > 0 ? "+" : ""}${nombre(r.diff)}</td>
      ${p ? `<td class="num">${virgule(p.points_attendus)}</td>${zones.map((z) => `<td class="num">${pct(p[z.cle])}</td>`).join("")}` : ""}</tr>`;
  }).join("")}</tbody>`;
}

/* ---------- calendrier d'un club */
function rendreClub() {
  const k = C.club, liste = C.d.matchs.filter((m) => m.home === k || m.away === k);
  const rang = C.d.classement.findIndex((r) => r.club === k), r = C.d.classement[rang], p = C.d.projection.find((x) => x.club === k);
  const morceaux = [];
  if (r && r.j) morceaux.push(`${rang + 1}<sup>${rang === 0 ? "er" : "e"}</sup> avec ${accord(r.pts, "point")} en ${accord(r.j, "match", "matchs")} (${accord(r.g, "victoire")}, ${accord(r.n, "nul")}, ${accord(r.p, "défaite")})`);
  if (p && C.d.zones.length) morceaux.push(`${virgule(p.points_attendus)} points attendus en fin de saison, ${C.d.zones.map((z) => `${esc(z.nom.toLowerCase())} ${pct(p[z.cle])}`).join(", ")}`);
  const legende = legendeJoues(liste);
  $("#club-resume").innerHTML = `<p>${etoile(k, nom(k), true)}</p>` + (morceaux.length ? `<p>${morceaux.join(". ")}.</p>` : "") + (legende ? `<p class="note">${legende}</p>` : "");
  $("#club-liste").innerHTML = liste.length ? `<ul class="matchs">${liste.map((m) => ligneMatch(m, C.d.clubs, { detail: detail(m), jourDansHeure: true, prefixe: "c" })).join("")}</ul>` : `<p class="vide">Aucun match.</p>`;
}

/* ---------- face-à-face */
function rendreFace() {
  const a = C.a, b = C.b, g = face(a, b);
  let va = 0, n = 0, vb = 0;
  g.forEach(([, x, , gx, gy]) => { const sa = x === a ? gx : gy, sb = x === a ? gy : gx; if (sa > sb) va++; else if (sa < sb) vb++; else n++; });
  $("#f-resume").innerHTML = g.length
    ? `Sur ${g.length} match${g.length > 1 ? "s" : ""} depuis ${esc(jourCourt(g[g.length - 1][0]).replace(/^\S+ \S+ /, ""))} : <b>${va}</b> victoire${va > 1 ? "s" : ""} de ${esc(nom(a))}, <b>${n}</b> nul${n > 1 ? "s" : ""}, <b>${vb}</b> victoire${vb > 1 ? "s" : ""} de ${esc(nom(b))}.`
    : "Aucun match entre ces deux clubs dans nos données.";
  $("#f-liste").innerHTML = g.length ? `<thead><tr><th>Date</th><th>Compétition</th><th>Domicile</th><th class="num">Score</th><th>Extérieur</th></tr></thead><tbody>${g.map(([d, x, y, gx, gy, c]) => `<tr>
    <td class="nowrap">${esc(jourCourt(d))}</td><td>${esc(compNom(c))}</td><td><span class="club">${ecusson(club(x))}${esc(nom(x))}</span></td>
    <td class="num">${nombre(gx)} - ${nombre(gy)}</td><td><span class="club">${ecusson(club(y))}${esc(nom(y))}</span></td></tr>`).join("")}</tbody>` : "";
}

/* ---------- fiabilité et journal */
function rendreFiabilite() {
  const f = C.d.fiabilite;
  if (!f) {
    $("#b-note").textContent = "Pas encore assez de matchs pour juger le modèle sur cette compétition.";
  } else {
    $("#b-note").textContent = `Chaque semaine depuis 2022, le modèle est rejoué avec les seuls matchs joués avant, comme s'il avait tourné à l'époque (${f.matchs.toLocaleString("fr-FR")} matchs). Score RPS : plus il est bas, plus les probabilités étaient justes. « Habitudes » : donner à chaque match les pourcentages habituels domicile, nul, extérieur.`;
    const rows = [["Nos statistiques", f.modele], ["Avec les cotes", f.avec_cotes], ["Cotes seules", f.marche], ["Habitudes", f.habitudes]].filter((r) => r[1]);
    $("#b-table").innerHTML = `<thead><tr><th>Méthode</th><th class="num">Score RPS</th><th class="num">Le favori gagne</th></tr></thead><tbody>${rows.map(([n, r]) => `<tr>
      <td>${esc(n)}</td><td class="num">${virgule(r.rps, 3)}</td><td class="num">${pct(r.bons_favoris)}</td></tr>`).join("")}</tbody>
      ${f.avec_cotes ? "" : "<caption>En coupe d'Europe, pas d'historique de cotes gratuit : seules nos statistiques sont jugées.</caption>"}`;
  }
  const j = C.d.journal || [];
  if (!j.length) {
    $("#journal").innerHTML = `<p class="vide">Les pronostics publiés avant chaque match apparaîtront ici avec le résultat.</p>`;
    return;
  }
  const ok = j.filter((e) => e.favori_juste).length;
  $("#journal").innerHTML = `<p>Le favori a gagné ${ok} fois sur ${j.length}.</p><div class="defile"><table class="tableau"><thead><tr><th>Match</th><th class="num">Score</th><th class="num">Annoncé</th><th>Résultat</th></tr></thead><tbody>${j.slice().reverse().map((e) => {
    const y = e.resultat;
    return `<tr><td>${esc(nom(e.home))} - ${esc(nom(e.away))}<br><small class="note">${esc(e.journee)}</small></td><td class="num"><b>${nombre(e.score[0])} - ${nombre(e.score[1])}</b></td>
      <td class="num nowrap">${pnum(e.p[0])} / ${pnum(e.p[1])} / ${pnum(e.p[2])}</td>
      <td>${e.surprise ? `<span class="tag-surprise">surprise</span>, ${pct(e.p[y])}` : e.favori_juste ? "favori vainqueur" : `${pct(e.p[y])} annoncé`}</td></tr>`;
  }).join("")}</tbody></table></div>`;
}

/* ---------- démarrage */
function options(sel, keys, courant, libelle = nom) {
  sel.innerHTML = keys.map((k) => `<option value="${esc(k)}"${k === courant ? " selected" : ""}>${esc(libelle(k))}</option>`).join("");
}
function ouvrirDepuisAdresse() {
  if (!location.hash.startsWith("#match=")) return;
  let id;
  try { id = decodeURIComponent(location.hash.slice(7)); } catch { return; }
  const m = C.d.matchs.find((x) => x.id === id);
  if (!m) return;
  C.journee = m.journee;
  rendreJournee();
  const el = document.getElementById(`m-${cleId(id)}`);
  if (el) { el.open = true; el.scrollIntoView({ block: "start" }); el.querySelector("summary").focus({ preventScroll: true }); }
}
async function main() {
  const slug = document.body.dataset.competition;
  const [d, h] = await Promise.allSettled([donnees(`foot/${slug}`), donnees(`foot/h2h_${slug}`)]);
  if (d.status !== "fulfilled") { erreur($("#j-liste"), d.reason); return; }
  C.d = d.value;
  C.h2h = h.status === "fulfilled" ? h.value.matchs : [];   // sans face-à-face, le reste de la page s'affiche quand même
  $("#c-chapeau").textContent = `Saison ${C.d.saison}. Chances de victoire, de nul et de défaite pour chaque match, recalculées plusieurs fois par jour. Mise à jour : ${quand(C.d.maj_utc)}.`;
  if (!C.d.matchs.length) {   // calendrier indisponible : on n'affiche que la fiabilité
    $(".pager").hidden = true;
    $("#j-liste").innerHTML = `<p class="vide">Le calendrier de cette compétition n'est pas disponible pour l'instant. Il sera repris à la prochaine mise à jour.</p>`;
    for (const id of ["classement", "club", "face"]) {
      $(`#${id}`).hidden = true;
      document.querySelector(`.sommaire a[href="#${id}"]`).hidden = true;
    }
    rendreFiabilite();
    return;
  }
  // un match en cours (coup d'envoi il y a moins de 2 h 30, ou 3 h en coupe) passe avant la prochaine journée : on ouvre la sienne
  const t = Date.now(), fenetre = C.d.type === "coupe" ? 108e5 : 9e6;
  const enCours = C.d.matchs.find((m) => m.kickoff && m.etat !== "joue" && t >= Date.parse(m.kickoff) && t - Date.parse(m.kickoff) < fenetre);
  C.journee = enCours?.journee || C.d.prochaine || C.d.journees[0];
  $("#j-select").innerHTML = C.d.journees.map((j) => `<option>${esc(j)}</option>`).join("");
  const keys = Object.keys(C.d.clubs).sort((x, y) => nom(x).localeCompare(nom(y), "fr"));
  const tete = C.d.classement.map((r) => r.club);
  C.club = tete[0] || keys[0]; C.a = tete[0] || keys[0]; C.b = tete[1] || keys[1];
  options($("#club-select"), keys, C.club); options($("#f-a"), keys, C.a); options($("#f-b"), keys, C.b);
  rendreJournee(); rendreClassement(); rendreClub(); rendreFace(); rendreFiabilite();
  ouvrirDepuisAdresse();
  suivreDirect([{ matchs: C.d.matchs, clubs: C.d.clubs, comp: C.d.code }]);
  $("#j-select").addEventListener("change", (e) => { C.journee = e.target.value; rendreJournee(); });
  $("#j-prev").addEventListener("click", () => { C.journee = C.d.journees[Math.max(0, C.d.journees.indexOf(C.journee) - 1)]; rendreJournee(); });
  $("#j-next").addEventListener("click", () => { C.journee = C.d.journees[Math.min(C.d.journees.length - 1, C.d.journees.indexOf(C.journee) + 1)]; rendreJournee(); });
  $("#club-select").addEventListener("change", (e) => { C.club = e.target.value; rendreClub(); });
  $("#f-a").addEventListener("change", (e) => { C.a = e.target.value; rendreFace(); });
  $("#f-b").addEventListener("change", (e) => { C.b = e.target.value; rendreFace(); });
  window.addEventListener("hashchange", ouvrirDepuisAdresse);
}
main();
