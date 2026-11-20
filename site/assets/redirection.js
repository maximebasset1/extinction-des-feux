/* Anciennes adresses : on suit jusqu'à la nouvelle page en gardant le lien vers un match (#match=...). */
"use strict";
(() => {
  const cible = document.currentScript && document.currentScript.dataset.cible;
  if (cible) location.replace(cible + location.hash);
})();
