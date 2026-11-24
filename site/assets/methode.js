/* Page Méthode : tableau de fiabilité par compétition, et bilan du modèle du direct (jugement et calibration à la mi-temps). */
"use strict";

/* diagramme de fiabilité : chance annoncée à la pause (axe horizontal) contre fréquence observée à la fin (axe vertical) ;
   un point sur la diagonale = un modèle juste ; la taille du point suit le nombre de matchs */
function diagrammeFiabilite(points) {
  const T = 340, g = 38, h = 12, d = 12, b = 34, w = T - g - d, ht = T - h - b, max = Math.max(...points.map((q) => q.matchs));
  const x = (p) => (g + w * p).toFixed(1), y = (p) => (h + ht * (1 - p)).toFixed(1);
  const axes = [0, 0.25, 0.5, 0.75, 1].map((p) => `<line class="c-grille" x1="${g}" x2="${T - d}" y1="${y(p)}" y2="${y(p)}"/><line class="c-grille" x1="${x(p)}" x2="${x(p)}" y1="${h}" y2="${h + ht}"/>`
    + `<text class="c-axe" x="${g - 6}" y="${(Number(y(p)) + 4).toFixed(1)}" text-anchor="end">${p * 100}</text><text class="c-axe" x="${x(p)}" y="${T - b + 16}" text-anchor="middle">${p * 100}</text>`).join("");
  const classe = { domicile: 0, nul: 1, exterieur: 2 };
  const pts = points.map((q) => `<circle class="k-pt k-p${classe[q.issue]}" cx="${x(q.annonce)}" cy="${y(q.observe)}" r="${(3 + 5 * Math.sqrt(q.matchs / max)).toFixed(1)}"><title>${esc(q.issue)} : annoncé ${pct(q.annonce)}, observé ${pct(q.observe)} (${q.matchs.toLocaleString("fr-FR")} matchs)</title></circle>`).join("");
  return `<svg class="courbe" viewBox="0 0 ${T} ${T}" role="img" aria-label="Diagramme de fiabilité : chances annoncées à la mi-temps contre fréquences observées à la fin du match. Les points suivent la diagonale.">${axes}`
    + `<line class="k-diag" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/>${pts}`
    + `<text class="c-axe" x="${(g + w / 2).toFixed(1)}" y="${T - 4}" text-anchor="middle">chance annoncée à la mi-temps (%)</text>`
    + `<text class="c-axe" transform="rotate(-90 11 ${(h + ht / 2).toFixed(1)})" x="11" y="${(h + ht / 2).toFixed(1)}" text-anchor="middle">fréquence observée (%)</text></svg>`;
}

function rendreDirect(d) {
  if (!d.fiabilite_mi_temps?.length) return;
  const n = d.matchs_test, periode = String(d.periode_test).replace("-", " à ");
  const total = d.fiabilite_mi_temps.reduce((s, q) => s + q.matchs, 0);
  const ecart = d.fiabilite_mi_temps.reduce((s, q) => s + Math.abs(q.annonce - q.observe) * q.matchs, 0) / total;
  $("#m-direct-txt").innerHTML = `Pendant un match, les chances sont recalculées dans ton navigateur à chaque but et à chaque minute qui passe. Les buts attendus de chaque équipe, calés pour redonner le pronostic publié au coup d'envoi, sont répartis sur le temps restant (loi de Poisson), avec un rythme qui dépend de l'écart au score : une équipe menée pousse, une équipe qui mène gère. Trois réglages seulement (part des buts en première mi-temps, rythme de l'équipe menée, rythme de l'équipe qui mène) ont été choisis sur les saisons ${esc(String(d.periode_choix).replace("-", " à "))} ; le jugement ci-dessous porte sur ${esc(periode)}, jamais vues pendant le réglage. Les données viennent de douze championnats (football-data.co.uk : score à la pause, score final, cotes d'avant-match).`;
  const rows = d.jugement_mi_temps;
  $("#m-jugement").innerHTML = `<caption>Backtest ${esc(periode)}, ${n.toLocaleString("fr-FR")} matchs : à la mi-temps, quelle chance de victoire, de nul et de défaite, comparée au résultat final. Log-loss et RPS : plus c'est bas, mieux c'est.</caption>
    <thead><tr><th>À la mi-temps, le modèle utilise</th><th class="num">Log-loss</th><th class="num">RPS</th><th class="num">Le favori gagne</th></tr></thead><tbody>${rows.map((r, i) => `<tr${i === rows.length - 1 ? ' class="total"' : ""}>
    <td>${esc(r.methode)}</td><td class="num">${virgule(r.log_loss, 3)}</td><td class="num">${virgule(r.rps, 4)}</td><td class="num">${pct(r.favori_juste)}</td></tr>`).join("")}</tbody>`;
  $("#m-calib").innerHTML = `${diagrammeFiabilite(d.fiabilite_mi_temps)}<figcaption>Calibration à la mi-temps, backtest ${esc(periode)}.</figcaption>`;
  $("#m-calib-txt").innerHTML = `<ul class="fiche-legende"><li class="c-k0"><i></i>Victoire à domicile</li><li class="c-k1"><i></i>Match nul</li><li class="c-k2"><i></i>Victoire à l'extérieur</li></ul>
    <p>À la pause, quand le modèle annonce une chance de 30 %, l'issue arrive-t-elle 30 fois sur 100 ? Chaque point regroupe les matchs de ${esc(periode)} dont la chance annoncée était voisine, et compare la moyenne annoncée à la fréquence observée à la fin du match. Plus les points sont près de la diagonale, plus les chances sont justes.</p>
    <p>L'écart moyen entre chance annoncée et fréquence observée est de <b>${virgule(ecart * 100)} point</b> (pondéré par le nombre de matchs).</p>
    <p class="note">Il s'agit d'un backtest sur des championnats passés, rejoué à la pause de chaque match, et non d'un suivi des matchs diffusés en direct sur ce site.</p>`;
}

function rendreJournal(j) {
  const note = $("#m-journal-note"), chiffres = $("#m-journal-chiffres"), table = $("#m-journal");
  if (!note || !chiffres || !table) return;
  if (!j || !j.matchs) {
    chiffres.hidden = true;
    table.innerHTML = "";
    note.textContent = j?.en_attente
      ? `Aucun match publié dans le journal n'est encore terminé (${j.en_attente} pronostic${j.en_attente > 1 ? "s" : ""} déjà figé${j.en_attente > 1 ? "s" : ""} en attente de résultat).`
      : "Aucun match publié dans le journal n'est encore évalué ; le bilan apparaîtra dès les premiers résultats.";
    return;
  }
  const periode = j.premier && j.dernier
    ? (j.premier === j.dernier ? `le ${jourCourt(j.premier)}` : `du ${jourCourt(j.premier)} au ${jourCourt(j.dernier)}`)
    : "";
  note.textContent = `Pronostics enregistrés avant le coup d'envoi et jugés sur leur résultat réel${periode ? ` (${periode})` : ""}`
    + `${j.en_attente ? `, plus ${j.en_attente} pronostic${j.en_attente > 1 ? "s" : ""} déjà figé${j.en_attente > 1 ? "s" : ""} pour les matchs à venir` : ""}.`;
  const rpsRef = `contre ${virgule(j.rps_habitudes, 3)} pour les habitudes`
    + (j.rps_marche != null
      ? ` et ${virgule(j.rps_marche, 3)} pour les cotes seules`
        + (j.matchs_cotes < j.matchs
          ? ` (${nombre(j.matchs_cotes)} match${j.matchs_cotes > 1 ? "s" : ""} avec cotes, journal à ${virgule(j.rps_sur_cotes, 3)} sur ces mêmes matchs)`
          : "")
      : "");
  chiffres.innerHTML = [
    [nombre(j.matchs).toLocaleString("fr-FR"), `<b>Match${j.matchs > 1 ? "s" : ""} évalué${j.matchs > 1 ? "s" : ""}</b> · ${j.surprises ? `${nombre(j.surprises)} surprise${j.surprises > 1 ? "s" : ""} (<20\u202f%)` : "aucune surprise (<20\u202f%)"}`],
    [virgule(j.rps, 3), `<b>RPS moyen</b> · ${rpsRef}`],
    [pct(j.taux_favori), `<b>Le favori gagne</b> · ${nombre(j.favoris_justes)} fois sur ${nombre(j.matchs)}`],
  ].map(([v, d]) => `<div><dt>${esc(v)}</dt><dd>${d}</dd></div>`).join("");
  chiffres.hidden = false;
  const rows = j.par_competition || [];
  const ligne = (r, total = false) => `<tr${total ? ' class="total"' : ""}><td>${esc(r.nom)}</td><td class="num">${nombre(r.matchs).toLocaleString("fr-FR")}</td>`
    + `<td class="num">${virgule(r.rps, 3)}</td><td class="num">${r.rps_marche != null ? virgule(r.rps_marche, 3) : "–"}</td>`
    + `<td class="num">${virgule(r.rps_habitudes, 3)}</td><td class="num">${pct(r.taux_favori)}</td></tr>`;
  table.innerHTML = `<thead><tr><th>Compétition</th><th class="num">Matchs</th><th class="num">RPS journal</th><th class="num">Cotes seules</th><th class="num">Habitudes</th><th class="num">Le favori gagne</th></tr></thead><tbody>`
    + rows.map((r) => ligne(r)).join("")
    + (rows.length > 1 ? ligne({ nom: "Total", ...j }, true) : "")
    + `</tbody><caption>Score RPS : plus il est bas, mieux c'est. Cotes seules : calculé sur les matchs disposant des cotes d'avant-match (football-data.co.uk). L'échantillon grandit journée après journée : il faut plusieurs centaines de matchs pour conclure statistiquement.</caption>`;
}

async function main() {
  donnees("foot/direct").then(rendreDirect).catch((err) => { $("#m-jugement").innerHTML = ""; erreur($("#m-calib"), err); });
  let i;
  try { i = await donnees("foot/index"); } catch (err) { erreur($("#m-table"), err); return; }
  $("#m-table").innerHTML = `<thead><tr><th>Compétition</th><th class="num">Matchs</th><th class="num">Nos statistiques</th><th class="num">Avec les cotes</th><th class="num">Cotes seules</th><th class="num">Habitudes</th><th class="num">Le favori gagne</th></tr></thead><tbody>${i.fiabilite.map((r) => `<tr>
    <td>${esc(r.nom)}</td><td class="num">${nombre(r.matchs).toLocaleString("fr-FR")}</td><td class="num">${virgule(r.modele.rps, 3)}</td>
    <td class="num">${r.avec_cotes ? virgule(r.avec_cotes.rps, 3) : "–"}</td><td class="num">${r.marche ? virgule(r.marche.rps, 3) : "–"}</td>
    <td class="num">${virgule(r.habitudes.rps, 3)}</td><td class="num">${pct((r.avec_cotes || r.modele).bons_favoris)}</td></tr>`).join("")}</tbody>
    <caption>Score RPS : plus il est bas, mieux c'est. En coupe d'Europe, pas d'historique de cotes gratuit : seules nos statistiques sont jugées.</caption>`;
  rendreJournal(i.journal);
  if (Number.isFinite(i.part_marche)) $("#m-part").textContent = `Elles comptent pour environ ${Math.round(i.part_marche * 100)} % du pronostic final`;
  $("#m-maj").textContent = `Dernière mise à jour des pronostics de football : ${quand(i.maj_utc)}.`;
}
main();
