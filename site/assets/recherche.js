/* Recherche de matchs : lit data/recherche/*.json produits par le calcul automatique. */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const col = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : null);
const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : "–");
const pct = (p) => (p == null ? "–" : p < 0.005 ? "<1 %" : p >= 0.995 ? ">99 %" : `${Math.round(p * 100)} %`);
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ");
const PAGE = 24;
const S = { m: null, p: null, comp: "", q: "", shown: PAGE, list: [] };
// surnoms courants, pour trouver un club comme on le dit
const ALIASES = { "FRA:Paris SG": "psg paris", "FRA:Marseille": "om", "FRA:Lyon": "ol", "FRA:Lille": "losc", "ESP:Barcelona": "barca barça",
  "ENG:Man United": "man utd manchester united", "ENG:Man City": "man city", "GER:Bayern Munich": "bayern munich munchen",
  "ESP:Ath Madrid": "atletico atleti", "ITA:Inter": "inter", "ENG:Tottenham": "spurs", "GER:Dortmund": "bvb" };

async function getJSON(name) {
  const r = await fetch(`data/recherche/${name}.json`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${name}.json : ${r.status}`);
  return r.json();
}
const club = (k) => S.m.clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };
const name = (k) => club(k).nom;
const compName = (c) => S.m.competitions[c] || c;
function badge(k) {
  const c = club(k);
  if (c.logo) return `<img class="crest" src="${esc(c.logo)}" alt="" width="28" height="28">`;
  const bg = col(c.couleur), fg = col(c.couleur2);
  const style = bg ? ` style="background:${bg};color:${fg || "#ffffff"}"` : "";
  const isLong = String(c.sigle).length > 3;
  return `<span class="crest pastille${bg ? "" : " neutre"}${isLong ? " long" : ""}"${style} aria-hidden="true">${esc(c.sigle)}</span>`;
}
const when = (iso) => new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
function kick(x) {
  if (x.kickoff) return when(x.kickoff);
  if (!x.jour) return "date à fixer";
  return `${new Date(`${x.jour}T12:00:00`).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })}, heure à confirmer`;
}
const day = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });

function probBar(p, home, away) {
  const [h, d, a] = p;
  const c1 = col(club(home).couleur) || "var(--teal)", c2 = col(club(away).couleur) || "#e5e7eb";
  return `<div class="pbar" role="img" aria-label="${esc(name(home))} ${pct(h)}, nul ${pct(d)}, ${esc(name(away))} ${pct(a)}">
    <span style="width:${(h * 100).toFixed(1)}%;background:${c1}"></span>
    <span class="draw" style="width:${(d * 100).toFixed(1)}%"></span>
    <span style="width:${(a * 100).toFixed(1)}%;background:${c2}"></span></div>
    <div class="plabels"><span>${pct(h)}</span><span>Nul ${pct(d)}</span><span>${pct(a)}</span></div>`;
}
const matchKey = (x) => `${x.home}|${x.away}|${x.jour || ""}`;

/* ---------- recherche */
let index = {};
function buildIndex() {
  index = {};
  for (const [k, c] of Object.entries(S.m.clubs)) index[k] = fold(`${c.nom} ${k.split(":").pop()} ${c.sigle} ${ALIASES[k] || ""}`);
}
const tokens = (q) => fold(q).split(" ").filter((t) => t.length > 1 || /\d/.test(t));
function filter() {
  const t = tokens(S.q);
  return S.m.matchs.filter((x) => (!S.comp || x.competition === S.comp)
    && t.every((w) => index[x.home]?.includes(w) || index[x.away]?.includes(w)));
}
function render() {
  S.list = filter();
  const t = tokens(S.q);
  const shown = S.list.slice(0, S.shown);
  $("#note").textContent = !S.list.length
    ? (t.length ? "Aucun match à venir pour cette recherche. Vérifie l'orthographe, ou essaie un seul club." : "Aucun match à venir.")
    : t.length ? `${S.list.length} match${S.list.length > 1 ? "s" : ""} à venir.` : "Prochains matchs, toutes compétitions. Heures à l'heure de ton appareil.";
  $("#results").innerHTML = shown.map((x) => `<li class="fixture clickable" tabindex="0" role="button" data-key="${esc(matchKey(x))}" aria-label="Voir le détail de ${esc(name(x.home))} contre ${esc(name(x.away))}">
    <p class="tiny muted comp-line"><span class="comp">${esc(compName(x.competition))}</span>${esc(kick(x))}</p>
    <div class="teams"><span class="team-l">${badge(x.home)}<b>${esc(name(x.home))}</b></span><span class="mid"></span>
      <span class="team-r"><b>${esc(name(x.away))}</b>${badge(x.away)}</span></div>
    ${probBar(x.p, x.home, x.away)}</li>`).join("");
  $("#more").hidden = S.list.length <= S.shown;
}
function suggest() {
  const t = tokens(S.q), box = $("#suggest");
  const hits = t.length ? Object.keys(S.m.clubs).filter((k) => t.every((w) => index[k].includes(w))).slice(0, 8) : [];
  box.innerHTML = hits.map((k, i) => `<li role="option" id="sg-${i}" data-club="${esc(k)}" tabindex="-1">${badge(k)}<span>${esc(name(k))}</span>
    <span class="tiny muted">${esc(club(k).competitions.map(compName).join(", "))}</span></li>`).join("");
  box.hidden = !hits.length || (hits.length === 1 && fold(name(hits[0])) === fold(S.q));
  $("#q").setAttribute("aria-expanded", String(!box.hidden));
}

/* ---------- détail */
function showDetail(key, isScroll = true) {
  const x = S.m.matchs.find((m) => matchKey(m) === key);
  if (!x) return;
  const sc = x.scores.map((s) => `<b>${esc(s.score)}</b> (${pct(s.p)})`).join(", ");
  const h2h = x.h2h || [];
  let wh = 0, d = 0, wa = 0;
  h2h.forEach(([, h, , a, b]) => { const gh = h === x.home ? a : b, ga = h === x.home ? b : a; if (gh > ga) wh++; else if (gh < ga) wa++; else d++; });
  $("#d-title").textContent = `${name(x.home)} - ${name(x.away)}`;
  $("#d-body").innerHTML = `<p class="muted small">${esc(compName(x.competition))}, ${esc(kick(x))}.</p>
    <div class="teams big-teams"><span class="team-l">${badge(x.home)}<b>${esc(name(x.home))}</b></span><span class="mid"></span>
      <span class="team-r"><b>${esc(name(x.away))}</b>${badge(x.away)}</span></div>
    ${probBar(x.p, x.home, x.away)}
    <div class="tiles three mt">
      <div class="tile"><p class="big">${pct(x.p[0])}</p><p>victoire ${esc(name(x.home))}</p></div>
      <div class="tile"><p class="big">${pct(x.p[1])}</p><p>match nul (90 minutes)</p></div>
      <div class="tile"><p class="big">${pct(x.p[2])}</p><p>victoire ${esc(name(x.away))}</p></div>
    </div>
    <p>Scores les plus probables : ${sc}. Buts attendus : ${Number(x.xg[0]).toFixed(1)} pour ${esc(name(x.home))}, ${Number(x.xg[1]).toFixed(1)} pour ${esc(name(x.away))}.</p>
    <p class="muted small">${x.avec_cotes ? "Cotes d'avant-match comprises : les blessures et l'actualité connues sont prises en compte."
      : "Statistiques seules : les cotes d'avant-match ne sont pas encore publiées. Les blessures et l'actualité récentes ne sont pas prises en compte."}</p>
    <h3 class="mt">Derniers face-à-face</h3>
    ${h2h.length ? `<p class="small">Sur les ${h2h.length} derniers : ${wh} victoire${wh > 1 ? "s" : ""} ${esc(name(x.home))}, ${d} nul${d > 1 ? "s" : ""}, ${wa} victoire${wa > 1 ? "s" : ""} ${esc(name(x.away))}.</p>
      <div class="scroll"><table class="table"><thead><tr><th>Date</th><th>Compétition</th><th>Domicile</th><th class="num">Score</th><th>Extérieur</th></tr></thead><tbody>${h2h.map(([dt, h, a, gh, ga, c]) => `<tr>
        <td class="nowrap">${esc(day(dt))}</td><td class="muted">${esc(S.m.competitions[c] || "Championnat")}</td>
        <td><span class="driver">${badge(h)}<b>${esc(name(h))}</b></span></td><td class="num">${n(gh)} - ${n(ga)}</td>
        <td><span class="driver">${badge(a)}<b>${esc(name(a))}</b></span></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="empty">Aucun match entre ces deux clubs depuis 2010 dans nos données.</p>`}`;
  $("#detail").hidden = false;
  history.replaceState(null, "", `#match=${encodeURIComponent(key)}`);
  if (isScroll) $("#detail").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

/* ---------- bilan */
function renderBilan() {
  const rows = S.p.competitions;
  $("#f-note").textContent = `Chaque semaine depuis ${S.p.saisons_test[0]}, le modèle est rejoué avec les seuls matchs joués avant, comme s'il avait tourné à l'époque ; ses réglages ont été choisis sur la saison 2021-22. Score RPS : plus il est bas, meilleur est le pronostic. « Habitudes » : donner à chaque match les pourcentages habituels domicile, nul, extérieur.`;
  $("#f-table").innerHTML = `<thead><tr><th>Compétition</th><th class="num">Matchs</th><th class="num">Nos statistiques</th><th class="num">Avec les cotes</th><th class="num">Marché seul</th><th class="num">Habitudes</th><th class="num">Bon favori</th></tr></thead><tbody>${rows.map((r) => `<tr>
    <td>${esc(r.nom)}</td><td class="num">${n(r.matchs).toLocaleString("fr-FR")}</td><td class="num">${r.modele.rps.toFixed(3)}</td>
    <td class="num">${r.avec_cotes ? r.avec_cotes.rps.toFixed(3) : "–"}</td><td class="num">${r.marche ? r.marche.rps.toFixed(3) : "–"}</td>
    <td class="num">${r.habitudes.rps.toFixed(3)}</td><td class="num">${Math.round((r.avec_cotes || r.modele).bons_favoris * 100)} %</td></tr>`).join("")}</tbody>
    <caption class="tiny muted">En coupe d'Europe, pas d'historique de cotes gratuit : seules nos statistiques sont jugées.</caption>`;
  if (Number.isFinite(S.p.part_marche)) $("#m-part").textContent = `elles comptent pour environ ${Math.round(S.p.part_marche * 100)} % du pronostic final`;
}

/* ---------- démarrage */
async function main() {
  try {
    [S.m, S.p] = await Promise.all(["matchs", "performance"].map(getJSON));
  } catch (err) {
    $("#note").innerHTML = `<span class="error">Les données n'ont pas pu être chargées (${esc(err.message)}). Recharge la page dans quelques minutes.</span>`;
    return;
  }
  buildIndex();
  const present = new Set(S.m.matchs.map((x) => x.competition));
  const comps = Object.keys(S.m.competitions);
  $("#chips").innerHTML = [["", "Toutes"], ...comps.map((c) => [c, compName(c)])].map(([c, l]) => {
    const isOn = present.has(c) || !c;
    return `<button type="button" class="chip" data-comp="${esc(c)}" aria-pressed="${c === "" ? "true" : "false"}"${isOn ? "" : " disabled title=\"Bientôt\""}>${esc(l)}${isOn ? "" : " (bientôt)"}</button>`;
  }).join("");
  $("#m-updated").textContent = `Dernière mise à jour : ${when(S.m.maj_utc)}.`;
  render(); renderBilan();
  const q = $("#q");
  q.addEventListener("input", () => { S.q = q.value; S.shown = PAGE; render(); suggest(); });
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
    q.value = name(li.dataset.club); S.q = q.value; S.shown = PAGE;
    $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); render(); q.focus();
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) { $("#suggest").hidden = true; q.setAttribute("aria-expanded", "false"); } });
  $("#chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-comp]");
    if (!b || b.disabled) return;
    S.comp = b.dataset.comp; S.shown = PAGE;
    document.querySelectorAll("#chips button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    render();
  });
  $("#more").addEventListener("click", () => { S.shown += PAGE; render(); });
  $("#results").addEventListener("click", (e) => { const li = e.target.closest("li[data-key]"); if (li) showDetail(li.dataset.key); });
  $("#results").addEventListener("keydown", (e) => {
    const li = e.target.closest("li[data-key]");
    if (li && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showDetail(li.dataset.key); }
  });
  $("#d-close").addEventListener("click", () => { $("#detail").hidden = true; history.replaceState(null, "", location.pathname); q.focus(); });
  const h = decodeURIComponent(location.hash.replace(/^#match=/, ""));
  if (location.hash.startsWith("#match=")) showDetail(h, false);
}
main();
