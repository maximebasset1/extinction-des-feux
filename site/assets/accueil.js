/* Accueil : prochain départ en Formule 1 et en football, matchs à la une, surprises récentes, grille la plus probable. */
"use strict";

const SEANCES = { FP1: "Essais libres 1", SQ: "Qualifications sprint", FP2: "Essais libres 2", S: "Sprint", FP3: "Essais libres 3", Q: "Qualifications", R: "Course" };
const ORDRE = ["FP1", "SQ", "FP2", "S", "FP3", "Q", "R"];
const DUREE = { FP1: 60, FP2: 60, FP3: 60, SQ: 45, S: 60, Q: 60, R: 120 };

function prochaineSeance(n) {
  const s = n.sessions || {}, now = Date.now();
  return ORDRE.filter((k) => s[k]).find((k) => new Date(s[k]).getTime() + (DUREE[k] || 60) * 6e4 > now);
}
function favorisPole(n) {
  const cle = n.pole.some((d) => d.apres != null) ? "apres" : "avant";
  return [...n.pole].map((d) => ({ ...d, p: d[cle] })).sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
}

function rendreF1(n) {
  const k = prochaineSeance(n);
  $("#dep-f1-titre").textContent = n.gp_fr || `Grand Prix ${n.gp}`;
  if (n.saison_terminee || !k) {
    $("#dep-f1-quand").textContent = n.saison_terminee ? "La saison est terminée." : "Course terminée. Le prochain pronostic arrive dans quelques heures.";
  } else {
    $("#dep-f1-quand").textContent = `${SEANCES[k]} ${quand(n.sessions[k])}, ${relatif(n.sessions[k])}`;
  }
  let liste, titre, h2, favoris;
  if (!n.saison_terminee && !k && (n.arrivee || []).length) {
    liste = n.arrivee.map((d) => ({ ...d, pos: d.place, p: null }));
    h2 = "Formule 1, résultat de la course"; titre = "Les six premiers à l'arrivée."; favoris = [];
  } else if (n.qualif_disputee && n.victoire && n.victoire.length) {
    // grille connue : les vraies places de départ, avec les chances de victoire
    liste = [...n.victoire].sort((a, b) => (a.grille ?? 99) - (b.grille ?? 99)).map((d, i) => ({ ...d, pos: d.grille ?? i + 1, p: d.proba }));
    favoris = [...liste].sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
    h2 = "Formule 1, qui va gagner ?";
    const enTete = liste[0];
    titre = n.grille_source === "officielle"
      ? `Grille officielle, pénalités comprises${enTete ? ` : ${enTete.nom} part en tête` : ""}. Chances de victoire.`
      : `${n.poleman ? `${n.poleman.nom} a fait la pole. ` : ""}Grille provisoire (ordre de la qualif) et chances de victoire.`;
  } else {
    liste = favorisPole(n).map((d, i) => ({ ...d, pos: i + 1 }));
    favoris = liste;
    h2 = "Formule 1, la grille la plus probable";
    titre = n.pole.some((d) => d.apres != null) ? "Chances de pole, mises à jour avec les essais du week-end." : "Chances de pole, avant les essais du week-end.";
  }
  $("#dep-f1-detail").textContent = favoris.slice(0, 3).map((d) => `${d.famille} ${pct(d.p)}`).join(", ");
  $("#h-grille").textContent = h2;
  $("#grille-note").textContent = titre;
  const max = Math.max(...liste.map((d) => d.p ?? 0), 0.01);
  $("#grille").innerHTML = liste.slice(0, 6).map((d) => `<li><span class="pos">${esc(d.pos)}</span>
    <span class="pilote"><b>${esc(d.famille)}${d.stands ? ` <span class="penalite">départ des stands</span>` : d.penalite > 0 ? ` <span class="penalite">pénalité : ${esc(d.penalite)} place${d.penalite > 1 ? "s" : ""}</span>` : ""}</b><span><i class="ecurie" style="background:${couleur(d.couleur) || "#888"}"></i>${esc(d.equipe)}</span></span>
    <span class="jauge">${d.p != null ? `<i style="width:${((100 * d.p) / max).toFixed(1)}%;background:${couleur(d.couleur) || "#888"}"></i>` : ""}</span>
    <span class="pct">${d.p != null ? pct(d.p) : ""}</span></li>`).join("");
}

function rendreFoot(i) {
  const lien = (m, comp) => `${ROOT}foot/${i.slugs[comp]}.html#match=${encodeURIComponent(m.id)}`;
  const prochain = i.a_la_une.find((m) => !m.kickoff || new Date(m.kickoff) > new Date());
  if (prochain) {
    const c = (k) => i.clubs[k] || { nom: k.split(":").pop() };
    $("#dep-foot").href = lien(prochain, prochain.c);
    $("#dep-foot-titre").textContent = `${c(prochain.home).nom} - ${c(prochain.away).nom}`;
    $("#dep-foot-quand").textContent = `${i.noms[prochain.c]}, ${quandMatch(prochain)}${prochain.kickoff ? `, ${relatif(prochain.kickoff)}` : ""}`;
    $("#dep-foot-detail").innerHTML = barre(prochain.p, c(prochain.home).nom, c(prochain.away).nom);
  } else {
    $("#dep-foot-titre").textContent = "Pas de grande affiche cette semaine";
  }
  $("#une").innerHTML = i.a_la_une.length
    ? i.a_la_une.map((m) => ligneMatch(m, i.clubs, { lien: lien(m, m.c), comp: i.noms[m.c], jourDansHeure: true })).join("")
    : `<li class="vide">Pas de match annoncé cette semaine.</li>`;
  $("#surprises").innerHTML = i.surprises.length
    ? i.surprises.map((m) => ligneMatch(m, i.clubs, { lien: lien(m, m.competition), comp: i.noms[m.competition], jourDansHeure: true })).join("")
    : `<li class="vide">Aucune surprise ces deux dernières semaines : les favoris ont tenu.</li>`;
  // une seule liste suivie : un match à la une et en direct garde les deux lignes à jour (même identifiant)
  const vus = new Set(), suivis = [...(i.du_jour || []), ...i.a_la_une].filter((m) => !vus.has(m.id) && vus.add(m.id));
  const rendreDirect = sectionDirect(i, lien);
  suivreDirect([{ matchs: suivis, clubs: i.clubs }], { apresTour: rendreDirect });
  listeCompetitions($("#competitions"), i.competitions);
  const t = i.fiabilite, coupes = t.filter((r) => !r.avec_cotes), ligues = t.filter((r) => r.avec_cotes);
  const gain = (r) => r.habitudes.rps - r.modele.rps;
  $("#fiable").textContent = `Rejoué semaine par semaine depuis ${i.saisons_test[0]} sur ${t.reduce((s, r) => s + r.matchs, 0).toLocaleString("fr-FR")} matchs, le modèle fait mieux que les pourcentages habituels dans ${t.filter((r) => gain(r) > 0).length} compétitions sur ${t.length}`
    + `${ligues.length ? `, et rejoint le niveau des bookmakers en championnat une fois leurs cotes ajoutées` : ""}. Le favori ne gagne pourtant qu'un peu plus d'un match sur deux : au football, ce sont les probabilités qui doivent être justes, pas chaque pronostic.`
    + `${coupes.length ? " En coupe d'Europe, sans historique de cotes gratuit, seules nos statistiques sont jugées." : ""}`;
}

async function main() {
  const [f1, foot] = await Promise.allSettled([donnees("next"), donnees("foot/index")]);
  if (f1.status === "fulfilled") rendreF1(f1.value);
  else { $("#dep-f1-titre").textContent = "Pronostic indisponible"; erreur($("#grille"), f1.reason); }
  if (foot.status === "fulfilled") rendreFoot(foot.value);
  else { $("#dep-foot-titre").textContent = "Pronostics indisponibles"; erreur($("#une"), foot.reason); }
}
main();
