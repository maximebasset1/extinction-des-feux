/* Page Formule 1 : lit les fichiers data/*.json publiés par le calcul automatique. */
"use strict";

const SEANCES = { FP1: "Essais libres 1", SQ: "Qualifications sprint", FP2: "Essais libres 2", S: "Sprint", FP3: "Essais libres 3", Q: "Qualifications", R: "Course" };
const ORDRE = ["FP1", "SQ", "FP2", "S", "FP3", "Q", "R"];
const DUREE = { FP1: 60, FP2: 60, FP3: 60, SQ: 45, S: 60, Q: 60, R: 120 };
const E = { next: null, history: null, perf: null, journal: null, season: null, cible: null };
const NOMS_GP = {};
const nomGP = (g) => NOMS_GP[g] || `Grand Prix ${g}`;
const personne = (code) => (E.history && E.history.pilotes[code]) || { nom: code, famille: code, couleur: "#888888" };
const ecurie = (c) => `<i class="ecurie" style="background:${couleur(c) || "#888888"}"></i>`;

function avecEssais() { return E.next.pole.some((d) => d.apres != null); }
function lignesPole() {
  const cle = avecEssais() ? "apres" : "avant";
  return [...E.next.pole].map((d) => ({ ...d, p: d[cle] })).sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
}
/* chance de pole annoncée avant la séance, pour le pilote donné */
function poleAnnoncee(code) { const d = lignesPole().find((x) => x.code === code); return d ? d.p : null; }
function courseFinie() {
  const n = E.next, r = n.sessions && n.sessions.R;
  return n.saison_terminee || (r && Date.now() > new Date(r).getTime() + DUREE.R * 6e4);
}

function rendreGP() {
  const n = E.next, fini = courseFinie();
  $("#gp-name").textContent = `${n.gp_fr || nomGP(n.gp)} ${n.saison}`;
  $("#question").textContent = fini ? "Résultat de la course" : n.qualif_disputee ? "Qui va gagner ?" : "Qui partira en pole ?";
  const bouts = [];
  if (n.saison_terminee) bouts.push("La saison est terminée. Les pronostics de la saison prochaine arriveront avec le calendrier.");
  else if (fini) bouts.push("Course terminée. Le prochain pronostic sera en ligne dans quelques heures.");
  else if (n.qualif_disputee) {
    const fav = lignesPole()[0], p = n.poleman ? poleAnnoncee(n.poleman.code) : null;
    let avant = "";
    if (p != null && fav) avant = fav.code === n.poleman.code ? ` C'était le favori du modèle (${pct(p)}).`
      : ` Avant la séance, le modèle lui donnait ${pct(p)} de chances ; son favori, ${fav.famille}, était à ${pct(fav.p)}.`;
    bouts.push(`${n.poleman ? `${n.poleman.nom} a fait la pole.${avant} ` : ""}Les chances de victoire partent maintenant de la vraie grille de départ.`);
  }
  else bouts.push(avecEssais() ? "Mis à jour avec les essais libres du week-end." : "Pronostic fait avant les essais. Il est mis à jour après chaque séance.");
  const mq = n.meteo && n.meteo.Q;
  if (!fini && !n.qualif_disputee && mq && mq.pluie != null)
    bouts.push(mq.pluie < 0.05 ? "Qualifications sur piste sèche attendues." : `${Math.round(mq.pluie * 100)}\u202f% de risque de pluie pendant les qualifications, pris en compte.`);
  if (n.debut_saison) bouts.push("Début de saison : le modèle connaît encore mal les voitures de l'année.");
  $("#status").textContent = bouts.join(" ");
}

function rendreSeances() {
  const s = E.next.sessions || {}, keys = ORDRE.filter((k) => s[k]), now = Date.now();
  const k0 = keys.find((k) => new Date(s[k]).getTime() + (DUREE[k] || 60) * 6e4 > now);
  $("#sessions").innerHTML = keys.map((k) => {
    const debut = new Date(s[k]).getTime(), fini = now >= debut + (DUREE[k] || 60) * 6e4, w = E.next.meteo && E.next.meteo[k];
    const meteo = !fini && w ? `<span${w.pluie >= 0.05 ? ' class="pluie"' : ""}>${w.temperature != null ? `${Math.round(w.temperature)} °C, ` : ""}${w.pluie >= 0.05 ? `${Math.round(w.pluie * 100)}\u202f% de pluie` : "sec"}</span>` : "";
    return `<li class="${fini ? "fini" : ""}${k === k0 ? " prochaine" : ""}"><b>${SEANCES[k]}</b><span>${quand(s[k])}</span>${meteo}</li>`;
  }).join("");
  let tz = "";
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { tz = ""; }
  $("#sessions-note").textContent = keys.length ? `Heures à l'heure de ton appareil${tz ? ` (${tz.replace(/_/g, " ")})` : ""}.${E.next.horaires_estimes ? " Horaires encore estimés." : ""}${E.next.meteo ? " Le risque de pluie compte la moindre averse." : ""}` : "";
  $("#session-next").textContent = k0 ? `Prochaine séance : ${SEANCES[k0]}` : "";
  E.cible = k0 ? new Date(s[k0]).getTime() : null;
  $("#countdown").hidden = !E.cible;
}
function tic() {
  if (!E.cible) return;
  let ms = Math.max(0, E.cible - Date.now());
  const j = Math.floor(ms / 864e5); ms -= j * 864e5;
  const h = Math.floor(ms / 36e5); ms -= h * 36e5;
  const m = Math.floor(ms / 6e4); ms -= m * 6e4;
  [["#cd-d", j], ["#cd-h", h], ["#cd-m", m], ["#cd-s", Math.floor(ms / 1e3)]].forEach(([id, v]) => { $(id).textContent = String(v).padStart(2, "0"); });
}

function rendreGrille() {
  const n = E.next;
  let lignes, titre;
  if (courseFinie() && (n.arrivee || []).length) {
    lignes = n.arrivee.map((d) => ({ ...d, pos: d.place, p: null })); titre = "Résultat de la course";
  } else if (n.qualif_disputee) {
    lignes = [...n.victoire].sort((a, b) => (a.grille ?? 99) - (b.grille ?? 99)).slice(0, 6).map((d, i) => ({ ...d, pos: d.grille ?? i + 1, p: d.proba }));
    titre = "Grille de départ et chances de victoire";
  } else {
    lignes = lignesPole().slice(0, 6).map((d, i) => ({ ...d, pos: i + 1 })); titre = "La grille la plus probable";
  }
  $("#grid-title").textContent = titre;
  const max = Math.max(...lignes.map((d) => d.p ?? 0), 0.01);
  $("#grid").innerHTML = lignes.map((d) => `<li><span class="pos">${esc(d.pos)}</span>
      <span class="pilote"><b>${esc(d.famille)}</b><span>${ecurie(d.couleur)}${esc(d.equipe)}</span></span>
      <span class="jauge">${d.p != null ? `<i style="width:${((100 * d.p) / max).toFixed(1)}%;background:${couleur(d.couleur) || "#888"}"></i>` : ""}</span>
      <span class="pct">${d.p != null ? pct(d.p) : ""}</span></li>`).join("");
}

function rendrePilotes() {
  const pole = lignesPole(), apres = E.next.qualif_disputee;
  if (!pole.length || courseFinie()) { $("#drivers").hidden = true; return; }
  const vic = new Map(E.next.victoire.map((d) => [d.code, d]));
  const proba = (d) => (vic.get(d.code) || {}).proba, depart = (d) => (vic.get(d.code) || {}).grille;
  // après la qualif, l'ordre est celui de la grille : le pronostic de pole n'est plus qu'un rappel
  const lignes = apres ? [...pole].sort((a, b) => (depart(a) ?? 99) - (depart(b) ?? 99)) : pole;
  const maxP = Math.max(...lignes.map((d) => d.p ?? 0), 0.01), maxV = Math.max(...lignes.map((d) => proba(d) ?? 0), 0.01);
  const jauge = (v, max, c) => `<span class="barcell"><span class="jauge"><i style="width:${((100 * (v ?? 0)) / max).toFixed(1)}%;background:${couleur(c) || "#888"}"></i></span><span class="num">${pct(v)}</span></span>`;
  const cellP = (d) => `<td>${jauge(d.p, maxP, d.couleur)}</td>`, cellV = (d) => `<td>${jauge(proba(d), maxV, d.couleur)}</td>`;
  $("#field").innerHTML = `<thead><tr><th>${apres ? "Départ" : "#"}</th><th>Pilote</th>${apres ? "<th>Victoire</th><th>Pole, annoncée avant la séance</th>" : "<th>Pole</th><th>Victoire</th>"}</tr></thead><tbody>${lignes.map((d, i) => `<tr>
      <td class="rang">${apres ? esc(depart(d) ?? "–") : i + 1}</td><td><span class="club">${ecurie(d.couleur)}<span><b>${esc(d.famille)}</b> <span class="note">${esc(d.equipe)}</span></span></span></td>
      ${apres ? cellV(d) + cellP(d) : cellP(d) + cellV(d)}</tr>`).join("")}</tbody>`;
  $("#field-note").textContent = apres
    ? "Dans l'ordre de la grille de départ. Les chances de pole sont celles annoncées avant les qualifications, gardées pour comparer."
    : "Dans l'ordre des chances de pole. La grille n'étant pas connue, les chances de victoire font la moyenne de milliers de grilles possibles.";
}

/* ---------- le modèle face à la réalité */
function chancePole(gp) {
  const d = gp.pilotes.find((p) => p.code === gp.poleman);
  return d ? (d.apres ?? d.avant ?? 0) : null;
}
function favori(gp) { return [...gp.pilotes].sort((a, b) => (b.apres ?? b.avant ?? 0) - (a.apres ?? a.avant ?? 0))[0]; }
function rendreSaisons() {
  const s = Object.keys(E.history.saisons).sort().reverse().slice(0, 3);
  $("#seasons").innerHTML = s.map((x) => `<button type="button" data-season="${x}" aria-pressed="${x === E.season}">${x}</button>`).join("");
}
function rendreGraphe() {
  const gps = E.history.saisons[E.season] || [];
  const W = 900, H = 230, gauche = 34, bas = 70, haut = 10, n = Math.max(gps.length, 1), bw = (W - gauche) / n;
  const y = (v) => haut + (H - haut - bas) * (1 - v);
  const hasard = gps.length ? 1 / gps[0].pilotes.length : 0.045;
  const grille = [0, 0.25, 0.5, 0.75, 1].map((v) => `<line x1="${gauche}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#d4d8d1"/><text x="${gauche - 6}" y="${y(v) + 4}" text-anchor="end">${v * 100}\u202f%</text>`).join("");
  const barres = gps.map((g, i) => {
    const p = chancePole(g) ?? 0, x = gauche + i * bw + bw * 0.15, w = bw * 0.7, c = couleur(personne(g.poleman).couleur) || "#888";
    const nomg = (g.gp_fr || nomGP(g.gp)).replace(/^Grand Prix (de |du |des |d’|d')?/, "");
    const lib = nomg.length > 11 ? `${nomg.slice(0, 10)}.` : nomg;
    return `<g><title>${esc(g.gp_fr || nomGP(g.gp))} : ${esc(personne(g.poleman).nom)} en pole, le modèle lui donnait ${pct(p)}</title>
      <rect x="${x}" y="${y(p)}" width="${w}" height="${Math.max(1, y(0) - y(p))}" rx="3" fill="${c}"/>
      <text x="${x + w / 2}" y="${y(0) + 10}" transform="rotate(-60 ${x + w / 2} ${y(0) + 10})" text-anchor="end">${esc(lib)}</text></g>`;
  }).join("");
  const ligne = `<line x1="${gauche}" x2="${W}" y1="${y(hasard)}" y2="${y(hasard)}" stroke="#5c646c" stroke-dasharray="5 4"/><text x="${W}" y="${y(hasard) - 4}" text-anchor="end">hasard</text>`;
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chance donnée au pilote qui a fait la pole, Grand Prix par Grand Prix">${grille}${barres}${ligne}</svg>`;
}
function rendreHistorique() {
  const gps = [...(E.history.saisons[E.season] || [])].reverse();
  $("#history-table").innerHTML = `<thead><tr><th>Grand Prix</th><th>Pole</th><th class="num">Chance donnée</th><th>Favori du modèle</th><th>Vainqueur</th></tr></thead><tbody>${gps.map((g) => {
    const pole = g.poleman ? personne(g.poleman) : null, fav = favori(g), vq = g.vainqueur ? personne(g.vainqueur) : null;
    return `<tr><td>${esc(g.gp_fr || nomGP(g.gp))}${g.pluie ? '<span class="mouille">pluie</span>' : ""}</td>
      <td>${pole ? `<span class="club">${ecurie(pole.couleur)}${esc(pole.famille)}</span>` : "–"}</td>
      <td class="num">${pct(chancePole(g))}</td><td>${fav ? esc(personne(fav.code).famille) : "–"}</td><td>${vq ? esc(vq.famille) : "–"}</td></tr>`;
  }).join("")}</tbody>`;
}

/* ---------- bilan */
function rangAvant(gp, code) { return [...gp.pilotes].sort((a, b) => (b.avant ?? 0) - (a.avant ?? 0)).findIndex((p) => p.code === code) + 1; }
function rendreBilan() {
  const s = E.history.saisons, passe = [...(s["2024"] || []), ...(s["2025"] || [])].filter((g) => g.poleman);
  const rangs = passe.map((g) => rangAvant(g, g.poleman));
  const gains = E.perf.gains || [];
  const g = (periode) => gains.find((x) => x.modele === "avant le week-end" && x.periode === periode && x.contre.startsWith("hasard"));
  const solide = g("2024-2025"), recent = g("fin 2026");
  const course = E.perf.course && (E.perf.course.gains || []).find((x) => x.periode === "2026");
  const items = [
    [`${rangs.filter((r) => r > 0 && r <= 3).length} sur ${passe.length}`, "Le poleman était dans le top 3 du modèle avant les essais, en 2024 et 2025."],
    [`${rangs.filter((r) => r === 1).length} sur ${passe.length}`, "Le favori du modèle a fait la pole. Un pronostic, pas une certitude."],
    solide && solide.ic95_bas > 0
      ? ["Mieux que le hasard", `Sur 2024 et 2025, jamais utilisées pour régler le modèle, ses probabilités battent nettement un tirage au hasard.${recent && recent.ic95_bas > 0 ? "" : " Ce n'est pas encore prouvé sur les dernières courses de 2026."}`]
      : ["Pas encore prouvé", "Le modèle ne bat pas encore nettement un tirage au hasard."],
    course && course.ic95_bas > 0
      ? ["Victoires", "Le modèle bat la règle simple selon laquelle la première ligne gagne le plus souvent."]
      : ["Victoires", `La position de départ explique l'essentiel d'une victoire. Le modèle ${course && course.gain_vs_grille > 0 ? "fait un peu mieux que cette règle simple, sans que ce soit encore prouvé" : "ne bat pas encore cette règle simple"}.`],
  ];
  $("#tiles").innerHTML = items.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join("");
}
function rendreJournal() {
  const ev = E.journal.evaluations || [];
  if (!ev.length) {
    $("#journal").innerHTML = `<p class="vide">Le journal démarre avec le ${esc(E.next.gp_fr || nomGP(E.next.gp))} ${esc(E.next.saison)}. Les pronostics publiés avant chaque séance apparaîtront ici avec le résultat.</p>`;
    return;
  }
  $("#journal").innerHTML = `<div class="defile"><table class="tableau"><thead><tr><th>Grand Prix</th><th>Publié</th><th>Réel</th><th class="num">Chance donnée</th><th class="num">Rang</th></tr></thead><tbody>${ev.slice().reverse().map((e) => `<tr>
      <td>${esc(nomGP(e.grand_prix))} ${esc(e.season)}, ${e.type === "pole" ? "pole" : "victoire"}</td><td>${esc(quand(e.publie_utc))}</td>
      <td><b>${esc(personne(e.reel).famille)}</b></td><td class="num">${pct(e.proba_du_vainqueur)}</td><td class="num">${esc(e.rang_du_vainqueur ?? "–")}</td></tr>`).join("")}</tbody></table></div>`;
}

async function main() {
  try {
    [E.next, E.history, E.perf, E.journal] = await Promise.all(["next", "history", "performance", "journal"].map(donnees));
  } catch (err) {
    $("#gp-name").textContent = "Pronostics indisponibles";
    erreur($("#grid"), err);
    return;
  }
  for (const gps of Object.values(E.history.saisons)) for (const g of gps) if (g.gp_fr) NOMS_GP[g.gp] = g.gp_fr;
  if (E.next.gp_fr) NOMS_GP[E.next.gp] = E.next.gp_fr;
  E.season = Object.keys(E.history.saisons).sort().reverse()[0];
  rendreGP(); rendreSeances(); rendreGrille(); rendrePilotes();
  rendreSaisons(); rendreGraphe(); rendreHistorique(); rendreBilan(); rendreJournal();
  $("#updated").textContent = `Dernière mise à jour : ${quand(E.next.maj_utc)}.`;
  tic(); setInterval(tic, 1000); setInterval(rendreSeances, 60000);
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-season]");
    if (!b) return;
    E.season = b.dataset.season; rendreSaisons(); rendreGraphe(); rendreHistorique();
  });
}
main();
