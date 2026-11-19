/* Predictions page in the PitLane Insider style. Reads the data/*.json files published by the engine. */
"use strict";

const $ = (s) => document.querySelector(s);
const SESSIONS = { FP1: "Practice 1", SQ: "Sprint quali", FP2: "Practice 2", S: "Sprint", FP3: "Practice 3", Q: "Qualifying", R: "Race" };
const ORDER = ["FP1", "SQ", "FP2", "S", "FP3", "Q", "R"];
const DURATION_MIN = { FP1: 60, FP2: 60, FP3: 60, SQ: 45, S: 60, Q: 60, R: 120 };
const state = { next: null, history: null, perf: null, journal: null, season: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const col = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#888888");
const pct = (p) => (p == null ? "–" : p < 0.01 ? "<1%" : `${Math.round(p * 100)}%`);
const gpName = (g) => `${g} GP`;
const ordinal = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
const localTime = (iso) => new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const person = (code) => (state.history && state.history.pilotes[code]) || { nom: code, famille: code, couleur: "#888888" };
const teamBar = (c) => `<i class="team" style="background:${col(c)}"></i>`;

async function getJSON(name) {
  const r = await fetch(`data/${name}.json`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${name}.json: ${r.status}`);
  return r.json();
}

/* ---------- next grand prix */
function hasPractice() {
  return state.next.pole.some((d) => d.apres != null);
}
function poleRows() {
  const key = hasPractice() ? "apres" : "avant";
  return [...state.next.pole].map((d) => ({ ...d, p: d[key] })).sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
}
function raceOver() {
  const n = state.next, r = n.sessions && n.sessions.R;
  return n.saison_terminee || (r && Date.now() > new Date(r).getTime() + DURATION_MIN.R * 6e4);
}

function renderGP() {
  const n = state.next;
  $("#gp-name").textContent = `${gpName(n.gp)} ${n.saison}`;
  const over = raceOver();
  $("#question").textContent = over ? "Race result" : n.qualif_disputee ? "Who wins?" : "Who takes pole?";
  const bits = [];
  if (n.saison_terminee) bits.push("The season is over. Next season's forecasts will appear once the calendar is out.");
  else if (over) bits.push("Race finished. The next forecast will be online in a few hours.");
  else if (n.qualif_disputee) bits.push(n.poleman ? `${n.poleman.nom} took pole. Win chances use the real starting grid.` : "Win chances use the real starting grid.");
  else bits.push(hasPractice() ? "Updated with this weekend's practice sessions." : "Forecast made before practice. It is updated after each session.");
  const wq = n.meteo && n.meteo.Q;
  if (!over && !n.qualif_disputee && wq && wq.pluie != null)
    bits.push(wq.pluie < 0.05 ? "Dry qualifying expected." : `${Math.round(wq.pluie * 100)}% chance of rain during qualifying, included in the forecast.`);
  if (n.debut_saison) bits.push("Early season: the model knows little about this year's cars yet.");
  $("#status").textContent = bits.join(" ");
}

function renderSessions() {
  const s = state.next.sessions || {}, keys = ORDER.filter((k) => s[k]), now = Date.now();
  const nextKey = keys.find((k) => new Date(s[k]).getTime() + (DURATION_MIN[k] || 60) * 6e4 > now);
  $("#sessions").innerHTML = keys.map((k) => {
    const start = new Date(s[k]).getTime(), done = now >= start + (DURATION_MIN[k] || 60) * 6e4;
    const w = state.next.meteo && state.next.meteo[k];
    const wx = !done && w ? `<span class="wx${w.pluie >= 0.05 ? " rain" : ""}">${w.temperature != null ? `${Math.round(w.temperature)}°C, ` : ""}${w.pluie >= 0.05 ? `${Math.round(w.pluie * 100)}% rain` : "dry"}</span>` : "";
    return `<li class="${done ? "done" : ""}${k === nextKey ? " next" : ""}"><b>${SESSIONS[k]}</b><span>${localTime(s[k])}</span>${wx}</li>`;
  }).join("");
  let tz = "";
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { tz = ""; }
  $("#sessions-note").textContent = keys.length ? `Times in your local time zone${tz ? ` (${tz.replace(/_/g, " ")})` : ""}.${state.next.horaires_estimes ? " Session times are still estimated." : ""}${state.next.meteo ? " Rain risk counts any shower, even a light one." : ""}` : "";
  $("#session-next").textContent = nextKey ? `Next: ${SESSIONS[nextKey]}` : "";
  state.countdownTo = nextKey ? new Date(s[nextKey]).getTime() : null;
  $("#countdown").hidden = !state.countdownTo;
}

function tick() {
  if (!state.countdownTo) return;
  let ms = Math.max(0, state.countdownTo - Date.now());
  const d = Math.floor(ms / 864e5); ms -= d * 864e5;
  const h = Math.floor(ms / 36e5); ms -= h * 36e5;
  const m = Math.floor(ms / 6e4); ms -= m * 6e4;
  const sec = Math.floor(ms / 1e3);
  [["#cd-d", d], ["#cd-h", h], ["#cd-m", m], ["#cd-s", sec]].forEach(([id, v]) => { $(id).textContent = String(v).padStart(2, "0"); });
}

function renderGrid() {
  const n = state.next;
  let rows, title;
  if (raceOver() && (n.arrivee || []).length) {
    rows = n.arrivee.map((d) => ({ ...d, label: ordinal(d.place), p: null })); title = "Race result";
  } else if (n.qualif_disputee) {
    rows = [...n.victoire].sort((a, b) => (a.grille ?? 99) - (b.grille ?? 99)).slice(0, 6).map((d, i) => ({ ...d, label: `P${d.grille ?? i + 1}`, p: d.proba }));
    title = "Starting grid and win chances";
  } else {
    rows = poleRows().slice(0, 6).map((d, i) => ({ ...d, label: `P${i + 1}` })); title = "Most likely front of the grid";
  }
  $("#grid-title").textContent = title;
  $("#grid").innerHTML = rows.map((d) => `<li><div class="slot">
      <span class="pos">${esc(d.label)}</span>
      <span class="who"><b>${esc(d.famille)}</b><span>${teamBar(d.couleur)}${esc(d.equipe)}</span></span>
      ${d.p != null ? `<span class="pct">${pct(d.p)}</span>` : ""}
    </div></li>`).join("");
}

function renderField() {
  const rows = poleRows();
  if (!rows.length || raceOver()) { $("#drivers").hidden = true; return; }
  const win = new Map(state.next.victoire.map((d) => [d.code, d.proba]));
  const maxP = Math.max(...rows.map((d) => d.p ?? 0), 0.01), maxW = Math.max(...rows.map((d) => win.get(d.code) ?? 0), 0.01);
  const bar = (v, max, c) => `<span class="barcell"><span class="track"><span class="fill" style="width:${((100 * (v ?? 0)) / max).toFixed(1)}%;background:${col(c)}"></span></span><span class="num">${pct(v)}</span></span>`;
  $("#field").innerHTML = `<thead><tr><th>#</th><th>Driver</th><th>Pole</th><th>Win</th></tr></thead><tbody>${rows.map((d, i) => `<tr>
      <td class="rank">${String(i + 1).padStart(2, "0")}</td>
      <td><span class="driver">${teamBar(d.couleur)}<b>${esc(d.famille)}</b><span>${esc(d.equipe)}</span></span></td>
      <td>${bar(d.p, maxP, d.couleur)}</td><td>${bar(win.get(d.code), maxW, d.couleur)}</td></tr>`).join("")}</tbody>`;
}

/* ---------- model vs reality */
function poleChance(gp) {
  const d = gp.pilotes.find((p) => p.code === gp.poleman);
  return d ? (d.apres ?? d.avant ?? 0) : null;
}
function favourite(gp) {
  return [...gp.pilotes].sort((a, b) => (b.apres ?? b.avant ?? 0) - (a.apres ?? a.avant ?? 0))[0];
}
function renderSeasons() {
  const seasons = Object.keys(state.history.saisons).sort().reverse().slice(0, 3);
  $("#seasons").innerHTML = seasons.map((s) => `<button type="button" data-season="${s}" aria-pressed="${s === state.season}">${s}</button>`).join("");
}
function renderChart() {
  const gps = state.history.saisons[state.season] || [];
  const W = 900, H = 230, left = 34, bottom = 70, top = 10, n = Math.max(gps.length, 1), bw = (W - left) / n;
  const y = (v) => top + (H - top - bottom) * (1 - v);
  const rnd = gps.length ? 1 / gps[0].pilotes.length : 0.045;
  const grid = [0, 0.25, 0.5, 0.75, 1].map((v) => `<line x1="${left}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#444"/><text x="${left - 6}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`).join("");
  const bars = gps.map((g, i) => {
    const p = poleChance(g) ?? 0, x = left + i * bw + bw * 0.15, w = bw * 0.7, c = col(person(g.poleman).couleur);
    const label = g.gp.length > 11 ? `${g.gp.slice(0, 10)}.` : g.gp;
    return `<g><title>${esc(gpName(g.gp))}: ${esc(person(g.poleman).nom)} on pole, the model gave ${pct(p)}</title>
      <rect x="${x}" y="${y(p)}" width="${w}" height="${Math.max(1, y(0) - y(p))}" rx="3" fill="${c}"/>
      <text x="${x + w / 2}" y="${y(0) + 10}" transform="rotate(-60 ${x + w / 2} ${y(0) + 10})" text-anchor="end">${esc(label)}</text></g>`;
  }).join("");
  const line = `<line x1="${left}" x2="${W}" y1="${y(rnd)}" y2="${y(rnd)}" stroke="#bbb" stroke-dasharray="5 4"/><text x="${W}" y="${y(rnd) - 4}" text-anchor="end">random</text>`;
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chance given to the actual pole sitter, grand prix by grand prix">${grid}${bars}${line}</svg>`;
}
function renderHistoryTable() {
  const gps = [...(state.history.saisons[state.season] || [])].reverse();
  $("#history-table").innerHTML = `<thead><tr><th>GP</th><th>Pole</th><th class="num">Model gave</th><th>Model favourite</th><th>Winner</th></tr></thead><tbody>${gps.map((g) => {
    const pole = g.poleman ? person(g.poleman) : null, fav = favourite(g), win = g.vainqueur ? person(g.vainqueur) : null;
    return `<tr><td>${esc(gpName(g.gp))}${g.pluie ? '<span class="wet">wet</span>' : ""}</td>
      <td>${pole ? `<span class="driver">${teamBar(pole.couleur)}<b>${esc(pole.famille)}</b></span>` : "–"}</td>
      <td class="num">${pct(poleChance(g))}</td>
      <td>${fav ? esc(person(fav.code).famille) : "–"}</td><td>${win ? esc(win.famille) : "–"}</td></tr>`;
  }).join("")}</tbody>`;
}

/* ---------- track record */
function rankBefore(gp, code) {
  return [...gp.pilotes].sort((a, b) => (b.avant ?? 0) - (a.avant ?? 0)).findIndex((p) => p.code === code) + 1;
}
function renderTiles() {
  const s = state.history.saisons, past = [...(s["2024"] || []), ...(s["2025"] || [])].filter((g) => g.poleman);
  const ranks = past.map((g) => rankBefore(g, g.poleman));
  const gains = state.perf.gains || [];
  const g = (period) => gains.find((x) => x.modele === "avant le week-end" && x.periode === period && x.contre.startsWith("hasard"));
  const solid = g("2024-2025"), recent = g("fin 2026");
  const race = state.perf.course && (state.perf.course.gains || []).find((x) => x.periode === "2026");
  const tiles = [
    `<p class="big">${ranks.filter((r) => r > 0 && r <= 3).length}/${past.length}</p><p>Pole sitter was in the model's top 3 before practice, in 2024 and 2025.</p>`,
    `<p class="big">${ranks.filter((r) => r === 1).length}/${past.length}</p><p>The model's favourite took pole. A forecast, not a certainty.</p>`,
    solid && solid.ic95_bas > 0
      ? `<p class="mid good">Better than chance</p><p>On 2024-2025, never used to tune the model, its probabilities clearly beat a random draw.${recent && recent.ic95_bas > 0 ? "" : " Not yet proven on the last 2026 races."}</p>`
      : `<p class="mid meh">Not proven yet</p><p>The model does not yet clearly beat a random draw.</p>`,
    race && race.ic95_bas > 0
      ? `<p class="mid good">Race wins</p><p>The model beats the simple rule that front-row starters usually win.</p>`
      : `<p class="mid meh">Race wins</p><p>Starting position explains most of a win. The model ${race && race.gain_vs_grille > 0 ? "does slightly better than that simple rule, not yet proven" : "does not beat that simple rule yet"}.</p>`,
  ];
  $("#tiles").innerHTML = tiles.map((t) => `<div class="tile">${t}</div>`).join("");
}
function renderJournal() {
  const ev = state.journal.evaluations || [];
  if (!ev.length) {
    $("#journal").innerHTML = `<p class="empty">The log starts with the ${esc(gpName(state.next.gp))} ${esc(state.next.saison)}. Forecasts published before each session will appear here with the result.</p>`;
    return;
  }
  $("#journal").innerHTML = `<div class="scroll"><table class="table"><thead><tr><th>GP</th><th>Published</th><th>Actual</th><th class="num">Chance given</th><th class="num">Rank</th></tr></thead><tbody>${ev.slice().reverse().map((e) => `<tr>
      <td>${esc(gpName(e.grand_prix))} ${esc(e.season)}, ${e.type === "pole" ? "pole" : "win"}</td><td>${esc(localTime(e.publie_utc))}</td>
      <td><b>${esc(person(e.reel).famille)}</b></td><td class="num">${pct(e.proba_du_vainqueur)}</td><td class="num">${esc(e.rang_du_vainqueur ?? "–")}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------- start */
async function main() {
  try {
    [state.next, state.history, state.perf, state.journal] = await Promise.all(["next", "history", "performance", "journal"].map(getJSON));
  } catch (err) {
    $("#gp-name").textContent = "Predictions unavailable";
    $("#status").innerHTML = `<span class="error">The data could not be loaded (${esc(err.message)}). Reload the page in a few minutes.</span>`;
    return;
  }
  state.season = Object.keys(state.history.saisons).sort().reverse()[0];
  renderGP(); renderSessions(); renderGrid(); renderField();
  renderSeasons(); renderChart(); renderHistoryTable(); renderTiles(); renderJournal();
  $("#updated").textContent = `Last updated ${localTime(state.next.maj_utc)}.`;
  tick(); setInterval(tick, 1000); setInterval(renderSessions, 60000);
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-season]");
    if (!b) return;
    state.season = b.dataset.season; renderSeasons(); renderChart(); renderHistoryTable();
  });
}
main();
