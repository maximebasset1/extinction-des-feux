// tests du relais du direct avec une fausse API-Football et un faux stockage KV
import test from "node:test";
import assert from "node:assert/strict";
import { tour, aCouvrir, servir, MARGE_SECURITE } from "../relais/relais.js";

const T0 = Date.parse("2026-11-22T13:00:00Z");
const min = 60000;

function fixture(id, league, ko, st, goals = [null, null], elapsed = null) {
  return { fixture: { id, date: ko, status: { short: st, elapsed, extra: null } }, league: { id: league },
    teams: { home: { name: `D${id}` }, away: { name: `E${id}` } }, goals: { home: goals[0], away: goals[1] },
    score: { halftime: { home: null, away: null } } };
}

function monde(reponses) {
  const kv = new Map(), appels = [];
  globalThis.fetch = async (url) => {
    const chemin = String(url).split("/v3.football.api-sports.io/")[1];
    appels.push(chemin);
    const r = reponses(chemin, appels.length);
    if (r.status) return new Response("{}", { status: r.status });
    return new Response(JSON.stringify({ errors: r.errors || [], response: r.response }),
      { headers: { "x-ratelimit-requests-remaining": String(100 - appels.length) } });
  };
  const env = { API_FOOTBALL_KEY: "x", DIRECT: {
    get: async (k) => (kv.has(k) ? JSON.parse(kv.get(k)) : null), put: async (k, v) => { kv.set(k, v); } } };
  return { env, appels, etat: () => JSON.parse(kv.get("etat")) };
}

test("le programme du jour ne garde que nos compétitions", async () => {
  const w = monde(() => ({ response: [
    fixture(1, 61, "2026-11-22T14:00:00+00:00", "NS"),
    fixture(2, 135, "2026-11-22T11:30:00+00:00", "NS"),
    fixture(3, 999, "2026-11-22T14:00:00+00:00", "NS"),
  ] }));
  await tour(w.env, T0);
  assert.deepEqual(w.appels, ["fixtures?date=2026-11-22"]);
  assert.deepEqual(w.etat().matchs.map((m) => [m.id, m.c]), [[1, "F1"], [2, "I1"]]);
});

test("aucun appel en direct hors des fenêtres de match", async () => {
  const w = monde(() => ({ response: [fixture(1, 61, "2026-11-22T18:00:00+00:00", "NS")] }));
  await tour(w.env, T0);
  for (let i = 1; i <= 30; i++) await tour(w.env, T0 + i * min);
  assert.equal(w.appels.length, 1);
});

test("les appels en direct sont espacés pour tenir le quota", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  const w = monde((c) => (c.startsWith("fixtures?date") ? { response: [fixture(1, 61, ko, "NS"), fixture(2, 39, "2026-11-22T19:00:00+00:00", "NS")] }
    : { response: [fixture(1, 61, ko, "1H", [0, 0], 10)] }));
  await tour(w.env, T0 - 3 * min);
  for (let i = 0; i <= 120; i++) await tour(w.env, T0 + i * min);
  const direct = w.appels.filter((c) => c === "fixtures?live=all").length;
  const { minutes } = aCouvrir(w.etat().matchs, T0 + 120 * min);
  assert.ok(direct >= 2 && direct <= 60, `appels en direct : ${direct}`);
  assert.ok(w.etat().intervalle_min >= 2, `intervalle : ${w.etat().intervalle_min}`);
  assert.ok(minutes > 0);
});

test("un match sorti du direct fait relire le programme pour le score final", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  let fini = false;
  const w = monde((c) => {
    if (c.startsWith("fixtures?date")) return { response: [fixture(1, 61, ko, fini ? "FT" : "NS", fini ? [2, 1] : [null, null], fini ? 90 : null)] };
    return { response: fini ? [] : [fixture(1, 61, ko, "2H", [2, 0], 80)] };
  });
  await tour(w.env, T0);
  await tour(w.env, T0 + 80 * min);
  assert.equal(w.etat().matchs[0].st, "2H");
  fini = true;
  await tour(w.env, T0 + 110 * min);
  assert.equal(w.etat().matchs[0].st, "FT?");
  await tour(w.env, T0 + 111 * min);
  assert.equal(w.etat().matchs[0].st, "FT");
  assert.deepEqual(w.etat().matchs[0].g, [2, 1]);
});

test("après une erreur de l'API, le relais attend avant de réessayer", async () => {
  const w = monde(() => ({ status: 500 }));
  await assert.rejects(tour(w.env, T0));
  assert.match(w.etat().erreur.message, /500/);
  await tour(w.env, T0 + min);
  assert.equal(w.appels.length, 1);
});


test("la chronologie des buts est relevée à chaque changement de score, sans doublon", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  let live = fixture(1, 61, ko, "1H", [0, 0], 10);
  const w = monde((c) => (c.startsWith("fixtures?date") ? { response: [fixture(1, 61, ko, "NS")] } : { response: [live] }));
  await tour(w.env, T0 - 3 * min);
  const pas = [[10, [0, 0]], [20, [1, 0]], [21, [1, 0]], [47, [1, 0]], [70, [1, 2]], [71, [1, 2]]];
  for (const [m, g] of pas) {
    live = fixture(1, 61, ko, m > 45 ? "2H" : "1H", g, m);
    await tour(w.env, T0 + m * min);
  }
  assert.deepEqual(w.etat().matchs[0].ev, [[20, 0, 1, 0], [70, 0, 1, 2]]);
});

test("un score déjà acquis au premier relevé et une annulation VAR sont notés tels quels", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  let live = fixture(1, 61, ko, "2H", [2, 0], 60);
  const w = monde((c) => (c.startsWith("fixtures?date") ? { response: [fixture(1, 61, ko, "NS")] } : { response: [live] }));
  await tour(w.env, T0 - 3 * min);
  await tour(w.env, T0 + 60 * min);
  live = fixture(1, 61, ko, "2H", [1, 0], 63);
  await tour(w.env, T0 + 63 * min);
  assert.deepEqual(w.etat().matchs[0].ev, [[60, 0, 2, 0], [63, 0, 1, 0]]);
});

test("la relecture du programme garde la chronologie et ajoute le score final", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  let fini = false;
  const w = monde((c) => {
    if (c.startsWith("fixtures?date")) return { response: [fixture(1, 61, ko, fini ? "FT" : "NS", fini ? [3, 1] : [null, null], fini ? 90 : null)] };
    return { response: fini ? [] : [fixture(1, 61, ko, "2H", [2, 0], 80)] };
  });
  await tour(w.env, T0);
  await tour(w.env, T0 + 80 * min);
  fini = true;
  await tour(w.env, T0 + 110 * min);
  await tour(w.env, T0 + 111 * min);
  const m = w.etat().matchs[0];
  assert.equal(m.st, "FT");
  assert.deepEqual(m.ev, [[80, 0, 2, 0], [90, 0, 3, 1]]);
});

test("le changement de jour réinitialise direct_utc, direct_ms et intervalle_min", async () => {
  const ko1 = "2026-11-22T13:00:00+00:00";
  const ko2 = "2026-11-23T19:45:00+00:00";
  const w = monde((c) => {
    if (c === "fixtures?date=2026-11-22") return { response: [fixture(1, 61, ko1, "NS")] };
    if (c === "fixtures?date=2026-11-23") return { response: [fixture(2, 135, ko2, "NS")] };
    return { response: [fixture(1, 61, ko1, "1H", [1, 0], 25)] };
  });
  await tour(w.env, T0);
  await tour(w.env, T0 + 25 * min);
  assert.ok(w.etat().direct_utc && w.etat().direct_ms && w.etat().intervalle_min);

  const lendemain = Date.parse("2026-11-23T10:20:00Z");
  await tour(w.env, lendemain);
  assert.equal(w.etat().jour, "2026-11-23");
  assert.equal(w.etat().direct_utc, null);
  assert.equal(w.etat().direct_ms, null);
  assert.equal(w.etat().intervalle_min, null);
  const pub = await (await servir(w.env)).json();
  assert.equal(pub.jour, "2026-11-23");
  assert.equal(pub.maj_utc, new Date(lendemain).toISOString());
  assert.equal(pub.intervalle_min, null);
});

test("la marge de sécurité empêche de consommer le plafond gratuit de 100 requêtes/jour", async () => {
  const ko = "2026-11-22T13:00:00+00:00";
  const kv = new Map();
  let appels = 0;
  globalThis.fetch = async (url) => {
    appels += 1;
    const chemin = String(url).split("/v3.football.api-sports.io/")[1];
    const body = chemin.startsWith("fixtures?date")
      ? [fixture(1, 135, ko, "NS")]
      : [fixture(1, 135, ko, "1H", [0, 0], 10)];
    return new Response(JSON.stringify({ errors: [], response: body }),
      { headers: { "x-ratelimit-requests-remaining": String(MARGE_SECURITE + 2 - appels) } });
  };
  const env = { API_FOOTBALL_KEY: "x", DIRECT: {
    get: async (k) => (kv.has(k) ? JSON.parse(kv.get(k)) : null), put: async (k, v) => { kv.set(k, v); } } };
  await tour(env, T0 - 3 * min);       // 1er appel : programme, restant = MARGE_SECURITE + 1
  await tour(env, T0 + 10 * min);      // 2e appel : live, restant = MARGE_SECURITE
  await tour(env, T0 + 90 * min);      // restant <= MARGE_SECURITE : plus aucun appel
  assert.equal(appels, 2);
});

test("un match manqué (resté NS après sa fenêtre de jeu) déclenche la relecture du score final", async () => {
  const koTermine = "2026-11-24T17:45:00+00:00";
  const koEnCours = "2026-11-24T20:00:00+00:00";
  let relu = false;
  const w = monde((c) => {
    if (c === "fixtures?date=2026-11-24") {
      if (!relu) {
        relu = true;
        return { response: [fixture(1, 2, koTermine, "NS"), fixture(2, 2, koEnCours, "NS")] };
      }
      return { response: [fixture(1, 2, koTermine, "FT", [2, 1], 90), fixture(2, 2, koEnCours, "1H", [1, 0], 15)] };
    }
    return { response: [fixture(2, 2, koEnCours, "1H", [1, 0], 15)] };
  });
  // Programme chargé le matin
  await tour(w.env, Date.parse("2026-11-24T04:30:00Z"));
  assert.equal(w.etat().matchs[0].st, "NS");
  // Reprise après retard cron à 20 h 15 UTC (le match de 17 h 45 est déjà fini depuis > 125 min)
  await tour(w.env, Date.parse("2026-11-24T20:15:00Z"));
  assert.equal(w.etat().matchs[0].st, "FT");
  assert.deepEqual(w.etat().matchs[0].g, [2, 1]);
  assert.equal(w.etat().matchs[1].st, "1H");
  assert.deepEqual(w.etat().matchs[1].g, [1, 0]);
});
