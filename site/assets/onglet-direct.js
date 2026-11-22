/* Barre des compétitions de la section Football : l'onglet « En direct » affiche une pastille et le nombre de matchs en cours
   (masqués quand il n'y en a aucun), et l'onglet de la page courante reste visible quand la barre défile (mobile).
   Le nombre vient du relais du direct (direct.js, partagé avec le suivi des matchs : une seule lecture toutes les 15 s au plus). */
"use strict";

(() => {
  const bande = document.querySelector(".bande-in");
  if (!bande) return;

  const courant = bande.querySelector('[aria-current="page"]');
  if (courant) {
    const dx = courant.getBoundingClientRect().left - bande.getBoundingClientRect().left;
    bande.scrollLeft = Math.max(0, bande.scrollLeft + dx - (bande.clientWidth - courant.offsetWidth) / 2);
  }

  const lien = bande.querySelector("a[data-direct]"), pastille = lien && lien.querySelector(".bande-live");
  if (!pastille || typeof lireRelais !== "function") return;
  const chiffre = pastille.querySelector("b"), texte = pastille.querySelector(".cache");
  const FRAIS_MS = 20 * 6e4;   // un relais muet depuis 20 min ne dit plus rien de fiable : on masque

  const afficher = (n) => {
    pastille.hidden = !n;
    chiffre.textContent = n || "";
    texte.textContent = n > 1 ? " matchs en cours" : " match en cours";
  };
  async function tour() {
    if (document.hidden) return;
    try {
      const r = await lireRelais();
      const frais = !r.maj_utc || Date.now() - Date.parse(r.maj_utc) < FRAIS_MS;
      afficher(frais ? (r.matchs || []).filter((f) => DIRECT_EN_JEU.has(f.st)).length : 0);
    } catch {
      afficher(0);   // relais injoignable : pas de pastille plutôt qu'un nombre périmé
    }
  }
  tour();
  setInterval(tour, 60e3);
  document.addEventListener("visibilitychange", tour);
})();
