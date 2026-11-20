/* Page Méthode : tableau de fiabilité par compétition. */
"use strict";

async function main() {
  let i;
  try { i = await donnees("foot/index"); } catch (err) { erreur($("#m-table"), err); return; }
  $("#m-table").innerHTML = `<thead><tr><th>Compétition</th><th class="num">Matchs</th><th class="num">Nos statistiques</th><th class="num">Avec les cotes</th><th class="num">Cotes seules</th><th class="num">Habitudes</th><th class="num">Le favori gagne</th></tr></thead><tbody>${i.fiabilite.map((r) => `<tr>
    <td>${esc(r.nom)}</td><td class="num">${nombre(r.matchs).toLocaleString("fr-FR")}</td><td class="num">${virgule(r.modele.rps, 3)}</td>
    <td class="num">${r.avec_cotes ? virgule(r.avec_cotes.rps, 3) : "–"}</td><td class="num">${r.marche ? virgule(r.marche.rps, 3) : "–"}</td>
    <td class="num">${virgule(r.habitudes.rps, 3)}</td><td class="num">${pct((r.avec_cotes || r.modele).bons_favoris)}</td></tr>`).join("")}</tbody>
    <caption>Score RPS : plus il est bas, mieux c'est. En coupe d'Europe, pas d'historique de cotes gratuit : seules nos statistiques sont jugées.</caption>`;
  if (Number.isFinite(i.part_marche)) $("#m-part").textContent = `Elles comptent pour environ ${Math.round(i.part_marche * 100)} % du pronostic final`;
  $("#m-maj").textContent = `Dernière mise à jour des pronostics de football : ${quand(i.maj_utc)}.`;
}
main();
