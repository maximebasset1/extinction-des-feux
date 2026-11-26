/* Outils communs à toutes les pages : données, dates en français, écussons, barre des probabilités, lignes de match. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const ROOT = document.body.dataset.root || "./";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const couleur = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : null);
const nombre = (v) => (Number.isFinite(Number(v)) ? Number(v) : "–");
// espace fine insécable avant « % » : « 14 % » ne se coupe jamais en fin de ligne
const pct = (p) => (p == null ? "–" : p < 0.005 ? "<1\u202f%" : p >= 0.995 ? ">99\u202f%" : `${Math.round(p * 100)}\u202f%`);
const pnum = (p) => (p == null ? "–" : p < 0.005 ? "<1" : p >= 0.995 ? ">99" : String(Math.round(p * 100)));
const virgule = (x, d = 1) => Number(x).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const plier = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ");

// paramètre changé chaque minute : le CDN de GitHub Pages (10 min) et les navigateurs mobiles ne servent pas de copie périmée
const fraicheur = () => `t=${Math.floor(Date.now() / 6e4)}`;
async function donnees(chemin) {
  const r = await fetch(`${ROOT}data/${chemin}.json?${fraicheur()}`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${chemin}.json : réponse ${r.status}`);
  return r.json();
}
function erreur(el, err) {
  if (el) el.innerHTML = `<p class="erreur">Les données n'ont pas pu être chargées (${esc(err.message)}). Recharge la page dans quelques minutes.</p>`;
}

/* ---------- dates : toujours à l'heure de l'appareil */
const quand = (iso) => new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const heure = (iso) => new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
const midi = (jour) => new Date(`${jour}T12:00:00`);
const jourLong = (jour) => midi(jour).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
const jourCourt = (jour) => midi(jour).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
function quandMatch(m) {
  if (m.kickoff) return quand(m.kickoff);
  if (!m.jour) return "date à fixer";
  return `${midi(m.jour).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })}, heure à fixer`;
}
function relatif(iso) {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "maintenant";
  const h = Math.floor(ms / 36e5), m = Math.round((ms % 36e5) / 6e4);
  if (h >= 48) return `dans ${Math.round(h / 24)} jours`;
  if (h >= 1) return `dans ${h} h${m ? ` ${String(m).padStart(2, "0")}` : ""}`;
  return `dans ${m} min`;
}

/* ---------- écussons : logo libre s'il existe, sinon le sigle (aux couleurs du club quand on les connaît) */
function ecusson(c) {
  if (!c) return "";
  if (c.logo) return `<img class="ecusson" src="${esc(ROOT + c.logo)}" alt="" width="32" height="32">`;
  const fond = couleur(c.couleur), texte = couleur(c.couleur2) || "#ffffff";
  const style = fond ? ` style="background:${fond};color:${texte}"` : "";
  return `<span class="ecusson${String(c.sigle).length > 3 ? " long" : ""}"${style} aria-hidden="true">${esc(c.sigle)}</span>`;
}

/* ---------- barre des probabilités : domicile, nul, extérieur ; le favori en gras */
function barre(p, dom, ext) {
  if (!p) return "";
  const fav = p.indexOf(Math.max(...p));
  const lab = `Victoire ${dom} ${pct(p[0])}, match nul ${pct(p[1])}, victoire ${ext} ${pct(p[2])}`;
  const seg = (k, cls) => `<span class="${cls}" style="width:${(p[k] * 100).toFixed(1)}%"></span>`;
  const chiffre = (k) => `<span${k === fav ? ' class="fav"' : ""}>${pnum(p[k])}<small>%</small></span>`;
  // des « span » seulement : la barre peut se trouver dans le « summary » d'une ligne dépliable
  return `<span class="proba" role="img" aria-label="${esc(lab)}"><span class="barre">${seg(0, "b1")}${seg(1, "bn")}${seg(2, "b2")}</span>
    <span class="trois">${chiffre(0)}${chiffre(1)}${chiffre(2)}</span></span>`;
}
const issue = (s) => (s[0] > s[1] ? 0 : s[0] === s[1] ? 1 : 2);

const CONFIANCE = {
  elevee: ["Confiance élevée", "conf-elevee"],
  indecis: ["Match indécis", "conf-indecis"],
  imprevisible: ["Équipe imprévisible", "conf-imprevisible"],
};
function badgeConfiance(m) {
  const c = m && CONFIANCE[m.confiance];
  return c ? `<span class="badge-conf ${c[1]}">${c[0]}</span>` : "";
}
function blocStatsGrille(m) {
  if (m?.btts == null && m?.plus25 == null) return "";
  const items = [];
  if (m.btts != null) items.push(`<span>Les deux équipes marquent <b>${pct(m.btts)}</b></span>`);
  if (m.plus25 != null) items.push(`<span>Plus de 2,5 buts <b>${pct(m.plus25)}</b></span>`);
  return `<div class="stats-grille">${items.join("")}</div>`;
}
function blocFacteurs(m, clubs) {
  const faits = Array.isArray(m?.facteurs) ? m.facteurs : [];
  const but = m?.buteurs;
  const hasBut = Boolean(but && ((but.dom && but.dom.length) || (but.ext && but.ext.length)));
  if (!faits.length && !hasBut) return "";
  const c = (k) => (clubs && clubs[k]) || { nom: String(k || "").split(":").pop() };
  let html = `<section class="facteurs-cles"><h3>Facteurs clés du match</h3>`;
  if (faits.length) {
    html += `<ul class="liste-facteurs">${faits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  }
  if (hasBut) {
    const col = (nom, liste) => (!liste?.length ? "" : `<div><p class="buteurs-equipe">${esc(nom)}</p><ul class="liste-buteurs">${
      liste.map((b) => `<li><span>${esc(b.nom)}</span><b>${pct(b.p)}</b></li>`).join("")}</ul></div>`);
    html += `<div class="buteurs-grille">${col(c(m.home).nom, but.dom)}${col(c(m.away).nom, but.ext)}</div>`
      + `<p class="note">Probabilité qu'un joueur marque au moins un but (loi de Poisson d'après les buts attendus de son équipe et sa part des buts de la saison). Sont écartés les absents signalés et les joueurs peu utilisés.</p>`;
  }
  return `${html}</section>`;
}

/* ---------- une ligne de match ; `detail` (HTML) la rend dépliable, `lien` en fait un lien vers la page de la compétition.
   Chaque nom d'équipe porte une étoile quand favoris.js est chargé. */
const etoileClub = (k, nom) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, nom, { mini: true }));
function ligneMatch(m, clubs, { detail = null, lien = null, comp = null, jourDansHeure = false, prefixe = "m", centre: impose = null, etoiles = true } = {}) {
  const c = (k) => clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };
  const dom = c(m.home), ext = c(m.away);
  let centre, sous = "";
  if (m.etat === "joue" && !m.score) {
    // match du jour passé à « joué » sans que son score soit publié (matchs_du_jour) : le relais du direct donne le score final
    centre = `<span class="m-etat">terminé</span>`;
  } else if (m.etat === "joue" || m.score) {
    const s = m.score;
    if (m.p) {
      const y = issue(s), verbe = m.source === "publie" ? "annoncé" : "estimé";
      const txt = `${y === 1 ? "nul " : ""}${verbe} à ${pct(m.p[y])}`;
      sous = m.surprise ? `<small class="surprise">surprise : ${txt}</small>` : `<small>${txt}</small>`;
    }
    centre = `<span class="m-score">${nombre(s[0])} - ${nombre(s[1])}${sous}</span>`;
  } else if (m.etat === "en_cours") {
    centre = `<span class="m-etat">en cours</span>`;
  } else if (m.etat === "en_attente") {
    centre = `<span class="m-etat">résultat en attente</span>`;
  } else if (m.etat === "reporte") {
    centre = `<span class="m-etat">reporté, date à fixer</span>`;
  } else {
    centre = `${barre(m.p, dom.nom, ext.nom)}${badgeConfiance(m)}`;
  }
  if (impose !== null) centre = impose;
  const etoileDe = (k, nom) => (etoiles ? etoileClub(k, nom) : "");
  const h = m.kickoff ? heure(m.kickoff) : "–";
  const quandTxt = jourDansHeure && m.jour ? `<small>${esc(midi(m.jour).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" }))}</small>` : "";
  const compTxt = comp ? `<small class="m-comp">${esc(comp)}</small>` : "";
  // clubs du match, lus par les scripts du football (favoris) pour repérer les lignes concernées
  const clubsData = ` data-home="${esc(m.home)}" data-away="${esc(m.away)}"`;
  const corps = `<span class="m-heure">${esc(h)}${quandTxt}${compTxt}</span>
      <span class="m-club m-dom">${etoileDe(m.home, dom.nom)}<b>${esc(dom.nom)}</b>${ecusson(dom)}</span>
      <span class="m-centre">${centre}</span>
      <span class="m-club m-ext">${ecusson(ext)}<b>${esc(ext.nom)}</b>${etoileDe(m.away, ext.nom)}</span>`;
  // le lien recouvre la ligne sans la contenir : les étoiles restent des boutons à part entière
  if (lien) return `<li class="match" data-match="${esc(cleId(m.id))}"${clubsData}><div class="m-ligne m-cliquable"><a class="m-lien" href="${esc(lien)}"><span class="cache">${esc(dom.nom)} contre ${esc(ext.nom)} : détail du match</span></a>${corps}</div></li>`;
  if (detail === null) return `<li class="match" data-match="${esc(cleId(m.id))}"${clubsData}><div class="m-ligne">${corps}</div></li>`;
  return `<li class="match" data-match="${esc(cleId(m.id))}"${clubsData}><details id="${prefixe}-${esc(cleId(m.id))}"><summary class="m-ligne">${corps}</summary><div class="m-detail">${detail}</div></details></li>`;
}
const cleId = (id) => String(id).replace(/[^A-Za-z0-9]+/g, "-");

/* explique « annoncé » et « estimé » quand une liste contient des matchs joués avant l'ouverture du journal */
const legendeJoues = (liste) => (liste.some((m) => m.etat === "joue" && m.p && m.source !== "publie")
  ? "« Annoncé » : pronostic publié avant le match. « Estimé » : reconstitution faite sans connaître le résultat." : "");

/* accord en nombre : zéro et un au singulier */
const accord = (n, mot, pluriel = `${mot}s`) => `${nombre(n)} ${Math.abs(n) < 2 ? mot : pluriel}`;

/* ---------- matchs groupés par jour */
function parJour(matchs, rendu) {
  let html = "", jour = null, ouvert = false;
  for (const m of matchs) {
    const j = m.jour || "à fixer";
    if (j !== jour) {
      if (ouvert) html += "</ul>";
      html += `<h3 class="jour-titre">${esc(m.jour ? jourLong(m.jour) : "Date à fixer")}</h3><ul class="matchs">`;
      jour = j; ouvert = true;
    }
    html += rendu(m);
  }
  return ouvert ? `${html}</ul>` : html;
}

/* ---------- recherche de clubs : un mot court (« OM ») doit correspondre exactement, sinon un début de mot suffit */
const SURNOMS = { "FRA:Paris SG": "psg paris", "FRA:Marseille": "om", "FRA:Lyon": "ol", "FRA:Lille": "losc", "ESP:Barcelona": "barca",
  "ENG:Man United": "man utd manchester united", "ENG:Man City": "man city", "GER:Bayern Munich": "bayern munchen",
  "ESP:Ath Madrid": "atletico atleti", "ITA:Inter": "inter", "ENG:Tottenham": "spurs", "GER:Dortmund": "bvb" };
function indexClubs(clubs) {
  const idx = {};
  for (const [k, c] of Object.entries(clubs)) idx[k] = new Set(plier(`${c.nom} ${k.split(":").pop()} ${c.sigle} ${SURNOMS[k] || ""}`).split(" ").filter(Boolean));
  return idx;
}
const mots = (q) => plier(q).split(" ").filter(Boolean);
const aLeMot = (idx, k, w) => (w.length <= 3 ? idx[k].has(w) : [...idx[k]].some((t) => t.startsWith(w)));
const clubsPour = (idx, ws) => Object.keys(idx).filter((k) => ws.every((w) => aLeMot(idx, k, w)));
/* la requête désigne un club (« Lille »), ou deux (« Lille Bayern ») */
function lireRequete(idx, q) {
  const ws = mots(q);
  if (!ws.length) return null;
  const un = clubsPour(idx, ws);
  if (un.length) return { un: new Set(un) };
  const deux = [];
  for (let i = 1; i < ws.length; i++) {
    const a = clubsPour(idx, ws.slice(0, i)), b = clubsPour(idx, ws.slice(i));
    if (a.length && b.length) deux.push([new Set(a), new Set(b)]);
  }
  return { deux };
}
function correspond(req, m) {
  if (!req) return true;
  if (req.un) return req.un.has(m.home) || req.un.has(m.away);
  return req.deux.some(([a, b]) => (a.has(m.home) && b.has(m.away)) || (b.has(m.home) && a.has(m.away)));
}

/* ---------- compétitions (accueil et page football) */
function listeCompetitions(el, comps) {
  el.innerHTML = comps.map((c) => {
    const finJ = (j) => jourLong(j).replace(/^\S+ /, "");
    const memeMois = c.du && c.au && c.du.slice(0, 7) === c.au.slice(0, 7);
    const dates = c.du ? (c.du === c.au ? jourLong(c.du) : `du ${memeMois ? midi(c.du).getDate() : finJ(c.du)} au ${finJ(c.au)}`) : "";
    const prochain = c.prochaine && dates ? `${esc(c.prochaine)}, ${esc(dates)}` : c.a_venir ? `${c.a_venir} matchs à venir` : "Pas de match annoncé pour l'instant";
    let tete = "";
    if (c.favori && c.zone_favori === "Titre") tete = `Favori pour le titre : <strong>${esc(c.favori.nom)}</strong> (${pct(c.favori.p)})`;
    else if (c.favori) tete = `Le plus sûr du top 8 : <strong>${esc(c.favori.nom)}</strong> (${pct(c.favori.p)})`;
    else if (c.leader_nom) tete = `En tête : <strong>${esc(c.leader_nom)}</strong>`;
    return `<li><a href="${ROOT}foot/${esc(c.slug)}.html"><b>${esc(c.nom)}</b><span>${prochain}</span><span>${tete}</span></a></li>`;
  }).join("");
}
