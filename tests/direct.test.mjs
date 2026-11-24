// tests du direct côté site : rattachement des matchs du relais et chances recalculées
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = vm.createContext({ document: { body: { dataset: {} }, querySelectorAll: () => [] }, console, CSS: { escape: (s) => s }, module: undefined });
for (const f of ["commun.js", "modele-direct.js", "direct.js"]) {
  vm.runInContext(readFileSync(new URL(`../site/assets/${f}`, import.meta.url), "utf8").replace(/^"use strict";/m, ""), ctx, { filename: f });
}
const { rattacher, minuteMaintenant, chancesEnDirect, tempsRestant, courbeChances, chronologieDe, scoreA, aSuivre, D } = vm.runInContext("({ rattacher, minuteMaintenant, chancesEnDirect, tempsRestant, courbeChances, chronologieDe, scoreA, aSuivre, D })", ctx);

const clubs = {
  "FRA:Lorient": { nom: "Lorient" }, "FRA:Rennes": { nom: "Stade Rennais" }, "FRA:Paris FC": { nom: "Paris FC" },
  "FRA:Angers": { nom: "Angers" }, "FRA:Marseille": { nom: "Marseille" }, "FRA:Le Mans": { nom: "Le Mans" },
  "FRA:Paris SG": { nom: "Paris Saint-Germain" }, "FRA:Nice": { nom: "Nice" },
  "ENG:Man United": { nom: "Manchester United" }, "ENG:Liverpool": { nom: "Liverpool" },
  "ENG:Man City": { nom: "Manchester City" }, "ENG:Everton": { nom: "Everton" },
  "GER:Werder Bremen": { nom: "Werder Brême" }, "GER:Hamburg": { nom: "Hamburger SV" },
  "GER:Augsburg": { nom: "Augsbourg" }, "GER:Mainz": { nom: "Mayence" },
  "ESP:Ath Madrid": { nom: "Atlético de Madrid" }, "ESP:Getafe": { nom: "Getafe" },
  "ITA:Inter": { nom: "Inter" }, "ITA:Napoli": { nom: "Napoli" },
};
const m = (c, ko, home, away) => ({ id: `${c}-${home}-${away}`, c, kickoff: ko, home, away });
const f = (id, c, ko, h, a) => ({ id, c, ko, h, a, st: "1H", min: 10, g: [0, 0] });

test("les noms d'API-Football retrouvent nos clubs, même à la même heure", () => {
  const nos = [
    m("F1", "2026-11-22T16:15:00Z", "FRA:Lorient", "FRA:Rennes"),
    m("F1", "2026-11-22T16:15:00Z", "FRA:Nice", "FRA:Paris SG"),
    m("E0", "2026-11-22T16:30:00Z", "ENG:Liverpool", "ENG:Man United"),
    m("E0", "2026-11-22T16:30:00Z", "ENG:Everton", "ENG:Man City"),
    m("D1", "2026-11-22T16:30:00Z", "GER:Werder Bremen", "GER:Hamburg"),
    m("D1", "2026-11-22T14:30:00Z", "GER:Augsburg", "GER:Mainz"),
    m("SP1", "2026-11-22T20:00:00Z", "ESP:Getafe", "ESP:Ath Madrid"),
  ];
  const leurs = [
    f(11, "F1", "2026-11-22T16:15:00+00:00", "Nice", "Paris Saint Germain"),
    f(10, "F1", "2026-11-22T16:15:00+00:00", "Lorient", "Rennes"),
    f(21, "E0", "2026-11-22T16:30:00+00:00", "Everton", "Manchester City"),
    f(20, "E0", "2026-11-22T16:30:00+00:00", "Liverpool", "Manchester United"),
    f(30, "D1", "2026-11-22T16:30:00+00:00", "Werder Bremen", "Hamburger SV"),
    f(31, "D1", "2026-11-22T14:30:00+00:00", "FC Augsburg", "FSV Mainz 05"),
    f(40, "SP1", "2026-11-22T20:00:00+00:00", "Getafe", "Atletico Madrid"),
    f(99, "E0", "2026-11-22T16:30:00+00:00", "Hull City", "Brighton"),
  ];
  const lien = rattacher(nos, leurs, clubs);
  const ids = Object.fromEntries([...lien].map(([a, b]) => [a.id, b.id]));
  assert.deepEqual(ids, {
    "F1-FRA:Lorient-FRA:Rennes": 10, "F1-FRA:Nice-FRA:Paris SG": 11, "E0-ENG:Liverpool-ENG:Man United": 20,
    "E0-ENG:Everton-ENG:Man City": 21, "D1-GER:Werder Bremen-GER:Hamburg": 30, "D1-GER:Augsburg-GER:Mainz": 31,
    "SP1-ESP:Getafe-ESP:Ath Madrid": 40,
  });
});

test("un autre match à la même heure n'est jamais pris pour le nôtre", () => {
  const lien = rattacher([m("E0", "2026-11-22T16:30:00Z", "ENG:Liverpool", "ENG:Man United")],
    [f(99, "E0", "2026-11-22T16:30:00+00:00", "Hull City", "Brighton")], clubs);
  assert.equal(lien.size, 0);
});

test("la minute avance entre deux relevés, sans dépasser la fin de la mi-temps", () => {
  const il_y_a = (min) => new Date(Date.now() - min * 6e4).toISOString();
  assert.deepEqual({ ...minuteMaintenant({ st: "2H", min: 60, plus: null }, il_y_a(5)) }, { base: 65, plus: null });
  assert.deepEqual({ ...minuteMaintenant({ st: "1H", min: 43, plus: null }, il_y_a(4)) }, { base: 45, plus: 2 });
});

test("mener 2-0 à la 80e donne de très fortes chances de victoire", () => {
  const params = { part_1re_mi_temps: 0.4338, rythme_selon_ecart: [1.0968, 1.0968, 1, 0.9769, 0.9769], minutes_mi_temps: [48, 52], pas_par_mi_temps: 10 };
  const { reste } = tempsRestant("80", 2, params);
  const { p } = chancesEnDirect(1.4, 1.1, 2, 0, 2, reste, params);
  assert.ok(p[0] > 0.93 && Math.abs(p[0] + p[1] + p[2] - 1) < 1e-9, JSON.stringify(p));
});

// les tableaux venus du contexte vm n'ont pas le prototype de ce fichier : on les compare après copie
const plat = (x) => JSON.parse(JSON.stringify(x));
const PARAMS = { part_1re_mi_temps: 0.4338, rythme_selon_ecart: [1.0968, 1.0968, 1, 0.9769, 0.9769], minutes_mi_temps: [48, 52], pas_par_mi_temps: 10 };

test("la fiche montre les cinq scores finaux les plus probables, du plus au moins probable", () => {
  const { scores } = chancesEnDirect(1.4, 1.1, 1, 0, 2, 0.5, PARAMS);
  assert.equal(scores.length, 5);
  for (let i = 1; i < scores.length; i++) assert.ok(scores[i - 1].p >= scores[i].p);
  assert.ok(scores.every((x) => { const [h, a] = x.score.split("-").map(Number); return h >= 1 && a >= 0; }), "le score final ne peut pas être sous le score actuel");
});

test("le score à une minute donnée suit la chronologie des buts, arrêts de jeu comptés dans leur mi-temps", () => {
  const ev = [[23, 0, 1, 0], [45, 2, 1, 1], [70, 0, 2, 1]];
  assert.deepEqual(plat(scoreA(ev, 0)), [0, 0]);
  assert.deepEqual(plat(scoreA(ev, 22)), [0, 0]);
  assert.deepEqual(plat(scoreA(ev, 23)), [1, 0]);
  assert.deepEqual(plat(scoreA(ev, 45)), [1, 1]);
  assert.deepEqual(plat(scoreA(ev, 90)), [2, 1]);
});

test("à défaut de chronologie, le score à la pause et le score du moment suffisent", () => {
  assert.deepEqual(plat(chronologieDe({ g: [2, 1], mt: [1, 0] }, 70)), [[45, 0, 1, 0], [70, 0, 2, 1]]);
  assert.deepEqual(plat(chronologieDe({ g: [0, 0], mt: [0, 0] }, 30)), []);
  assert.deepEqual(plat(chronologieDe({ g: [1, 0], mt: [null, null] }, 12)), [[12, 0, 1, 0]]);
  assert.deepEqual(plat(chronologieDe({ g: [1, 0], ev: [[5, 0, 1, 0]] }, 80)), [[5, 0, 1, 0]]);
});

test("la courbe part du pronostic, saute à chaque but et finit sur le résultat acquis", () => {
  const depart = chancesEnDirect(1.4, 1.1, 0, 0, 0, 1, PARAMS).p;
  const ev = [[23, 0, 1, 0]];
  const c = courbeChances(1.4, 1.1, ev, 90, PARAMS, { termine: true });
  assert.equal(c[0].t, 0);
  assert.deepEqual(plat(c[0].p.map((x) => +x.toFixed(9))), plat(depart.map((x) => +x.toFixed(9))));
  const avant = c.filter((q) => q.t < 23).at(-1).p[0], apres = c.find((q) => q.t === 23).p[0];
  assert.ok(apres > avant + 0.1, `un but à domicile doit faire monter la victoire domicile (${avant} -> ${apres})`);
  assert.ok(c.every((q) => Math.abs(q.p[0] + q.p[1] + q.p[2] - 1) < 1e-9));
  assert.deepEqual(plat(c.at(-1).p.map(Math.round)), [1, 0, 0]);
  assert.equal(c.at(-1).t, 90);
});

test("la courbe d'un match en cours s'arrête à la minute actuelle, et à la pause la seconde période est entière", () => {
  const c = courbeChances(1.4, 1.1, [], 67, PARAMS);
  assert.equal(c.at(-1).t, 67);
  assert.ok(c.at(-1).p[1] > 0.1 && c.at(-1).p[1] < 0.6);
  const pause = courbeChances(1.4, 1.1, [[20, 0, 1, 0]], 45, PARAMS, { pause: true }).at(-1);
  const direct = chancesEnDirect(1.4, 1.1, 1, 0, 2, 1, PARAMS).p;
  assert.deepEqual(plat(pause.p.map((x) => +x.toFixed(9))), plat(direct.map((x) => +x.toFixed(9))));
});

test("un match du jour déjà « joué » mais sans score publié ne fait pas échouer la liste (relais : score final)", () => {
  const ligne = vm.runInContext(`ligneMatch({ id: "F1|a|b", etat: "joue", kickoff: "2026-11-22T14:00:00Z", home: "FRA:Lille", away: "FRA:Lyon", p: [0.5, 0.3, 0.2] }, {})`, ctx);
  assert.match(ligne, /terminé/);
  assert.match(ligne, /data-match=/);
});

test("le suivi couvre les prolongations et tirs au but en coupe et tant que le relais indique un match en jeu", () => {
  const ko = "2026-11-24T20:00:00Z", t0 = Date.parse(ko), min = 6e4;
  const ligue = m("I1", ko, "ITA:Inter", "ITA:Napoli");
  const coupe = m("LDC", ko, "ITA:Inter", "ENG:Liverpool");
  D.suivis = [];
  assert.equal(aSuivre(ligue, t0 + 150 * min), true);
  assert.equal(aSuivre(ligue, t0 + 160 * min), false);
  // coupe : suivi étendu à 180 min sans même avoir besoin du statut relais
  assert.equal(aSuivre(coupe, t0 + 175 * min), true);
  assert.equal(aSuivre(coupe, t0 + 185 * min), false);
  // prolongations / tirs au but encore en cours dans le relais : le suivi continue au-delà de 180 min
  D.suivis = [{ m: coupe, f: { st: "P" }, clubs }];
  assert.equal(aSuivre(coupe, t0 + 195 * min), true);
  // dès que le match est terminé (PEN / FT), le suivi s'arrête
  D.suivis = [{ m: coupe, f: { st: "PEN" }, clubs }];
  assert.equal(aSuivre(coupe, t0 + 195 * min), false);
  // filet de sécurité à 240 min même si le statut reste figé
  D.suivis = [{ m: coupe, f: { st: "ET" }, clubs }];
  assert.equal(aSuivre(coupe, t0 + 245 * min), false);
  D.suivis = [];
});

test("les clubs de Serie A d'API-Football se rattachent bien aux nôtres", () => {
  const nos = [m("I1", "2026-11-22T19:45:00Z", "ITA:Inter", "ITA:Napoli")];
  const leurs = [f(50, "I1", "2026-11-22T19:45:00+00:00", "Inter", "Napoli")];
  const lien = rattacher(nos, leurs, clubs);
  assert.equal(lien.get(nos[0])?.id, 50);
});
