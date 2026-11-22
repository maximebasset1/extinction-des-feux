/* Module Formule 1 : pages « Formule 1 » et « Méthode & Bilan F1 ».
   Autonome : n'utilise aucun autre script du site. Lit les fichiers publiés par le moteur F1
   (data/next.json, history.json, performance.json, journal.json, etude_f1.json) ; leur format est décrit
   dans docs/contrat-f1.md. */
(() => {
  "use strict";

  /* ---------- outils */
  const $ = (s) => document.querySelector(s);
  const ROOT = document.body.dataset.root || "./";
  const PAGE = document.body.dataset.page || "f1";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const couleur = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#888888");
  const pct = (p) => (p == null ? "–" : p < 0.005 ? "<1 %" : p >= 0.995 ? ">99 %" : `${Math.round(p * 100)} %`);
  const virgule = (x, d = 3) => Number(x).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const quand = (iso) => new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  async function donnees(nom) {
    const r = await fetch(`${ROOT}data/${nom}.json`, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${nom}.json : réponse ${r.status}`);
    return r.json();
  }
  const ecurie = (c) => `<i class="ecurie" style="background:${couleur(c)}"></i>`;
  const jauge = (p, max, c) => `<span class="jauge"><i style="width:${((100 * (p ?? 0)) / max).toFixed(1)}%;background:${couleur(c)}"></i></span>`;

  const SEANCES = { FP1: "Essais libres 1", SQ: "Qualifications sprint", FP2: "Essais libres 2", S: "Sprint", FP3: "Essais libres 3", Q: "Qualifications", R: "Course" };
  const ORDRE = ["FP1", "SQ", "FP2", "S", "FP3", "Q", "R"];
  const DUREE = { FP1: 60, FP2: 60, FP3: 60, SQ: 45, S: 60, Q: 60, R: 120 };
  const E = { next: null, history: null, perf: null, journal: null, etude: null, season: null, cible: null };
  const NOMS_GP = {};
  const nomGP = (g) => NOMS_GP[g] || `Grand Prix ${g}`;
  const personne = (code) => (E.history && E.history.pilotes[code]) || { nom: code, famille: code, couleur: "#888888" };

  /* badge quand un pilote ne part pas à sa place de qualif */
  const badgeDepart = (d) => (d.stands ? ` <span class="penalite">départ des stands</span>`
    : d.penalite > 0 ? ` <span class="penalite">pénalité : ${esc(d.penalite)} place${d.penalite > 1 ? "s" : ""}</span>` : "");

  /* ---------- état du week-end */
  function lignesPole() {
    const cle = E.next.pole.some((d) => d.apres != null) ? "apres" : "avant";
    return [...E.next.pole].map((d) => ({ ...d, p: d[cle] })).sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
  }
  const poleAnnoncee = (code) => { const d = lignesPole().find((x) => x.code === code); return d ? d.p : null; };
  function courseFinie() {
    const n = E.next, r = n.sessions && n.sessions.R;
    return n.saison_terminee || (r && Date.now() > new Date(r).getTime() + DUREE.R * 6e4);
  }

  /* ---------- en-tête du Grand Prix */
  function rendreGP() {
    const n = E.next, fini = courseFinie();
    $("#gp-name").textContent = `${n.gp_fr || nomGP(n.gp)} ${n.saison}`;
    $("#question").textContent = fini ? "Résultat de la course" : n.qualif_disputee ? "Qui va gagner ?" : "Qui partira en pole ?";
    let txt;
    if (n.saison_terminee) txt = "La saison est terminée. Les pronostics de la saison prochaine arriveront avec le calendrier.";
    else if (fini) txt = "Course terminée. Le prochain pronostic sera en ligne dans quelques heures.";
    else if (n.qualif_disputee) {
      const p = n.poleman ? poleAnnoncee(n.poleman.code) : null;
      txt = n.poleman ? `${n.poleman.nom} a fait la pole${p != null ? ` (${pct(p)} annoncé avant la séance)` : ""}.` : "Qualification terminée.";
    } else txt = E.next.pole.some((d) => d.apres != null) ? "Pronostic mis à jour avec les essais libres du week-end." : "Pronostic fait avant les essais, mis à jour après chaque séance.";
    if (n.debut_saison) txt += " Début de saison : le modèle connaît encore mal les voitures de l'année.";
    $("#status").textContent = txt;
  }

  /* ---------- programme et météo */
  function rendreSeances() {
    const s = E.next.sessions || {}, keys = ORDRE.filter((k) => s[k]), now = Date.now();
    const k0 = keys.find((k) => new Date(s[k]).getTime() + (DUREE[k] || 60) * 6e4 > now);
    $("#sessions").innerHTML = keys.map((k) => {
      const debut = new Date(s[k]).getTime(), fini = now >= debut + (DUREE[k] || 60) * 6e4, w = E.next.meteo && E.next.meteo[k];
      const meteo = !fini && w ? `<span class="f1-meteo${w.pluie >= 0.05 ? " pluie" : ""}">${w.temperature != null ? `${Math.round(w.temperature)} °C, ` : ""}${w.pluie >= 0.05 ? `pluie ${pct(w.pluie)}` : "sec"}</span>` : "";
      return `<li class="${fini ? "fini" : ""}${k === k0 ? " prochaine" : ""}"><b>${SEANCES[k]}</b><span>${quand(s[k])}</span>${meteo}</li>`;
    }).join("");
    let tz = "";
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { tz = ""; }
    $("#sessions-note").textContent = keys.length ? `Heures de ton appareil${tz ? ` (${tz.replace(/_/g, " ")})` : ""}. Le risque de pluie compte la moindre averse.${E.next.horaires_estimes ? " Horaires encore estimés." : ""}` : "";
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

  /* ---------- grille : probable, provisoire ou officielle */
  function rendreGrille() {
    const n = E.next;
    let lignes, titre, source;
    if (courseFinie() && (n.arrivee || []).length) {
      lignes = n.arrivee.map((d) => ({ ...d, pos: d.place, p: null })); titre = "Arrivée"; source = "Résultat de la course";
    } else if (n.qualif_disputee) {
      lignes = [...n.victoire].sort((a, b) => (a.grille ?? 99) - (b.grille ?? 99)).slice(0, 10).map((d, i) => ({ ...d, pos: d.grille ?? i + 1, p: d.proba }));
      titre = "Grille de départ";
      source = n.grille_source === "officielle" ? "Grille officielle, pénalités comprises. Chances de victoire."
        : "Grille provisoire : ordre de la qualif, pénalités pas encore publiées. Chances de victoire.";
    } else {
      lignes = lignesPole().slice(0, 10).map((d, i) => ({ ...d, pos: i + 1 })); titre = "Grille probable"; source = "Chances de pole.";
    }
    $("#grid-title").textContent = titre;
    $("#grid-source").textContent = source;
    const max = Math.max(...lignes.map((d) => d.p ?? 0), 0.01);
    $("#grid").innerHTML = lignes.map((d) => `<li><span class="pos">${esc(d.pos)}</span>
      <span class="pilote"><b>${esc(d.famille)}${badgeDepart(d)}</b><span>${ecurie(d.couleur)}${esc(d.equipe)}</span></span>
      ${d.p != null ? jauge(d.p, max, d.couleur) : "<span></span>"}
      <span class="pct">${d.p != null ? pct(d.p) : ""}</span></li>`).join("");
  }

  /* ---------- favoris : pole et victoire */
  function carteFavoris(el, titre, lignes, pied) {
    el.innerHTML = `<h3>${esc(titre)}</h3><ol class="f1-favoris">${lignes.slice(0, 3).map((d) => `<li>
      <span class="f1-fav-nom">${ecurie(d.couleur)}<b>${esc(d.famille)}</b> <span>${esc(d.equipe)}</span></span>
      <span class="f1-fav-p">${pct(d.p)}</span></li>`).join("")}</ol>${pied ? `<p class="note">${pied}</p>` : ""}`;
  }
  function rendreFavoris() {
    const n = E.next;
    if (courseFinie()) { $("#favoris").hidden = true; document.querySelector(".f1-haut").classList.add("seule"); return; }
    if (n.qualif_disputee && n.poleman) {
      const p = poleAnnoncee(n.poleman.code), fav = lignesPole()[0];
      $("#fav-pole").innerHTML = `<h3>Pole</h3><p class="f1-fait">${esc(n.poleman.famille)}</p>
        <p class="note">Le modèle lui donnait ${pct(p)} avant la séance${fav && fav.code !== n.poleman.code ? ` ; son favori, ${esc(fav.famille)}, était à ${pct(fav.p)}` : " : c'était son favori"}.</p>`;
    } else {
      carteFavoris($("#fav-pole"), "Pole", lignesPole(), null);
    }
    const vic = [...n.victoire].map((d) => ({ ...d, p: d.proba })).sort((a, b) => b.p - a.p);
    carteFavoris($("#fav-victoire"), "Victoire", vic, n.qualif_disputee ? null : "Avant la qualif : moyenne sur des milliers de grilles possibles.");
  }

  /* ---------- tous les pilotes */
  function rendrePilotes() {
    const pole = lignesPole(), apres = E.next.qualif_disputee;
    if (!pole.length || courseFinie()) { $("#drivers").hidden = true; return; }
    const vic = new Map(E.next.victoire.map((d) => [d.code, d]));
    const info = (d) => vic.get(d.code) || {}, proba = (d) => info(d).proba, depart = (d) => info(d).grille;
    // après la qualif, l'ordre est celui de la grille : le pronostic de pole n'est plus qu'un rappel
    const lignes = apres ? [...pole].sort((a, b) => (depart(a) ?? 99) - (depart(b) ?? 99)) : pole;
    const maxP = Math.max(...lignes.map((d) => d.p ?? 0), 0.01), maxV = Math.max(...lignes.map((d) => proba(d) ?? 0), 0.01);
    const cell = (v, max, c) => `<td><span class="barcell">${jauge(v, max, c)}<span class="num">${pct(v)}</span></span></td>`;
    $("#field").innerHTML = `<thead><tr><th>${apres ? "Départ" : "#"}</th><th>Pilote</th>${apres ? "<th>Victoire</th><th>Pole, annoncée avant la séance</th>" : "<th>Pole</th><th>Victoire</th>"}</tr></thead><tbody>${lignes.map((d, i) => `<tr>
      <td class="rang">${apres ? esc(depart(d) ?? "–") : i + 1}</td>
      <td><span class="club">${ecurie(d.couleur)}<span><b>${esc(d.famille)}</b> <span class="f1-equipe">${esc(d.equipe)}</span>${apres ? badgeDepart(info(d)) : ""}</span></span></td>
      ${apres ? cell(proba(d), maxV, d.couleur) + cell(d.p, maxP, d.couleur) : cell(d.p, maxP, d.couleur) + cell(proba(d), maxV, d.couleur)}</tr>`).join("")}</tbody>`;
    $("#field-note").textContent = apres ? "Dans l'ordre de la grille de départ." : "Dans l'ordre des chances de pole.";
  }

  /* ---------- prévu contre réel : dernier Grand Prix terminé */
  function chancePole(gp) { const d = gp.pilotes.find((p) => p.code === gp.poleman); return d ? (d.apres ?? d.avant ?? 0) : null; }
  function favoriPole(gp) { return [...gp.pilotes].sort((a, b) => (b.apres ?? b.avant ?? 0) - (a.apres ?? a.avant ?? 0))[0]; }
  function rendreReel() {
    const saisons = Object.keys(E.history.saisons).sort().reverse();
    let gp = null, saison = null;
    for (const s of saisons) { gp = [...E.history.saisons[s]].reverse().find((g) => g.vainqueur); if (gp) { saison = s; break; } }
    if (!gp) { $("#reel").hidden = true; return; }
    const fav = favoriPole(gp), vq = gp.pilotes.find((p) => p.code === gp.vainqueur);
    const favV = [...gp.pilotes].filter((p) => p.victoire != null).sort((a, b) => b.victoire - a.victoire)[0];
    const ligne = (titre, reel, chance, favori, favChance) => `<div class="f1-reel-ligne"><span class="f1-reel-quoi">${titre}</span>
      <span class="f1-reel-qui">${ecurie(personne(reel).couleur)}<b>${esc(personne(reel).famille)}</b></span>
      <span>annoncé à <b>${pct(chance)}</b>${favori && favori !== reel ? `, favori du modèle : ${esc(personne(favori).famille)} (${pct(favChance)})` : ", c'était le favori"}</span></div>`;
    $("#reel-titre").textContent = `Prévu et réel : ${gp.gp_fr || nomGP(gp.gp)} ${saison}`;
    $("#reel-corps").innerHTML = ligne("Pole", gp.poleman, chancePole(gp), fav && fav.code, fav && (fav.apres ?? fav.avant))
      + (vq ? ligne("Victoire", gp.vainqueur, vq.victoire, favV && favV.code, favV && favV.victoire) : "");
  }

  /* ---------- journal des pronostics publiés */
  function lignesJournal(ev) {
    return ev.map((e) => `<tr>
      <td>${esc(nomGP(e.grand_prix))} ${esc(e.season)}, ${e.type === "pole" ? "pole" : "victoire"}${e.recalcule ? ` <span class="f1-equipe">(recalculé après la course sur la grille officielle : le pronostic publié ignorait les pénalités)</span>` : ""}</td>
      <td>${esc(quand(e.publie_utc))}</td><td><b>${esc(personne(e.reel).famille)}</b></td>
      <td class="num">${pct(e.proba_du_vainqueur)}</td><td class="num">${esc(e.rang_du_vainqueur ?? "–")}</td></tr>`).join("");
  }
  function rendreJournal(el, n) {
    const ev = (E.journal.evaluations || []).slice().reverse();
    if (!ev.length) { el.innerHTML = `<p class="vide">Les pronostics publiés avant chaque séance apparaîtront ici avec le résultat.</p>`; return; }
    el.innerHTML = `<div class="defile"><table class="tableau"><thead><tr><th>Pronostic</th><th>Publié</th><th>Réel</th><th class="num">Chance donnée</th><th class="num">Rang</th></tr></thead><tbody>${lignesJournal(n ? ev.slice(0, n) : ev)}</tbody></table></div>`;
  }

  /* ---------- Méthode & Bilan : le modèle face à la réalité */
  function rendreSaisons() {
    const s = Object.keys(E.history.saisons).sort().reverse().slice(0, 3);
    $("#seasons").innerHTML = s.map((x) => `<button type="button" data-season="${x}" aria-pressed="${x === E.season}">${x}</button>`).join("");
  }
  function rendreGraphe() {
    const gps = E.history.saisons[E.season] || [];
    const W = 900, H = 230, gauche = 34, bas = 70, haut = 10, n = Math.max(gps.length, 1), bw = (W - gauche) / n;
    const y = (v) => haut + (H - haut - bas) * (1 - v);
    const hasard = gps.length ? 1 / gps[0].pilotes.length : 0.045;
    const grille = [0, 0.25, 0.5, 0.75, 1].map((v) => `<line x1="${gauche}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#2a2f39"/><text x="${gauche - 6}" y="${y(v) + 4}" text-anchor="end">${v * 100} %</text>`).join("");
    const barres = gps.map((g, i) => {
      const p = chancePole(g) ?? 0, x = gauche + i * bw + bw * 0.15, w = bw * 0.7, c = couleur(personne(g.poleman).couleur);
      const nomg = (g.gp_fr || nomGP(g.gp)).replace(/^Grand Prix (de |du |des |d’|d')?/, "");
      const lib = nomg.length > 11 ? `${nomg.slice(0, 10)}.` : nomg;
      return `<g><title>${esc(g.gp_fr || nomGP(g.gp))} : ${esc(personne(g.poleman).nom)} en pole, le modèle lui donnait ${pct(p)}</title>
        <rect x="${x}" y="${y(p)}" width="${w}" height="${Math.max(1, y(0) - y(p))}" rx="3" fill="${c}"/>
        <text x="${x + w / 2}" y="${y(0) + 10}" transform="rotate(-60 ${x + w / 2} ${y(0) + 10})" text-anchor="end">${esc(lib)}</text></g>`;
    }).join("");
    const ligne = `<line x1="${gauche}" x2="${W}" y1="${y(hasard)}" y2="${y(hasard)}" stroke="#808a96" stroke-dasharray="5 4"/><text x="${W}" y="${y(hasard) - 4}" text-anchor="end">hasard</text>`;
    $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chance donnée au pilote qui a fait la pole, Grand Prix par Grand Prix">${grille}${barres}${ligne}</svg>`;
  }
  function rendreHistorique() {
    const gps = [...(E.history.saisons[E.season] || [])].reverse();
    $("#history-table").innerHTML = `<thead><tr><th>Grand Prix</th><th>Pole</th><th class="num">Chance donnée</th><th>Favori du modèle</th><th>Vainqueur</th></tr></thead><tbody>${gps.map((g) => {
      const pole = g.poleman ? personne(g.poleman) : null, fav = favoriPole(g), vq = g.vainqueur ? personne(g.vainqueur) : null;
      return `<tr><td>${esc(g.gp_fr || nomGP(g.gp))}${g.pluie ? '<span class="f1-mouille">pluie</span>' : ""}</td>
        <td>${pole ? `<span class="club">${ecurie(pole.couleur)}${esc(pole.famille)}</span>` : "–"}</td>
        <td class="num">${pct(chancePole(g))}</td><td>${fav ? esc(personne(fav.code).famille) : "–"}</td><td>${vq ? esc(vq.famille) : "–"}</td></tr>`;
    }).join("")}</tbody>`;
  }
  function rendreBilan() {
    const s = E.history.saisons, passe = [...(s["2024"] || []), ...(s["2025"] || [])].filter((g) => g.poleman);
    const rang = (gp, code) => [...gp.pilotes].sort((a, b) => (b.avant ?? 0) - (a.avant ?? 0)).findIndex((p) => p.code === code) + 1;
    const rangs = passe.map((g) => rang(g, g.poleman));
    $("#tiles").innerHTML = [
      [`${rangs.filter((r) => r > 0 && r <= 3).length} sur ${passe.length}`, "Le poleman était dans les 3 favoris du modèle avant les essais (2024 et 2025)."],
      [`${rangs.filter((r) => r === 1).length} sur ${passe.length}`, "Le favori du modèle a fait la pole. Un pronostic, pas une certitude."],
    ].map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join("");
  }
  function rendreEtude() {
    const e = E.etude;
    if (!e) { $("#etude").hidden = true; return; }
    $("#etude-grille").innerHTML = `<thead><tr><th>Modèle de victoire</th><th class="num">Log-loss ${esc(e.periode_choix)}</th><th class="num">Brier ${esc(e.periode_choix)}</th><th class="num">Log-loss ${esc(e.periode_test)}</th><th class="num">Brier ${esc(e.periode_test)}</th></tr></thead><tbody>${e.grille.map((r) => `<tr>
      <td>${esc(r.modele)}</td><td class="num">${virgule(r.log_loss_choix)}</td><td class="num">${virgule(r.brier_choix)}</td><td class="num">${virgule(r.log_loss_test)}</td><td class="num">${virgule(r.brier_test)}</td></tr>`).join("")}</tbody>`;
    const fl = (a) => `${virgule(a[0])} → ${virgule(a[1])}`;
    $("#etude-variables").innerHTML = `<thead><tr><th>Variable ajoutée</th><th class="num">Log-loss ${esc(e.periode_choix)}</th><th class="num">Brier ${esc(e.periode_choix)}</th><th class="num">Log-loss ${esc(e.periode_test)}</th><th class="num">Brier ${esc(e.periode_test)}</th><th>Décision</th></tr></thead><tbody>${e.variables.map((v) => `<tr>
      <td>${esc(v.variable)}</td><td class="num">${fl(v.log_loss_choix)}</td><td class="num">${fl(v.brier_choix)}</td><td class="num">${fl(v.log_loss_test)}</td><td class="num">${fl(v.brier_test)}</td>
      <td>${v.retenue ? "retenue" : "écartée"}</td></tr>`).join("")}</tbody>`;
  }

  /* ---------- démarrage */
  async function main() {
    try {
      [E.next, E.history, E.perf, E.journal] = await Promise.all(["next", "history", "performance", "journal"].map(donnees));
    } catch (err) {
      if ($("#gp-name")) $("#gp-name").textContent = "Pronostics indisponibles";
      const el = $("#grid") || $("#chart");
      if (el) el.innerHTML = `<p class="erreur">Les données n'ont pas pu être chargées (${esc(err.message)}). Recharge la page dans quelques minutes.</p>`;
      return;
    }
    try { E.etude = await donnees("etude_f1"); } catch { E.etude = null; }
    for (const gps of Object.values(E.history.saisons)) for (const g of gps) if (g.gp_fr) NOMS_GP[g.gp] = g.gp_fr;
    if (E.next.gp_fr) NOMS_GP[E.next.gp] = E.next.gp_fr;
    E.season = Object.keys(E.history.saisons).sort().reverse()[0];
    if (PAGE === "f1-methode") {
      rendreBilan(); rendreSaisons(); rendreGraphe(); rendreHistorique(); rendreEtude(); rendreJournal($("#journal"), 0);
      document.addEventListener("click", (e) => {
        const b = e.target.closest("[data-season]");
        if (!b) return;
        E.season = b.dataset.season; rendreSaisons(); rendreGraphe(); rendreHistorique();
      });
    } else {
      rendreGP(); rendreSeances(); rendreGrille(); rendreFavoris(); rendrePilotes(); rendreReel(); rendreJournal($("#journal"), 5);
      tic(); setInterval(tic, 1000); setInterval(rendreSeances, 60000);
    }
    $("#updated").textContent = `Dernière mise à jour : ${quand(E.next.maj_utc)}.`;
  }
  main();
})();
