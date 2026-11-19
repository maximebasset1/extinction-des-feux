/* Extinction des feux : lit les fichiers data/*.json produits chaque jour par le calcul automatique. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SESSION_NAMES = { FP1: "Essais libres 1", FP2: "Essais libres 2", FP3: "Essais libres 3",
  SQ: "Qualif sprint", S: "Course sprint", Q: "Qualifications", R: "Course" };
const SESSION_ORDER = ["FP1", "SQ", "FP2", "S", "FP3", "Q", "R"];
const state = { kind: "pole", moment: "apres", next: null, history: null, perf: null, drivers: null, journal: null, season: null, gp: null, showAll: false };

const NUM_FR = { 2: "Deux", 3: "Trois", 4: "Quatre", 5: "Cinq", 6: "Six", 7: "Sept", 8: "Huit", 9: "Neuf" };
const pct = (p) => (p == null ? "–" : p < 0.01 ? "< 1 %" : `${Math.round(p * 100)} %`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const col = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#888888"); // couleur venue des données : vérifiée
const SHORT = { "Grande-Bretagne": "G.-Bretagne", "Arabie saoudite": "Arabie s.", "Émilie-Romagne": "Imola",
  "Espagne (Madrid)": "Madrid", "Azerbaïdjan": "Bakou" };
const DURATION_MIN = { FP1: 60, FP2: 60, FP3: 60, SQ: 45, S: 60, Q: 60, R: 120 };
// « à Las Vegas », « au Qatar », « en Australie » ; « Grand Prix du Japon », « d'Italie »…
const PLACES = { "Las Vegas": ["à", "de"], Qatar: ["au", "du"], "Abou Dabi": ["à", "d'"], Australie: ["en", "d'"],
  Chine: ["en", "de"], Japon: ["au", "du"], "Bahreïn": ["à", "de"], "Arabie saoudite": ["en", "d'"], Miami: ["à", "de"],
  "Émilie-Romagne": ["en", "d'"], Monaco: ["à", "de"], Espagne: ["en", "d'"], Barcelone: ["à", "de"], Canada: ["au", "du"],
  Autriche: ["en", "d'"], "Grande-Bretagne": ["en", "de"], Belgique: ["en", "de"], Hongrie: ["en", "de"],
  "Pays-Bas": ["aux", "des"], Italie: ["en", "d'"], "Azerbaïdjan": ["en", "d'"], Singapour: ["à", "de"],
  "États-Unis": ["aux", "des"], Mexique: ["au", "du"], "São Paulo": ["à", "de"], Portugal: ["au", "du"], Turquie: ["en", "de"] };
const join = (w, name) => (w.endsWith("'") ? w + name : `${w} ${name}`);
function inPlace(name) {
  if (name === "Espagne (Madrid)") return "à Madrid";
  const p = PLACES[name];
  return join(p ? p[0] : "à", name);
}
function grandPrix(name) {
  if (name === "Espagne (Madrid)") return "Grand Prix d'Espagne, à Madrid";
  const p = PLACES[name];
  return `Grand Prix ${join(p ? p[1] : (/^[aeiouyéèêâîôûœh]/i.test(name) ? "d'" : "de"), name)}`;
}
const ordinal = (n) => (n === 1 ? "1er" : `${n}e`);
const fmtDate = (iso, opts) => new Intl.DateTimeFormat("fr-FR", opts).format(new Date(iso));
const when = (iso) => fmtDate(iso, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

function countdown(iso) {
  const ms = new Date(iso) - Date.now();
  if (ms <= 0) return null;
  const h = Math.floor(ms / 3.6e6), m = Math.floor((ms % 3.6e6) / 6e4);
  if (h >= 48) return `dans ${Math.round(h / 24)} jours`;
  return h > 0 ? `dans ${h} h ${String(m).padStart(2, "0")}` : `dans ${m} min`;
}

async function getJSON(name) {
  const r = await fetch(`data/${name}.json`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${name}.json : ${r.status}`);
  return r.json();
}

/* ---------- prochain Grand Prix */
function poleList() {
  const n = state.next, hasAfter = n.pole.some((d) => d.apres != null);
  const key = state.moment === "apres" && hasAfter ? "apres" : "avant";
  return { key, list: [...n.pole].sort((a, b) => (b[key] ?? 0) - (a[key] ?? 0)) };
}

function raceOver(n) {
  const r = n.sessions && n.sessions.R;
  return n.saison_terminee || (r && Date.now() > new Date(r).getTime() + DURATION_MIN.R * 6e4);
}

function slots(rows, label) {
  return rows.slice(0, 6).map((d, i) => `
    <li><div class="slot${i === 0 ? " p1" : ""}">
      <span class="pos">${label(d, i)}</span>
      <span class="who">${esc(d.famille)}</span>
      <span class="team"><i style="background:${col(d.couleur)}"></i>${esc(d.equipe)}</span>
      ${d.p != null ? `<span class="pct" aria-label="${pct(d.p)} de chances">${pct(d.p)}</span>` : ""}
    </div></li>`).join("");
}

function renderHero() {
  const n = state.next, grid = $("#grid"), note = $("#grid-note"), sub = [];
  const q = n.sessions.Q;

  if (raceOver(n)) {
    $("#titre-gp").textContent = n.saison_terminee ? `La saison ${n.saison} est terminée` : `Course terminée ${inPlace(n.gp_fr)}`;
    const arr = n.arrivee || [];
    const win = arr.find((d) => d.place === 1);
    if (win) sub.push(`Victoire de <strong>${esc(win.nom)}</strong>${n.poleman ? `, pole de <strong>${esc(n.poleman.nom)}</strong>` : ""}.`);
    else sub.push("Le résultat officiel arrive dans quelques heures.");
    sub.push(n.saison_terminee ? "Le prochain pronostic apparaîtra ici dès que le calendrier de la saison suivante sera publié."
      : "Le pronostic du prochain Grand Prix sera en ligne dans quelques heures.");
    $("#hero-sub").innerHTML = sub.join(" ");
    grid.setAttribute("aria-label", "Arrivée de la course");
    grid.innerHTML = slots(arr, (d) => ordinal(d.place));
    note.innerHTML = arr.length ? `<p>L'arrivée des six premiers du ${esc(grandPrix(n.gp_fr))}.</p>
      <p>Les pronostics publiés avant la qualif et la course sont comparés au résultat dans le journal, plus bas.</p>` : "";
    return;
  }

  if (!n.pole.length) {
    $("#titre-gp").textContent = grandPrix(n.gp_fr);
    $("#hero-sub").textContent = "Les pronostics sont en cours de calcul. Reviens dans quelques heures.";
    grid.innerHTML = ""; note.innerHTML = "";
    return;
  }

  if (n.qualif_disputee) {
    $("#titre-gp").textContent = `Qui gagnera ${inPlace(n.gp_fr)} ?`;
    if (n.poleman) sub.push(`<strong>${esc(n.poleman.nom)}</strong> a signé la pole.`);
    sub.push("Les chances de victoire tiennent compte de la grille de départ.");
    const rows = n.victoire.map((d) => ({ ...d, p: d.proba }));
    const ordered = rows.some((d) => d.grille) ? [...rows].sort((a, b) => (a.grille ?? 99) - (b.grille ?? 99)) : rows;
    grid.setAttribute("aria-label", "Les six premiers de la grille de départ et leurs chances de victoire");
    grid.innerHTML = slots(ordered, (d, i) => `P${d.grille ?? i + 1}`);
    const top = [...rows].sort((a, b) => b.p - a.p)[0];
    note.innerHTML = `<p>Voici la vraie grille de départ. Le pourcentage indique les chances de victoire de chaque pilote.</p>
      <p><strong>${esc(top.nom)}</strong> est le favori, avec ${pct(top.p)} de chances${top.grille ? `, en partant ${top.grille === 1 ? "de la pole" : `${ordinal(top.grille)}`}` : ""}.</p>
      <p>En course, un départ raté, une stratégie ou une voiture de sécurité suffisent à tout changer.</p>`;
  } else {
    const { key, list } = poleList();
    $("#titre-gp").textContent = `Qui partira en pole ${inPlace(n.gp_fr)} ?`;
    if (q) sub.push(`${esc(grandPrix(n.gp_fr))} ${n.saison}, qualifications ${when(q)}${n.horaires_estimes ? " (horaire encore estimé)" : ""}.`);
    sub.push(n.statut.startsWith("avant") ? "Pronostic établi avant les essais libres ; il sera mis à jour après chaque séance."
      : `Pronostic mis à jour ${esc(n.statut)}.`);
    const rows = list.map((d) => ({ ...d, p: d[key] }));
    grid.setAttribute("aria-label", "Grille de départ la plus probable");
    grid.innerHTML = slots(rows, (d, i) => `P${i + 1}`);
    const top = rows[0], open = rows.filter((d) => d.p >= 0.1).length;
    const flat = rows.length > 1 && top.p - rows[rows.length - 1].p < 0.02;
    const spread = flat ? "Pour l'instant, le modèle ne départage pas les pilotes : ils ont à peu près tous les mêmes chances. Les essais libres feront la différence."
      : open > 1 ? `${NUM_FR[open] || open} pilotes ont au moins une chance sur dix : rien n'est joué.`
      : top.p >= 0.3 ? "Un favori net se détache."
      : "Aucun pilote n'atteint une chance sur dix : la pole est très ouverte.";
    note.innerHTML = `
      ${flat ? "" : `<p><strong>${esc(top.nom)}</strong> est le favori pour la pole, avec ${pct(top.p)} de chances.</p>`}
      <p>${spread}</p>
      <p>Cette grille classe les pilotes selon leurs chances. Ce n'est pas un résultat : un tour raté suffit à tout changer.</p>`;
  }
  if (n.debut_saison) sub.push("Début de saison : le modèle manque encore de repères sur les voitures de cette année, ses pronostics sont plus incertains.");
  $("#hero-sub").innerHTML = sub.join(" ");
}

function renderWeekend() {
  const s = state.next.sessions, keys = SESSION_ORDER.filter((k) => s[k]);
  const box = $("#weekend");
  box.style.setProperty("--n", keys.length);
  const now = Date.now();
  const nextKey = keys.find((k) => new Date(s[k]) > now);
  box.innerHTML = keys.map((k) => {
    const start = new Date(s[k]).getTime(), end = start + (DURATION_MIN[k] || 60) * 6e4;
    const live = start <= now && now < end, done = now >= end, next = k === nextKey;
    const cd = next ? countdown(s[k]) : null;
    return `<div class="session${done ? " done" : ""}${next || live ? " next" : ""}">
      <b>${SESSION_NAMES[k]}</b>
      <span>${fmtDate(s[k], { weekday: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
      ${live ? '<span class="soon">en cours</span>' : cd ? `<span class="soon">${cd}</span>` : done ? "<span>terminée</span>" : ""}
    </div>`;
  }).join("");
  let tz = "";
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { tz = ""; }
  $("#tz-note").hidden = !keys.length;
  $("#tz-note").textContent = `Horaires à l'heure de ton appareil${tz ? ` (${tz.replace(/_/g, " ")})` : ""}${state.next.horaires_estimes ? ", encore estimés" : ""}.`;
}

function renderBars() {
  const n = state.next;
  const hasAfter = n.pole.some((d) => d.apres != null);
  $("#moment-switch").hidden = state.kind !== "pole" || !hasAfter;
  let rows, explain;
  if (state.kind === "pole") {
    const { key, list } = poleList();
    rows = list.map((d) => ({ ...d, p: d[key] }));
    explain = key === "apres" ? "Probabilité de faire la pole, en tenant compte des essais libres déjà disputés."
      : "Probabilité de faire la pole, d'après la forme des derniers Grands Prix.";
  } else {
    rows = [...n.victoire].sort((a, b) => b.proba - a.proba).map((d) => ({ ...d, p: d.proba }));
    explain = n.qualif_disputee ? "Probabilité de gagner la course, d'après la grille de départ."
      : "Probabilité de gagner la course. La grille n'est pas encore connue : on simule des milliers de qualifications possibles.";
  }
  $("#chances-explain").textContent = explain;
  if (!rows.length) { $("#bars").innerHTML = '<li class="empty">Les chances seront affichées dès que le calcul sera terminé.</li>'; $("#bars-more").hidden = true; return; }
  const max = Math.max(...rows.map((r) => r.p ?? 0), 0.01);
  const bars = $("#bars");
  bars.classList.toggle("short", !state.showAll);
  bars.innerHTML = rows.map((d, i) => `
    <li class="bar">
      <span class="rk">${i + 1}</span>
      <span class="nm">${esc(d.nom)}<small>${esc(d.equipe)}${state.kind === "victoire" && d.grille ? `, ${ordinal(d.grille)} sur la grille` : ""}</small></span>
      <span class="track" aria-hidden="true"><span class="fill" style="display:block;width:${(100 * (d.p ?? 0)) / max}%;background:${col(d.couleur)}"></span></span>
      <span class="vl">${pct(d.p)}</span>
    </li>`).join("");
  const more = $("#bars-more");
  more.hidden = rows.length <= 10;
  more.textContent = state.showAll ? "Afficher les dix premiers" : "Voir tous les pilotes";
  more.setAttribute("aria-expanded", String(state.showAll));
}

/* ---------- historique */
function seasonGPs() {
  return state.history.saisons[state.season] || [];
}
function poleChance(gp) {
  const d = gp.pilotes.find((p) => p.code === gp.poleman);
  return d ? (d.apres ?? d.avant ?? 0) : 0;
}
function rankOf(gp, code, key = "apres") {
  const sorted = [...gp.pilotes].sort((a, b) => (b[key] ?? b.avant ?? 0) - (a[key] ?? a.avant ?? 0));
  return sorted.findIndex((p) => p.code === code) + 1;
}
function person(code) {
  return state.history.pilotes[code] || { nom: code, famille: code, couleur: "#888888" };
}

function renderSeasonSwitch() {
  const seasons = Object.keys(state.history.saisons).sort().reverse();
  const box = $("#season-switch");
  box.innerHTML = seasons.map((s) => `<button type="button" data-season="${s}" aria-pressed="${s === state.season}">${s}</button>`).join("");
}

function renderStrip() {
  const gps = seasonGPs();
  const strip = $("#strip");
  const maxP = 0.7;
  const rnd = gps.length ? 1 / gps[0].pilotes.length : 0.045;
  strip.innerHTML = `<div class="chance-line" style="bottom:calc(5.55rem + ${(rnd / maxP).toFixed(4)} * 9.4rem)" aria-hidden="true"></div>` +
    gps.map((g) => {
      const p = poleChance(g), c = g.poleman ? person(g.poleman).couleur : "#888888";
      const h = Math.max(2, (Math.min(p, maxP) / maxP) * 100);
      const who = g.poleman ? `${person(g.poleman).nom} en pole, le modèle lui donnait ${pct(p)}` : "poleman inconnu";
      return `<div role="listitem"><button type="button" class="gpbar" data-gp="${esc(g.gp)}" aria-pressed="${g.gp === state.gp}"
        aria-label="${esc(g.gp_fr)} : ${esc(who)}">
        <span class="col-area"><span class="col" style="height:${h.toFixed(1)}%;background:${col(c)}"></span></span>
        <span class="lab">${esc(SHORT[g.gp_fr] || g.gp_fr)}</span></button></div>`;
    }).join("");
}

function scrollStripToSelection() {
  requestAnimationFrame(() => {
    const wrap = $(".strip-wrap"), btn = state.gp && $(`[data-gp="${CSS.escape(state.gp)}"]`);
    if (!wrap || !btn) return;
    const w = wrap.getBoundingClientRect(), r = btn.getBoundingClientRect();
    if (r.right > w.right) wrap.scrollLeft += r.right - w.right + 24;
    else if (r.left < w.left) wrap.scrollLeft -= w.left - r.left + 24;
  });
}

function renderDetail() {
  const g = seasonGPs().find((x) => x.gp === state.gp);
  const box = $("#gp-detail");
  if (!g) { box.innerHTML = ""; return; }
  if (!g.poleman) { box.innerHTML = `<div><h3>${esc(g.gp_fr)} ${state.season}</h3><p class="facts">Le poleman de ce Grand Prix n'est pas encore connu.</p></div>`; return; }
  const pole = person(g.poleman), p = poleChance(g), rk = rankOf(g, g.poleman);
  const fav = [...g.pilotes].sort((a, b) => (b.apres ?? b.avant ?? 0) - (a.apres ?? a.avant ?? 0))[0];
  const win = g.vainqueur ? person(g.vainqueur) : null;
  const winRow = g.pilotes.find((x) => x.code === g.vainqueur);
  const verdict = rk === 1 ? "C'était son favori." : rk <= 3 ? `Il faisait partie de ses trois favoris (${ordinal(rk)}).` : `Il le classait seulement ${ordinal(rk)} : une surprise.`;
  const rows = [...g.pilotes].sort((a, b) => (b.apres ?? b.avant ?? 0) - (a.apres ?? a.avant ?? 0)).slice(0, 10);
  box.innerHTML = `
    <div>
      <h3>${esc(g.gp_fr)} ${state.season}</h3>
      <div class="facts">
        <p>Pole&nbsp;: <strong>${esc(pole.nom)}</strong>. Le modèle lui donnait <strong>${pct(p)}</strong> de chances. ${verdict}</p>
        <p>Son favori&nbsp;: ${esc(person(fav.code).nom)} (${pct(fav.apres ?? fav.avant)}).</p>
        ${win ? `<p>Victoire&nbsp;: <strong>${esc(win.nom)}</strong>${winRow && winRow.victoire != null ? `, à qui il donnait ${pct(winRow.victoire)} une fois la grille connue` : ""}.</p>` : ""}
        ${g.pluie ? "<p>Qualification sous la pluie : le modèle n'est pas fait pour ces conditions.</p>" : ""}
      </div>
    </div>
    <table class="mini">
      <caption class="visually-hidden">Les dix favoris du modèle pour la pole et leur résultat</caption>
      <thead><tr><th>Pilote</th><th class="num">Avant le week-end</th><th class="num">Après les essais</th><th class="num">Qualif</th><th class="num">Arrivée</th></tr></thead>
      <tbody>${rows.map((d) => `<tr class="${d.code === g.poleman ? "real" : ""}">
        <td><span class="chip" style="background:${col(person(d.code).couleur)}"></span>${esc(person(d.code).nom)}</td>
        <td class="num">${pct(d.avant)}</td><td class="num">${pct(d.apres)}</td>
        <td class="num">${d.qualif ? `P${Math.round(d.qualif)}` : "–"}</td><td class="num">${d.arrivee ? Math.round(d.arrivee) : "–"}</td></tr>`).join("")}
      </tbody></table>`;
}

/* ---------- bilan */
function renderVerdicts() {
  const seasons = state.history.saisons, gains = state.perf.gains;
  const past = [...(seasons["2024"] || []), ...(seasons["2025"] || [])];
  const top3 = past.filter((g) => g.poleman && rankOf(g, g.poleman, "avant") <= 3).length;
  const fav = past.filter((g) => g.poleman && rankOf(g, g.poleman, "avant") === 1).length;
  const g = (periode, contre) => gains.find((x) => x.modele === "avant le week-end" && x.periode === periode && x.contre.startsWith(contre));
  const solid = g("2024-2025", "hasard"), naive = g("2024-2025", "part"), recent = g("fin 2026", "hasard");
  const beats = (x) => x && x.ic95_bas > 0;
  const items = [
    { big: `${top3} sur ${past.length}`, txt: "En 2024 et 2025, le futur poleman figurait parmi les trois favoris du modèle, avant même les essais libres (reconstitution)." },
    { big: `${fav} sur ${past.length}`, txt: "Le favori du modèle a fait la pole. Un pronostic, pas une certitude." },
    beats(solid)
      ? { big: "Mieux que le hasard", txt: `Sur 2024-2025, les probabilités font nettement mieux qu'un tirage au sort${beats(naive) ? ", et mieux qu'une simple règle « celui qui a déjà fait le plus de poles »" : ""}. Ces saisons n'ont jamais servi à régler le modèle.` }
      : { big: "Pas mieux que le hasard", meh: true, txt: "Sur 2024-2025, on ne peut pas affirmer que les probabilités font mieux qu'un tirage au sort." },
    beats(recent)
      ? { big: "Fin 2026 : confirmé", txt: "Sur les dernières courses de 2026, jamais utilisées pour le régler, le modèle fait mieux que le hasard." }
      : { big: "Fin 2026 : rien de prouvé", meh: true, txt: "Sur les dernières courses de 2026, encore peu nombreuses et très imprévisibles, on ne peut pas encore affirmer que le modèle fait mieux que le hasard." },
  ];
  $("#verdicts").innerHTML = items.map((v) => `<div class="verdict${v.meh ? " meh" : ""}"><p>${v.big}</p><p>${v.txt}</p></div>`).join("");
}

function renderJournal() {
  const ev = state.journal.evaluations || [];
  const box = $("#journal");
  if (!ev.length) {
    box.innerHTML = `<p class="empty">Le journal démarre avec le ${esc(grandPrix(state.next.gp_fr))} ${state.next.saison}. Chaque pronostic publié avant une séance apparaîtra ici avec le résultat réel, dès qu'il sera connu.</p>`;
    return;
  }
  const kindFr = { pole: "Pole", victoire: "Victoire" };
  box.innerHTML = `<div class="table-scroll"><table class="mini">
    <thead><tr><th>Grand Prix</th><th>Pronostic</th><th>Publié</th><th>Résultat</th><th class="num">Chance donnée</th><th class="num">Rang</th></tr></thead>
    <tbody>${ev.slice().reverse().map((e) => `<tr>
      <td>${esc(e.gp_fr || e.grand_prix)} ${esc(e.season)}</td><td>${esc(kindFr[e.type] || e.type)}, ${esc(e.etape)}</td>
      <td>${fmtDate(e.publie_utc, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
      <td>${esc(person(e.reel).nom)}</td><td class="num">${pct(e.proba_du_vainqueur)}</td><td class="num">${esc(e.rang_du_vainqueur ?? "–")}</td></tr>`).join("")}
    </tbody></table></div>`;
}

/* ---------- pilotes */
function sparkline(d, gps) {
  const w = 220, h = 34, pad = 3, cap = 2;
  const pts = gps.map((g, i) => {
    const v = d.ecarts[g.gp];
    if (v == null) return null;
    const x = pad + (i * (w - 2 * pad)) / Math.max(1, gps.length - 1);
    const y = pad + (Math.min(v, cap) / cap) * (h - 2 * pad);
    return [x, y, v === 0];
  });
  const segs = [];
  let cur = [];
  pts.forEach((p) => { if (p) cur.push(p); else if (cur.length) { segs.push(cur); cur = []; } });
  if (cur.length) segs.push(cur);
  const lines = segs.map((s) => `<polyline fill="none" stroke="${col(d.couleur)}" stroke-width="2" points="${s.map((p) => p.slice(0, 2).join(",")).join(" ")}"/>`).join("");
  const poles = pts.filter((p) => p && p[2]).map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="#f2c200"/>`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="Écart au poleman sur la saison${poles ? ", points jaunes : poles" : ""}"><line x1="0" x2="${w}" y1="${pad}" y2="${pad}" stroke="rgba(239,238,232,.15)"/>${lines}${poles}</svg>`;
}

function renderDrivers() {
  const D = state.drivers;
  const rows = D.pilotes.filter((d) => Object.keys(d.ecarts).length >= 3);
  $("#titre-pilotes").textContent = `La saison ${D.saison} des pilotes en qualifications`;
  if (!rows.length) { $("#drivers").innerHTML = '<caption class="empty">Le tableau se remplira après les premières qualifications de la saison.</caption>'; return; }
  $("#drivers").innerHTML = `
    <caption class="visually-hidden">Saison ${D.saison} des pilotes en qualifications</caption>
    <thead><tr><th>Pilote</th><th class="num">Poles</th><th class="num">Victoires</th><th class="num">Podiums</th><th>Proximité de la pole, course après course</th></tr></thead>
    <tbody>${rows.map((d) => `<tr>
      <td class="nm"><span class="chip" style="background:${col(d.couleur)}"></span>${esc(d.nom)}<small>${esc(d.equipe)}</small></td>
      <td class="num big">${d.poles}</td><td class="num big">${d.victoires}</td><td class="num big">${d.podiums}</td>
      <td>${sparkline(d, D.gps)}</td></tr>`).join("")}</tbody>`;
}

/* ---------- interactions */
function bind() {
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.kind) { state.kind = b.dataset.kind; setPressed(b); renderBars(); }
    else if (b.dataset.moment) { state.moment = b.dataset.moment; setPressed(b); renderBars(); }
    else if (b.dataset.season) {
      state.season = b.dataset.season; setPressed(b);
      const gps = seasonGPs(); state.gp = gps.length ? gps[gps.length - 1].gp : null;
      renderStrip(); renderDetail(); scrollStripToSelection();
    } else if (b.dataset.gp) { state.gp = b.dataset.gp; renderStrip(); renderDetail(); $(`[data-gp="${CSS.escape(state.gp)}"]`)?.focus(); }
    else if (b.id === "bars-more") { state.showAll = !state.showAll; renderBars(); }
  });
}
function setPressed(btn) {
  btn.parentElement.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === btn)));
}

function startLights() {
  const lights = $(".start-lights"), grid = $("#grid");
  if (reduceMotion) return;
  grid.classList.add("waiting");
  lights.classList.add("on");
  setTimeout(() => grid.classList.remove("waiting"), 2950);
}

async function main() {
  bind();
  startLights();
  try {
    [state.next, state.history, state.perf, state.drivers, state.journal] = await Promise.all(
      ["next", "history", "performance", "drivers", "journal"].map(getJSON));
  } catch (err) {
    $("#hero-sub").innerHTML = `<span class="error">Les données n'ont pas pu être chargées (${esc(err.message)}). Recharge la page dans quelques minutes.</span>`;
    $("#grid").classList.remove("waiting");
    return;
  }
  if (!state.next.pole.some((d) => d.apres != null)) state.moment = "avant";
  const seasons = Object.keys(state.history.saisons).sort();
  state.season = seasons[seasons.length - 1];
  const gps = seasonGPs(); state.gp = gps.length ? gps[gps.length - 1].gp : null;
  if (state.next.qualif_disputee) {
    state.kind = "victoire";
    document.querySelectorAll("[data-kind]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === "victoire")));
  }
  renderHero(); renderWeekend(); renderBars();
  renderSeasonSwitch(); renderStrip(); renderDetail(); scrollStripToSelection();
  renderVerdicts(); renderJournal(); renderDrivers();
  const host = location.hostname;
  if (host.endsWith("github.io")) {
    const user = host.split(".")[0], repo = location.pathname.split("/").filter(Boolean)[0] || `${user}.github.io`;
    $("#foot-code").href = `https://github.com/${user}/${repo}`;
  } else { $("#foot-code").parentElement.hidden = true; }
  $("#foot-update").textContent = `Dernière mise à jour ${when(state.next.maj_utc)}. Le site se met à jour tout seul plusieurs fois par jour.`;
  setInterval(renderWeekend, 60000);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(scrollStripToSelection);
}
main();
