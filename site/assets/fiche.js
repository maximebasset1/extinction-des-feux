/* Fiche d'un match en direct (football) : courbe des chances 1/N/2 depuis le coup d'envoi, avant-match contre maintenant,
   scores finaux les plus probables. S'ouvre en cliquant un match suivi par direct.js (accueil, pages des compétitions).
   Tout est recalculé dans le navigateur avec le modèle de modele-direct.js, à partir des buts relevés par le relais. */
"use strict";

const FICHE = { dlg: null, corps: null, cle: null, html: "", lien: null, detail: null };
const COURBE = { L: 440, H: 250, g: 36, d: 12, h: 12, b: 28 };   // taille du dessin et marges (gauche, droite, haut, bas)

const clubDe = (clubs, k) => clubs[k] || { nom: String(k).split(":").pop(), sigle: String(k).split(":").pop().slice(0, 3).toUpperCase() };

/* ---------- courbe : trois lignes (domicile, nul, extérieur) de 0 à 90 minutes, un trait vertical à chaque but relevé */
function svgCourbe(points, ev, fin, noms) {
  const { L, H, g, d, h, b } = COURBE, w = L - g - d, ht = H - h - b;
  const x = (t) => (g + (w * t) / 90).toFixed(1), y = (p) => (h + ht * (1 - p)).toFixed(1);
  const ligne = (k) => points.map((q, i) => `${i ? "L" : "M"}${x(q.t)},${y(q.p[k])}`).join(" ");
  const fond = [0, 0.25, 0.5, 0.75, 1].map((p) => `<line class="c-grille" x1="${g}" x2="${L - d}" y1="${y(p)}" y2="${y(p)}"/>`
    + `<text class="c-axe" x="${g - 6}" y="${(Number(y(p)) + 4).toFixed(1)}" text-anchor="end">${Math.round(p * 100)}</text>`).join("");
  const temps = [0, 15, 30, 45, 60, 75, 90].map((t) => `<text class="c-axe" x="${x(t)}" y="${H - 8}" text-anchor="middle">${t}′</text>`).join("");
  const buts = [...new Map(ev.filter(([m]) => Number.isFinite(m) && m <= fin).map((e) => [e[0], e])).values()].map(([m, , hg, ag]) => `<line class="c-but" x1="${x(m)}" x2="${x(m)}" y1="${h}" y2="${h + ht}"/>`
    + `<text class="c-score" x="${x(m)}" y="${h - 2}" text-anchor="${m > 80 ? "end" : m < 10 ? "start" : "middle"}">${nombre(hg)}-${nombre(ag)}</text>`).join("");
  const dernier = points[points.length - 1];
  const bouts = [0, 1, 2].map((k) => `<circle class="c-bout c-l${k}" cx="${x(dernier.t)}" cy="${y(dernier.p[k])}" r="3.5"/>`).join("");
  const resume = `Chances de victoire de ${noms[0]} : ${pct(points[0].p[0])} au coup d'envoi, ${pct(dernier.p[0])} à la ${dernier.t}e minute. `
    + `Match nul : ${pct(points[0].p[1])}, puis ${pct(dernier.p[1])}. Victoire de ${noms[1]} : ${pct(points[0].p[2])}, puis ${pct(dernier.p[2])}.`;
  return `<svg class="courbe" viewBox="0 0 ${L} ${H}" role="img" aria-label="${esc(resume)}">${fond}`
    + `<line class="c-mt" x1="${x(45)}" x2="${x(45)}" y1="${h}" y2="${h + ht}"/>${buts}${temps}`
    + `<path class="c-l1" d="${ligne(1)}"/><path class="c-l2" d="${ligne(2)}"/><path class="c-l0" d="${ligne(0)}"/>${bouts}</svg>`;
}

/* ---------- contenu d'une fiche */
function contenuFiche({ m, f, clubs }) {
  const dom = clubDe(clubs, m.home), ext = clubDe(clubs, m.away), g = f.g || [0, 0];
  const t = minuteMaintenant(f, D.relais?.maj_utc);
  const fini = DIRECT_FINI.has(f.st), enModele = ["1H", "HT", "2H"].includes(f.st);
  const etat = f.st === "HT" ? "mi-temps" : fini ? (f.st === "FT?" ? "terminé, score à confirmer" : f.st === "FT" ? "terminé" : f.st === "AET" ? "après prolongation" : "tirs au but")
    : ["1H", "2H"].includes(f.st) ? minuteTexte(t) : f.st === "P" ? "tirs au but" : f.st === "ET" ? "prolongation" : "interrompu";
  // minute de jeu d'arrivée de la courbe : la pause à 45, la fin à 90 (les prolongations ne sont pas modélisées)
  const jusqua = fini || ["ET", "BT", "P"].includes(f.st) ? 90 : f.st === "HT" ? 45 : Math.min(90, t.base ?? 0);
  const badge = typeof badgeConfiance === "function" ? badgeConfiance(m) : "";
  let html = `<header class="fiche-tete"><h2 id="fiche-titre"><span class="club">${ecusson(dom)}${esc(dom.nom)}</span>
      <span class="fiche-score">${nombre(g[0])} - ${nombre(g[1])}</span><span class="club">${ecusson(ext)}${esc(ext.nom)}</span></h2>
    <p class="fiche-etat">${fini ? "" : `<i class="pastille" aria-hidden="true"></i>`}${esc(etat)}${badge ? ` ${badge}` : ""}</p></header>`;

  const ev = chronologieDe(f, t.base);
  if (m.lam && D.params) {
    const [lh, la] = m.lam;
    // un point par but relevé pour que la marche soit à la bonne minute, un point toutes les trois minutes sinon
    const courbe = courbeChances(lh, la, ev, jusqua, D.params, { pause: f.st === "HT", termine: fini });
    const noms = [dom.nom, ext.nom];
    const now = courbe[courbe.length - 1].p;
    const avant = m.p || courbe[0].p;
    html += `<section aria-labelledby="fiche-h-courbe"><h3 id="fiche-h-courbe">Les chances, minute par minute</h3>
      <ul class="fiche-legende"><li class="c-k0"><i></i>Victoire ${esc(dom.nom)} <b>${pct(now[0])}</b></li><li class="c-k1"><i></i>Match nul <b>${pct(now[1])}</b></li>
        <li class="c-k2"><i></i>Victoire ${esc(ext.nom)} <b>${pct(now[2])}</b></li></ul>
      ${svgCourbe(courbe, ev, jusqua, noms)}
      <p class="note">${ev.length ? `Buts relevés : ${ev.map(([mn, , h, a]) => `${nombre(mn)}′ (${nombre(h)}-${nombre(a)})`).join(", ")}. ` : "Aucun but pour l'instant. "}Chaque trait vertical marque un changement de score vu par le relais${D.relais?.intervalle_min ? ` (relevé toutes les ${D.relais.intervalle_min === 1 ? "minutes" : `${D.relais.intervalle_min} minutes`} : la minute d'un but est précise à ce relevé près)` : ""}.</p></section>`;

    html += `<section aria-labelledby="fiche-h-compar"><h3 id="fiche-h-compar">Avant le match, maintenant</h3><div class="fiche-compar">
      <div><p class="fiche-etiq">Avant le coup d'envoi</p>${barre(avant, dom.nom, ext.nom)}</div>
      <div><p class="fiche-etiq">${f.st === "HT" ? "À la mi-temps" : fini ? "Au coup de sifflet final" : `Maintenant, ${minuteTexte(t)}`}</p>${barre(now, dom.nom, ext.nom)}</div></div>
      <p class="note">${[0, 1, 2].map((k) => {
        const dp = Math.round((now[k] - avant[k]) * 100), nom = ["victoire " + dom.nom, "match nul", "victoire " + ext.nom][k];
        return `${nom} ${dp > 0 ? "+" : dp < 0 ? "−" : "±"}${Math.abs(dp)} point${Math.abs(dp) > 1 ? "s" : ""}`;
      }).join(" · ")}.</p></section>`;

    if (enModele) {
      const mi = f.st === "1H" ? 1 : 2;   // à la pause, la seconde période entière reste à jouer (comme la barre de la ligne)
      const { reste } = tempsRestant(f.st === "HT" ? "45" : `${t.base}${t.plus ? `+${t.plus}` : ""}`, mi, D.params);
      const { scores } = chancesEnDirect(lh, la, g[0], g[1], mi, reste, D.params);
      const max = scores[0]?.p || 1;
      html += `<section aria-labelledby="fiche-h-scores"><h3 id="fiche-h-scores">Scores finaux les plus probables</h3>
        <ol class="fiche-scores">${scores.map((s) => `<li><b>${esc(s.score.replace("-", " - "))}</b><span class="jauge"><i style="width:${((100 * s.p) / max).toFixed(1)}%"></i></span><span class="pct">${pct(s.p)}</span></li>`).join("")}</ol>
        <p class="note">Score au bout des 90 minutes (arrêts de jeu compris), prolongations non comprises.</p></section>`;
    }
  } else {
    html += `<p class="note">${D.params ? "Les buts attendus de ce match ne sont pas publiés : la courbe est indisponible." : "Le modèle du direct n'a pas pu être chargé : la courbe est indisponible."}</p>`;
  }

  const stats = typeof blocStatsGrille === "function" ? blocStatsGrille(m) : "";
  if (stats) html += `<section aria-labelledby="fiche-h-grille"><h3 id="fiche-h-grille">Indicateurs avant-match (grille des scores)</h3>${stats}</section>`;
  if (typeof blocFacteurs === "function") html += blocFacteurs(m, clubs);

  const suivre = `<div class="fiche-clubs">${Favoris_bouton(m.home, dom.nom)}${Favoris_bouton(m.away, ext.nom)}</div>`;
  const aller = FICHE.lien ? `<a class="lien-match" href="${esc(FICHE.lien)}">Pronostic d'avant-match et face-à-face</a>`
    : FICHE.detail ? `<button type="button" class="lien-bouton" data-fiche-detail>Pronostic d'avant-match et face-à-face</button>` : "";
  html += `<footer class="fiche-pied">${suivre}${aller}<p class="note">Chances recalculées dans ton navigateur avec le modèle décrit sur la page <a href="${ROOT}methode.html">Méthode</a> :
    buts attendus calés sur le pronostic publié avant le match, rythme de jeu selon le temps restant et l'écart au score.</p></footer>`;
  return html;
}
const Favoris_bouton = (k, nom) => (typeof Favoris === "undefined" ? "" : Favoris.bouton(k, nom, { texte: true }));

/* ---------- fenêtre */
function creerFiche() {
  const dlg = document.createElement("dialog");
  dlg.className = "fiche";
  dlg.setAttribute("aria-labelledby", "fiche-titre");
  dlg.innerHTML = `<button type="button" class="fiche-fermer" aria-label="Fermer la fiche du match"><span aria-hidden="true">×</span></button><div class="fiche-corps"></div>`;
  document.body.appendChild(dlg);
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg || e.target.closest(".fiche-fermer")) dlg.close();   // clic hors de la fiche : fermeture
    if (e.target.closest("[data-fiche-detail]")) {
      const el = FICHE.detail && document.getElementById(FICHE.detail);
      dlg.close();
      if (el) { el.open = true; el.scrollIntoView({ block: "start" }); el.querySelector("summary")?.focus({ preventScroll: true }); }
    }
  });
  dlg.addEventListener("close", () => { FICHE.cle = null; FICHE.html = ""; });
  FICHE.dlg = dlg; FICHE.corps = dlg.querySelector(".fiche-corps");
}

function majFiche() {
  if (!FICHE.dlg?.open || !FICHE.cle) return;
  const s = D.suivis.find((x) => cleId(x.m.id) === FICHE.cle);
  if (!s) return;
  const html = contenuFiche(s);
  if (html === FICHE.html) return;   // rien n'a changé : on ne touche pas à la fenêtre (le focus reste en place)
  const actif = document.activeElement?.closest?.("[data-favori]")?.dataset.favori;
  FICHE.html = html;
  FICHE.corps.innerHTML = html;
  if (typeof Favoris !== "undefined") Favoris.marquer(FICHE.corps);
  if (actif) FICHE.corps.querySelector(`[data-favori="${CSS.escape(actif)}"]`)?.focus();
}

function ouvrirFiche(cle, lien, detail) {
  if (!FICHE.dlg) creerFiche();
  FICHE.cle = cle; FICHE.lien = lien; FICHE.detail = detail; FICHE.html = "";
  if (!FICHE.dlg.open) FICHE.dlg.showModal();
  majFiche();
  FICHE.dlg.scrollTop = 0;
}

/* clic sur une ligne de match suivie en direct : la fiche s'ouvre à la place du lien ou du dépliant ;
   les autres lignes (à venir, jouées depuis longtemps) gardent leur comportement */
document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  if (e.target.closest("button, .m-detail, dialog")) return;
  const li = e.target.closest("li.match[data-match]");
  if (!li || typeof D === "undefined") return;
  const s = D.suivis.find((x) => cleId(x.m.id) === li.dataset.match);
  if (!s || s.connu === false || DIRECT_REPORTE[s.f.st]) return;
  e.preventDefault();
  const a = li.querySelector("a.m-lien"), det = li.querySelector("details");
  ouvrirFiche(li.dataset.match, a ? a.getAttribute("href") : null, det ? det.id : null);
});
