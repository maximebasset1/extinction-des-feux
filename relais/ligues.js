/* API des ligues de pronostics (routes /ligues du Worker, contrat dans relais/README.md). Données : base D1 `DB`
   (schema.sql) et programme des matchs dans KV (programme.js). Aucune route n'appelle API-Football ni n'écrit dans KV :
   le direct et son quota ne dépendent pas des ligues. Pas de compte : le code de la ligue ouvre la consultation et
   l'inscription, le jeton remis à l'inscription (gardé par le navigateur) identifie un joueur. */
import { calculerPoints } from "./points.js";
import { CLE_PROGRAMME, trouver } from "./programme.js";

const MAX_JOUEURS = 30;                    // par ligue, Bot IA non compris
const CORPS_MAX = 2048;
const BUTS_MAX = 20;
const PROGRAMME_MAX_MS = 48 * 3600000;     // au-delà, les heures de coup d'envoi ne sont plus assez sûres pour verrouiller
const BOT = "Bot IA";
const LETTRES = "ABCDEFGHJKLMNPQRSTUVWXYZ";   // sans I ni O, qu'on confond avec 1 et 0
const FORMAT_CODE = /^[A-Z]{3}-\d{3}$/;
const PSEUDO = { champ: "pseudo", min: 2, max: 20, permis: /^[\p{L}\p{M}\p{N} ._'’-]+$/u };
const NOM = { champ: "nom", min: 3, max: 40, permis: /^[\p{L}\p{M}\p{N} ._'’!?&(),:+-]+$/u };

const ENTETES = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "cache-control": "no-store",             // la réponse dépend du jeton et de l'heure : jamais de cache
  vary: "authorization",
  "x-content-type-options": "nosniff",
};
const PREVOL = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, OPTIONS",
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

async function lireCorps(req) {
  const texte = await req.text();
  if (texte.length > CORPS_MAX) throw new Refus(413, "corps_trop_long", "Requête trop longue.");
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

// ---------------------------------------------------------------- accès

async function lireLigue(env, code) {
  const ligue = FORMAT_CODE.test(code) ? await env.DB.prepare("SELECT code, nom, cree_le FROM ligues WHERE code = ?").bind(code).first() : null;
  if (!ligue) throw new Refus(404, "ligue_inconnue", "Aucune ligue ne porte ce code.");
  return ligue;
}

/* le joueur du jeton « Authorization: Bearer ... » dans cette ligue ; null sans en-tête, refus si le jeton ne correspond pas */
async function lireJoueur(req, env, code) {
  const entete = req.headers.get("authorization");
  if (!entete) return null;
  const jeton = /^Bearer ([0-9a-f]{64})$/.exec(entete)?.[1];
  const joueur = jeton && await env.DB.prepare("SELECT id FROM membres WHERE ligue_code = ? AND jeton_hash = ? AND est_bot = 0")
    .bind(code, await hacher(jeton)).first();
  if (!joueur) throw new Refus(401, "jeton_invalide", "Jeton refusé pour cette ligue.");
  return joueur;
}

async function lireProgramme(env) {
  const programme = await env.DIRECT.get(CLE_PROGRAMME, { type: "json", cacheTtl: 60 });
  if (!programme?.matchs) throw new Refus(503, "programme_indisponible", "Le programme des matchs n'est pas disponible. Réessaie plus tard.");
  return programme;
}

// ---------------------------------------------------------------- routes

async function creer(req, env) {
  const corps = await lireCorps(req);
  const nom = saisie(corps.nom, NOM), pseudo = saisie(corps.pseudo, PSEUDO);
  if (clePseudo(pseudo) === clePseudo(BOT)) throw pseudoPris();
  const joueur = await nouveauJoueur(), quand = maintenantIso();
  const membre = (code, id, p, hash, bot) => env.DB
    .prepare("INSERT INTO membres (id, ligue_code, pseudo, pseudo_cle, jeton_hash, est_bot, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(id, code, p, clePseudo(p), hash, bot, quand);
  for (let essai = 1; essai <= 5; essai++) {
    const code = tirerCode();
    try {
      await env.DB.batch([                 // une transaction : jamais de ligue sans son créateur ni son Bot IA
        env.DB.prepare("INSERT INTO ligues (code, nom, cree_le) VALUES (?, ?, ?)").bind(code, nom, quand),
        membre(code, joueur.id, pseudo, joueur.hash, 0),
        membre(code, crypto.randomUUID(), BOT, "", 1),
      ]);
      return repondre({ code, membre_id: joueur.id, jeton: joueur.jeton }, 201);
    } catch (error) {
      if (!dejaPris(error, "ligues.code")) throw error;
    }
  }
  throw new Error("aucun code de ligue libre après 5 tirages");
}

async function rejoindre(req, env, code) {
  await lireLigue(env, code);
  const pseudo = saisie((await lireCorps(req)).pseudo, PSEUDO);
  const joueur = await nouveauJoueur();
  let resultat;
  try {
    // le compte des places fait partie de l'insertion : deux inscriptions simultanées ne peuvent pas dépasser la limite
    resultat = await env.DB.prepare(`INSERT INTO membres (id, ligue_code, pseudo, pseudo_cle, jeton_hash, est_bot, cree_le)
      SELECT ?, ?, ?, ?, ?, 0, ? WHERE (SELECT COUNT(*) FROM membres WHERE ligue_code = ? AND est_bot = 0) < ?`)
      .bind(joueur.id, code, pseudo, clePseudo(pseudo), joueur.hash, maintenantIso(), code, MAX_JOUEURS).run();
  } catch (error) {
    if (dejaPris(error, "pseudo_cle")) throw pseudoPris();
    throw error;
  }
  if (!resultat.meta.changes) throw new Refus(409, "ligue_complete", `Cette ligue a déjà ${MAX_JOUEURS} joueurs.`);
  return repondre({ membre_id: joueur.id, jeton: joueur.jeton }, 201);
}

async function pronostiquer(req, env, code) {
  await lireLigue(env, code);
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
  const { results: membres } = await env.DB
    .prepare("SELECT id, pseudo, est_bot FROM membres WHERE ligue_code = ? ORDER BY est_bot, cree_le, pseudo_cle").bind(code).all();
  const { results: lignes } = await env.DB
    .prepare("SELECT membre_id, match_id, buts_dom, buts_ext, maj_le FROM pronos WHERE ligue_code = ?").bind(code).all();

  const brut = new Map();
  for (const ligne of lignes) {
    if (!brut.has(ligne.membre_id)) brut.set(ligne.membre_id, []);
    brut.get(ligne.membre_id).push(situer(ligne, programme, maintenant));
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
    code: ligue.code, nom: ligue.nom, cree_le: ligue.cree_le, moi: moi?.id ?? null, programme_maj_utc: programme.maj_utc,
    // le score du Bot IA est déjà public (c'est le score probable affiché par le site) : il n'est jamais masqué
    membres: membres.map((m) => ({ id: m.id, pseudo: m.pseudo, est_bot: Boolean(m.est_bot),
      pronos: parMembre.get(m.id).map((p) => montrer(p, Boolean(m.est_bot) || m.id === moi?.id || p.commence)) })),
    matchs,
    classement: classer(membres.map((m) => bilan(m, parMembre.get(m.id)))),
  });
}

function router(req, env, chemin) {
  const [, , code, action, reste] = chemin.split("/");
  const route = code === undefined ? { POST: () => creer(req, env) }
    : action === undefined ? { GET: () => consulter(req, env, code.toUpperCase()) }
    : reste === undefined && action === "rejoindre" ? { POST: () => rejoindre(req, env, code.toUpperCase()) }
    : reste === undefined && action === "pronos" ? { POST: () => pronostiquer(req, env, code.toUpperCase()) }
    : null;
  if (!route) throw new Refus(404, "route_inconnue", "Adresse inconnue.");
  if (!Object.hasOwn(route, req.method)) throw new Refus(405, "methode_non_permise", "Méthode non permise.");
  if (!env.DB) throw new Refus(503, "ligues_indisponibles", "Les ligues ne sont pas disponibles.");
  return route[req.method]();
}

export async function servirLigues(req, env, url) {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: PREVOL });
  try {
    return await router(req, env, url.pathname);
  } catch (error) {
    if (error instanceof Refus) return repondre({ erreur: { code: error.code, message: error.message } }, error.statut);
    console.error("ligues", error);         // le détail reste dans les journaux du Worker
    return repondre({ erreur: { code: "erreur_interne", message: "Erreur interne. Réessaie plus tard." } }, 500);
  }
}
