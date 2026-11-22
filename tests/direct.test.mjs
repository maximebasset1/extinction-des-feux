// tests du direct côté site : rattachement des matchs du relais et chances recalculées
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = vm.createContext({ document: { body: { dataset: {} }, querySelectorAll: () => [] }, console, CSS: { escape: (s) => s }, module: undefined });
for (const f of ["commun.js", "modele-direct.js", "direct.js"]) {
  vm.runInContext(readFileSync(new URL(`../site/assets/${f}`, import.meta.url), "utf8").replace(/^"use strict";/m, ""), ctx, { filename: f });
}
const { rattacher, minuteMaintenant, chancesEnDirect, tempsRestant } = vm.runInContext("({ rattacher, minuteMaintenant, chancesEnDirect, tempsRestant })", ctx);

const clubs = {
  "FRA:Lorient": { nom: "Lorient" }, "FRA:Rennes": { nom: "Stade Rennais" }, "FRA:Paris FC": { nom: "Paris FC" },
  "FRA:Angers": { nom: "Angers" }, "FRA:Marseille": { nom: "Marseille" }, "FRA:Le Mans": { nom: "Le Mans" },
  "FRA:Paris SG": { nom: "Paris Saint-Germain" }, "FRA:Nice": { nom: "Nice" },
  "ENG:Man United": { nom: "Manchester United" }, "ENG:Liverpool": { nom: "Liverpool" },
  "ENG:Man City": { nom: "Manchester City" }, "ENG:Everton": { nom: "Everton" },
  "GER:Werder Bremen": { nom: "Werder Brême" }, "GER:Hamburg": { nom: "Hamburger SV" },
  "GER:Augsburg": { nom: "Augsbourg" }, "GER:Mainz": { nom: "Mayence" },
  "ESP:Ath Madrid": { nom: "Atlético de Madrid" }, "ESP:Getafe": { nom: "Getafe" },
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
