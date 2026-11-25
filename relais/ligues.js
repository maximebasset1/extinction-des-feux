/* API des ligues de pronostics et des comptes (routes /ligues et /comptes du Worker, contrat dans relais/README.md).
   Données : base D1 `DB` (schema.sql) et programme des matchs dans KV (programme.js). Aucune route n'appelle
   API-Football ni n'écrit dans KV : le direct et son quota ne dépendent pas des ligues.
   Le compte est facultatif. Sans lui, le code de la ligue ouvre la consultation et l'inscription, et le jeton remis à
   l'inscription (gardé par le navigateur) identifie un joueur. Avec lui, le jeton de compte ouvre en plus tous les
   joueurs rattachés au compte, sur chaque appareil connecté. */
import { calculerPoints } from "./points.js";
import { CLE_PROGRAMME, FICHIERS, competition, trouver } from "./programme.js";

const MAX_JOUEURS = 30;                    // par ligue, Bot IA non compris
const CORPS_MAX = 2048;
const BUTS_MAX = 20;
const PROGRAMME_MAX_MS = 48 * 3600000;     // au-delà, les heures de coup d'envoi ne sont plus assez sûres pour verrouiller
const BOT = "Bot IA";
const LETTRES = "ABCDEFGHJKLMNPQRSTUVWXYZ";   // sans I ni O, qu'on confond avec 1 et 0
const FORMAT_CODE = /^[A-Z]{3}-\d{3}$/;
const PSEUDO = { champ: "pseudo", min: 2, max: 20, permis: /^[\p{L}\p{M}\p{N} ._'’-]+$/u };
const NOM = { champ: "nom", min: 3, max: 40, permis: /^[\p{L}\p{M}\p{N} ._'’!?&(),:+-]+$/u };
const PSEUDO_COMPTE = { ...PSEUDO, max: 24 };
const MDP_MIN = 4, MDP_MAX = 128;
const FAVORIS_MAX = 20;                    // par compte
const FAVORIS_LOCAUX_MAX = 100;            // ce qu'un navigateur peut apporter au rattachement (favoris.js)
const FORMAT_CLUB = /^[A-Z]{2,4}:[^\p{C}<>]{1,60}$/u;      // identifiant de club du site : « FRA:Paris SG »
const SESSIONS_MAX = 10;                   // appareils connectés par compte
const ESSAIS_MAX = 5;                      // mots de passe examinés par pseudo et par période
const ESSAIS_PERIODE_MS = 15 * 60000;
const RATTACHER_MAX = 20;                  // ligues par requête : une écriture chacune, D1 limite les requêtes par appel
const CORPS_RATTACHER_MAX = 16384;
const CORPS_FAVORIS_MAX = 4096;
const TOUTES_COMPETITIONS = Object.keys(FICHIERS);
const ALIAS_COMPETITIONS = { PL: "E0", BL1: "D1", PD: "SP1", SA: "I1", FL1: "F1", CL: "LDC", EL: "LEC" };

const ENTETES = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "cache-control": "no-store",             // la réponse dépend du jeton et de l'heure : jamais de cache
  vary: "authorization",
  "x-content-type-options": "nosniff",
};
const PREVOL = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS",
  "access-control-allow-headers": "authorization, content-type",
  "access-control-max-age": "86400",
};

class Refus extends Error {
  constructor(statut, code, message) {
    super(message);
    Object.assign(this, { statut, code });
  }
}
const repondre = (corps, statut = 200) => new Response(JSON.stringify(corps), { status: statut, headers: ENTETES });
const maintenantIso = () => new Date(Date.now()).toISOString();
const hexa = (octets) => [...new Uint8Array(octets)].map((o) => o.toString(16).padStart(2, "0")).join("");
const hacher = async (jeton) => hexa(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(jeton)));
const dejaPris = (error, colonne) => /UNIQUE constraint failed/.test(error.message) && error.message.includes(colonne);

function tirerCode() {
  const o = crypto.getRandomValues(new Uint8Array(6));
  return `${[0, 1, 2].map((i) => LETTRES[o[i] % LETTRES.length]).join("")}-${[3, 4, 5].map((i) => o[i] % 10).join("")}`;
}

async function nouveauJoueur() {
  const jeton = hexa(crypto.getRandomValues(new Uint8Array(32)));
  return { id: crypto.randomUUID(), jeton, hash: await hacher(jeton) };
}

// ---------------------------------------------------------------- saisies

async function lireCorps(req, max = CORPS_MAX) {
  const texte = await req.text();
  if (texte.length > max) throw new Refus(413, "corps_trop_long", "Requête trop longue.");
  let corps = null;
  try { corps = JSON.parse(texte); } catch { /* refusé juste après */ }
  if (!corps || typeof corps !== "object" || Array.isArray(corps)) {
    throw new Refus(400, "corps_invalide", "Le corps de la requête doit être un objet JSON.");
  }
  return corps;
}

/* texte saisi : forme Unicode unique, espaces réduits, caractères permis seulement (ni balises ni caractères invisibles) */
function saisie(valeur, { champ, min, max, permis }) {
  const texte = typeof valeur === "string" ? valeur.normalize("NFKC").replace(/\s+/g, " ").trim() : "";
  const longueur = [...texte].length;
  if (longueur < min || longueur > max || !permis.test(texte) || !/[\p{L}\p{N}]/u.test(texte)) {
    throw new Refus(400, `${champ}_invalide`, `Le champ « ${champ} » doit faire de ${min} à ${max} caractères (lettres, chiffres et ponctuation simple).`);
  }
  return texte;
}
const clePseudo = (pseudo) => pseudo.toLocaleLowerCase("fr");
const pseudoPris = () => new Refus(409, "pseudo_pris", "Ce pseudo est déjà pris dans cette ligue.");

/* compétitions d'une ligue : absent/null = toutes (rétrocompatibilité), sinon tableau non vide de codes connus */
function normaliserCompetitions(valeur) {
  if (valeur === undefined || valeur === null) return { colonne: null, liste: [...TOUTES_COMPETITIONS] };
  if (!Array.isArray(valeur) || !valeur.length) {
    throw new Refus(400, "competitions_invalides", "Choisis au moins une compétition valide.");
  }
  const set = new Set();
  for (const brut of valeur) {
    if (typeof brut !== "string") throw new Refus(400, "competitions_invalides", "Compétition invalide.");
    const c = brut.trim().toUpperCase();
    const code = ALIAS_COMPETITIONS[c] ?? c;
    if (!Object.hasOwn(FICHIERS, code)) {
      throw new Refus(400, "competitions_invalides", `Compétition inconnue : « ${brut} ».`);
    }
    set.add(code);
  }
  const liste = TOUTES_COMPETITIONS.filter((c) => set.has(c));
  return { colonne: liste.length === TOUTES_COMPETITIONS.length ? null : JSON.stringify(liste), liste };
}

function competitionsLigue(colonne) {
  if (!colonne) return [...TOUTES_COMPETITIONS];
  try {
    const brut = JSON.parse(colonne);
    if (!Array.isArray(brut) || !brut.length) return [...TOUTES_COMPETITIONS];
    const set = new Set(brut.map((c) => ALIAS_COMPETITIONS[c] ?? c).filter((c) => Object.hasOwn(FICHIERS, c)));
    const liste = TOUTES_COMPETITIONS.filter((c) => set.has(c));
    return liste.length ? liste : [...TOUTES_COMPETITIONS];
  } catch {
    return [...TOUTES_COMPETITIONS];
  }
}

// ---------------------------------------------------------------- accès

async function lireLigue(env, code) {
  const ligue = FORMAT_CODE.test(code)
    ? await env.DB.prepare("SELECT code, nom, cree_le, competitions, createur_id FROM ligues WHERE code = ?").bind(code).first()
    : null;
  if (!ligue) throw new Refus(404, "ligue_inconnue", "Aucune ligue ne porte ce code.");
  return ligue;
}

const jetonDe = (entete) => /^Bearer ([0-9a-f]{64})$/.exec(entete)?.[1];

/* le joueur du jeton « Authorization: Bearer ... » dans cette ligue ; null sans en-tête, refus si le jeton ne correspond pas.
   Deux jetons conviennent : celui remis au joueur, ou celui d'une session du compte auquel ce joueur est rattaché */
async function lireJoueur(req, env, code) {
  const entete = req.headers.get("authorization");
  if (!entete) return null;
  const jeton = jetonDe(entete);
  const hash = jeton && await hacher(jeton);
  const joueur = hash && await env.DB.prepare(`SELECT id FROM membres WHERE ligue_code = ? AND est_bot = 0
    AND (jeton_hash = ? OR compte_id = (SELECT compte_id FROM sessions WHERE jeton_hash = ?))`).bind(code, hash, hash).first();
  if (!joueur) throw new Refus(401, "jeton_invalide", "Jeton refusé pour cette ligue.");
  return joueur;
}

/* le compte de la session « Authorization: Bearer <jeton de compte> » ; null sans en-tête, refus si la session est inconnue */
async function lireCompte(req, env) {
  const entete = req.headers.get("authorization");
  if (!entete) return null;
  const jeton = jetonDe(entete);
  const hash = jeton && await hacher(jeton);
  const compte = hash && await env.DB.prepare(`SELECT c.id, c.pseudo, c.favoris FROM sessions s JOIN comptes c ON c.id = s.compte_id
    WHERE s.jeton_hash = ?`).bind(hash).first();
  if (!compte) throw new Refus(401, "session_invalide", "Session expirée : reconnecte-toi.");
  return { ...compte, jeton, hash };
}

async function exigerCompte(req, env) {
  const compte = await lireCompte(req, env);
  if (!compte) throw new Refus(401, "jeton_manquant", "En-tête « Authorization: Bearer <jeton> » manquant.");
  return compte;
}

const membreDuCompte = (env, code, compteId) => env.DB
  .prepare("SELECT id, pseudo FROM membres WHERE ligue_code = ? AND compte_id = ?").bind(code, compteId).first();

async function lireProgramme(env) {
  const programme = await env.DIRECT.get(CLE_PROGRAMME, { type: "json", cacheTtl: 60 });
  if (!programme?.matchs) throw new Refus(503, "programme_indisponible", "Le programme des matchs n'est pas disponible. Réessaie plus tard.");
  return programme;
}

// ---------------------------------------------------------------- routes

async function creer(req, env) {
  const compte = await lireCompte(req, env);
  const corps = await lireCorps(req);
  const nom = saisie(corps.nom, NOM), pseudo = saisie(corps.pseudo, PSEUDO);
  const { colonne, liste: competitions } = normaliserCompetitions(corps.competitions);
  if (clePseudo(pseudo) === clePseudo(BOT)) throw pseudoPris();
  const joueur = await nouveauJoueur(), quand = maintenantIso();
  const membre = (code, id, p, hash, bot, compteId) => env.DB
    .prepare("INSERT INTO membres (id, ligue_code, pseudo, pseudo_cle, jeton_hash, est_bot, cree_le, compte_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(id, code, p, clePseudo(p), hash, bot, quand, compteId);
  for (let essai = 1; essai <= 5; essai++) {
    const code = tirerCode();
    try {
      await env.DB.batch([                 // une transaction : jamais de ligue sans son créateur ni son Bot IA
        env.DB.prepare("INSERT INTO ligues (code, nom, cree_le, competitions, createur_id) VALUES (?, ?, ?, ?, ?)")
          .bind(code, nom, quand, colonne, joueur.id),
        membre(code, joueur.id, pseudo, joueur.hash, 0, compte?.id ?? null),
        membre(code, crypto.randomUUID(), BOT, "", 1, null),
      ]);
      return repondre({ code, membre_id: joueur.id, jeton: joueur.jeton, competitions }, 201);
    } catch (error) {
      if (!dejaPris(error, "ligues.code")) throw error;
    }
  }
  throw new Error("aucun code de ligue libre après 5 tirages");
}

/* le compte est déjà dans la ligue : on lui rend son joueur, que son jeton de compte ouvre déjà */
const dejaMembre = (membre, compte) => repondre({ membre_id: membre.id, jeton: compte.jeton, pseudo: membre.pseudo, deja_membre: true });

async function rejoindre(req, env, code) {
  await lireLigue(env, code);
  const compte = await lireCompte(req, env);
  const present = compte && await membreDuCompte(env, code, compte.id);
  if (present) return dejaMembre(present, compte);
  const pseudo = saisie((await lireCorps(req)).pseudo, PSEUDO);
  const joueur = await nouveauJoueur();
  let resultat;
  try {
    // le compte des places fait partie de l'insertion : deux inscriptions simultanées ne peuvent pas dépasser la limite
    resultat = await env.DB.prepare(`INSERT INTO membres (id, ligue_code, pseudo, pseudo_cle, jeton_hash, est_bot, cree_le, compte_id)
      SELECT ?, ?, ?, ?, ?, 0, ?, ? WHERE (SELECT COUNT(*) FROM membres WHERE ligue_code = ? AND est_bot = 0) < ?`)
      .bind(joueur.id, code, pseudo, clePseudo(pseudo), joueur.hash, maintenantIso(), compte?.id ?? null, code, MAX_JOUEURS).run();
  } catch (error) {
    // deux demandes simultanées du même compte : la seconde retrouve le joueur créé par la première
    const entretemps = compte && await membreDuCompte(env, code, compte.id);
    if (entretemps) return dejaMembre(entretemps, compte);
    if (dejaPris(error, "pseudo_cle")) throw pseudoPris();
    throw error;
  }
  if (!resultat.meta.changes) throw new Refus(409, "ligue_complete", `Cette ligue a déjà ${MAX_JOUEURS} joueurs.`);
  return repondre({ membre_id: joueur.id, jeton: joueur.jeton }, 201);
}

async function pronostiquer(req, env, code) {
  const ligue = await lireLigue(env, code);
  const joueur = await lireJoueur(req, env, code);
  if (!joueur) throw new Refus(401, "jeton_manquant", "En-tête « Authorization: Bearer <jeton> » manquant.");
  const { match_id: id, buts_dom: dom, buts_ext: ext } = await lireCorps(req);
  if (typeof id !== "string" || !id || id.length > 160) throw new Refus(400, "match_invalide", "Le champ « match_id » est invalide.");
  if (![dom, ext].every((b) => Number.isInteger(b) && b >= 0 && b <= BUTS_MAX)) {
    throw new Refus(400, "score_invalide", `« buts_dom » et « buts_ext » doivent être des entiers de 0 à ${BUTS_MAX}.`);
  }
  const programme = await lireProgramme(env);
  if (Date.now() - programme.maj_ms > PROGRAMME_MAX_MS) {
    throw new Refus(503, "programme_indisponible", "Le programme des matchs n'est plus à jour : les pronostics sont suspendus.");
  }
  if (!Object.hasOwn(programme.matchs, id)) throw new Refus(404, "match_inconnu", "Ce match ne figure pas au programme.");
  if (!competitionsLigue(ligue.competitions).includes(competition(id))) {
    throw new Refus(400, "competition_non_autorisee", "Cette compétition ne fait pas partie de cette ligue.");
  }
  const match = programme.matchs[id];
  const quand = maintenantIso();            // l'heure du serveur, jamais celle du navigateur
  if (match.et !== "a_venir" || !(Date.parse(quand) < Date.parse(match.ko))) {
    throw new Refus(409, "match_verrouille", "Ce match a commencé ou n'est plus ouvert aux pronostics.");
  }
  await env.DB.prepare(`INSERT INTO pronos (ligue_code, membre_id, match_id, buts_dom, buts_ext, maj_le) VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT (ligue_code, membre_id, match_id) DO UPDATE SET buts_dom = excluded.buts_dom, buts_ext = excluded.buts_ext, maj_le = excluded.maj_le`)
    .bind(code, joueur.id, id, dom, ext, quand).run();
  return repondre({ match_id: id, buts_dom: dom, buts_ext: ext, coup_envoi: match.ko, maj_le: quand });
}

/* suppression définitive, réservée au créateur : une transaction, les lignes qui en référencent d'autres d'abord */
async function supprimer(req, env, code) {
  const ligue = await lireLigue(env, code);
  const joueur = await lireJoueur(req, env, code);
  if (!joueur) throw new Refus(401, "jeton_manquant", "En-tête « Authorization: Bearer <jeton> » manquant.");
  if (joueur.id !== ligue.createur_id) throw new Refus(403, "pas_createur", "Seul le créateur peut supprimer la ligue.");
  await env.DB.batch(["DELETE FROM pronos WHERE ligue_code = ?", "DELETE FROM membres WHERE ligue_code = ?",
    "DELETE FROM ligues WHERE code = ?"].map((sql) => env.DB.prepare(sql).bind(code)));
  return repondre({ code, supprimee: true });
}

/* un pronostic enregistré, rattaché à son match du programme (il le suit si le match est déplacé) */
function situer(ligne, programme, maintenant) {
  const trouve = trouver(programme, ligne.match_id);
  const match = trouve?.match ?? null;
  return {
    id: trouve?.id ?? ligne.match_id, match, score: [ligne.buts_dom, ligne.buts_ext], maj_le: ligne.maj_le,
    // match inconnu ou reporté : on ne peut pas affirmer qu'il a commencé, les pronostics restent cachés
    commence: Boolean(match) && match.et !== "reporte" && Date.parse(match.ko) <= maintenant,
    // le coup d'envoi a pu être avancé après l'enregistrement : ce pronostic-là ne compte pas
    horsDelai: Boolean(match) && Date.parse(ligne.maj_le) >= Date.parse(match.ko),
  };
}

/* un seul pronostic par joueur et par match : après un déplacement, le dernier saisi à temps l'emporte */
function unParMatch(situes) {
  const gardes = new Map();
  for (const p of situes) {
    const autre = gardes.get(p.id);
    if (!autre || (autre.horsDelai && !p.horsDelai) || (autre.horsDelai === p.horsDelai && p.maj_le > autre.maj_le)) gardes.set(p.id, p);
  }
  const coupEnvoi = (p) => p.match?.ko ?? "";
  return [...gardes.values()].sort((x, y) => coupEnvoi(x).localeCompare(coupEnvoi(y)) || x.id.localeCompare(y.id));
}

const detail = (p) => (p.commence && p.match.res && !p.horsDelai ? calculerPoints(p.score, p.match.res, p.match.p) : null);

function montrer(p, visible) {
  if (!visible) return { match_id: p.id, masque: true };
  return { match_id: p.id, buts_dom: p.score[0], buts_ext: p.score[1], ...(p.horsDelai ? { hors_delai: true } : {}), ...detail(p) };
}

function bilan(membre, pronos) {
  const juges = pronos.map(detail).filter(Boolean);
  const combien = (cle) => juges.filter((d) => d[cle]).length;
  return {
    membre_id: membre.id, pseudo: membre.pseudo, est_bot: Boolean(membre.est_bot),
    points: juges.reduce((total, d) => total + d.points, 0),
    scores_exacts: combien("score_exact"), bonnes_issues: combien("bonne_issue"), bons_ecarts: combien("bon_ecart"),
    coups_de_poker: combien("coup_de_poker"), matchs_juges: juges.length,
  };
}

/* points, puis scores exacts, puis bonnes issues ; à égalité sur les trois, même rang */
function classer(bilans) {
  const ecart = (x, y) => y.points - x.points || y.scores_exacts - x.scores_exacts || y.bonnes_issues - x.bonnes_issues;
  const tries = bilans.sort((x, y) => ecart(x, y) || x.pseudo.localeCompare(y.pseudo, "fr"));
  let rang = 0;
  return tries.map((b, i) => {
    if (!i || ecart(tries[i - 1], b)) rang = i + 1;
    return { rang, ...b };
  });
}

async function consulter(req, env, code) {
  const ligue = await lireLigue(env, code);
  const moi = await lireJoueur(req, env, code);
  const programme = await lireProgramme(env);
  const maintenant = Date.now();
  const competitions = competitionsLigue(ligue.competitions);
  const autorisees = new Set(competitions);
  const { results: membres } = await env.DB
    .prepare("SELECT id, pseudo, est_bot FROM membres WHERE ligue_code = ? ORDER BY est_bot, cree_le, pseudo_cle").bind(code).all();
  const { results: lignes } = await env.DB
    .prepare("SELECT membre_id, match_id, buts_dom, buts_ext, maj_le FROM pronos WHERE ligue_code = ?").bind(code).all();

  const brut = new Map();
  for (const ligne of lignes) {
    const situe = situer(ligne, programme, maintenant);
    if (!autorisees.has(competition(situe.id))) continue;
    if (!brut.has(ligne.membre_id)) brut.set(ligne.membre_id, []);
    brut.get(ligne.membre_id).push(situe);
  }
  const parMembre = new Map(membres.map((m) => [m.id, unParMatch(brut.get(m.id) || [])]));

  // le Bot IA ne joue que les matchs que la ligue joue : au moins un joueur les a pronostiqués à temps
  const joues = [...parMembre.values()].flat().filter((p) => p.match?.bot && !p.horsDelai);
  const duBot = unParMatch(joues.map((p) => ({ ...p, score: p.match.bot, horsDelai: false, maj_le: "" })));
  for (const m of membres) if (m.est_bot) parMembre.set(m.id, duBot);

  const matchs = {};
  for (const p of [...parMembre.values()].flat()) {
    if (p.match) matchs[p.id] = { coup_envoi: p.match.ko, commence: p.commence, score: p.match.res, probas: p.match.p };
  }
  return repondre({
    code: ligue.code, nom: ligue.nom, cree_le: ligue.cree_le, competitions, moi: moi?.id ?? null,
    createur_id: ligue.createur_id ?? null, programme_maj_utc: programme.maj_utc,
    // le score du Bot IA est déjà public (c'est le score probable affiché par le site) : il n'est jamais masqué
    membres: membres.map((m) => ({ id: m.id, pseudo: m.pseudo, est_bot: Boolean(m.est_bot),
      pronos: parMembre.get(m.id).map((p) => montrer(p, Boolean(m.est_bot) || m.id === moi?.id || p.commence)) })),
    matchs,
    classement: classer(membres.map((m) => bilan(m, parMembre.get(m.id)))),
  });
}

// ---------------------------------------------------------------- comptes

function motDePasse(valeur) {
  // forme Unicode unique : le même mot de passe accentué saisi sur deux claviers donne la même empreinte
  const texte = typeof valeur === "string" ? valeur.normalize("NFC") : "";
  const longueur = [...texte].length;
  if (longueur < MDP_MIN || longueur > MDP_MAX) {
    throw new Refus(400, "mot_de_passe_invalide", `Mot de passe : de ${MDP_MIN} à ${MDP_MAX} caractères.`);
  }
  return texte;
}
const empreinteMdp = (sel, mdp) => hacher(`${sel}:${mdp}`);

const estClub = (v) => typeof v === "string" && FORMAT_CLUB.test(v);
function lireFavoris(colonne) {
  try {
    const brut = JSON.parse(colonne);
    return Array.isArray(brut) ? brut.filter(estClub).slice(0, FAVORIS_MAX) : [];
  } catch {
    return [];
  }
}
const ecrireFavoris = (env, compteId, favoris) => env.DB.prepare("UPDATE comptes SET favoris = ?, maj_le = ? WHERE id = ?")
  .bind(JSON.stringify(favoris), maintenantIso(), compteId).run();

/* une session par appareil : les plus anciennes au-delà de la limite sont fermées */
async function ouvrirSession(env, compteId) {
  const { jeton, hash } = await nouveauJoueur();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO sessions (jeton_hash, compte_id, cree_le) VALUES (?, ?, ?)").bind(hash, compteId, maintenantIso()),
    env.DB.prepare(`DELETE FROM sessions WHERE compte_id = ? AND jeton_hash NOT IN
      (SELECT jeton_hash FROM sessions WHERE compte_id = ? ORDER BY cree_le DESC, rowid DESC LIMIT ?)`)
      .bind(compteId, compteId, SESSIONS_MAX),
  ]);
  return jeton;
}

/* les ligues rattachées au compte : le jeton de la session en cours est le jeton actif de chacun de ces joueurs */
async function liguesDuCompte(env, compteId, jeton) {
  const { results } = await env.DB.prepare(`SELECT l.code, l.nom, m.id AS membre_id, m.pseudo FROM membres m
    JOIN ligues l ON l.code = m.ligue_code WHERE m.compte_id = ? ORDER BY m.cree_le, l.code`).bind(compteId).all();
  return results.map(({ code, nom, membre_id, pseudo }) => ({ code, nom, membre_id, pseudo, jeton }));
}

async function inscription(req, env) {
  const corps = await lireCorps(req);
  const pseudo = saisie(corps.pseudo, PSEUDO_COMPTE), mdp = motDePasse(corps.mot_de_passe);
  const pris = () => new Refus(409, "pseudo_pris", "Ce pseudo est déjà pris.");
  if (clePseudo(pseudo) === clePseudo(BOT)) throw pris();
  const id = crypto.randomUUID(), sel = hexa(crypto.getRandomValues(new Uint8Array(16))), quand = maintenantIso();
  try {
    await env.DB.prepare("INSERT INTO comptes (id, pseudo, pseudo_cle, mdp_hash, sel, cree_le, maj_le) VALUES (?, ?, ?, ?, ?, ?, ?)")
      .bind(id, pseudo, clePseudo(pseudo), await empreinteMdp(sel, mdp), sel, quand, quand).run();
  } catch (error) {
    if (dejaPris(error, "pseudo_cle")) throw pris();
    throw error;
  }
  return repondre({ compte_id: id, pseudo, jeton_compte: await ouvrirSession(env, id), favoris: [] }, 201);
}

/* chaque essai est compté avant que le mot de passe soit examiné, en une seule écriture : des demandes envoyées en même
   temps ne passent pas toutes. Un essai refusé ne repousse pas la fin de la période. Les sessions ouvertes ne sont pas
   concernées. Le compte porte sur le pseudo : qui le connaît peut donc retarder les connexions de son propriétaire. */
async function compterEssai(env, cle) {
  const maintenant = Date.now();
  await env.DB.prepare("DELETE FROM essais WHERE depuis <= ?").bind(new Date(maintenant - ESSAIS_PERIODE_MS).toISOString()).run();
  const { nombre, depuis } = await env.DB.prepare(`INSERT INTO essais (pseudo_cle, nombre, depuis) VALUES (?, 1, ?)
    ON CONFLICT (pseudo_cle) DO UPDATE SET nombre = nombre + 1 RETURNING nombre, depuis`).bind(cle, maintenantIso()).first();
  if (nombre > ESSAIS_MAX) {
    const minutes = Math.max(1, Math.ceil((Date.parse(depuis) + ESSAIS_PERIODE_MS - maintenant) / 60000));
    throw new Refus(429, "trop_d_essais", `Trop d'essais. Réessaie dans ${minutes} minute${minutes > 1 ? "s" : ""}.`);
  }
}
const oublierEssais = (env, cle) => env.DB.prepare("DELETE FROM essais WHERE pseudo_cle = ?").bind(cle).run();

async function connexion(req, env) {
  const corps = await lireCorps(req);
  const pseudo = typeof corps.pseudo === "string" ? corps.pseudo.normalize("NFKC").replace(/\s+/g, " ").trim() : "";
  const mdp = typeof corps.mot_de_passe === "string" ? corps.mot_de_passe.normalize("NFC") : "";
  // même réponse pour un pseudo inconnu et un mot de passe faux
  const refus = () => new Refus(401, "identifiants_invalides", "Pseudo ou mot de passe incorrect.");
  // aucune inscription ne permet ces longueurs : rien à examiner, ni à garder en base
  if ([...pseudo].length < PSEUDO_COMPTE.min || [...pseudo].length > PSEUDO_COMPTE.max
    || [...mdp].length < MDP_MIN || [...mdp].length > MDP_MAX) throw refus();
  const cle = clePseudo(pseudo);
  await compterEssai(env, cle);
  const compte = await env.DB.prepare("SELECT id, pseudo, mdp_hash, sel, favoris FROM comptes WHERE pseudo_cle = ?")
    .bind(cle).first();
  if (!compte || await empreinteMdp(compte.sel, mdp) !== compte.mdp_hash) throw refus();
  await oublierEssais(env, cle);
  const jeton = await ouvrirSession(env, compte.id);
  return repondre({ compte_id: compte.id, pseudo: compte.pseudo, jeton_compte: jeton, favoris: lireFavoris(compte.favoris),
    ligues: await liguesDuCompte(env, compte.id, jeton) });
}

async function monCompte(req, env) {
  const compte = await exigerCompte(req, env);
  return repondre({ compte_id: compte.id, pseudo: compte.pseudo, favoris: lireFavoris(compte.favoris),
    ligues: await liguesDuCompte(env, compte.id, compte.jeton) });
}

async function enregistrerFavoris(req, env) {
  const compte = await exigerCompte(req, env);
  const { favoris } = await lireCorps(req, CORPS_FAVORIS_MAX);
  const uniques = Array.isArray(favoris) && favoris.every(estClub) ? [...new Set(favoris)] : null;
  if (!uniques || uniques.length > FAVORIS_MAX) {
    throw new Refus(400, "favoris_invalides", `« favoris » doit être une liste de ${FAVORIS_MAX} clubs au plus.`);
  }
  await ecrireFavoris(env, compte.id, uniques);
  return repondre({ favoris: uniques });
}

/* ce que le navigateur gardait sans compte : ses joueurs (prouvés par leur jeton) et ses clubs favoris.
   Un joueur déjà rattaché ailleurs, ou un second joueur dans la même ligue, reste comme il était. */
async function rattacher(req, env) {
  const compte = await exigerCompte(req, env);
  const { ligues = [], favoris = [] } = await lireCorps(req, CORPS_RATTACHER_MAX);
  if (!Array.isArray(ligues) || ligues.length > RATTACHER_MAX || !Array.isArray(favoris) || favoris.length > FAVORIS_LOCAUX_MAX) {
    throw new Refus(400, "rattachement_invalide", `Au plus ${RATTACHER_MAX} ligues et ${FAVORIS_LOCAUX_MAX} favoris par demande.`);
  }
  const rattachees = [];
  for (const entree of ligues) {
    const code = typeof entree?.code === "string" ? entree.code.toUpperCase() : "";
    const jeton = typeof entree?.jeton === "string" ? entree.jeton : "";
    if (!FORMAT_CODE.test(code) || !/^[0-9a-f]{64}$/.test(jeton)) continue;
    // une seule écriture : libre (ou déjà au compte) et aucun autre joueur de ce compte dans la ligue
    const { meta } = await env.DB.prepare(`UPDATE membres SET compte_id = ? WHERE ligue_code = ? AND jeton_hash = ? AND est_bot = 0
      AND (compte_id IS NULL OR compte_id = ?) AND NOT EXISTS (SELECT 1 FROM membres AS autre
        WHERE autre.ligue_code = ? AND autre.compte_id = ? AND autre.jeton_hash <> ?)`)
      .bind(compte.id, code, await hacher(jeton), compte.id, code, compte.id, await hacher(jeton)).run();
    if (meta.changes) rattachees.push(code);
  }
  const fusion = [...new Set([...lireFavoris(compte.favoris), ...favoris.filter(estClub)])].slice(0, FAVORIS_MAX);
  await ecrireFavoris(env, compte.id, fusion);
  return repondre({ favoris: fusion, rattachees, ligues: await liguesDuCompte(env, compte.id, compte.jeton) });
}

/* « Quitter la ligue » avec un compte : le joueur reste dans la ligue mais n'appartient plus au compte */
async function detacher(req, env) {
  const compte = await exigerCompte(req, env);
  const { code: brut } = await lireCorps(req);
  const code = typeof brut === "string" ? brut.toUpperCase() : "";
  if (!FORMAT_CODE.test(code)) throw new Refus(400, "code_invalide", "Code de ligue invalide.");
  await env.DB.prepare("UPDATE membres SET compte_id = NULL WHERE ligue_code = ? AND compte_id = ?").bind(code, compte.id).run();
  return repondre({ code, detachee: true });
}

async function deconnexion(req, env) {
  const compte = await exigerCompte(req, env);
  await env.DB.prepare("DELETE FROM sessions WHERE jeton_hash = ?").bind(compte.hash).run();
  return repondre({ deconnecte: true });
}

const ROUTES_COMPTES = {
  inscription: { POST: inscription }, connexion: { POST: connexion }, moi: { GET: monCompte },
  favoris: { PUT: enregistrerFavoris }, rattacher: { POST: rattacher }, detacher: { POST: detacher },
  deconnexion: { POST: deconnexion },
};

// ---------------------------------------------------------------- aiguillage

/* la fonction de la route demandée, après les contrôles communs (adresse, méthode, base disponible) */
function choisir(route, req, env, indisponible) {
  if (!route) throw new Refus(404, "route_inconnue", "Adresse inconnue.");
  if (!Object.hasOwn(route, req.method)) throw new Refus(405, "methode_non_permise", "Méthode non permise.");
  if (!env.DB) throw new Refus(503, ...indisponible);
  return route[req.method];
}

function routerComptes(req, env, chemin) {
  const [, , action, reste] = chemin.split("/");
  const route = reste === undefined && action !== undefined && Object.hasOwn(ROUTES_COMPTES, action) ? ROUTES_COMPTES[action] : null;
  return choisir(route, req, env, ["comptes_indisponibles", "Les comptes ne sont pas disponibles."])(req, env);
}

function router(req, env, chemin) {
  const [, , code, action, reste] = chemin.split("/");
  const route = code === undefined ? { POST: () => creer(req, env) }
    : action === undefined ? { GET: () => consulter(req, env, code.toUpperCase()),
      DELETE: () => supprimer(req, env, code.toUpperCase()) }
    : reste === undefined && action === "rejoindre" ? { POST: () => rejoindre(req, env, code.toUpperCase()) }
    : reste === undefined && action === "pronos" ? { POST: () => pronostiquer(req, env, code.toUpperCase()) }
    : null;
  return choisir(route, req, env, ["ligues_indisponibles", "Les ligues ne sont pas disponibles."])();
}

export async function servirLigues(req, env, url) {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: PREVOL });
  try {
    return await (url.pathname.startsWith("/comptes") ? routerComptes : router)(req, env, url.pathname);
  } catch (error) {
    if (error instanceof Refus) return repondre({ erreur: { code: error.code, message: error.message } }, error.statut);
    console.error("ligues", error);         // le détail reste dans les journaux du Worker
    return repondre({ erreur: { code: "erreur_interne", message: "Erreur interne. Réessaie plus tard." } }, 500);
  }
}
