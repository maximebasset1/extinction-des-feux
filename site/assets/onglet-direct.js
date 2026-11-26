/* Barre principale : « En direct » montre une pastille et le nombre de matchs de football en cours (masqués quand il n'y
   en a aucun), et l'entrée de la page courante reste visible quand la barre ou la ligne de filtres défile (mobile).
   Le nombre vient du relais du direct (direct.js, partagé avec le suivi des matchs : une seule lecture toutes les 15 s au plus). */
"use strict";

(() => {
  for (const barre of document.querySelectorAll(".menu, .filtres")) {
    const courant = barre.querySelector('[aria-current="page"]');
    if (!courant) continue;
    const dx = courant.getBoundingClientRect().left - barre.getBoundingClientRect().left;
    barre.scrollLeft = Math.max(0, barre.scrollLeft + dx - (barre.clientWidth - courant.offsetWidth) / 2);
  }

  const pastille = document.querySelector(".menu a[data-direct] .menu-live");
  if (!pastille || typeof lireRelais !== "function") return;
  const chiffre = pastille.querySelector("b"), texte = pastille.querySelector(".cache");
  const afficher = (n) => {
    pastille.hidden = !n;
    chiffre.textContent = n || "";
    texte.textContent = n > 1 ? " matchs en cours" : " match en cours";
  };
  async function tour() {
    if (document.hidden) return;
    try {
      const r = await lireRelais();
      afficher(relaisPerime(r) ? 0 : enDirectMaintenant(r, []).length);   // relevé trop vieux : rien de fiable, on masque
    } catch {
      afficher(0);   // relais injoignable : pas de pastille plutôt qu'un nombre périmé
    }
  }
  tour();
  setInterval(tour, 60e3);
  document.addEventListener("visibilitychange", tour);
})();
