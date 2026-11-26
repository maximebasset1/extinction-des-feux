// navigation du football : journées d'une compétition, matchs en cours remontés en tête, vue « En direct »,
// et branchement complet entre la route /direct du Worker (relais/relais.js) et le code du site (direct.js)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import worker, { tour } from "../relais/relais.js";

const lireSource = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

function charger(extra = {}) {
  const ctx = vm.createContext({ document: { body: { dataset: {} }, querySelectorAll: () => [], addEventListener: () => {} }, console, URL,
    CSS: { escape: (s) => s }, module: undefined, ...extra });
  for (const f of ["commun.js", "modele-direct.js", "direct.js", "journees.js"]) {
    vm.runInContext(lireSource(`site/assets/${f}`).replace(/^"use strict";/m, ""), ctx, { filename: f });
  }
  const api = vm.runInContext(`({ D, RELAIS, lireRelais, rattacher, relaisPerime, matchsSuivables, enDirectMaintenant, repartirDuJour,
    alerteDirect, centreDirect, ligneMatch, libelleCourt, journeeParDefaut })`, ctx);
  return { ctx, ...api };
}

// les objets du contexte vm n'ont pas les prototypes de ce fichier : on les compare après copie
const plat = (x) => JSON.parse(JSON.stringify(x));
const MIN = 6e4;
const T = Date.parse("2026-11-26T15:00:00Z");              // milieu de journée : même date à Paris et en UTC
const dans = (min) => new Date(T + min * MIN).toISOString();
const clubs = {
  "FRA:Lille": { nom: "Lille", sigle: "LIL" }, "FRA:Lyon": { nom: "Lyon", sigle: "OL" },
  "FRA:Nice": { nom: "Nice", sigle: "NIC" }, "FRA:Marseille": { nom: "Marseille", sigle: "OM" },
  "FRA:Rennes": { nom: "Stade Rennais", sigle: "REN" }, "FRA:Brest": { nom: "Brest", sigle: "BRE" },
};
const match = (id, min, home, away, extra = {}) => ({ id, c: "F1", kickoff: dans(min), jour: dans(min).slice(0, 10), home, away,
  etat: "a_venir", p: [0.5, 0.3, 0.2], ...extra });
const releve = (id, min, h, a, st, extra = {}) => ({ id, c: "F1", ko: dans(min), h, a, st, min: null, plus: null, g: [null, null], mt: [null, null], ...extra });
const relaisDe = (matchs, extra = {}) => ({ jour: dans(0).slice(0, 10), maj_utc: dans(-1), intervalle_min: 2, erreur: null, matchs, ...extra });

/* ---------- journées */
test("les pilules de journée ont un libellé court, quelle que soit la compétition", () => {
  const { libelleCourt } = charger();
  const attendu = {
    "Journée 1": "J1", "Journée 34": "J34", "Barrages": "Barrages", "Huitièmes de finale": "8es", "Quarts de finale": "Quarts",
    "Demi-finales": "Demies", "Finale": "Finale", "Qualifications": "Qualifs",
    "Semaine du 24 septembre": "24 sept.", "Semaine du 1 octobre": "1 oct.", "Semaine du 12 mars": "12 mars", "Tour inconnu": "Tour inconnu",
  };
  for (const [long, court] of Object.entries(attendu)) assert.equal(libelleCourt(long), court, long);
});

test("la journée ouverte est celle d'un match en cours, puis celle du jour, puis la prochaine", () => {
  const { journeeParDefaut } = charger();
  const journees = ["Journée 1", "Journée 2", "Journée 3"];
  const jour = dans(0).slice(0, 10);
  const d = (matchs, prochaine = "Journée 3") => ({ journees, prochaine, matchs });
  const enCours = { journee: "Journée 1", kickoff: dans(-40), jour, etat: "en_cours" };
  const fini = { journee: "Journée 2", kickoff: dans(-300), jour, etat: "joue" };
  assert.equal(journeeParDefaut(d([fini, enCours]), T, jour), "Journée 1");
  assert.equal(journeeParDefaut(d([fini]), T, jour), "Journée 2");
  assert.equal(journeeParDefaut(d([]), T, jour), "Journée 3");
  assert.equal(journeeParDefaut(d([], "Journée 99"), T, jour), "Journée 3", "à défaut : la dernière");
});

/* ---------- matchs suivis et matchs en cours */
test("les matchs du jour et les matchs à venir sont réunis sans doublon, avec les buts attendus du jour", () => {
  const { matchsSuivables } = charger();
  const index = { du_jour: [match("a", 60, "FRA:Lille", "FRA:Lyon", { lam: [1.4, 1.1] })], clubs: { "FRA:Lille": clubs["FRA:Lille"] } };
  const recherche = { matchs: [match("a", 60, "FRA:Lille", "FRA:Lyon"), match("b", 1500, "FRA:Nice", "FRA:Brest")], clubs };
  const r = plat(matchsSuivables(index, recherche));
  assert.deepEqual(r.matchs.map((m) => m.id), ["a", "b"]);
  assert.deepEqual(r.matchs[0].lam, [1.4, 1.1]);
  assert.ok(r.clubs["FRA:Brest"]);
  assert.deepEqual(plat(matchsSuivables(null, null)), { matchs: [], clubs: {} });
});

test("tout match en cours chez le relais remonte, même s'il ne se rattache à aucun de nos matchs", () => {
  const { enDirectMaintenant } = charger();
  const lie = releve(1, -30, "Lille", "Lyon", "1H", { min: 30, g: [1, 0] });
  const seul = releve(2, -20, "Toulouse", "Auxerre", "2H", { min: 50, g: [0, 0] });
  const fini = releve(3, -130, "Nice", "Brest", "FT", { g: [2, 2] });
  const pasCommence = releve(4, 120, "Marseille", "Stade Rennais", "NS");
  const fige = releve(5, -300, "Lens", "Metz", "2H", { min: 80, g: [1, 1] });   // statut resté « en jeu » 5 h après
  const suivis = [{ m: match("a", -30, "FRA:Lille", "FRA:Lyon"), f: lie, clubs }];
  const liste = enDirectMaintenant(relaisDe([lie, seul, fini, pasCommence, fige]), suivis, { maintenant: T });
  assert.deepEqual(plat(liste.map((x) => [x.f.id, x.connu])), [[1, true], [2, false]]);
  const inconnu = liste[1];
  assert.equal(inconnu.clubs[inconnu.m.home].nom, "Toulouse");
  assert.equal(inconnu.clubs[inconnu.m.away].nom, "Auxerre");
  assert.equal(enDirectMaintenant(relaisDe([lie, seul]), suivis, { comp: "LDC", maintenant: T }).length, 0, "filtre par compétition");
  assert.equal(enDirectMaintenant(null, [], { maintenant: T }).length, 0);
});

test("boucle arrêtée en plein match : passé la durée d'un match, il n'est plus annoncé en cours", () => {
  const { enDirectMaintenant, repartirDuJour } = charger();
  const fige = releve(1, -170, "Lille", "Lyon", "2H", { min: 80, g: [1, 0] });
  const muet = relaisDe([fige], { maj_utc: dans(-100) });
  assert.equal(enDirectMaintenant(muet, [], { maintenant: T }).length, 0, "championnat : 2 h 30");
  assert.equal(enDirectMaintenant(relaisDe([fige]), [], { maintenant: T }).length, 1, "relevé frais : match réellement long");
  assert.equal(enDirectMaintenant(relaisDe([{ ...fige, c: "LDC" }], { maj_utc: dans(-100) }), [], { maintenant: T }).length, 1, "coupe : 3 h");
  const recent = releve(2, -60, "Nice", "Brest", "2H", { min: 50, g: [0, 0] });
  assert.equal(enDirectMaintenant(relaisDe([recent], { maj_utc: dans(-30) }), [], { maintenant: T }).length, 1, "encore plausible : gardé, avec son heure de relevé");
  const programme = repartirDuJour([match("a", -170, "FRA:Lille", "FRA:Lyon")], clubs, muet, T);
  assert.deepEqual(plat(programme.aVenir.map((x) => [x.m.id, x.etat])), [["a", "attente"]], "il reste dans le programme du jour");
});

test("le badge DIRECT montre la minute et le score ; un relevé trop vieux n'est plus annoncé comme direct", () => {
  const api = charger();
  const m = match("a", -30, "FRA:Lille", "FRA:Lyon");
  const f = releve(1, -30, "Lille", "Lyon", "1H", { min: 30, g: [1, 0] });
  api.D.relais = relaisDe([f], { maj_utc: new Date().toISOString() });
  const html = api.centreDirect(m, f, clubs);
  assert.match(html, /class="badge-direct"/);
  assert.match(html, />DIRECT</);
  assert.match(html, /30′/);
  assert.match(html, /1 - 0/);
  assert.match(api.centreDirect(m, { ...f, st: "HT" }, clubs), /mi-temps/);
  api.D.relais = relaisDe([f], { maj_utc: new Date(Date.now() - 90 * MIN).toISOString() });
  const vieux = api.centreDirect(m, f, clubs);
  assert.doesNotMatch(vieux, />DIRECT</);
  assert.match(vieux, /relevé à/);
  assert.match(vieux, /1 - 0/);
});

test("un relevé n'est périmé qu'au-delà de 20 min, ou de deux intervalles quand le relais espace ses appels", () => {
  const { relaisPerime } = charger();
  assert.equal(relaisPerime({ maj_utc: dans(-19), intervalle_min: 2 }, T), false);
  assert.equal(relaisPerime({ maj_utc: dans(-21), intervalle_min: 2 }, T), true);
  assert.equal(relaisPerime({ maj_utc: dans(-24), intervalle_min: 10 }, T), false);
  assert.equal(relaisPerime({ maj_utc: dans(-26), intervalle_min: 10 }, T), true);
  assert.equal(relaisPerime({}, T), false);
});

/* ---------- vue « En direct » */
test("sans match en cours, le programme du jour reste là avec les heures de coup d'envoi", () => {
  const { repartirDuJour } = charger();
  const matchs = [
    match("soir", 180, "FRA:Marseille", "FRA:Rennes"),
    match("tot", -200, "FRA:Nice", "FRA:Brest", { etat: "a_venir" }),
    match("demain", 1440, "FRA:Lille", "FRA:Lyon"),
  ];
  const relais = relaisDe([releve(1, -200, "Nice", "Brest", "FT", { g: [2, 1] }), releve(2, 180, "Marseille", "Rennes", "NS"),
    releve(3, 240, "Toulouse", "Auxerre", "NS")]);
  const r = repartirDuJour(matchs, clubs, relais, T);
  assert.deepEqual(plat(r.aVenir.map((x) => [x.m.id, x.etat])), [["soir", "a_venir"], ["relais|3", "a_venir"]],
    "le match connu du relais seul est montré une fois, le nôtre n'est pas doublé");
  assert.deepEqual(plat(r.termines.map((x) => [x.m.id, x.etat, x.f.g])), [["tot", "fini", [2, 1]]]);
  assert.deepEqual(plat(r.suivants.map((x) => x.m.id)), ["demain"]);
});

test("coup d'envoi passé sans relevé : le match reste attendu, et un match en cours n'est pas répété dans le programme", () => {
  const { repartirDuJour } = charger();
  const matchs = [match("juste", -5, "FRA:Marseille", "FRA:Rennes"), match("encours", -40, "FRA:Lille", "FRA:Lyon"),
    match("perdu", -290, "FRA:Nice", "FRA:Brest"), match("report", 60, "FRA:Brest", "FRA:Lyon", { etat: "reporte" })];
  const relais = relaisDe([releve(1, -40, "Lille", "Lyon", "1H", { min: 40, g: [0, 0] })]);
  const r = repartirDuJour(matchs, clubs, relais, T);
  assert.deepEqual(plat(r.aVenir.map((x) => [x.m.id, x.etat])), [["juste", "attente"], ["report", "reporte"]]);
  assert.deepEqual(plat(r.termines.map((x) => [x.m.id, x.etat])), [["perdu", "sans_score"]]);
});

test("relais injoignable : le programme du jour s'affiche quand même", () => {
  const { repartirDuJour } = charger();
  const r = repartirDuJour([match("soir", 180, "FRA:Marseille", "FRA:Rennes")], clubs, null, T);
  assert.deepEqual(plat(r.aVenir.map((x) => [x.m.id, x.etat])), [["soir", "a_venir"]]);
});

test("l'alerte dit quand le direct ne marche pas : relais muet pendant un match, injoignable ou en erreur", () => {
  const { alerteDirect } = charger();
  const joue = [match("encours", -40, "FRA:Lille", "FRA:Lyon")];
  const soir = [match("soir", 180, "FRA:Marseille", "FRA:Rennes")];
  assert.equal(alerteDirect(relaisDe([]), joue, { maintenant: T }), null);
  assert.equal(alerteDirect(relaisDe([], { maj_utc: dans(-600) }), soir, { maintenant: T }), null, "au repos : un vieux relevé est normal");
  assert.equal(alerteDirect(relaisDe([], { maj_utc: dans(-600) }), joue, { maintenant: T }).type, "muet");
  assert.equal(alerteDirect(null, joue, { echec: T, maintenant: T }).type, "panne");
  assert.equal(alerteDirect(relaisDe([], { erreur: { utc: dans(-3), message: "quota" } }), soir, { maintenant: T }).type, "erreur");
  assert.doesNotMatch(alerteDirect(relaisDe([], { erreur: { utc: dans(-3), message: "x-ratelimit=0" } }), soir, { maintenant: T }).texte,
    /ratelimit/, "le message technique de l'API n'est pas affiché");
});

/* ---------- lecture du relais */
test("la lecture du relais est partagée 15 s, forcée par « Actualiser », et note l'heure de synchronisation", async () => {
  let appels = 0, panne = false, corps = { matchs: [] };
  const { lireRelais, D } = charger({ fetch: async () => { appels += 1; if (panne) throw new Error("hors ligne"); return { ok: true, json: async () => corps }; } });
  await lireRelais();
  await lireRelais();
  assert.equal(appels, 1);
  const avant = D.synchro;
  assert.ok(avant > 0);
  await lireRelais({ force: true });
  assert.equal(appels, 2);
  panne = true;
  const synchro = D.synchro;
  await assert.rejects(lireRelais({ force: true }));
  assert.equal(D.synchro, synchro, "un échec ne change pas l'heure de dernière synchronisation");
  panne = false; corps = { pas: "le bon format" };
  await assert.rejects(lireRelais({ force: true }), /illisible/);
});

/* ---------- branchement complet : API-Football (simulée) → boucle du relais → route /direct du Worker → site */
test("un but relevé par la boucle arrive, par la route /direct du Worker, sur la ligne de notre match", async () => {
  const ko = "2026-11-26T20:00:00+00:00", t0 = Date.parse(ko);
  const fixture = (st, elapsed, buts) => ({ fixture: { id: 77, date: ko, status: { short: st, elapsed, extra: null } },
    league: { id: 61 }, teams: { home: { name: "Lille" }, away: { name: "Lyon" } }, goals: { home: buts[0], away: buts[1] },
    score: { halftime: { home: null, away: null } } });
  const kv = new Map();
  const env = { API_FOOTBALL_KEY: "cle-de-test", DIRECT: {
    get: async (k) => (kv.has(k) ? JSON.parse(kv.get(k)) : null), put: async (k, v) => { kv.set(k, v); } } };
  const vrai = globalThis.fetch;
  globalThis.fetch = async (url) => new Response(JSON.stringify({ errors: [],
    response: [String(url).includes("live=all") ? fixture("1H", 23, [1, 0]) : fixture("NS", null, [null, null])] }),
  { headers: { "x-ratelimit-requests-remaining": "90" } });
  try {
    await tour(env, t0 + 22 * MIN);   // programme du jour
    await tour(env, t0 + 23 * MIN);   // scores en direct
  } finally {
    globalThis.fetch = vrai;
  }

  const site = charger();
  const adresse = new URL(site.RELAIS);
  assert.equal(adresse.pathname, "/direct");
  assert.ok(lireSource("scripts/build_site.py").includes(`connect-src 'self' ${adresse.origin}`), "la CSP doit autoriser le relais");
  const reponse = await worker.fetch(new Request(site.RELAIS), env);
  assert.equal(reponse.status, 200);
  assert.equal(reponse.headers.get("access-control-allow-origin"), "*");
  const relais = await reponse.json();

  const notre = { id: "F1|FRA:Lille|FRA:Lyon|2026-11-26", c: "F1", kickoff: "2026-11-26T20:00:00Z", jour: "2026-11-26", home: "FRA:Lille", away: "FRA:Lyon", etat: "a_venir" };
  const lien = site.rattacher([notre], relais.matchs, clubs);
  const [entree] = site.enDirectMaintenant(relais, [...lien].map(([m, f]) => ({ m, f, clubs })), { maintenant: t0 + 24 * MIN });
  assert.equal(entree.m.id, notre.id);
  assert.equal(entree.connu, true);
  assert.deepEqual(plat(entree.f.g), [1, 0]);
  assert.equal(entree.f.min, 23);
  assert.deepEqual(plat(entree.f.ev), [[23, 0, 1, 0]]);
});
