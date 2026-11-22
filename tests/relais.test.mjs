// tests du relais du direct avec une fausse API-Football et un faux stockage KV
import test from "node:test";
import assert from "node:assert/strict";
import { tour, aCouvrir } from "../relais/relais.js";

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
  const w = monde(() => ({ response: [fixture(1, 61, "2026-11-22T14:00:00+00:00", "NS"), fixture(2, 999, "2026-11-22T14:00:00+00:00", "NS")] }));
  await tour(w.env, T0);
  assert.deepEqual(w.appels, ["fixtures?date=2026-11-22"]);
  assert.deepEqual(w.etat().matchs.map((m) => [m.id, m.c]), [[1, "F1"]]);
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

