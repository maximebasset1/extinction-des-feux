// tests des ligues de pronostics : barème, programme des matchs et API (base D1 simulée par SQLite)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import relais from "../relais/relais.js";
import { calculerPoints, issue, SEUIL_COUP_DE_POKER } from "../relais/points.js";
import { fusionner, trouver } from "../relais/programme.js";
import { publier } from "../relais/publier-programme.mjs";

// ---------------------------------------------------------------- barème

const FAVORI_DOM = [0.5, 0.3, 0.2];

test("barème : mauvaise issue, aucun point même avec le bon écart en valeur absolue", () => {
  const r = calculerPoints([2, 1], [1, 2], FAVORI_DOM);
  assert.deepEqual(r, { points: 0, bonne_issue: false, bon_ecart: false, score_exact: false, coup_de_poker: false });
});

test("barème : bonne issue seule, 3 points", () => {
  const r = calculerPoints([1, 0], [3, 0], FAVORI_DOM);
  assert.equal(r.points, 3);
  assert.equal(r.bonne_issue, true);
  assert.equal(r.bon_ecart, false);
  assert.equal(r.score_exact, false);
});

test("barème : bonne issue et bon écart, 5 points", () => {
  const r = calculerPoints([2, 0], [3, 1], FAVORI_DOM);
  assert.equal(r.points, 5);
  assert.equal(r.bon_ecart, true);
  assert.equal(r.score_exact, false);
});

test("barème : score exact, 10 points", () => {
  const r = calculerPoints([2, 1], [2, 1], FAVORI_DOM);
  assert.deepEqual(r, { points: 10, bonne_issue: true, bon_ecart: true, score_exact: true, coup_de_poker: false });
});

test("barème : match nul annoncé, l'écart est forcément bon (5 points), 10 si le score est exact", () => {
  assert.equal(calculerPoints([1, 1], [2, 2], FAVORI_DOM).points, 5);
  assert.equal(calculerPoints([0, 0], [0, 0], FAVORI_DOM).points, 10);
  assert.equal(calculerPoints([1, 1], [1, 0], FAVORI_DOM).points, 0);
  assert.equal(calculerPoints([1, 0], [1, 1], FAVORI_DOM).points, 0);
});

test("coup de poker : bonne issue sous 25 %, points multipliés par 1,5 et arrondis au supérieur", () => {
  const probas = [0.7, 0.18, 0.12];
  const issueSeule = calculerPoints([0, 3], [0, 1], probas);
  assert.equal(issueSeule.points, 5);        // 3 x 1,5 = 4,5
  assert.equal(issueSeule.coup_de_poker, true);
  assert.equal(calculerPoints([1, 2], [0, 1], probas).points, 8);    // 5 x 1,5 = 7,5
  assert.equal(calculerPoints([0, 1], [0, 1], probas).points, 15);
  assert.equal(calculerPoints([1, 1], [2, 2], probas).points, 8);    // le nul à 18 % compte aussi
});

test("coup de poker : 25 % tout juste ne suffit pas, et une mauvaise issue ne rapporte rien", () => {
  assert.equal(SEUIL_COUP_DE_POKER, 0.25);
  const juste = calculerPoints([0, 1], [0, 1], [0.5, 0.25, 0.25]);
  assert.equal(juste.points, 10);
  assert.equal(juste.coup_de_poker, false);
  assert.equal(calculerPoints([0, 1], [1, 0], [0.7, 0.18, 0.12]).coup_de_poker, false);
});

test("coup de poker : seule la probabilité de l'issue obtenue compte, et sans probabilités il n'y en a pas", () => {
  assert.equal(calculerPoints([1, 0], [1, 0], [0.7, 0.18, 0.12]).points, 10);
  assert.equal(calculerPoints([0, 1], [0, 1], null).points, 10);
  assert.equal(calculerPoints([0, 1], [0, 1], [null, null, null]).coup_de_poker, false);
});

test("issue : 0 pour le domicile, 1 pour le nul, 2 pour l'extérieur", () => {
  assert.deepEqual([issue(2, 0), issue(1, 1), issue(0, 4)], [0, 1, 2]);
});

// ---------------------------------------------------------------- programme des matchs (construit depuis les JSON du site)

const MAINTENANT = Date.parse("2026-11-24T12:00:00Z");
const heure = 3600000;
const F1_A_VENIR = "F1|FRA:Brest|FRA:Paris FC|2026-11-27";

function matchSite(id, kickoff, extra = {}) {
  return { id, jour: id.split("|").pop(), kickoff, etat: "a_venir", p: [0.35, 0.29, 0.36], scores: [{ score: "1-1", p: 0.14 }, { score: "0-0", p: 0.09 }], ...extra };
}
const fichier = (code, matchs) => ({ code, matchs });
const aVenir = () => matchSite(F1_A_VENIR, "2026-11-27T19:45:00Z");

test("programme : un match à venir garde coup d'envoi, probabilités et score n° 1 pour le Bot IA", () => {
  const prog = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  assert.deepEqual(prog.matchs[F1_A_VENIR], { ko: "2026-11-27T19:45:00Z", et: "a_venir", p: [0.35, 0.29, 0.36], bot: [1, 1], res: null });
  assert.equal(prog.maj_ms, MAINTENANT);
});

test("programme : après le coup d'envoi, probabilités et score du Bot IA sont figés, le résultat s'ajoute", () => {
  const avant = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  const apres = Date.parse("2026-11-28T08:00:00Z");
  const joue = { id: F1_A_VENIR, jour: "2026-11-27", kickoff: "2026-11-27T19:45:00Z", etat: "joue", score: [0, 2], p: [0.6, 0.2, 0.2] };
  const prog = fusionner(avant, { F1: fichier("F1", [joue]) }, apres);
  assert.deepEqual(prog.matchs[F1_A_VENIR], { ko: "2026-11-27T19:45:00Z", et: "joue", p: [0.35, 0.29, 0.36], bot: [1, 1], res: [0, 2] });
});

test("programme : un fichier encore « à venir » après le coup d'envoi ne change plus rien au pronostic du Bot IA", () => {
  const avant = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  const enRetard = matchSite(F1_A_VENIR, "2026-11-27T19:45:00Z", { p: [0.9, 0.05, 0.05], scores: [{ score: "4-0", p: 0.2 }] });
  const prog = fusionner(avant, { F1: fichier("F1", [enRetard]) }, Date.parse("2026-11-27T20:30:00Z"));
  assert.deepEqual(prog.matchs[F1_A_VENIR].bot, [1, 1]);
  assert.deepEqual(prog.matchs[F1_A_VENIR].p, [0.35, 0.29, 0.36]);
});

test("programme : une compétition dont le fichier manque ou est vide garde ses matchs", () => {
  const avant = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  for (const source of [null, fichier("F1", []), fichier("E0", [])]) {
    const prog = fusionner(avant, { F1: source }, MAINTENANT + heure);
    assert.ok(prog.matchs[F1_A_VENIR], "match perdu");
  }
});

test("programme : un match déplacé disparaît de son ancienne date, un résultat déjà connu est gardé", () => {
  const vieux = { id: "F1|FRA:Lyon|FRA:Nice|2026-11-01", jour: "2026-11-01", kickoff: "2026-11-01T19:45:00Z", etat: "joue", score: [1, 0], p: [0.5, 0.3, 0.2] };
  const avant = fusionner(null, { F1: fichier("F1", [aVenir(), vieux]) }, MAINTENANT);
  const deplace = matchSite("F1|FRA:Brest|FRA:Paris FC|2026-11-29", "2026-11-29T15:00:00Z");
  const prog = fusionner(avant, { F1: fichier("F1", [deplace]) }, MAINTENANT + heure);
  assert.equal(prog.matchs[F1_A_VENIR], undefined);
  assert.deepEqual(prog.matchs[vieux.id].res, [1, 0]);
  assert.equal(trouver(prog, F1_A_VENIR).id, "F1|FRA:Brest|FRA:Paris FC|2026-11-29");
});

test("programme : l'affiche retour ou un identifiant inconnu ne sont jamais confondus avec un autre match", () => {
  const prog = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  assert.equal(trouver(prog, "F1|FRA:Paris FC|FRA:Brest|2026-11-27"), null);
  assert.equal(trouver(prog, "F1|FRA:Brest|FRA:Paris FC|2026-04-01"), null);   // plus de 90 jours d'écart
  assert.equal(trouver(prog, "constructor"), null);
  assert.equal(trouver(prog, "__proto__"), null);
});

test("programme : un match sans heure connue n'est pas pronosticable", () => {
  const prog = fusionner(null, { F1: fichier("F1", [matchSite(F1_A_VENIR, null)]) }, MAINTENANT);
  assert.equal(prog.matchs[F1_A_VENIR], undefined);
});

function fauxKv(initial = {}) {
  const kv = new Map(Object.entries(initial).map(([k, v]) => [k, JSON.stringify(v)]));
  return { kv, get: async (k) => (kv.has(k) ? JSON.parse(kv.get(k)) : null), put: async (k, v) => { kv.set(k, v); } };
}

test("publication du programme : les sept fichiers du site sont lus et le résultat est rangé dans KV", async () => {
  const stockage = fauxKv(), demandes = [];
  const bilan = await publier({ stockage, maintenant: MAINTENANT, lireFichier: async (nom) => {
    demandes.push(nom);
    if (nom === "ligue-1") return fichier("F1", [aVenir()]);
    throw new Error("404");
  } });
  assert.equal(demandes.length, 7);
  assert.deepEqual(Object.keys((await stockage.get("programme")).matchs), [F1_A_VENIR]);
  assert.deepEqual(bilan, { matchs: 1, lus: 1, absents: ["E0", "D1", "SP1", "I1", "LDC", "LEC"] });
});

test("publication du programme : si aucun fichier n'est lisible, rien n'est réécrit (la date du programme ne ment pas)", async () => {
  const ancien = fusionner(null, { F1: fichier("F1", [aVenir()]) }, MAINTENANT);
  const stockage = fauxKv({ programme: ancien });
  await assert.rejects(publier({ stockage, maintenant: MAINTENANT + heure, lireFichier: async () => { throw new Error("panne"); } }), /aucun fichier/);
  assert.equal((await stockage.get("programme")).maj_ms, MAINTENANT);
});

// ---------------------------------------------------------------- API : base D1 simulée par SQLite, avec le vrai schema.sql

const SCHEMA = readFileSync(new URL("../relais/schema.sql", import.meta.url), "utf8");

/* ce que le Worker utilise de D1 : prepare/bind/first/all/run et batch (une transaction) */
function fausseD1() {
  const base = new DatabaseSync(":memory:");
  base.exec("PRAGMA foreign_keys = ON");
  base.exec(SCHEMA);
  base.exec(SCHEMA);                     // le déploiement le rejoue à chaque fois
  const preparer = (sql, valeurs = []) => ({
    bind: (...v) => preparer(sql, v),
    first: async () => base.prepare(sql).get(...valeurs) ?? null,
    all: async () => ({ results: base.prepare(sql).all(...valeurs) }),
    run: async () => ({ meta: { changes: Number(base.prepare(sql).run(...valeurs).changes) } }),
  });
  return {
    base,
    prepare: (sql) => preparer(sql),
    async batch(requetes) {
      base.exec("BEGIN");
      try {
        const sorties = [];
        for (const r of requetes) sorties.push(await r.run());
        base.exec("COMMIT");
        return sorties;
      } catch (error) {
        base.exec("ROLLBACK");
        throw error;
      }
    },
  };
}

const M1 = "F1|FRA:Brest|FRA:Paris FC|2026-11-27";       // coup d'envoi le 27 à 19 h 45
const M2 = "LDC|AZE:Sabah FK|ESP:Barcelona|2026-11-25";  // coup d'envoi le 25 à 17 h 45, Barcelone grand favori
const KO1 = Date.parse("2026-11-27T19:45:00Z");
const KO2 = Date.parse("2026-11-25T17:45:00Z");

const site = (surcharges = {}) => ({
  F1: fichier("F1", [{ ...matchSite(M1, "2026-11-27T19:45:00Z"), ...surcharges[M1] }]),
  LDC: fichier("LDC", [{ ...matchSite(M2, "2026-11-25T17:45:00Z", { p: [0.03, 0.06, 0.91], scores: [{ score: "0-4", p: 0.08 }] }), ...surcharges[M2] }]),
});

/* un Worker complet avec son horloge ; les routes des ligues ne doivent jamais appeler l'extérieur (quota API-Football) */
function ligueMonde(t) {
  const horloge = { t: MAINTENANT };
  const vraieHeure = Date.now, vraiFetch = globalThis.fetch;
  Date.now = () => horloge.t;
  globalThis.fetch = async (url) => { throw new Error(`appel extérieur interdit : ${url}`); };
  t.after(() => { Date.now = vraieHeure; globalThis.fetch = vraiFetch; });
  const DB = fausseD1();
  const DIRECT = fauxKv();
  const env = { DB, DIRECT };
  const publierProgramme = async (surcharges) => {
    await DIRECT.put("programme", JSON.stringify(fusionner(await DIRECT.get("programme"), site(surcharges), horloge.t)));
  };
  async function appel(methode, chemin, { corps, jeton, brut } = {}) {
    const headers = jeton ? { authorization: `Bearer ${jeton}` } : {};
    const r = await relais.fetch(new Request(`https://relais.test${chemin}`, { method: methode, headers,
      body: brut ?? (corps === undefined ? undefined : JSON.stringify(corps)) }), env);
    const texte = await r.text();
    let json = null;
    try { json = JSON.parse(texte); } catch { /* réponse en texte */ }
    return { statut: r.status, entetes: r.headers, texte, json };
  }
  const creer = async (pseudo = "Maxime") => (await appel("POST", "/ligues", { corps: { nom: "Les experts", pseudo } })).json;
  const rejoindre = async (code, pseudo) => (await appel("POST", `/ligues/${code}/rejoindre`, { corps: { pseudo } })).json;
  const pronostiquer = (code, jeton, match_id, buts_dom, buts_ext) =>
    appel("POST", `/ligues/${code}/pronos`, { jeton, corps: { match_id, buts_dom, buts_ext } });
  return { env, DB, DIRECT, horloge, appel, creer, rejoindre, pronostiquer, publierProgramme };
}

async function ligueADeux(t) {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const ana = await w.creer("Ana");
  const ben = await w.rejoindre(ana.code, "Ben");
  return { ...w, code: ana.code, ana, ben };
}
const membre = (vue, pseudo) => vue.membres.find((m) => m.pseudo === pseudo);
const prono = (vue, pseudo, id) => membre(vue, pseudo).pronos.find((p) => p.match_id === id);
const rang = (vue, pseudo) => vue.classement.find((c) => c.pseudo === pseudo);

test("créer une ligue : code lisible, jeton remis une seule fois, créateur et Bot IA inscrits", async (t) => {
  const w = ligueMonde(t);
  const r = await w.appel("POST", "/ligues", { corps: { nom: "  Les   experts ", pseudo: "Maxime" } });
  assert.equal(r.statut, 201);
  assert.match(r.json.code, /^[A-HJ-NP-Z]{3}-\d{3}$/);
  assert.match(r.json.jeton, /^[0-9a-f]{64}$/);
  assert.equal(r.entetes.get("access-control-allow-origin"), "*");
  assert.equal(r.entetes.get("cache-control"), "no-store");
  const lignes = w.DB.base.prepare("SELECT id, pseudo, est_bot, jeton_hash FROM membres ORDER BY est_bot").all();
  assert.deepEqual(lignes.map((m) => [m.pseudo, m.est_bot]), [["Maxime", 0], ["Bot IA", 1]]);
  assert.equal(lignes[0].id, r.json.membre_id);
  assert.notEqual(lignes[0].jeton_hash, r.json.jeton);
  assert.equal(lignes[1].jeton_hash, "");
  assert.equal(w.DB.base.prepare("SELECT nom FROM ligues").get().nom, "Les experts");
});

test("créer une ligue : saisies refusées sans rien écrire", async (t) => {
  const w = ligueMonde(t);
  const essais = [
    [{ brut: "{pas du json" }, 400], [{ brut: "[1]" }, 400], [{ brut: "null" }, 400],
    [{ corps: { pseudo: "Ana" } }, 400], [{ corps: { nom: "Ligue" } }, 400], [{ corps: { nom: "Ligue", pseudo: 42 } }, 400],
    [{ corps: { nom: "ab", pseudo: "Ana" } }, 400], [{ corps: { nom: "x".repeat(41), pseudo: "Ana" } }, 400],
    [{ corps: { nom: "Ligue", pseudo: "A" } }, 400], [{ corps: { nom: "Ligue", pseudo: "x".repeat(21) } }, 400],
    [{ corps: { nom: "Ligue", pseudo: "<img src=x>" } }, 400], [{ corps: { nom: "Ligue", pseudo: "a​b" } }, 400],
    [{ corps: { nom: "<b>Ligue</b>", pseudo: "Ana" } }, 400], [{ corps: { nom: "Ligue", pseudo: "bot ia" } }, 409],
    [{ brut: JSON.stringify({ nom: "Ligue", pseudo: "Ana", bourrage: "x".repeat(3000) }) }, 413],
  ];
  for (const [options, statut] of essais) {
    const r = await w.appel("POST", "/ligues", options);
    assert.equal(r.statut, statut, `${JSON.stringify(options).slice(0, 80)} : ${r.texte}`);
    assert.equal(typeof r.json.erreur.message, "string");
    assert.equal(r.entetes.get("access-control-allow-origin"), "*");
  }
  assert.equal(w.DB.base.prepare("SELECT COUNT(*) AS n FROM ligues").get().n, 0);
  assert.equal(w.DB.base.prepare("SELECT COUNT(*) AS n FROM membres").get().n, 0);
});

test("créer une ligue : un code déjà pris est retiré au sort à nouveau", async (t) => {
  const w = ligueMonde(t);
  const vrai = crypto.getRandomValues.bind(crypto);
  let figes = 2;           // les deux premiers tirages de code (6 octets) sont identiques, puis le hasard reprend
  t.mock.method(crypto, "getRandomValues", (tableau) => {
    if (tableau.length === 6 && figes > 0) { figes -= 1; return tableau.fill(0); }
    return vrai(tableau);
  });
  const a = await w.creer("Ana"), b = await w.creer("Ben");
  assert.equal(a.code, "AAA-000");
  assert.notEqual(b.code, "AAA-000");
  assert.equal(w.DB.base.prepare("SELECT COUNT(*) AS n FROM membres").get().n, 4);
});

test("rejoindre : pseudo unique sans tenir compte de la casse (accents compris), code accepté en minuscules", async (t) => {
  const w = ligueMonde(t);
  const { code } = await w.creer("Élodie");
  const ok = await w.appel("POST", `/ligues/${code.toLowerCase()}/rejoindre`, { corps: { pseudo: "Zoé" } });
  assert.equal(ok.statut, 201);
  assert.deepEqual(Object.keys(ok.json).sort(), ["jeton", "membre_id"]);
  for (const pseudo of ["ÉLODIE", "  zoé ", "ZOÉ", "BOT IA", "Bot   IA"]) {
    const r = await w.appel("POST", `/ligues/${code}/rejoindre`, { corps: { pseudo } });
    assert.equal(r.statut, 409, pseudo);
    assert.equal(r.json.erreur.code, "pseudo_pris");
  }
});

test("rejoindre : ligue inconnue, pseudo invalide, ligue complète", async (t) => {
  const w = ligueMonde(t);
  const { code } = await w.creer("Ana");
  assert.equal((await w.appel("POST", "/ligues/ZZZ-999/rejoindre", { corps: { pseudo: "Ben" } })).statut, 404);
  assert.equal((await w.appel("POST", "/ligues/nimporte/rejoindre", { corps: { pseudo: "Ben" } })).statut, 404);
  assert.equal((await w.appel("POST", `/ligues/${code}/rejoindre`, { corps: { pseudo: " " } })).statut, 400);
  for (let i = 2; i <= 30; i++) assert.equal((await w.appel("POST", `/ligues/${code}/rejoindre`, { corps: { pseudo: `Joueur ${i}` } })).statut, 201);
  const trop = await w.appel("POST", `/ligues/${code}/rejoindre`, { corps: { pseudo: "Retardataire" } });
  assert.equal(trop.statut, 409);
  assert.equal(trop.json.erreur.code, "ligue_complete");
});

test("pronostiquer : enregistre puis modifie le score avant le coup d'envoi", async (t) => {
  const w = await ligueADeux(t);
  const r = await w.pronostiquer(w.code, w.ana.jeton, M1, 2, 1);
  assert.equal(r.statut, 200);
  assert.deepEqual(r.json, { match_id: M1, buts_dom: 2, buts_ext: 1, coup_envoi: "2026-11-27T19:45:00Z", maj_le: "2026-11-24T12:00:00.000Z" });
  w.horloge.t = KO1 - 1000;
  await w.publierProgramme();
  assert.equal((await w.pronostiquer(w.code, w.ana.jeton, M1, 0, 0)).statut, 200);
  const lignes = w.DB.base.prepare("SELECT membre_id, buts_dom, buts_ext FROM pronos").all();
  assert.deepEqual(lignes.map((l) => ({ ...l })), [{ membre_id: w.ana.membre_id, buts_dom: 0, buts_ext: 0 }]);
});

test("pronostiquer : verrouillé à l'heure du coup d'envoi et après", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M1, 2, 1);
  for (const instant of [KO1, KO1 + 1000, KO1 + 48 * heure]) {
    w.horloge.t = instant;
    await w.publierProgramme();       // programme frais, même si le fichier du site dit encore « à venir »
    const r = await w.pronostiquer(w.code, w.ana.jeton, M1, 5, 0);
    assert.equal(r.statut, 409);
    assert.equal(r.json.erreur.code, "match_verrouille");
  }
  assert.equal(w.DB.base.prepare("SELECT buts_dom FROM pronos").get().buts_dom, 2);
});

test("pronostiquer : un match que le site ne dit plus « à venir » est verrouillé même avant l'heure prévue", async (t) => {
  const w = await ligueADeux(t);
  for (const etat of ["en_cours", "en_attente", "reporte", "joue"]) {
    await w.publierProgramme({ [M1]: { etat, score: [1, 0] } });
    assert.equal((await w.pronostiquer(w.code, w.ana.jeton, M1, 1, 0)).statut, 409, etat);
  }
});

test("pronostiquer : jeton absent, faux, d'une autre ligue ou ligue inconnue", async (t) => {
  const w = await ligueADeux(t);
  const autre = await w.creer("Chloé");
  for (const jeton of [undefined, "abc", "0".repeat(64), autre.jeton]) {
    const r = await w.pronostiquer(w.code, jeton, M1, 1, 0);
    assert.equal(r.statut, 401, String(jeton));
  }
  assert.equal((await w.pronostiquer("ZZZ-999", w.ana.jeton, M1, 1, 0)).statut, 404);
  assert.equal(w.DB.base.prepare("SELECT COUNT(*) AS n FROM pronos").get().n, 0);
});

test("pronostiquer : score ou match invalides", async (t) => {
  const w = await ligueADeux(t);
  for (const [dom, ext] of [[-1, 0], [0, 21], [1.5, 0], ["1", 0], [null, 0], [undefined, 1]]) {
    assert.equal((await w.pronostiquer(w.code, w.ana.jeton, M1, dom, ext)).statut, 400, `${dom}-${ext}`);
  }
  for (const id of [undefined, 12, "", "x".repeat(200)]) {
    assert.equal((await w.pronostiquer(w.code, w.ana.jeton, id, 1, 0)).statut, 400, String(id));
  }
  for (const id of ["F1|FRA:Brest|FRA:Lyon|2026-11-27", "constructor", "F1|FRA:Brest|FRA:Paris FC|2026-11-20"]) {
    const r = await w.pronostiquer(w.code, w.ana.jeton, id, 1, 0);
    assert.equal(r.statut, 404, id);
    assert.equal(r.json.erreur.code, "match_inconnu");
  }
});

test("pronostiquer : sans programme, ou avec un programme de plus de 48 h, rien n'est accepté", async (t) => {
  const w = ligueMonde(t);
  const ana = await w.creer("Ana");
  assert.equal((await w.pronostiquer(ana.code, ana.jeton, M1, 1, 0)).statut, 503);
  await w.publierProgramme();
  w.horloge.t = MAINTENANT + 49 * heure;
  const r = await w.pronostiquer(ana.code, ana.jeton, M1, 1, 0);
  assert.equal(r.statut, 503);
  assert.equal(r.json.erreur.code, "programme_indisponible");
});

test("consulter : avant le coup d'envoi, chacun ne voit que ses propres scores", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M1, 2, 1);
  await w.pronostiquer(w.code, w.ben.jeton, M1, 0, 3);
  const vueAna = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ana.jeton })).json;
  assert.equal(vueAna.moi, w.ana.membre_id);
  assert.equal(prono(vueAna, "Ana", M1).buts_dom, 2);
  assert.deepEqual(prono(vueAna, "Ben", M1), { match_id: M1, masque: true });
  const anonyme = await w.appel("GET", `/ligues/${w.code}`);
  assert.equal(anonyme.statut, 200);
  assert.equal(anonyme.json.moi, null);
  for (const pseudo of ["Ana", "Ben"]) assert.deepEqual(prono(anonyme.json, pseudo, M1), { match_id: M1, masque: true });
  assert.ok(!/jeton|hash/.test(anonyme.texte), "secret dans la réponse");
  assert.equal(anonyme.entetes.get("cache-control"), "no-store");
  assert.equal(anonyme.entetes.get("vary"), "authorization");
});

test("consulter : dès le coup d'envoi, les scores de ce match sont visibles, les autres restent masqués", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ben.jeton, M1, 0, 3);
  await w.pronostiquer(w.code, w.ben.jeton, M2, 0, 5);
  w.horloge.t = KO2 - 1000;
  let vue = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ana.jeton })).json;
  assert.equal(prono(vue, "Ben", M2).masque, true);
  w.horloge.t = KO2;
  vue = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ana.jeton })).json;
  assert.deepEqual([prono(vue, "Ben", M2).buts_dom, prono(vue, "Ben", M2).buts_ext], [0, 5]);
  assert.equal(prono(vue, "Ben", M1).masque, true);
  assert.equal(vue.matchs[M2].commence, true);
  assert.equal(vue.matchs[M1].commence, false);
});

test("consulter : un match reporté ne dévoile rien, même après son heure prévue", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ben.jeton, M1, 0, 3);
  w.horloge.t = KO1 + heure;
  await w.publierProgramme({ [M1]: { etat: "reporte" } });
  const vue = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ana.jeton })).json;
  assert.deepEqual(prono(vue, "Ben", M1), { match_id: M1, masque: true });
});

test("consulter : le Bot IA joue le score n° 1 des seuls matchs pronostiqués par la ligue", async (t) => {
  const w = await ligueADeux(t);
  let vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.deepEqual(membre(vue, "Bot IA").pronos, []);
  await w.pronostiquer(w.code, w.ana.jeton, M2, 0, 3);
  vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.equal(membre(vue, "Bot IA").est_bot, true);
  assert.deepEqual(membre(vue, "Bot IA").pronos, [{ match_id: M2, buts_dom: 0, buts_ext: 4 }]);
});

test("classement : points détaillés, coup de poker, Bot IA classé avec les joueurs", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M2, 1, 0);   // Sabah à 3 % : coup de poker réussi, score exact
  await w.pronostiquer(w.code, w.ben.jeton, M2, 0, 2);   // mauvaise issue
  await w.pronostiquer(w.code, w.ana.jeton, M1, 3, 2);   // bon écart sur un 2-1
  await w.pronostiquer(w.code, w.ben.jeton, M1, 1, 0);
  w.horloge.t = KO1 + 12 * heure;
  await w.publierProgramme({ [M1]: { etat: "joue", score: [2, 1] }, [M2]: { etat: "joue", score: [1, 0] } });
  const vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.deepEqual(vue.matchs[M2], { coup_envoi: "2026-11-25T17:45:00Z", commence: true, score: [1, 0], probas: [0.03, 0.06, 0.91] });
  assert.deepEqual(prono(vue, "Ana", M2), { match_id: M2, buts_dom: 1, buts_ext: 0, points: 15,
    bonne_issue: true, bon_ecart: true, score_exact: true, coup_de_poker: true });
  assert.deepEqual(vue.classement.map((c) => [c.rang, c.pseudo, c.points]), [[1, "Ana", 20], [2, "Ben", 5], [3, "Bot IA", 0]]);
  assert.deepEqual(rang(vue, "Ana"), { rang: 1, membre_id: w.ana.membre_id, pseudo: "Ana", est_bot: false, points: 20,
    scores_exacts: 1, bonnes_issues: 2, bons_ecarts: 2, coups_de_poker: 1, matchs_juges: 2 });
  assert.equal(rang(vue, "Bot IA").matchs_juges, 2);
});

test("classement : à égalité parfaite, même rang ; un joueur sans pronostic reste classé avec zéro", async (t) => {
  const w = await ligueADeux(t);
  await w.rejoindre(w.code, "Zoé");
  await w.pronostiquer(w.code, w.ana.jeton, M1, 2, 0);
  await w.pronostiquer(w.code, w.ben.jeton, M1, 2, 0);
  w.horloge.t = KO1 + 12 * heure;
  await w.publierProgramme({ [M1]: { etat: "joue", score: [1, 0] } });
  const vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.deepEqual(vue.classement.map((c) => [c.rang, c.pseudo, c.points]),
    [[1, "Ana", 3], [1, "Ben", 3], [3, "Bot IA", 0], [3, "Zoé", 0]]);
});

test("match déplacé : le pronostic suit le match et un nouveau pronostic remplace l'ancien", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M1, 1, 0);
  await w.pronostiquer(w.code, w.ben.jeton, M1, 0, 1);
  const NOUVEAU = "F1|FRA:Brest|FRA:Paris FC|2026-11-28";
  const deplace = { [M1]: { id: NOUVEAU, jour: "2026-11-28", kickoff: "2026-11-28T15:00:00Z" } };
  w.horloge.t = MAINTENANT + heure;
  await w.publierProgramme(deplace);
  await w.pronostiquer(w.code, w.ben.jeton, NOUVEAU, 4, 4);
  let vue = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ben.jeton })).json;
  assert.deepEqual(membre(vue, "Ben").pronos, [{ match_id: NOUVEAU, buts_dom: 4, buts_ext: 4 }]);
  assert.deepEqual(membre(vue, "Ana").pronos, [{ match_id: NOUVEAU, masque: true }]);
  w.horloge.t = Date.parse("2026-11-29T08:00:00Z");
  await w.publierProgramme({ [M1]: { ...deplace[M1], etat: "joue", score: [1, 0] } });
  vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.equal(rang(vue, "Ana").points, 10);
  assert.equal(rang(vue, "Ben").matchs_juges, 1);
});

test("anti-triche : un pronostic postérieur au coup d'envoi réel (horaire avancé après coup) ne rapporte rien", async (t) => {
  const w = await ligueADeux(t);
  w.horloge.t = KO1 - 2 * heure;
  await w.publierProgramme();
  await w.pronostiquer(w.code, w.ana.jeton, M1, 1, 0);
  w.horloge.t = KO1 + 12 * heure;
  await w.publierProgramme({ [M1]: { kickoff: "2026-11-27T15:00:00Z", etat: "joue", score: [1, 0] } });
  const vue = (await w.appel("GET", `/ligues/${w.code}`)).json;
  assert.deepEqual(prono(vue, "Ana", M1), { match_id: M1, buts_dom: 1, buts_ext: 0, hors_delai: true });
  assert.equal(rang(vue, "Ana").points, 0);
  assert.deepEqual(membre(vue, "Bot IA").pronos, []);
});

test("consulter : ligue inconnue, jeton invalide, programme absent", async (t) => {
  const w = ligueMonde(t);
  const ana = await w.creer("Ana");
  assert.equal((await w.appel("GET", "/ligues/ZZZ-999")).statut, 404);
  assert.equal((await w.appel("GET", `/ligues/${ana.code}`, { jeton: "0".repeat(64) })).statut, 401);
  assert.equal((await w.appel("GET", `/ligues/${ana.code}`)).statut, 503);
});

test("routes : pré-requête CORS, méthodes et chemins non prévus", async (t) => {
  const w = ligueMonde(t);
  for (const chemin of ["/ligues", "/ligues/EDF-742/pronos"]) {
    const r = await w.appel("OPTIONS", chemin);
    assert.ok(r.statut === 200 || r.statut === 204);
    assert.equal(r.entetes.get("access-control-allow-origin"), "*");
    assert.equal(r.entetes.get("access-control-allow-methods"), "GET, POST, OPTIONS");
    assert.equal(r.entetes.get("access-control-allow-headers"), "authorization, content-type");
  }
  assert.equal((await w.appel("OPTIONS", "/direct")).entetes.get("access-control-allow-methods"), "GET");
  assert.equal((await w.appel("GET", "/ligues")).statut, 405);
  assert.equal((await w.appel("DELETE", "/ligues/EDF-742")).statut, 405);
  assert.equal((await w.appel("GET", "/ligues/EDF-742/pronos")).statut, 405);
  assert.equal((await w.appel("GET", "/ligues/EDF-742/autre")).statut, 404);
  assert.equal((await w.appel("POST", "/direct")).statut, 405);
});

test("isolation : base D1 absente ou en panne, /direct répond toujours et rien d'interne ne fuit", async (t) => {
  const w = ligueMonde(t);
  t.mock.method(console, "error", () => {});
  w.env.DB = { prepare() { throw new Error("SQLITE détail interne"); } };
  const panne = await w.appel("GET", "/ligues/EDF-742");
  assert.equal(panne.statut, 500);
  assert.ok(!panne.texte.includes("SQLITE"));
  assert.equal(panne.entetes.get("access-control-allow-origin"), "*");
  delete w.env.DB;
  assert.equal((await w.appel("POST", "/ligues", { corps: { nom: "Ligue", pseudo: "Ana" } })).statut, 503);
  const direct = await w.appel("GET", "/direct");
  assert.equal(direct.statut, 200);
  assert.deepEqual(direct.json.matchs, []);
  assert.equal(direct.entetes.get("cache-control"), "public, max-age=20");
});
