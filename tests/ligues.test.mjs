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
const MIGRATIONS = readFileSync(new URL("../relais/migrations.sql", import.meta.url), "utf8")
  .split(/\r?\n/).filter((l) => l.trim() && !l.startsWith("--"));
const migrer = (base) => {
  for (const ordre of MIGRATIONS) {
    try { base.exec(ordre); } catch (error) { assert.match(error.message, /duplicate column name/); }
  }
};

/* ce que le Worker utilise de D1 : prepare/bind/first/all/run et batch (une transaction) */
function fausseD1() {
  const base = new DatabaseSync(":memory:");
  base.exec("PRAGMA foreign_keys = ON");
  base.exec(SCHEMA);
  base.exec(SCHEMA);                     // le déploiement le rejoue à chaque fois
  migrer(base);                          // puis les migrations, comme relais.yml
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
  for (const chemin of ["/ligues", "/ligues/EDF-742/pronos", "/comptes/favoris"]) {
    const r = await w.appel("OPTIONS", chemin);
    assert.ok(r.statut === 200 || r.statut === 204);
    assert.equal(r.entetes.get("access-control-allow-origin"), "*");
    assert.equal(r.entetes.get("access-control-allow-methods"), "GET, POST, PUT, DELETE, OPTIONS");
    assert.equal(r.entetes.get("access-control-allow-headers"), "authorization, content-type");
  }
  assert.equal((await w.appel("OPTIONS", "/direct")).entetes.get("access-control-allow-methods"), "GET");
  assert.equal((await w.appel("GET", "/ligues")).statut, 405);
  assert.equal((await w.appel("PUT", "/ligues/EDF-742")).statut, 405);
  assert.equal((await w.appel("DELETE", "/ligues")).statut, 405);
  assert.equal((await w.appel("DELETE", "/ligues/EDF-742/pronos")).statut, 405);
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

// ---------------------------------------------------------------- frontend (site/assets/ligues.js)

import {
  normaliserCode, estCodeValide, lireScoreSaisi, estVerrouille,
  codeDepuisUrl, lienInvitation, competitionsActives, chargerStockage, enregistrerLigue,
  selectionnerLigue, retirerLigue, calculerClassementLive, filtrerMatchsPronosticables, estCreateur,
} from "../site/assets/ligues.js";
import { calculerPoints as calculerPointsSite } from "../site/assets/points.js";

function memStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => { m.set(k, String(v)); },
    removeItem: (k) => { m.delete(k); },
  };
}

test("frontend ligues : synchronisation du barème points.js et helpers code / score / verrouillage", () => {
  assert.deepEqual(calculerPointsSite([2, 1], [2, 1], [0.2, 0.3, 0.5]), calculerPoints([2, 1], [2, 1], [0.2, 0.3, 0.5]));
  assert.equal(normaliserCode("klm 482"), "KLM-482");
  assert.equal(normaliserCode("abc-007"), "ABC-007");
  assert.equal(estCodeValide("KLM-482"), true);
  assert.equal(estCodeValide("KLM-48"), false);
  assert.equal(codeDepuisUrl("?code=klm482"), "KLM-482");
  assert.equal(codeDepuisUrl("?code=invalide"), null);
  assert.equal(lienInvitation("KLM-482", { origin: "https://example.test", pathname: "/foot/ligues.html" }),
    "https://example.test/foot/ligues.html?code=KLM-482");
  assert.equal(lireScoreSaisi("0"), 0);
  assert.equal(lireScoreSaisi("20"), 20);
  assert.equal(lireScoreSaisi("21"), null);
  assert.equal(lireScoreSaisi("-1"), null);
  assert.equal(lireScoreSaisi("1.5"), null);
  assert.equal(lireScoreSaisi(""), null);
  const ko = "2026-11-27T20:00:00Z";
  assert.equal(estVerrouille(ko, Date.parse("2026-11-27T19:59:59Z")), false);
  assert.equal(estVerrouille(ko, Date.parse("2026-11-27T20:00:00Z")), true);
  assert.equal(estVerrouille(null, Date.parse("2026-11-27T19:00:00Z")), true);
});

test("frontend ligues : stockage multi-ligues dans localStorage", () => {
  const st = memStorage();
  assert.deepEqual(chargerStockage(st), { active: null, ligues: [] });
  let etat = enregistrerLigue(st, { code: "klm482", nom: "Bureau", membre_id: "m1", jeton: "tok1", pseudo: "Max" });
  assert.equal(etat.active, "KLM-482");
  assert.equal(etat.ligues.length, 1);
  etat = enregistrerLigue(st, { code: "ABC-123", nom: "Famille", membre_id: "m2", jeton: "tok2", pseudo: "Maxime" });
  assert.equal(etat.active, "ABC-123");
  assert.equal(etat.ligues.length, 2);
  etat = selectionnerLigue(st, "KLM-482");
  assert.equal(etat.active, "KLM-482");
  etat = retirerLigue(st, "KLM-482");
  assert.equal(etat.active, "ABC-123");
  assert.equal(etat.ligues.length, 1);
  etat = retirerLigue(st, "ABC-123");
  assert.deepEqual(etat, { active: null, ligues: [] });
});

test("frontend ligues : filtrage des matchs pronosticables (compétition, favoris, horizon)", () => {
  const now = Date.parse("2026-11-24T12:00:00Z");
  const matchs = [
    { id: "m1", c: "F1", etat: "a_venir", kickoff: "2026-11-25T20:00:00Z", home: "FRA:Paris SG", away: "FRA:Lyon" },
    { id: "m2", c: "LDC", etat: "a_venir", kickoff: "2026-11-26T20:00:00Z", home: "ESP:Real Madrid", away: "ITA:Inter" },
    { id: "m3", c: "F1", etat: "a_venir", kickoff: "2026-11-24T11:00:00Z", home: "FRA:Lens", away: "FRA:Lille" },
    { id: "m4", c: "F1", etat: "joue", kickoff: "2026-11-25T20:00:00Z", home: "FRA:Nice", away: "FRA:Brest" },
    { id: "m5", c: "E0", etat: "a_venir", kickoff: "2026-12-20T20:00:00Z", home: "ENG:Arsenal", away: "ENG:Chelsea" },
  ];
  assert.deepEqual(filtrerMatchsPronosticables(matchs, { maintenant: now }).map((m) => m.id), ["m1", "m2"]);
  assert.deepEqual(filtrerMatchsPronosticables(matchs, { comp: "LDC", maintenant: now }).map((m) => m.id), ["m2"]);
  assert.deepEqual(
    filtrerMatchsPronosticables(matchs, { comp: "FAV", favoris: new Set(["FRA:Paris SG"]), maintenant: now }).map((m) => m.id),
    ["m1"],
  );
});

test("frontend ligues : classement provisoire en direct sans double comptage", () => {
  const ligue = {
    matchs: {
      m_fini: { score: [2, 1], probas: [0.5, 0.25, 0.25] },
      m_live: { score: null, probas: [0.2, 0.3, 0.5] },
    },
    classement: [
      { rang: 1, membre_id: "bot", pseudo: "Bot IA", est_bot: true, points: 10, scores_exacts: 1, bonnes_issues: 1, coups_de_poker: 0, matchs_juges: 1 },
      { rang: 2, membre_id: "ana", pseudo: "Ana", est_bot: false, points: 3, scores_exacts: 0, bonnes_issues: 1, coups_de_poker: 0, matchs_juges: 1 },
    ],
    membres: [
      { id: "bot", pseudo: "Bot IA", est_bot: true, pronos: [
        { match_id: "m_fini", buts_dom: 2, buts_ext: 1, points: 10 },
        { match_id: "m_live", buts_dom: 0, buts_ext: 2 },
      ] },
      { id: "ana", pseudo: "Ana", est_bot: false, pronos: [
        { match_id: "m_fini", buts_dom: 1, buts_ext: 0, points: 3 },
        { match_id: "m_live", buts_dom: 2, buts_ext: 0 }, // exact + coup de poker (< 0.25) -> 15 pts provisoires
      ] },
    ],
  };
  const direct = new Map([
    ["m_fini", { st: "FT", g: [2, 1] }],   // déjà jugé officiellement -> ne doit pas être recompté
    ["m_live", { st: "2H", g: [2, 0] }],   // en cours -> points provisoires
  ]);
  const { lignes, nbMatchsLive } = calculerClassementLive(ligue, direct);
  assert.equal(nbMatchsLive, 1);
  assert.deepEqual(
    lignes.map((r) => [r.rang_affiche, r.pseudo, r.points, r.points_live, r.points_total]),
    [[1, "Ana", 3, 15, 18], [2, "Bot IA", 10, 0, 10]],
  );
});

test("compétitions par ligue : création, alias, validation et rétrocompatibilité NULL", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();

  // par défaut (sans competitions) -> toutes les 7, NULL en base
  const defaut = await w.appel("POST", "/ligues", { corps: { nom: "Toutes", pseudo: "Max" } });
  assert.equal(defaut.statut, 201);
  assert.deepEqual(defaut.json.competitions, ["E0", "D1", "SP1", "I1", "F1", "LDC", "LEC"]);
  assert.equal(w.DB.base.prepare("SELECT competitions FROM ligues WHERE code = ?").get(defaut.json.code).competitions, null);

  // sous-ensemble avec codes canoniques
  const l1Ldc = await w.appel("POST", "/ligues", { corps: { nom: "L1 et LDC", pseudo: "Ana", competitions: ["LDC", "F1"] } });
  assert.equal(l1Ldc.statut, 201);
  assert.deepEqual(l1Ldc.json.competitions, ["F1", "LDC"]);
  assert.equal(w.DB.base.prepare("SELECT competitions FROM ligues WHERE code = ?").get(l1Ldc.json.code).competitions, '["F1","LDC"]');

  // alias football-data.org (FL1, CL, PL, PD, BL1, SA, EL) normalisés et dédupliqués
  const alias = await w.appel("POST", "/ligues", { corps: { nom: "Alias", pseudo: "Ben", competitions: ["FL1", "CL", "PL", "F1"] } });
  assert.equal(alias.statut, 201);
  assert.deepEqual(alias.json.competitions, ["E0", "F1", "LDC"]);

  // saisies invalides refusées en 400
  for (const mauvaises of [[], ["XX"], ["F1", "INCONNU"], "F1", [123]]) {
    const r = await w.appel("POST", "/ligues", { corps: { nom: "Mauvaise", pseudo: "Max", competitions: mauvaises } });
    assert.equal(r.statut, 400);
    assert.equal(r.json.erreur.code, "competitions_invalides");
  }
});

test("compétitions par ligue : refus des pronostics hors périmètre et filtrage du classement / Bot IA", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const r = await w.appel("POST", "/ligues", { corps: { nom: "Ligue 1 pure", pseudo: "Ana", competitions: ["F1"] } });
  assert.equal(r.statut, 201);
  const { code, jeton, membre_id } = r.json;

  // match F1 accepté, match LDC refusé en 400
  assert.equal((await w.pronostiquer(code, jeton, M1, 1, 0)).statut, 200);
  const refus = await w.pronostiquer(code, jeton, M2, 0, 4);
  assert.equal(refus.statut, 400);
  assert.equal(refus.json.erreur.code, "competition_non_autorisee");

  // même si une ligne hors périmètre existait en base, GET /ligues/:code l'ignore partout (membres, Bot IA, matchs, classement)
  w.DB.base.prepare("INSERT INTO pronos (ligue_code, membre_id, match_id, buts_dom, buts_ext, maj_le) VALUES (?, ?, ?, 0, 4, ?)")
    .run(code, membre_id, M2, new Date(MAINTENANT).toISOString());

  w.horloge.t = KO1 + 3 * heure;
  await w.publierProgramme({
    [M1]: { etat: "joue", score: [1, 0] },
    [M2]: { etat: "joue", score: [0, 4] },
  });

  const vue = (await w.appel("GET", `/ligues/${code}`, { jeton })).json;
  assert.deepEqual(vue.competitions, ["F1"]);
  assert.deepEqual(Object.keys(vue.matchs), [M1]);
  assert.deepEqual(membre(vue, "Ana").pronos.map((p) => p.match_id), [M1]);
  assert.deepEqual(membre(vue, "Bot IA").pronos.map((p) => p.match_id), [M1]);
  assert.equal(rang(vue, "Ana").matchs_juges, 1);
  assert.equal(rang(vue, "Ana").points, 10);
  assert.equal(rang(vue, "Bot IA").matchs_juges, 1);
});

test("frontend ligues : competitionsActives et filtrage selon les compétitions de la ligue", () => {
  assert.deepEqual(competitionsActives(null), ["E0", "D1", "SP1", "I1", "F1", "LDC", "LEC"]);
  assert.deepEqual(competitionsActives({ competitions: ["LDC", "F1"] }), ["F1", "LDC"]);
  const now = Date.parse("2026-11-24T12:00:00Z");
  const matchs = [
    { id: "m1", c: "F1", etat: "a_venir", kickoff: "2026-11-25T20:00:00Z", home: "FRA:Paris SG", away: "FRA:Lyon" },
    { id: "m2", c: "LDC", etat: "a_venir", kickoff: "2026-11-26T20:00:00Z", home: "ESP:Real Madrid", away: "ITA:Inter" },
    { id: "m3", c: "E0", etat: "a_venir", kickoff: "2026-11-26T20:00:00Z", home: "ENG:Arsenal", away: "ENG:Chelsea" },
  ];
  assert.deepEqual(
    filtrerMatchsPronosticables(matchs, { autorisees: ["F1", "LDC"], maintenant: now }).map((m) => m.id),
    ["m1", "m2"],
  );
  assert.deepEqual(
    filtrerMatchsPronosticables(matchs, { comp: "FAV", favoris: new Set(["ENG:Arsenal", "FRA:Paris SG"]), autorisees: ["F1", "LDC"], maintenant: now }).map((m) => m.id),
    ["m1"],
  );
  // calculerClassementLive ignore les matchs live hors compétitions de la ligue
  const ligue = {
    competitions: ["F1"],
    matchs: { "E0|ENG:Arsenal|ENG:Chelsea|2026-11-26": { score: null, probas: [0.5, 0.25, 0.25] } },
    classement: [{ rang: 1, membre_id: "ana", pseudo: "Ana", est_bot: false, points: 0, scores_exacts: 0, bonnes_issues: 0, coups_de_poker: 0, matchs_juges: 0 }],
    membres: [{ id: "ana", pseudo: "Ana", est_bot: false, pronos: [{ match_id: "E0|ENG:Arsenal|ENG:Chelsea|2026-11-26", buts_dom: 2, buts_ext: 0 }] }],
  };
  const live = calculerClassementLive(ligue, new Map([["E0|ENG:Arsenal|ENG:Chelsea|2026-11-26", { st: "2H", g: [2, 0] }]]));
  assert.equal(live.nbMatchsLive, 0);
  assert.equal(live.lignes[0].points_total, 0);
});

// ---------------------------------------------------------------- suppression de ligue et créateur

const lignesDe = (w, table, code) => w.DB.base.prepare(
  `SELECT COUNT(*) AS n FROM ${table} WHERE ${table === "ligues" ? "code" : "ligue_code"} = ?`).get(code).n;

test("créateur : enregistré à la création et indiqué par la consultation", async (t) => {
  const w = await ligueADeux(t);
  assert.equal(w.DB.base.prepare("SELECT createur_id FROM ligues WHERE code = ?").get(w.code).createur_id, w.ana.membre_id);
  const vue = (await w.appel("GET", `/ligues/${w.code}`, { jeton: w.ben.jeton })).json;
  assert.equal(vue.createur_id, w.ana.membre_id);
  assert.equal(vue.moi, w.ben.membre_id);
});

test("supprimer : refusé sans le jeton du créateur, et rien n'est effacé", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M1, 1, 0);
  const autre = await w.creer("Zoé");

  const sans = await w.appel("DELETE", `/ligues/${w.code}`);
  assert.deepEqual([sans.statut, sans.json.erreur.code], [401, "jeton_manquant"]);
  const faux = await w.appel("DELETE", `/ligues/${w.code}`, { jeton: "0".repeat(64) });
  assert.deepEqual([faux.statut, faux.json.erreur.code], [401, "jeton_invalide"]);
  // le créateur d'une autre ligue n'a aucun droit sur celle-ci
  const voisin = await w.appel("DELETE", `/ligues/${w.code}`, { jeton: autre.jeton });
  assert.deepEqual([voisin.statut, voisin.json.erreur.code], [401, "jeton_invalide"]);
  const membre2 = await w.appel("DELETE", `/ligues/${w.code}`, { jeton: w.ben.jeton });
  assert.deepEqual([membre2.statut, membre2.json.erreur.code], [403, "pas_createur"]);

  assert.deepEqual(["ligues", "membres", "pronos"].map((x) => lignesDe(w, x, w.code)), [1, 3, 1]);
});

test("supprimer : le créateur efface la ligue, ses membres et ses pronostics, et eux seuls", async (t) => {
  const w = await ligueADeux(t);
  await w.pronostiquer(w.code, w.ana.jeton, M1, 1, 0);
  await w.pronostiquer(w.code, w.ben.jeton, M2, 0, 3);
  const autre = await w.creer("Zoé");
  await w.pronostiquer(autre.code, autre.jeton, M1, 2, 2);

  const r = await w.appel("DELETE", `/ligues/${w.code.toLowerCase()}`, { jeton: w.ana.jeton });
  assert.equal(r.statut, 200);
  assert.deepEqual(r.json, { code: w.code, supprimee: true });
  assert.equal(r.entetes.get("access-control-allow-origin"), "*");
  assert.deepEqual(["ligues", "membres", "pronos"].map((x) => lignesDe(w, x, w.code)), [0, 0, 0]);
  assert.deepEqual(["ligues", "membres", "pronos"].map((x) => lignesDe(w, x, autre.code)), [1, 2, 1]);
  assert.equal((await w.appel("GET", `/ligues/${w.code}`)).statut, 404);
  assert.equal((await w.appel("DELETE", `/ligues/${w.code}`, { jeton: w.ana.jeton })).statut, 404);
});

test("migration : une base d'avant reçoit les colonnes, le créateur est retrouvé, et la rejouer ne casse rien", () => {
  const base = new DatabaseSync(":memory:");
  base.exec(`CREATE TABLE ligues (code TEXT PRIMARY KEY, nom TEXT NOT NULL, cree_le TEXT NOT NULL);
    CREATE TABLE membres (id TEXT PRIMARY KEY, ligue_code TEXT NOT NULL, pseudo TEXT NOT NULL, pseudo_cle TEXT NOT NULL,
      jeton_hash TEXT NOT NULL, est_bot INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL);`);
  base.exec(`INSERT INTO ligues VALUES ('ABC-123', 'Ancienne', '2026-11-20T10:00:00.000Z');
    INSERT INTO membres VALUES ('bot', 'ABC-123', 'Bot IA', 'bot ia', '', 1, '2026-11-20T10:00:00.000Z');
    INSERT INTO membres VALUES ('invite', 'ABC-123', 'Ben', 'ben', 'h2', 0, '2026-11-21T09:00:00.000Z');
    INSERT INTO membres VALUES ('fondatrice', 'ABC-123', 'Ana', 'ana', 'h1', 0, '2026-11-20T10:00:00.000Z');`);
  for (let passage = 0; passage < 2; passage++) migrer(base);
  assert.deepEqual({ ...base.prepare("SELECT competitions, createur_id FROM ligues").get() },
    { competitions: null, createur_id: "fondatrice" });
});

test("frontend ligues : le bouton de suppression est réservé au créateur", () => {
  assert.equal(estCreateur({ moi: "a", createur_id: "a" }), true);
  assert.equal(estCreateur({ moi: "b", createur_id: "a" }), false);
  assert.equal(estCreateur({ moi: null, createur_id: null }), false);
  assert.equal(estCreateur(null), false);
});

// ---------------------------------------------------------------- comptes personnels

const MDP = "motdepasse-1";
const compter = (w, table) => w.DB.base.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
const compteDe = (w, membreId) => w.DB.base.prepare("SELECT compte_id FROM membres WHERE id = ?").get(membreId).compte_id;
const inscrire = (w, pseudo, mot_de_passe = MDP) => w.appel("POST", "/comptes/inscription", { corps: { pseudo, mot_de_passe } });
const connecter = (w, pseudo, mot_de_passe = MDP) => w.appel("POST", "/comptes/connexion", { corps: { pseudo, mot_de_passe } });
const moi = (w, jeton) => w.appel("GET", "/comptes/moi", { jeton });
const mettreFavoris = (w, jeton, favoris) => w.appel("PUT", "/comptes/favoris", { jeton, corps: { favoris } });
const rattacherA = (w, jeton, corps) => w.appel("POST", "/comptes/rattacher", { jeton, corps });
const creerAvec = (w, jeton, pseudo = "Ana", nom = "Les experts") => w.appel("POST", "/ligues", { jeton, corps: { nom, pseudo } });
const rejoindreAvec = (w, jeton, code, pseudo) => w.appel("POST", `/ligues/${code}/rejoindre`, { jeton, corps: pseudo === undefined ? {} : { pseudo } });
const clubsN = (n) => Array.from({ length: n }, (_, i) => `FRA:Club ${i + 1}`);

test("inscription : compte créé, mot de passe jamais enregistré en clair, empreinte salée différente pour chacun", async (t) => {
  const w = ligueMonde(t);
  const r = await inscrire(w, "  Maxime   B ");
  assert.equal(r.statut, 201);
  assert.deepEqual(Object.keys(r.json).sort(), ["compte_id", "favoris", "jeton_compte", "pseudo"]);
  assert.equal(r.json.pseudo, "Maxime B");
  assert.deepEqual(r.json.favoris, []);
  assert.match(r.json.jeton_compte, /^[0-9a-f]{64}$/);
  assert.equal(r.entetes.get("cache-control"), "no-store");
  await inscrire(w, "Zoé");
  const lignes = w.DB.base.prepare("SELECT * FROM comptes ORDER BY pseudo_cle").all();
  assert.deepEqual(lignes.map((l) => l.pseudo_cle), ["maxime b", "zoé"]);
  assert.equal(lignes[0].id, r.json.compte_id);
  assert.equal(lignes[0].favoris, "[]");
  assert.equal(lignes[0].cree_le, "2026-11-24T12:00:00.000Z");
  assert.equal(lignes[0].maj_le, lignes[0].cree_le);
  for (const l of lignes) {
    assert.match(l.sel, /^[0-9a-f]{32}$/);
    assert.match(l.mdp_hash, /^[0-9a-f]{64}$/);
    assert.ok(!JSON.stringify(l).includes(MDP), "mot de passe en clair");
  }
  assert.notEqual(lignes[0].sel, lignes[1].sel);
  assert.notEqual(lignes[0].mdp_hash, lignes[1].mdp_hash);   // même mot de passe, empreintes différentes
  const attendu = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${lignes[0].sel}:${MDP}`));
  assert.equal(lignes[0].mdp_hash, Buffer.from(attendu).toString("hex"));
  // la base ne garde que l'empreinte du jeton de session
  const sessions = w.DB.base.prepare("SELECT jeton_hash FROM sessions").all();
  assert.equal(sessions.length, 2);
  assert.ok(sessions.every((x) => x.jeton_hash !== r.json.jeton_compte));
});

test("inscription : pseudo de 2 à 24 caractères, mot de passe de 4 au moins, saisies refusées sans rien écrire", async (t) => {
  const w = ligueMonde(t);
  for (const [corps, code] of [
    [{ pseudo: "A", mot_de_passe: MDP }, "pseudo_invalide"],
    [{ pseudo: "x".repeat(25), mot_de_passe: MDP }, "pseudo_invalide"],
    [{ pseudo: "<img>", mot_de_passe: MDP }, "pseudo_invalide"],
    [{ mot_de_passe: MDP }, "pseudo_invalide"],
    [{ pseudo: "Ana", mot_de_passe: "abc" }, "mot_de_passe_invalide"],
    [{ pseudo: "Ana", mot_de_passe: "x".repeat(129) }, "mot_de_passe_invalide"],
    [{ pseudo: "Ana", mot_de_passe: 123456 }, "mot_de_passe_invalide"],
    [{ pseudo: "Ana" }, "mot_de_passe_invalide"],
  ]) {
    const r = await w.appel("POST", "/comptes/inscription", { corps });
    assert.deepEqual([r.statut, r.json.erreur.code], [400, code], JSON.stringify(corps).slice(0, 60));
  }
  assert.equal((await inscrire(w, "bot  ia")).statut, 409);
  assert.equal((await w.appel("POST", "/comptes/inscription", { brut: "{non" })).statut, 400);
  assert.equal(compter(w, "comptes"), 0);
  assert.equal(compter(w, "sessions"), 0);
  assert.equal((await inscrire(w, "x".repeat(24), "abcd")).statut, 201);
});

test("inscription : un pseudo déjà pris est refusé sans tenir compte de la casse", async (t) => {
  const w = ligueMonde(t);
  assert.equal((await inscrire(w, "Élodie")).statut, 201);
  for (const pseudo of ["élodie", "  ÉLODIE ", "Élodie"]) {
    const r = await inscrire(w, pseudo, "autre-mot-de-passe");
    assert.deepEqual([r.statut, r.json.erreur.code], [409, "pseudo_pris"], pseudo);
  }
  assert.equal(compter(w, "comptes"), 1);
  assert.equal(compter(w, "sessions"), 1);
});

test("connexion : bon mot de passe accepté ; mot de passe faux et pseudo inconnu donnent la même réponse", async (t) => {
  const w = ligueMonde(t);
  const a = (await inscrire(w, "Maxime", "motdepassé")).json;
  const ok = await connecter(w, "  MAXIME ", "motdepassé".normalize("NFD"));   // même mot de passe, saisi sur un autre clavier
  assert.equal(ok.statut, 200);
  assert.deepEqual(Object.keys(ok.json).sort(), ["compte_id", "favoris", "jeton_compte", "ligues", "pseudo"]);
  assert.deepEqual([ok.json.compte_id, ok.json.pseudo, ok.json.favoris, ok.json.ligues], [a.compte_id, "Maxime", [], []]);
  assert.notEqual(ok.json.jeton_compte, a.jeton_compte);
  // plusieurs appareils : les deux sessions restent ouvertes
  assert.equal((await moi(w, a.jeton_compte)).statut, 200);
  assert.equal((await moi(w, ok.json.jeton_compte)).statut, 200);
  const faux = await connecter(w, "Maxime", "pas-le-bon");
  const inconnu = await connecter(w, "Personne", "pas-le-bon");
  assert.equal(faux.statut, 401);
  assert.equal(faux.json.erreur.code, "identifiants_invalides");
  assert.deepEqual([inconnu.statut, inconnu.json], [faux.statut, faux.json]);
  assert.equal((await connecter(w, "Maxime", "Motdepassé")).statut, 401);
});

test("connexion : dix sessions au plus par compte, la plus ancienne est fermée", async (t) => {
  const w = ligueMonde(t);
  const premiere = (await inscrire(w, "Maxime")).json.jeton_compte;
  let derniere = null;
  for (let i = 0; i < 10; i++) {
    w.horloge.t += 1000;
    derniere = (await connecter(w, "Maxime")).json.jeton_compte;
  }
  assert.equal(compter(w, "sessions"), 10);
  assert.equal((await moi(w, premiere)).statut, 401);
  assert.equal((await moi(w, derniere)).statut, 200);
});

test("routes du compte : sans jeton ou avec un jeton inconnu, rien n'est lu ni écrit", async (t) => {
  const w = ligueMonde(t);
  await inscrire(w, "Maxime");
  for (const [methode, chemin] of [["GET", "/comptes/moi"], ["PUT", "/comptes/favoris"], ["POST", "/comptes/rattacher"],
    ["POST", "/comptes/detacher"], ["POST", "/comptes/deconnexion"]]) {
    const corps = methode === "GET" ? undefined : { favoris: ["FRA:Brest"], code: "ABC-123" };
    const sans = await w.appel(methode, chemin, { corps });
    assert.deepEqual([sans.statut, sans.json.erreur.code], [401, "jeton_manquant"], chemin);
    for (const jeton of ["abc", "0".repeat(64)]) {
      const r = await w.appel(methode, chemin, { corps, jeton });
      assert.deepEqual([r.statut, r.json.erreur.code], [401, "session_invalide"], `${chemin} ${jeton}`);
    }
  }
  assert.equal(w.DB.base.prepare("SELECT favoris FROM comptes").get().favoris, "[]");
});

test("favoris : enregistrés sur le compte, sans doublon, relus depuis un autre appareil", async (t) => {
  const w = ligueMonde(t);
  const { jeton_compte, compte_id } = (await inscrire(w, "Maxime")).json;
  w.horloge.t += heure;
  const r = await mettreFavoris(w, jeton_compte, ["FRA:Paris SG", "CZE:Viktoria Plzeň", "FRA:Paris SG"]);
  assert.equal(r.statut, 200);
  assert.deepEqual(r.json, { favoris: ["FRA:Paris SG", "CZE:Viktoria Plzeň"] });
  assert.equal(w.DB.base.prepare("SELECT maj_le FROM comptes").get().maj_le, "2026-11-24T13:00:00.000Z");
  assert.deepEqual((await moi(w, jeton_compte)).json,
    { compte_id, pseudo: "Maxime", favoris: ["FRA:Paris SG", "CZE:Viktoria Plzeň"], ligues: [] });
  assert.deepEqual((await connecter(w, "Maxime")).json.favoris, ["FRA:Paris SG", "CZE:Viktoria Plzeň"]);
  assert.deepEqual((await mettreFavoris(w, jeton_compte, [])).json, { favoris: [] });
});

test("favoris : vingt clubs au plus et seulement des identifiants de club", async (t) => {
  const w = ligueMonde(t);
  const { jeton_compte } = (await inscrire(w, "Maxime")).json;
  assert.equal((await mettreFavoris(w, jeton_compte, clubsN(20))).statut, 200);
  for (const favoris of [clubsN(21), "FRA:Brest", null, [42], ["Brest"], ["FRA:<script>"], [`FRA:${"x".repeat(80)}`], ["FRA:a\u0000b"]]) {
    const r = await mettreFavoris(w, jeton_compte, favoris);
    assert.deepEqual([r.statut, r.json.erreur.code], [400, "favoris_invalides"], JSON.stringify(favoris).slice(0, 50));
  }
  assert.deepEqual((await moi(w, jeton_compte)).json.favoris, clubsN(20));
});

test("déconnexion : seule la session utilisée est fermée", async (t) => {
  const w = ligueMonde(t);
  const a = (await inscrire(w, "Maxime")).json.jeton_compte;
  const b = (await connecter(w, "Maxime")).json.jeton_compte;
  const r = await w.appel("POST", "/comptes/deconnexion", { jeton: a, corps: {} });
  assert.deepEqual([r.statut, r.json], [200, { deconnecte: true }]);
  assert.equal((await moi(w, a)).statut, 401);
  assert.equal((await moi(w, b)).statut, 200);
});

test("créer et rejoindre avec un compte : le joueur est rattaché ; un second passage rend le joueur existant", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const ana = (await inscrire(w, "Ana")).json, ben = (await inscrire(w, "Ben")).json;
  const ligue = await creerAvec(w, ana.jeton_compte, "Ana la boss");
  assert.equal(ligue.statut, 201);
  assert.deepEqual(Object.keys(ligue.json).sort(), ["code", "competitions", "jeton", "membre_id"]);
  assert.equal(compteDe(w, ligue.json.membre_id), ana.compte_id);
  assert.equal(w.DB.base.prepare("SELECT compte_id FROM membres WHERE est_bot = 1").get().compte_id, null);

  const entree = await rejoindreAvec(w, ben.jeton_compte, ligue.json.code, "Benji");
  assert.equal(entree.statut, 201);
  assert.equal(compteDe(w, entree.json.membre_id), ben.compte_id);

  // depuis un autre appareil, avec ou sans pseudo, même différent : on retrouve son joueur, sans en créer
  const autreAppareil = (await connecter(w, "Ben")).json.jeton_compte;
  for (const pseudo of [undefined, "Un autre", "Ana la boss"]) {
    const r = await rejoindreAvec(w, autreAppareil, ligue.json.code, pseudo);
    assert.equal(r.statut, 200, String(pseudo));
    assert.deepEqual(r.json, { membre_id: entree.json.membre_id, jeton: autreAppareil, pseudo: "Benji", deja_membre: true });
  }
  assert.equal(compter(w, "membres"), 3);
});

test("rejoindre : deux demandes simultanées du même compte ne créent qu'un joueur", async (t) => {
  const w = ligueMonde(t);
  const { code } = await w.creer("Ana");
  const ben = (await inscrire(w, "Ben")).json;
  const reponses = await Promise.all(["Benji", "Benji"].map((p) => rejoindreAvec(w, ben.jeton_compte, code, p)));
  assert.deepEqual(reponses.map((r) => r.statut).sort(), [200, 201], reponses.map((r) => r.texte).join(" "));
  assert.equal(new Set(reponses.map((r) => r.json.membre_id)).size, 1);
  assert.equal(compter(w, "membres"), 3);
});

test("créer et rejoindre avec une session fermée : refusé, rien n'est écrit", async (t) => {
  const w = ligueMonde(t);
  const { code } = await w.creer("Ana");
  for (const jeton of ["abc", "0".repeat(64)]) {
    for (const r of [await creerAvec(w, jeton), await rejoindreAvec(w, jeton, code, "Ben")]) {
      assert.deepEqual([r.statut, r.json.erreur.code], [401, "session_invalide"]);
    }
  }
  assert.deepEqual([compter(w, "ligues"), compter(w, "membres")], [1, 2]);
});

test("le jeton du compte ouvre ses ligues rattachées, et seulement elles", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const ana = (await inscrire(w, "Ana")).json;
  const ligue = (await creerAvec(w, ana.jeton_compte)).json;
  const ailleurs = await w.creer("Zoé");
  const connexion = (await connecter(w, "Ana")).json;
  assert.deepEqual(connexion.ligues,
    [{ code: ligue.code, nom: "Les experts", membre_id: ligue.membre_id, pseudo: "Ana", jeton: connexion.jeton_compte }]);
  assert.deepEqual((await moi(w, connexion.jeton_compte)).json.ligues, connexion.ligues);

  assert.equal((await w.pronostiquer(ligue.code, connexion.jeton_compte, M1, 2, 1)).statut, 200);
  const vue = (await w.appel("GET", `/ligues/${ligue.code}`, { jeton: connexion.jeton_compte })).json;
  assert.equal(vue.moi, ligue.membre_id);
  assert.equal(prono(vue, "Ana", M1).buts_dom, 2);
  assert.ok(!/compte_id|jeton|hash/.test(JSON.stringify(vue)), "identifiant de compte ou secret dans la réponse");
  // le jeton de joueur remis à la création reste valable
  assert.equal((await w.pronostiquer(ligue.code, ligue.jeton, M1, 3, 1)).statut, 200);
  assert.equal((await w.pronostiquer(ailleurs.code, connexion.jeton_compte, M1, 1, 0)).statut, 401);
  assert.equal((await w.appel("DELETE", `/ligues/${ligue.code}`, { jeton: connexion.jeton_compte })).statut, 200);
  assert.deepEqual((await moi(w, ana.jeton_compte)).json.ligues, []);
});

test("rattacher : les ligues du navigateur et les favoris locaux rejoignent le compte, les jetons de joueur restent valables", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const l1 = await w.creer("Max au bureau"), l2 = await w.creer("Zoé");
  const entree = await w.rejoindre(l2.code, "Max");
  const compte = (await inscrire(w, "Maxime")).json;
  await mettreFavoris(w, compte.jeton_compte, ["FRA:Brest"]);
  const corps = { ligues: [{ code: l1.code, jeton: l1.jeton }, { code: l2.code.toLowerCase(), jeton: entree.jeton }],
    favoris: ["ENG:Arsenal", "FRA:Brest", "pas un club"] };
  for (let passage = 0; passage < 2; passage++) {          // rejouable sans effet de bord
    const r = await rattacherA(w, compte.jeton_compte, corps);
    assert.equal(r.statut, 200, r.texte);
    assert.deepEqual(r.json.favoris, ["FRA:Brest", "ENG:Arsenal"]);
    assert.deepEqual(r.json.rattachees.sort(), [l1.code, l2.code].sort());
    assert.deepEqual(r.json.ligues.map((l) => [l.code, l.membre_id, l.jeton]).sort(),
      [[l1.code, l1.membre_id, compte.jeton_compte], [l2.code, entree.membre_id, compte.jeton_compte]].sort());
  }
  assert.equal(compteDe(w, l1.membre_id), compte.compte_id);
  assert.equal(compteDe(w, entree.membre_id), compte.compte_id);
  assert.equal(compteDe(w, l2.membre_id), null);           // la créatrice de la seconde ligue n'est pas concernée
  assert.equal((await w.pronostiquer(l1.code, l1.jeton, M1, 1, 0)).statut, 200);
});

test("rattacher : jeton faux, joueur d'un autre compte, second joueur dans la même ligue et Bot IA sont ignorés", async (t) => {
  const w = ligueMonde(t);
  const l1 = await w.creer("Ana"), second = await w.rejoindre(l1.code, "Ana bis");
  const ana = (await inscrire(w, "Ana")).json, ben = (await inscrire(w, "Ben")).json;
  const essai = async (jeton, ligues) => (await rattacherA(w, jeton, { ligues })).json;
  assert.deepEqual((await essai(ana.jeton_compte, [{ code: l1.code, jeton: "0".repeat(64) }])).rattachees, []);
  assert.deepEqual((await essai(ana.jeton_compte, [{ code: l1.code, jeton: "" }, { code: "nimporte", jeton: l1.jeton }, null, 3])).rattachees, []);
  assert.deepEqual((await essai(ana.jeton_compte, [{ code: l1.code, jeton: l1.jeton }])).rattachees, [l1.code]);
  assert.deepEqual((await essai(ben.jeton_compte, [{ code: l1.code, jeton: l1.jeton }])).rattachees, []);   // déjà à Ana
  assert.deepEqual((await essai(ana.jeton_compte, [{ code: l1.code, jeton: second.jeton }])).rattachees, []);   // un joueur par ligue
  assert.equal(compteDe(w, l1.membre_id), ana.compte_id);
  assert.equal(compteDe(w, second.membre_id), null);
  assert.equal(compter(w, "membres"), 3);
});

test("rattacher : saisies bornées, favoris coupés à vingt, ceux du compte d'abord", async (t) => {
  const w = ligueMonde(t);
  const { jeton_compte } = (await inscrire(w, "Ana")).json;
  await mettreFavoris(w, jeton_compte, ["ENG:Arsenal"]);
  const r = await rattacherA(w, jeton_compte, { favoris: clubsN(100) });
  assert.equal(r.statut, 200, r.texte);
  assert.deepEqual(r.json.favoris, ["ENG:Arsenal", ...clubsN(19)]);
  assert.equal((await rattacherA(w, jeton_compte, {})).statut, 200);
  for (const corps of [{ ligues: "ABC-123" }, { favoris: {} }, { ligues: Array(21).fill({ code: "ABC-123", jeton: "x" }) }, { favoris: clubsN(101) }]) {
    assert.equal((await rattacherA(w, jeton_compte, corps)).statut, 400, JSON.stringify(corps).slice(0, 40));
  }
  assert.equal((await rattacherA(w, jeton_compte, { bourrage: "x".repeat(20000) })).statut, 413);
});

test("détacher : la ligue quitte le compte, le joueur reste dans la ligue", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const { jeton_compte } = (await inscrire(w, "Ana")).json;
  const ligue = (await creerAvec(w, jeton_compte)).json;
  const r = await w.appel("POST", "/comptes/detacher", { jeton: jeton_compte, corps: { code: ligue.code.toLowerCase() } });
  assert.deepEqual([r.statut, r.json], [200, { code: ligue.code, detachee: true }]);
  assert.deepEqual((await moi(w, jeton_compte)).json.ligues, []);
  assert.equal(compteDe(w, ligue.membre_id), null);
  assert.equal((await w.appel("GET", `/ligues/${ligue.code}`, { jeton: jeton_compte })).statut, 401);
  assert.equal((await w.appel("GET", `/ligues/${ligue.code}`, { jeton: ligue.jeton })).statut, 200);
  assert.equal((await w.appel("POST", "/comptes/detacher", { jeton: jeton_compte, corps: {} })).statut, 400);
});

test("sans compte : créer, rejoindre et pronostiquer répondent comme avant", async (t) => {
  const w = await ligueADeux(t);
  assert.deepEqual(Object.keys(w.ana).sort(), ["code", "competitions", "jeton", "membre_id"]);
  assert.deepEqual(Object.keys(w.ben).sort(), ["jeton", "membre_id"]);
  assert.equal((await w.pronostiquer(w.code, w.ben.jeton, M1, 1, 1)).statut, 200);
  assert.deepEqual(w.DB.base.prepare("SELECT DISTINCT compte_id FROM membres").all().map((l) => l.compte_id), [null]);
  assert.deepEqual([compter(w, "comptes"), compter(w, "sessions")], [0, 0]);
});

test("routes des comptes : chemins et méthodes non prévus, base absente", async (t) => {
  const w = ligueMonde(t);
  for (const chemin of ["/comptes", "/comptes/autre", "/comptes/constructor", "/comptes/moi/x"]) {
    assert.equal((await w.appel("GET", chemin)).statut, 404, chemin);
  }
  assert.equal((await w.appel("GET", "/comptes/connexion")).statut, 405);
  assert.equal((await w.appel("POST", "/comptes/moi", { corps: {} })).statut, 405);
  assert.equal((await w.appel("POST", "/comptes/favoris", { corps: {} })).statut, 405);
  delete w.env.DB;
  const r = await w.appel("GET", "/comptes/moi");
  assert.deepEqual([r.statut, r.json.erreur.code], [503, "comptes_indisponibles"]);
});

test("migration : une base en ligne reçoit compte_id et son index sans perdre de joueur", () => {
  const base = new DatabaseSync(":memory:");
  base.exec(`CREATE TABLE ligues (code TEXT PRIMARY KEY, nom TEXT NOT NULL, cree_le TEXT NOT NULL, competitions TEXT, createur_id TEXT);
    CREATE TABLE membres (id TEXT PRIMARY KEY, ligue_code TEXT NOT NULL, pseudo TEXT NOT NULL, pseudo_cle TEXT NOT NULL,
      jeton_hash TEXT NOT NULL, est_bot INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL, UNIQUE (ligue_code, pseudo_cle));
    INSERT INTO ligues VALUES ('ABC-123', 'Ancienne', '2026-11-20T10:00:00.000Z', NULL, 'a');
    INSERT INTO membres VALUES ('a', 'ABC-123', 'Ana', 'ana', 'h1', 0, '2026-11-20T10:00:00.000Z');`);
  for (let deploiement = 0; deploiement < 2; deploiement++) {   // même ordre que relais.yml : schéma, puis migrations
    base.exec(SCHEMA);
    migrer(base);
  }
  assert.deepEqual({ ...base.prepare("SELECT pseudo, compte_id FROM membres").get() }, { pseudo: "Ana", compte_id: null });
  assert.equal(base.prepare("SELECT COUNT(*) AS n FROM comptes").get().n, 0);
  base.exec("UPDATE membres SET compte_id = 'c1'");
  assert.throws(() => base.exec("INSERT INTO membres VALUES ('b', 'ABC-123', 'Ben', 'ben', 'h2', 0, 'x', 'c1')"), /UNIQUE/);
});

// ---------------------------------------------------------------- compte côté navigateur (site/assets/compte.js)

import Compte from "../site/assets/compte.js";
import { CLE_STOCKAGE, memeEntree } from "../site/assets/ligues.js";

function fauxFavoris(initial = []) {
  let liste = [...initial];
  return {
    liste: () => [...liste],
    remplacer: (neuve) => { liste = [...neuve]; },
    basculer(club) { liste = liste.includes(club) ? liste.filter((k) => k !== club) : [club, ...liste]; },
  };
}

/* un navigateur : son stockage, ses favoris, et le vrai Worker au bout du réseau */
function appareil(w, { favoris = [] } = {}) {
  const stockage = memStorage(), fav = fauxFavoris(favoris), signaux = [], appels = [];
  const reseau = { coupe: false, panne: null, pendant: null };
  const requete = async (url, init) => {
    assert.ok(url.startsWith(Compte.API), url);
    const chemin = url.slice(Compte.API.length);
    appels.push(`${init.method} ${chemin}`);
    if (reseau.coupe || reseau.panne === chemin) throw new TypeError("réseau coupé");
    const r = await relais.fetch(new Request(`https://relais.test/comptes${chemin}`, init), w.env);
    if (reseau.pendant) { const action = reseau.pendant; reseau.pendant = null; await action(); }
    return r;
  };
  const client = Compte.creerClientCompte({ stockage, requete, favoris: fav, signaler: (s) => signaux.push(s) });
  const ligues = () => chargerStockage(stockage).ligues;
  const toucher = (club) => { fav.basculer(club); return client.favorisModifies(); };
  return { stockage, fav, client, signaux, appels, reseau, ligues, toucher };
}
const surLeCompte = (w) => JSON.parse(w.DB.base.prepare("SELECT favoris FROM comptes").get().favoris);

/* A joue sans compte : une ligue créée dans ce navigateur et un favori */
async function appareilAvecLigue(w) {
  const A = appareil(w, { favoris: ["FRA:Brest"] });
  const ligue = await w.creer("Max");
  enregistrerLigue(A.stockage, { code: ligue.code, nom: "Les experts", membre_id: ligue.membre_id, jeton: ligue.jeton, pseudo: "Max" });
  return { A, ligue };
}

test("compte navigateur : une réponse de ligue n'est gardée que si la même ligue est ouverte avec le même jeton", () => {
  const demandee = { code: "ABC-123", jeton: "j1" };
  assert.equal(memeEntree(demandee, { code: "ABC-123", jeton: "j1", nom: "Bureau" }), true);
  assert.equal(memeEntree(demandee, null), false);                              // déconnexion pendant la requête
  assert.equal(memeEntree(demandee, { code: "ABC-123", jeton: "j2" }), false);   // autre session
  assert.equal(memeEntree(demandee, { code: "ZZZ-999", jeton: "j1" }), false);   // autre ligue choisie
});

test("compte navigateur : mêmes clés que les ligues, et une ligue gardée retient son compte", () => {
  assert.equal(Compte.CLE_LIGUES, CLE_STOCKAGE);
  assert.equal(Compte.MAX_FAVORIS, 20);
  const st = memStorage();
  enregistrerLigue(st, { code: "ABC-123", membre_id: "m1", jeton: "j1", pseudo: "Max", compte: "c1" });
  enregistrerLigue(st, { ...chargerStockage(st).ligues[0], nom: "Bureau" });
  assert.equal(chargerStockage(st).ligues[0].compte, "c1");
});

test("compte navigateur : créé sur un appareil, favoris et ligues retrouvés sur un autre", async (t) => {
  const w = ligueMonde(t);
  await w.publierProgramme();
  const { A, ligue } = await appareilAvecLigue(w);
  await A.client.inscrire("Maxime", MDP);
  assert.equal(A.client.lire().pseudo, "Maxime");
  assert.deepEqual(surLeCompte(w), ["FRA:Brest"]);
  assert.deepEqual(A.ligues().map((l) => [l.code, l.membre_id, l.compte]), [[ligue.code, ligue.membre_id, A.client.lire().compte_id]]);

  const B = appareil(w, { favoris: ["ENG:Arsenal"] });
  await B.client.connecter("maxime", MDP);
  assert.deepEqual(B.fav.liste(), ["FRA:Brest", "ENG:Arsenal"]);
  assert.deepEqual(B.ligues().map((l) => [l.code, l.nom, l.pseudo]), [[ligue.code, "Les experts", "Max"]]);
  assert.equal(chargerStockage(B.stockage).active, ligue.code);
  assert.equal((await w.pronostiquer(ligue.code, B.ligues()[0].jeton, M1, 2, 0)).statut, 200);

  await B.toucher("FRA:Brest");
  await A.client.synchroniser();
  assert.deepEqual(A.fav.liste(), ["ENG:Arsenal"]);
  assert.ok(B.signaux.includes("compte") && B.signaux.includes("ligues"));
});

test("compte navigateur : une ligue quittée ailleurs disparaît à la synchronisation, sans rechargement inutile ensuite", async (t) => {
  const w = ligueMonde(t);
  const { A, ligue } = await appareilAvecLigue(w);
  await A.client.inscrire("Maxime", MDP);
  const B = appareil(w);
  await B.client.connecter("Maxime", MDP);
  await B.client.detacher(ligue.code);
  await A.client.synchroniser();
  assert.deepEqual(A.ligues(), []);
  A.signaux.length = 0;
  await A.client.synchroniser();
  assert.ok(!A.signaux.includes("ligues"), "rien n'a changé : la page des ligues n'est pas rechargée");
});

test("compte navigateur : la déconnexion ne laisse rien du compte et laisse l'autre appareil connecté", async (t) => {
  const w = ligueMonde(t);
  const { A, ligue } = await appareilAvecLigue(w);
  await A.client.inscrire("Maxime", MDP);
  const B = appareil(w);
  await B.client.connecter("Maxime", MDP);
  const jetonB = B.client.lire().jeton;
  await B.client.deconnecter();
  assert.equal(B.client.lire(), null);
  assert.deepEqual([B.fav.liste(), B.ligues()], [[], []]);
  assert.equal((await moi(w, jetonB)).statut, 401);
  await A.client.synchroniser();
  assert.deepEqual(A.ligues().map((l) => l.code), [ligue.code]);
  assert.deepEqual(surLeCompte(w), ["FRA:Brest"]);
});

test("compte navigateur : hors ligne, un favori attend puis part à la synchronisation suivante", async (t) => {
  const w = ligueMonde(t);
  const A = appareil(w);
  await A.client.inscrire("Maxime", MDP);
  A.reseau.coupe = true;
  await A.toucher("FRA:Lens");
  await A.client.synchroniser();
  assert.deepEqual([A.fav.liste(), surLeCompte(w)], [["FRA:Lens"], []]);
  A.reseau.coupe = false;
  await A.client.synchroniser();
  assert.deepEqual([A.fav.liste(), surLeCompte(w)], [["FRA:Lens"], ["FRA:Lens"]]);
});

test("compte navigateur : déconnecté hors ligne, les favoris jamais envoyés restent dans le navigateur", async (t) => {
  const w = ligueMonde(t);
  const A = appareil(w);
  await A.client.inscrire("Maxime", MDP);
  A.reseau.coupe = true;
  await A.toucher("FRA:Lens");
  await A.client.deconnecter();
  assert.deepEqual([A.client.lire(), A.fav.liste()], [null, ["FRA:Lens"]]);
});

test("compte navigateur : un favori touché pendant une synchronisation n'est pas écrasé par la réponse plus ancienne", async (t) => {
  const w = ligueMonde(t);
  const A = appareil(w, { favoris: ["FRA:Brest"] });
  await A.client.inscrire("Maxime", MDP);
  let envoi;
  A.reseau.pendant = () => { envoi = A.toucher("FRA:Lens"); };
  await A.client.synchroniser();
  await envoi;
  assert.deepEqual(A.fav.liste(), ["FRA:Lens", "FRA:Brest"]);
  assert.deepEqual(surLeCompte(w), ["FRA:Lens", "FRA:Brest"]);
});

test("compte navigateur : un rattachement interrompu est repris, sans perdre les favoris locaux", async (t) => {
  const w = ligueMonde(t);
  const { A, ligue } = await appareilAvecLigue(w);
  A.reseau.panne = "/rattacher";
  await A.client.inscrire("Maxime", MDP);
  assert.equal(A.client.lire().pseudo, "Maxime");
  assert.deepEqual([A.fav.liste(), surLeCompte(w), compteDe(w, ligue.membre_id)], [["FRA:Brest"], [], null]);
  await A.toucher("FRA:Lens");                               // pas d'envoi qui écraserait le compte avant la fusion
  assert.ok(!A.appels.includes("PUT /favoris"));
  A.reseau.panne = null;
  await A.client.synchroniser();
  assert.deepEqual(surLeCompte(w), ["FRA:Lens", "FRA:Brest"]);
  assert.equal(compteDe(w, ligue.membre_id), A.client.lire().compte_id);
});

test("compte navigateur : plus de vingt ligues locales rattachées en plusieurs demandes, favoris coupés signalés", async (t) => {
  const w = ligueMonde(t);
  const A = appareil(w, { favoris: clubsN(25) });
  for (let i = 0; i < 23; i++) {
    const l = await w.creer(`Joueur ${i}`);
    enregistrerLigue(A.stockage, { code: l.code, nom: l.code, membre_id: l.membre_id, jeton: l.jeton, pseudo: `Joueur ${i}` });
  }
  await A.client.inscrire("Maxime", MDP);
  assert.equal(A.appels.filter((a) => a === "POST /rattacher").length, 2);
  assert.equal(A.ligues().filter((l) => l.compte).length, 23);
  assert.deepEqual(A.fav.liste(), clubsN(20));
  assert.ok(A.signaux.includes("favoris_coupes"));
});

test("compte navigateur : session fermée côté serveur, retour sans compte en gardant les favoris", async (t) => {
  const w = ligueMonde(t);
  const { A } = await appareilAvecLigue(w);
  await A.client.inscrire("Maxime", MDP);
  w.DB.base.exec("DELETE FROM sessions");
  await A.client.synchroniser();
  assert.deepEqual([A.client.lire(), A.fav.liste(), A.ligues()], [null, ["FRA:Brest"], []]);
  assert.ok(A.signaux.includes("session_expiree"));
});

test("compte navigateur : erreurs de connexion rendues avec leur message, rien n'est gardé", async (t) => {
  const w = ligueMonde(t);
  const A = appareil(w);
  await assert.rejects(A.client.connecter("Personne", MDP), /Pseudo ou mot de passe incorrect/);
  A.reseau.coupe = true;
  await assert.rejects(A.client.inscrire("Maxime", MDP), /Connexion impossible/);
  assert.equal(A.client.lire(), null);
});

test("compte navigateur : sans compte, aucune requête ne part", async (t) => {
  const w = ligueMonde(t);
  const { A, ligue } = await appareilAvecLigue(w);
  await A.toucher("FRA:Lens");
  await A.client.synchroniser();
  await A.client.deconnecter();
  assert.deepEqual(A.appels, []);
  assert.deepEqual([A.fav.liste(), A.ligues().map((l) => l.code)], [["FRA:Lens", "FRA:Brest"], [ligue.code]]);
});

test("compte navigateur : un autre joueur de ce navigateur dans la même ligue est mis de côté puis rendu", () => {
  const local = { active: "ABC-123", ligues: [
    { code: "ABC-123", nom: "Bureau", membre_id: "anonyme", jeton: "j-anonyme", pseudo: "Invité" },
    { code: "ZZZ-999", nom: "Famille", membre_id: "x", jeton: "j-x", pseudo: "X" },
  ] };
  const duCompte = [{ code: "ABC-123", nom: "Bureau", membre_id: "moi", pseudo: "Max", jeton: "session" }];
  const connecte = Compte.fusionnerLigues(local, duCompte, "c1");
  assert.deepEqual(connecte.ligues.map((l) => [l.code, l.membre_id, l.jeton, l.compte ?? null]),
    [["ABC-123", "moi", "session", "c1"], ["ZZZ-999", "x", "j-x", null]]);
  assert.deepEqual(Compte.fusionnerLigues(connecte, duCompte, "c1"), connecte);
  assert.deepEqual(Compte.retirerLiguesDuCompte(connecte, "c1"), local);
});
