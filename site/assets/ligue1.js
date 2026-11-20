/* Page Ligue 1 : lit data/ligue1/*.json produits par le calcul automatique. */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const col = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#888888");
const pct = (p) => (p == null ? "–" : p < 0.005 ? "<1 %" : p >= 0.995 ? ">99 %" : `${Math.round(p * 100)} %`);
const S = { m: null, s: null, h: null, p: null, round: 1, club: null, a: null, b: null };

async function getJSON(name) {
  const r = await fetch(`data/ligue1/${name}.json`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${name}.json : ${r.status}`);
  return r.json();
}
const club = (k) => S.m.clubs[k] || { nom: k, sigle: k.slice(0, 3).toUpperCase(), couleur: "#888888", couleur2: "#ffffff" };
const name = (k) => club(k).nom;
function badge(k) {
  const c = club(k);
  if (c.logo) return `<img class="crest" src="${esc(c.logo)}" alt="" width="28" height="28">`;
  return `<span class="crest pastille" style="background:${col(c.couleur)};color:${col(c.couleur2)}" aria-hidden="true">${esc(c.sigle)}</span>`;
}
const when = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "date à fixer");
const day = (d) => new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });

function probBar(p, home, away) {
  const [h, d, a] = p;
  return `<div class="pbar" role="img" aria-label="${esc(name(home))} ${pct(h)}, nul ${pct(d)}, ${esc(name(away))} ${pct(a)}">
    <span style="width:${(h * 100).toFixed(1)}%;background:${col(club(home).couleur)}"></span>
    <span class="draw" style="width:${(d * 100).toFixed(1)}%"></span>
    <span style="width:${(a * 100).toFixed(1)}%;background:${col(club(away).couleur)}"></span></div>
    <div class="plabels"><span>${pct(h)}</span><span>Nul ${pct(d)}</span><span>${pct(a)}</span></div>`;
}

/* ---------- journée */
function renderRound() {
  const r = S.round, list = S.m.matchs.filter((x) => x.round === r).sort((x, y) => String(x.kickoff).localeCompare(String(y.kickoff)));
  $("#j-title").textContent = `Ligue 1, journée ${r}`;
  $("#j-select").value = String(r);
  $("#j-prev").disabled = r <= 1; $("#j-next").disabled = r >= S.m.journees;
  const anyMarket = list.some((x) => x.with_market);
  $("#j-note").textContent = list.every((x) => x.played) ? "Journée terminée. Sous chaque score : ce que le modèle aurait prévu avant le match (reconstitution)."
    : anyMarket ? "Probabilités de victoire à domicile, de nul et de victoire à l'extérieur, cotes d'avant-match comprises. Heures à l'heure de ton appareil."
    : "Probabilités calculées avec les statistiques seules : les cotes d'avant-match ne sont publiées que quelques jours avant la journée.";
  $("#fixtures").innerHTML = list.map((x) => {
    const teams = `<span class="team-l">${badge(x.home)}<b>${esc(name(x.home))}</b></span>
      <span class="mid">${x.played ? `<b class="score">${x.hg} - ${x.ag}</b>` : `<span class="muted tiny">${esc(when(x.kickoff))}</span>`}</span>
      <span class="team-r"><b>${esc(name(x.away))}</b>${badge(x.away)}</span>`;
    if (x.played) {
      const xg = x.hxg != null ? `<span class="muted tiny">xG ${x.hxg.toFixed(1)} - ${x.axg.toFixed(1)}</span>` : "";
      const rec = x.p_reconstitue ? `<div class="recon">${probBar(x.p_reconstitue, x.home, x.away)}</div>` : "";
      return `<li class="fixture played"><div class="teams">${teams}</div>${xg}${rec}</li>`;
    }
    const sc = x.scores.map((s) => `${s.score} (${pct(s.p)})`).join(", ");
    return `<li class="fixture"><div class="teams">${teams}</div>${probBar(x.p, x.home, x.away)}
      <p class="muted tiny">Scores les plus probables : ${esc(sc)}. Buts attendus ${x.xg[0].toFixed(1)} - ${x.xg[1].toFixed(1)}, plus de 2,5 buts ${pct(x.over25)}${x.with_market ? "" : ", sans les cotes"}.</p></li>`;
  }).join("");
}

/* ---------- club */
function renderClub() {
  const k = S.club, c = club(k);
  const proj = S.s.projection.find((x) => x.club === k), rank = S.s.classement.findIndex((x) => x.club === k) + 1;
  const now = S.s.classement[rank - 1];
  $("#club-head").innerHTML = `<div class="club-id">${badge(k)}<b class="wide">${esc(c.nom)}</b></div>
    <div class="tiles">
      <div class="tile"><p class="big">${rank}<small>e</small></p><p>${now.pts} points en ${now.j} matchs (${now.g} V, ${now.n} N, ${now.p} D, ${now.bp} - ${now.bc})</p></div>
      <div class="tile"><p class="big">${proj.points_attendus}</p><p>points attendus en fin de saison, ${proj.rang_moyen}e en moyenne</p></div>
      <div class="tile"><p class="big">${pct(proj.top4)}</p><p>de chances de finir dans le top 4 (titre : ${pct(proj.titre)})</p></div>
      <div class="tile"><p class="big">${pct(proj.barrage + proj.relegation)}</p><p>de chances de finir 16e ou plus bas (barrage ou relégation)</p></div>
    </div>`;
  const list = S.m.matchs.filter((x) => x.home === k || x.away === k).sort((x, y) => x.round - y.round);
  $("#club-table").innerHTML = `<thead><tr><th>J.</th><th>Date</th><th>Adversaire</th><th></th><th>Résultat ou pronostic</th></tr></thead><tbody>${list.map((x) => {
    const home = x.home === k, opp = home ? x.away : x.home;
    let res;
    if (x.played) {
      const gf = home ? x.hg : x.ag, ga = home ? x.ag : x.hg, o = gf > ga ? "V" : gf === ga ? "N" : "D";
      res = `<span class="res ${o}">${o}</span> <b>${gf} - ${ga}</b>`;
    } else {
      const [w, d, l] = home ? x.p : [x.p[2], x.p[1], x.p[0]];
      res = `<span class="triple">victoire <b>${pct(w)}</b>, nul <b>${pct(d)}</b>, défaite <b>${pct(l)}</b></span>`;
    }
    return `<tr><td class="rank">${x.round}</td><td class="nowrap">${x.played ? esc(day(x.date)) : esc(when(x.kickoff))}</td>
      <td><span class="driver">${badge(opp)}<b>${esc(name(opp))}</b></span></td><td class="muted">${home ? "dom." : "ext."}</td><td>${res}</td></tr>`;
  }).join("")}</tbody>`;
}

/* ---------- face-à-face */
function renderH2H() {
  const a = S.a, b = S.b;
  const games = S.h.matchs.filter((g) => (g[1] === a && g[2] === b) || (g[1] === b && g[2] === a)).reverse();
  let wa = 0, wb = 0, d = 0, ga = 0, gb = 0;
  games.forEach(([, h, , x, y]) => {
    const sa = h === a ? x : y, sb = h === a ? y : x;
    ga += sa; gb += sb;
    if (sa > sb) wa++; else if (sa < sb) wb++; else d++;
  });
  $("#h2h-sum").innerHTML = games.length ? `
    <div class="tile"><p class="big">${wa}</p><p>victoires ${esc(name(a))}</p></div>
    <div class="tile"><p class="big">${d}</p><p>nuls</p></div>
    <div class="tile"><p class="big">${wb}</p><p>victoires ${esc(name(b))}</p></div>` : `<p class="empty">Aucun match entre ces deux clubs en Ligue 1 depuis 1993.</p>`;
  $("#h2h-table").innerHTML = games.length ? `<thead><tr><th>Date</th><th>Domicile</th><th>Score</th><th>Extérieur</th></tr></thead><tbody>${games.map(([dt, h, aw, x, y]) => `<tr>
      <td class="nowrap">${esc(day(dt))}</td><td><span class="driver">${badge(h)}<b>${esc(name(h))}</b></span></td>
      <td class="num">${x} - ${y}</td><td><span class="driver">${badge(aw)}<b>${esc(name(aw))}</b></span></td></tr>`).join("")}</tbody>
      <caption class="tiny muted">${games.length} matchs depuis 1993, ${ga} buts pour ${esc(name(a))}, ${gb} pour ${esc(name(b))}.</caption>` : "";
}

/* ---------- classement */
function renderTable() {
  const proj = new Map(S.s.projection.map((x) => [x.club, x]));
  $("#sim-note").textContent = `Fin de saison simulée ${S.s.simulations.toLocaleString("fr-FR")} fois avec les pronostics de chaque match restant. Le nombre de places européennes dépend des coupes : le top 4 est indicatif.`;
  $("#table").innerHTML = `<thead><tr><th>#</th><th>Club</th><th class="num">Pts</th><th class="num">J</th><th class="num">Diff.</th><th class="num">Pts attendus</th><th class="num">Titre</th><th class="num">Top 4</th><th class="num">16e</th><th class="num">17e-18e</th></tr></thead><tbody>${S.s.classement.map((r, i) => {
    const p = proj.get(r.club);
    return `<tr><td class="rank">${i + 1}</td><td><span class="driver">${badge(r.club)}<b>${esc(name(r.club))}</b></span></td>
      <td class="num">${r.pts}</td><td class="num">${r.j}</td><td class="num">${r.diff > 0 ? "+" : ""}${r.diff}</td>
      <td class="num">${p.points_attendus}</td><td class="num">${pct(p.titre)}</td><td class="num">${pct(p.top4)}</td>
      <td class="num">${pct(p.barrage)}</td><td class="num">${pct(p.relegation)}</td></tr>`;
  }).join("")}</tbody>`;
}

/* ---------- bilan */
function renderBilan() {
  const t = S.p.test, by = (n) => t.find((x) => x.modele === n);
  const mine = by("notre modèle (statistiques)"), mix = by("notre modèle + marché"), freq = by("fréquence domicile/nul/extérieur"), mkt = by("marché seul (cotes)");
  const g = (n) => (S.p.gains.find((x) => x.compare === n) || {}).gain_rps || [0, 0, 0];
  const gf = g("modèle vs fréquence"), gm = g("mélange vs marché");
  $("#bilan-tiles").innerHTML = `
    <div class="tile"><p class="big">${Math.round(mix.bons_favoris * 100)} %</p><p>des matchs gagnés par le favori du pronostic (nul compris dans les possibilités), sur ${mix.matchs.toLocaleString("fr-FR")} matchs depuis 2021.</p></div>
    <div class="tile"><p class="mid ${gf[1] > 0 ? "good" : "meh"}">${gf[1] > 0 ? "Mieux que les habitudes" : "Pas mieux que les habitudes"}</p><p>Avec les seules statistiques, le modèle fait nettement mieux que la règle « l'équipe à domicile gagne 45 % du temps ».</p></div>
    <div class="tile"><p class="mid ${gm[1] > 0 ? "good" : "meh"}">${gm[1] > 0 ? "Mieux que le marché" : "Au niveau du marché"}</p><p>Avec les cotes, il fait jeu égal avec le marché des paris, qui reste la référence la plus difficile à battre.</p></div>
    <div class="tile"><p class="mid meh">Le nul reste imprévisible</p><p>Même bien calibré, un pronostic de foot se trompe souvent sur un match : ce sont les probabilités qui doivent être justes.</p></div>`;
  const rows = [["Notre modèle (statistiques)", mine], ["Notre modèle avec les cotes", mix], ["Marché seul", mkt], ["Habitudes (domicile/nul/extérieur)", freq], ["Hasard (1 chance sur 3)", by("hasard")]];
  $("#bilan-table").innerHTML = `<thead><tr><th>Méthode</th><th class="num">Score RPS (plus bas = mieux)</th><th class="num">Log-loss</th><th class="num">Bon favori</th></tr></thead><tbody>${rows.map(([n, r]) => `<tr>
    <td>${esc(n)}</td><td class="num">${r.rps.toFixed(3)}</td><td class="num">${r.log_loss.toFixed(3)}</td><td class="num">${Math.round(r.bons_favoris * 100)} %</td></tr>`).join("")}</tbody>`;
  const j = S.p.journal || [];
  if (!j.length) { $("#journal").innerHTML = `<p class="empty">Le journal démarre avec la journée ${S.m.prochaine_journee}. Les pronostics publiés avant chaque match apparaîtront ici avec le résultat.</p>`; return; }
  const ok = j.filter((x) => x.favori_juste).length;
  $("#journal").innerHTML = `<p class="small">Favori juste ${ok} fois sur ${j.length}.</p><div class="scroll"><table class="table"><thead><tr><th>J.</th><th>Match</th><th class="num">Score</th><th>Pronostic publié</th></tr></thead><tbody>${j.slice().reverse().map((x) => `<tr>
    <td class="rank">${x.journee}</td><td>${esc(name(x.domicile))} - ${esc(name(x.exterieur))}</td><td class="num">${esc(x.score)}</td>
    <td>${pct(x.p[0])} / ${pct(x.p[1])} / ${pct(x.p[2])} ${x.favori_juste ? "<span class=\"res V\">juste</span>" : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------- démarrage */
function options(sel, keys, current) {
  sel.innerHTML = keys.map((k) => `<option value="${esc(k)}"${k === current ? " selected" : ""}>${esc(name(k))}</option>`).join("");
}
async function main() {
  try {
    [S.m, S.s, S.h, S.p] = await Promise.all(["matches", "season", "h2h", "performance"].map(getJSON));
  } catch (err) {
    $("#j-title").textContent = "Pronostics indisponibles";
    $("#j-note").innerHTML = `<span class="error">Les données n'ont pas pu être chargées (${esc(err.message)}). Recharge la page dans quelques minutes.</span>`;
    return;
  }
  S.round = S.m.prochaine_journee;
  $("#j-select").innerHTML = Array.from({ length: S.m.journees }, (_, i) => `<option value="${i + 1}">Journée ${i + 1}</option>`).join("");
  const keys = Object.keys(S.m.clubs).sort((x, y) => name(x).localeCompare(name(y), "fr"));
  S.club = S.s.classement[0].club; S.a = S.s.classement[0].club; S.b = S.s.classement[1].club;
  options($("#club-select"), keys, S.club); options($("#h2h-a"), keys, S.a); options($("#h2h-b"), keys, S.b);
  renderRound(); renderClub(); renderH2H(); renderTable(); renderBilan();
  $("#l1-updated").textContent = `Dernière mise à jour : ${when(S.m.maj_utc)}.`;
  $("#j-select").addEventListener("change", (e) => { S.round = Number(e.target.value); renderRound(); });
  $("#j-prev").addEventListener("click", () => { S.round = Math.max(1, S.round - 1); renderRound(); });
  $("#j-next").addEventListener("click", () => { S.round = Math.min(S.m.journees, S.round + 1); renderRound(); });
  $("#club-select").addEventListener("change", (e) => { S.club = e.target.value; renderClub(); });
  $("#h2h-a").addEventListener("change", (e) => { S.a = e.target.value; renderH2H(); });
  $("#h2h-b").addEventListener("change", (e) => { S.b = e.target.value; renderH2H(); });
}
main();
