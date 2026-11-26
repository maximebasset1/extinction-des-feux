/* Page d'une compétition : lit data/foot/<compétition>.json et data/foot/h2h_<compétition>.json. Deux vues : « Matchs »
   (journées en un clic, matchs en cours en tête) et « Classement » (classement, face-à-face, calendrier d'un club). */
"use strict";

/* ouverte : la journée montrée à l'arrivée, repérée parmi les pilules ; enCours : matchs affichés en tête de liste */
const C = { d: null, h2h: [], journee: null, ouverte: null, club: null, a: null, b: null, enCours: new Set() };
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
    const badge = badgeConfiance(m);
    if (badge) html += `<p class="detail-conf">${badge}</p>`;
    html += trois(m.p);
    html += blocStatsGrille(m);
    html += `<p>Scores les plus probables : ${sc}. Buts attendus : ${virgule(m.xg[0])} pour ${esc(h)}, ${virgule(m.xg[1])} pour ${esc(a)}.</p>`;
    html += blocFacteurs(m, C.d.clubs);
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
    const badge = badgeConfiance(m);
    if (badge) html += `<p class="detail-conf">${badge}</p>`;
    html += `<p>Pronostic publié avant le coup d'envoi :</p>${trois(m.p)}`;
    html += blocStatsGrille(m);
    html += blocFacteurs(m, C.d.clubs);
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

/* ---------- matchs d'une journée (les matchs en cours sont en tête de liste, ils ne sont pas répétés ici) */
function rendreJournee() {
  const j = C.journee, tous = C.d.matchs.filter((m) => m.journee === j)
    .sort((x, y) => String(x.kickoff || `${x.jour}T23:59`).localeCompare(String(y.kickoff || `${y.jour}T23:59`)));
  const liste = tous.filter((m) => !C.enCours.has(m.id));
  const i = C.d.journees.indexOf(j);
  $("#j-titre").textContent = j || "Matchs";
  $("#j-prev").disabled = i <= 0;
  $("#j-next").disabled = i >= C.d.journees.length - 1;
  const aVenir = tous.filter((m) => m.etat === "a_venir");
  const joues = tous.filter((m) => m.etat === "joue");
  const legende = legendeJoues(tous);
  $("#j-note").textContent = !tous.length ? "" : !aVenir.length && joues.length === tous.length
    ? `Journée terminée (${accord(joues.length, "match", "matchs")} joué${joues.length > 1 ? "s" : ""}). Sous chaque score, la chance que le modèle donnait au résultat avant le match. ${legende ? `${legende} ` : ""}Déplie un match pour le détail.`
    : `${joues.length ? `${accord(joues.length, "résultat")} enregistré${joues.length > 1 ? "s" : ""}, chances` : "Chances"} de victoire à domicile, de nul et de victoire à l'extérieur${aVenir.some((m) => m.avec_cotes) ? ", cotes d'avant-match comprises quand elles sont publiées" : ""}. Heures à l'heure de ton appareil. ${legende ? `${legende} ` : ""}Déplie un match pour le détail.`;
  $("#j-liste").innerHTML = liste.length ? parJour(liste, ligne)
    : `<p class="vide">${tous.length ? "Les matchs de cette journée sont en cours, en tête de liste." : "Aucun match pour l'instant."}</p>`;
  if (typeof Favoris !== "undefined") Favoris.marquer($("#j-liste"));
  if (typeof appliquer === "function") appliquer();
}
function rendrePilules() {
  $("#j-pilules").innerHTML = C.d.journees.map((j) => `<button type="button" data-journee="${esc(j)}" title="${esc(j)}"${j === C.ouverte ? ' class="actuelle"' : ""}>${esc(libelleCourt(j))}</button>`).join("");
}
/* la pilule choisie, et un point rouge sur les journées qui ont un match en cours ; une seule pilule dans l'ordre de tabulation */
function majPilules() {
  const enDirect = new Set(C.d.matchs.filter((m) => C.enCours.has(m.id)).map((m) => m.journee));
  for (const b of $("#j-pilules").children) {
    const j = b.dataset.journee, choisie = j === C.journee;
    if (choisie) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");
    b.tabIndex = choisie ? 0 : -1;
    b.classList.toggle("en-direct", enDirect.has(j));
    b.setAttribute("aria-label", enDirect.has(j) ? `${j}, match en cours` : j);
  }
}
/* la journée choisie au milieu de la bande, sans faire défiler la page */
function centrerPilule() {
  const bande = $("#j-pilules"), b = bande.querySelector('[aria-current="true"]');
  if (b) bande.scrollLeft = b.offsetLeft - (bande.clientWidth - b.offsetWidth) / 2;
}
function choisirJournee(j, { focus = false } = {}) {
  if (!C.d.journees.includes(j)) return;
  C.journee = j;
  rendreJournee(); majPilules(); centrerPilule();
  if (focus) $('#j-pilules [aria-current="true"]')?.focus({ preventScroll: true });
}
const journeeVoisine = (pas) => C.d.journees[Math.max(0, Math.min(C.d.journees.length - 1, C.d.journees.indexOf(C.journee) + pas))];

/* ---------- direct : les matchs en cours de la compétition en tête de liste */
const ligneDirect = (x) => (x.connu ? ligneMatch(x.m, C.d.clubs, { detail: detail(x.m), prefixe: "d" })
  : ligneMatch(x.m, x.clubs, { etoiles: false, centre: centreDirect(x.m, x.f, x.clubs) }));

/* un match déplié le reste quand les listes sont refaites, même s'il passe de la journée au direct ou l'inverse */
function garderOuverts(refaire) {
  const ouverts = [...document.querySelectorAll("#vue-matchs li.match > details[open]")].map((d) => d.parentElement.dataset.match);
  refaire();
  for (const cle of ouverts) {
    const d = document.querySelector(`#vue-matchs li.match[data-match="${CSS.escape(cle)}"] > details`);
    if (d) d.open = true;
  }
}
function majDirect() {
  const code = C.d.code;
  const entrees = enDirectMaintenant(D.relais, D.suivis, { comp: code });
  const ids = new Set(entrees.filter((x) => x.connu).map((x) => x.m.id));
  const change = ids.size !== C.enCours.size || [...ids].some((id) => !C.enCours.has(id));
  garderOuverts(() => {
    C.enCours = ids;
    rendreBlocDirect($("#bloc-direct"), entrees, ligneDirect);
    if (change) { rendreJournee(); majPilules(); }
  });
  // l'état du direct n'est signalé que les jours où la compétition joue
  const relais = D.relais && { ...D.relais, matchs: D.relais.matchs.filter((f) => f.c === code) };
  const joueAujourdhui = C.d.matchs.some((m) => m.jour === aujourdhui());
  const alerte = joueAujourdhui ? alerteDirect(relais, C.d.matchs.map((m) => ({ ...m, c: code })), { echec: D.echec }) : null;
  const boite = $("#direct-alerte");
  boite.hidden = !alerte;
  if (alerte && boite.textContent !== alerte.texte) boite.textContent = alerte.texte;
}

/* ---------- classement et fin de saison */
function rendreClassement() {
  const t = C.d.classement;
  if (!t.length) {
    if (C.d.type === "coupe") {   // pas de classement complet : la section disparaît et l'onglet dit ce qu'il contient
      $("#classement").hidden = true;
      $("#onglet-classement").textContent = "Face-à-face";
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
/* les deux vues ; les anciennes ancres de la page (#classement, #face, #club, #matchs, #fiabilite) restent valables */
const ANCRES_CLASSEMENT = new Set(["#classement", "#face", "#club"]);
function afficherVue(vue) {
  for (const b of document.querySelectorAll('.vues [role="tab"]')) {
    const choisi = b.id === `onglet-${vue}`;
    b.setAttribute("aria-selected", String(choisi));
    b.tabIndex = choisi ? 0 : -1;
  }
  $("#vue-matchs").hidden = vue !== "matchs";
  $("#vue-classement").hidden = vue !== "classement";
  if (vue === "matchs") centrerPilule();   // la bande ne se centre que lorsqu'elle est visible
}
function choisirVue(vue) {
  afficherVue(vue);
  history.replaceState(null, "", vue === "classement" ? "#classement" : location.pathname + location.search);
}
function ouvrirDepuisAdresse() {
  const ancre = location.hash;
  if (ANCRES_CLASSEMENT.has(ancre)) {
    afficherVue("classement");
    if (ancre !== "#classement") $(ancre).scrollIntoView({ block: "start" });
    return;
  }
  afficherVue("matchs");
  if (ancre === "#fiabilite") {
    $("#fiabilite details").open = true;
    $("#fiabilite").scrollIntoView({ block: "start" });
    return;
  }
  if (!ancre.startsWith("#match=")) return;
  let id;
  try { id = decodeURIComponent(ancre.slice(7)); } catch { return; }
  const m = C.d.matchs.find((x) => x.id === id);
  if (!m) return;
  if (typeof FICHE !== "undefined" && FICHE.dlg?.open) FICHE.dlg.close();
  choisirJournee(m.journee);
  const el = document.getElementById(`m-${cleId(id)}`) || document.getElementById(`d-${cleId(id)}`);   // d- : le match est en cours
  if (el) { el.open = true; el.scrollIntoView({ block: "start" }); el.querySelector("summary").focus({ preventScroll: true }); }
}
function suivre() {
  suivreDirect([{ matchs: C.d.matchs, clubs: C.d.clubs, comp: C.d.code }],
    { inclureDuJourSansScore: true, toujours: true, inconnus: { comp: C.d.code }, apresTour: majDirect });
}
async function main() {
  const slug = document.body.dataset.competition;
  const [d, h] = await Promise.allSettled([donnees(`foot/${slug}`), donnees(`foot/h2h_${slug}`)]);
  if (d.status !== "fulfilled") { erreur($("#j-liste"), d.reason); return; }
  C.d = d.value;
  C.h2h = h.status === "fulfilled" ? h.value.matchs : [];   // sans face-à-face, le reste de la page s'affiche quand même
  $("#c-chapeau").textContent = `Saison ${C.d.saison}, mise à jour ${quand(C.d.maj_utc)}.`;
  if (!C.d.matchs.length) {   // calendrier indisponible : on n'affiche que la fiabilité
    $(".vues").hidden = true;
    $(".journees").hidden = true;
    $("#j-liste").innerHTML = `<p class="vide">Le calendrier de cette compétition n'est pas disponible pour l'instant. Il sera repris à la prochaine mise à jour.</p>`;
    rendreFiabilite();
    suivre();   // les matchs en cours connus du relais remontent quand même
    return;
  }
  C.ouverte = journeeParDefaut(C.d);
  C.journee = C.ouverte;
  const keys = Object.keys(C.d.clubs).sort((x, y) => nom(x).localeCompare(nom(y), "fr"));
  const tete = C.d.classement.map((r) => r.club);
  C.club = tete[0] || keys[0]; C.a = tete[0] || keys[0]; C.b = tete[1] || keys[1];
  options($("#club-select"), keys, C.club); options($("#f-a"), keys, C.a); options($("#f-b"), keys, C.b);
  rendrePilules(); rendreJournee(); majPilules(); rendreClassement(); rendreClub(); rendreFace(); rendreFiabilite();
  ouvrirDepuisAdresse();
  $("#j-pilules").addEventListener("click", (e) => { const b = e.target.closest("button[data-journee]"); if (b) choisirJournee(b.dataset.journee); });
  $("#j-pilules").addEventListener("keydown", (e) => {
    const cible = { ArrowLeft: journeeVoisine(-1), ArrowRight: journeeVoisine(1), Home: C.d.journees[0], End: C.d.journees[C.d.journees.length - 1] }[e.key];
    if (cible === undefined) return;
    e.preventDefault();
    choisirJournee(cible, { focus: true });
  });
  $("#j-prev").addEventListener("click", () => choisirJournee(journeeVoisine(-1)));
  $("#j-next").addEventListener("click", () => choisirJournee(journeeVoisine(1)));
  $(".vues").addEventListener("click", (e) => { const b = e.target.closest('[role="tab"]'); if (b) choisirVue(b.id.replace("onglet-", "")); });
  $(".vues").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const autre = $("#onglet-matchs").getAttribute("aria-selected") === "true" ? "classement" : "matchs";
    choisirVue(autre);
    $(`#onglet-${autre}`).focus();
  });
  $("#club-select").addEventListener("change", (e) => { C.club = e.target.value; rendreClub(); });
  $("#f-a").addEventListener("change", (e) => { C.a = e.target.value; rendreFace(); });
  $("#f-b").addEventListener("change", (e) => { C.b = e.target.value; rendreFace(); });
  window.addEventListener("hashchange", ouvrirDepuisAdresse);
  window.addEventListener("resize", centrerPilule);
  document.fonts?.ready.then(centrerPilule);   // la police arrivée après coup change la largeur des pilules
  document.addEventListener("favoris", () => { majDirect(); appliquer(); });   // un favori réordonne les matchs en cours
  suivre();
}
main();
