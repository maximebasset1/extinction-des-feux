/* Journées d'une compétition (football) : libellé court des pilules et journée ouverte à l'arrivée.
   Les libellés longs viennent de football/pipeline.py : « Journée 12 », tours de coupe, « Semaine du 24 septembre ». */
"use strict";

const FENETRE_JOURNEE_MS = 12 * 36e5;   // un match commencé depuis moins de 12 h garde sa journée ouverte
const TOURS_COURTS = { "Qualifications": "Qualifs", "Huitièmes de finale": "8es", "Quarts de finale": "Quarts", "Demi-finales": "Demies" };
const MOIS_COURTS = { janvier: "janv.", février: "févr.", avril: "avr.", juillet: "juil.", septembre: "sept.", octobre: "oct.",
  novembre: "nov.", décembre: "déc." };

function libelleCourt(journee) {
  const numero = /^Journée (\d+)$/.exec(journee);
  if (numero) return `J${numero[1]}`;
  const semaine = /^Semaine du (\d+) (\S+)$/.exec(journee);
  if (semaine) return `${semaine[1]} ${MOIS_COURTS[semaine[2]] || semaine[2]}`;
  return TOURS_COURTS[journee] || journee;
}

/* la journée d'un match en cours, sinon celle d'un match joué aujourd'hui, sinon la prochaine, sinon la dernière */
function journeeParDefaut(d, maintenant = Date.now(), jour = aujourdhui()) {
  const enCours = d.matchs.find((m) => m.kickoff && m.etat !== "joue" && maintenant >= Date.parse(m.kickoff)
    && maintenant - Date.parse(m.kickoff) < FENETRE_JOURNEE_MS);
  const duJour = [...d.matchs].reverse().find((m) => m.etat === "joue" && m.jour === jour);
  return enCours?.journee || duJour?.journee || (d.journees.includes(d.prochaine) ? d.prochaine : null)
    || d.journees[d.journees.length - 1];
}
