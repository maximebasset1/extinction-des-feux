/* Clubs favoris (football) : gardés dans le localStorage de ce navigateur. Sans compte, rien n'est envoyé ; avec un
   compte, compte.js les enregistre aussi côté serveur et garde cette liste comme copie.
   Les lignes de match d'un club favori sont mises en valeur ; la section « En direct » de l'accueil les place en tête (direct.js).
   Les pages appellent seulement `Favoris.bouton(club, nom)` ; le reste (état des boutons, lignes à marquer) se fait ici.
   Évènement « favoris » : avec `detail.club` quand l'utilisateur touche une étoile, sans quand la liste vient d'ailleurs. */
"use strict";

const Favoris = (() => {
  const CLE = "extinction.favoris.v1";
  const MAX = 100;
  let memoire = [];   // secours quand le navigateur refuse le stockage (navigation privée, données bloquées)
  let refuse = false;
  let limite = () => MAX;   // compte.js l'abaisse quand un compte est connecté

  function lire() {
    if (refuse) return memoire;
    try {
      const v = JSON.parse(localStorage.getItem(CLE) || "[]");
      return Array.isArray(v) ? v.filter((k) => typeof k === "string" && k.length < 80).slice(0, MAX) : [];
    } catch { return memoire; }
  }
  function ecrire(liste) {
    memoire = liste;
    try { localStorage.setItem(CLE, JSON.stringify(liste)); } catch { refuse = true; /* le favori tient jusqu'à la fermeture de la page */ }
  }

  const liste = () => lire();
  const est = (club) => lire().includes(club);
  const matchFavori = (m) => { const l = lire(); return l.includes(m.home) || l.includes(m.away) ? 1 : 0; };

  function basculer(club) {
    const l = lire(), i = l.indexOf(club);
    if (i < 0 && l.length >= limite()) {
      document.dispatchEvent(new CustomEvent("favoris-plein", { detail: { max: limite() } }));
      return;
    }
    if (i >= 0) l.splice(i, 1); else l.unshift(club);
    ecrire(l.slice(0, MAX));
    marquer();
    document.dispatchEvent(new CustomEvent("favoris", { detail: { club } }));
  }

  /* la liste d'un compte (ou la liste vide après une déconnexion) remplace celle du navigateur */
  function remplacer(neuve) {
    const propre = neuve.filter((k) => typeof k === "string").slice(0, MAX);
    if (JSON.stringify(propre) === JSON.stringify(lire())) return;
    ecrire(propre);
    marquer();
    document.dispatchEvent(new CustomEvent("favoris"));
  }
  const fixerLimite = (f) => { limite = f; };

  /* bouton étoile ; avec `texte`, une pastille « Suivre Lille » plutôt que l'étoile seule ; `mini` : à côté d'un nom
     d'équipe dans une ligne de match */
  function bouton(club, nom, { texte = false, mini = false } = {}) {
    const etoile = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><polygon points="12,2 15,9 22.5,9 16.5,13.5 18.7,21 12,16.5 5.3,21 7.5,13.5 1.5,9 9,9"/></svg>`;
    return `<button type="button" class="etoile${texte ? " etoile-texte" : ""}${mini ? " etoile-mini" : ""}" data-favori="${esc(club)}" data-nom="${esc(nom)}" data-texte="${texte ? "1" : ""}" aria-pressed="${est(club)}">${etoile}${texte ? `<span></span>` : ""}</button>`;
  }

  /* met à jour les boutons et les lignes de match de `racine` */
  function marquer(racine = document) {
    const l = new Set(lire());
    for (const b of racine.querySelectorAll("button[data-favori]")) {
      const on = l.has(b.dataset.favori), nom = b.dataset.nom || b.dataset.favori.split(":").pop();
      b.setAttribute("aria-pressed", String(on));
      b.setAttribute("aria-label", `${nom}, club favori`);
      b.title = on ? `Retirer ${nom} des favoris` : `Ajouter ${nom} aux favoris`;
      const t = b.querySelector("span");
      const texte = on ? `${nom}, suivi` : `Suivre ${nom}`;
      if (t && t.textContent !== texte) t.textContent = texte;   // réécrire un texte identique relancerait l'observateur en boucle
    }
    for (const li of racine.querySelectorAll("li.match[data-home], li.prono-item[data-home]")) {
      li.classList.toggle("fav", l.has(li.dataset.home) || l.has(li.dataset.away));
    }
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-favori]");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    basculer(b.dataset.favori);
  });
  // les pages refont leurs listes à tout moment : on remarque les nouvelles lignes, sans toucher à ce qui est déjà marqué
  let attente = false;
  new MutationObserver(() => {
    if (attente) return;
    attente = true;
    requestAnimationFrame(() => { attente = false; marquer(); });
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("storage", (e) => { if (e.key === CLE) { marquer(); document.dispatchEvent(new CustomEvent("favoris")); } });
  document.addEventListener("DOMContentLoaded", () => marquer());

  return { liste, est, basculer, remplacer, fixerLimite, matchFavori, bouton, marquer };
})();

if (typeof module !== "undefined") module.exports = { Favoris };
