/* Relais du direct. `tour` (lancé chaque minute par relais/boucle.mjs dans GitHub Actions) interroge API-Football
   seulement pendant nos matchs et range les scores dans le stockage KV ; le Worker sert ces scores au site.
   API-Football limite les appels venus de Cloudflare (adresses partagées) : la clé ne sert donc que dans GitHub.
   Le Worker sert aussi les ligues de pronostics et les comptes (routes /ligues et /comptes, ligues.js), indépendants du direct. */
import { servirLigues } from "./ligues.js";

const API = "https://v3.football.api-sports.io";
// identifiants API-Football de nos compétitions (codes du site entre parenthèses)
const LIGUES = { 39: "E0", 78: "D1", 140: "SP1", 135: "I1", 61: "F1", 2: "LDC", 3: "LEC" };
const QUOTA_JOUR = 100;          // offre gratuite : remis à zéro à minuit UTC
const MARGE_SECURITE = 10;       // marge conservée sous le plafond gratuit de 100 appels/jour
const RESERVE = 15;              // marge + appels gardés pour relire le programme en fin de match
const AVANT_MATCH_MIN = 2;       // on commence à suivre un match 2 min avant le coup d'envoi
const DUREE_MATCH_MIN = 125;     // 90 min, mi-temps, arrêts de jeu ; prolongé tant que le match est en cours
const EN_JEU = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
const FINI = new Set(["FT", "AET", "PEN", "PST", "CANC", "ABD", "AWD", "WO"]);
const CLE_ETAT = "etat";
const PAUSE_ERREUR_MIN = 5;
const ESSAIS = 2;
const ATTENTE_ESSAI_MS = 7000;      // après une erreur de l'API, on attend avant de réessayer pour ne pas user le quota

const minute = 60000;

/* appel à API-Football ; renvoie la réponse et le nombre d'appels encore permis aujourd'hui */
async function appeler(env, chemin, essai = 1) {
  const r = await fetch(`${API}/${chemin}`, { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } });
  if (!r.ok) throw new Error(`API-Football ${chemin} : ${r.status}`);
  const corps = await r.json();
  const erreurs = corps.errors && (Array.isArray(corps.errors) ? corps.errors.length : Object.keys(corps.errors).length);
  if (erreurs && corps.errors.rateLimit && essai < ESSAIS) {
    // limite à la minute : un second essai quelques secondes plus tard passe souvent
    await new Promise((ok) => setTimeout(ok, ATTENTE_ESSAI_MS));
    return appeler(env, chemin, essai + 1);
  }
  if (erreurs) {
    const quota = ["x-ratelimit-requests-limit", "x-ratelimit-requests-remaining", "x-ratelimit-limit", "x-ratelimit-remaining"]
      .map((h) => `${h}=${r.headers.get(h)}`).join(" ");
    throw new Error(`API-Football ${chemin} : ${JSON.stringify(corps.errors)} (essai ${essai}, ${quota})`);
  }
  const restant = Number(r.headers.get("x-ratelimit-requests-remaining"));
  return { liste: corps.response || [], restant: Number.isFinite(restant) ? restant : null };
}

/* ce que l'on garde d'un match : rien de plus que ce qu'affiche une page de scores */
function resume(f) {
  return {
    id: f.fixture.id, c: LIGUES[f.league.id], ko: f.fixture.date, st: f.fixture.status.short,
    min: f.fixture.status.elapsed, plus: f.fixture.status.extra ?? null,
    h: f.teams.home.name, a: f.teams.away.name,
    g: [f.goals.home, f.goals.away], mt: [f.score?.halftime?.home ?? null, f.score?.halftime?.away ?? null],
  };
}
const nosMatchs = (liste) => liste.filter((f) => LIGUES[f.league.id]).map(resume);

/* Chronologie des buts : `ev` = [[minute, arrêts de jeu, buts domicile, buts extérieur], ...], un point à chaque changement de score
   vu par le relais (donc à la minute du relevé, au plus à `intervalle_min` minutes du but). Le site en tire la courbe des chances
   depuis le coup d'envoi, y compris pour qui arrive en cours de match. Rien n'est inventé : un score déjà acquis lors du premier
   relevé (relais lancé en retard) apparaît à la minute de ce relevé. */
const EV_MAX = 40;
function avecChronologie(neuf, ancien) {
  const ev = Array.isArray(ancien?.ev) ? ancien.ev.slice() : [];
  const [h, a] = neuf.g || [];
  if (neuf.st !== "NS" && Number.isInteger(h) && Number.isInteger(a)) {
    const [dh, da] = ev.length ? ev[ev.length - 1].slice(2) : [0, 0];
    if (h !== dh || a !== da) {
      const dernier = ev.length ? ev[ev.length - 1][0] : 0;
      ev.push([neuf.min ?? dernier, neuf.plus ?? 0, h, a]);
    }
  }
  return { ...neuf, ev: ev.slice(-EV_MAX) };
}

/* fin de la fenêtre de suivi d'un match : prolongée tant que l'API le dit encore en jeu */
function fenetre(m, maintenant) {
  const debut = Date.parse(m.ko) - AVANT_MATCH_MIN * minute;
  if (FINI.has(m.st)) return null;
  const fin = Math.max(Date.parse(m.ko) + DUREE_MATCH_MIN * minute, EN_JEU.has(m.st) ? maintenant + 15 * minute : 0);
  return [debut, fin];
}

/* minutes de suivi encore à couvrir aujourd'hui (union des fenêtres), vrai si un match est suivi maintenant,
   et horodatage du prochain début de fenêtre à venir (null s'il n'y en a plus) */
function aCouvrir(matchs, maintenant) {
  const f = matchs.map((m) => fenetre(m, maintenant)).filter(Boolean).sort((x, y) => x[0] - y[0]);
  let total = 0, actif = false, fin = maintenant, prochainDebut = null;
  for (const [d, e] of f) {
    if (d <= maintenant && maintenant <= e) actif = true;
    if (d > maintenant && prochainDebut === null) prochainDebut = d;
    const a = Math.max(d, fin);
    if (e > a) { total += e - a; fin = e; }
  }
  return { actif, minutes: total / minute, prochainDebut };
}

const jourUtc = (t) => new Date(t).toISOString().slice(0, 10);

/* un tour du relais (toutes les minutes) ; une erreur est gardée dans l'état, montrée par /direct, puis relancée */
async function tour(env, maintenant = Date.now()) {
  const etat = (await env.DIRECT.get(CLE_ETAT, "json")) || {};
  if (etat.erreur_ms && maintenant - etat.erreur_ms < PAUSE_ERREUR_MIN * minute) return etat;
  try {
    return await avancer(env, etat, maintenant);
  } catch (error) {
    Object.assign(etat, { erreur_ms: maintenant, erreur: { utc: new Date(maintenant).toISOString(), message: String(error.message) } });
    await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
    throw new Error("Tour du relais en échec", { cause: error });
  }
}

/* programme du jour une fois par jour, puis scores en direct à un intervalle qui fait tenir le quota jusqu'au soir */
async function avancer(env, etat, maintenant) {
  const jour = jourUtc(maintenant);
  const nouveauJour = etat.jour !== jour;
  if (nouveauJour || (etat.relire && (etat.restant ?? QUOTA_JOUR) > MARGE_SECURITE)) {
    const { liste, restant } = await appeler(env, `fixtures?date=${jour}`);
    const avant = nouveauJour ? new Map() : new Map((etat.matchs || []).map((m) => [m.id, m]));
    // la relecture du programme (score final) ne doit pas effacer la chronologie déjà relevée
    const prog = nosMatchs(liste).map((m) => (avant.has(m.id) || m.st !== "NS" ? avecChronologie(m, avant.get(m.id)) : m));
    Object.assign(etat, { jour, matchs: prog, relire: false, restant, programme_ms: maintenant,
      programme_utc: new Date(maintenant).toISOString(),
      ...(nouveauJour ? { direct_utc: null, direct_ms: null, intervalle_min: null } : {}),
      erreur: null, erreur_ms: null });
    await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
    return etat;
  }
  if (etat.relire) {
    etat.relire = false;
    await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
  }
  const { actif, minutes } = aCouvrir(etat.matchs || [], maintenant);
  // Si un match est resté « NS » alors que sa fenêtre de jeu est dépassée (ex. retard cron GitHub),
  // on force une relecture du programme (au plus toutes les 15 min) pour récupérer son score final.
  const manques = (etat.matchs || []).some((m) => m.st === "NS" && Date.parse(m.ko) + DUREE_MATCH_MIN * minute < maintenant);
  const progFrais = etat.programme_ms && maintenant - etat.programme_ms < 15 * minute;
  if (manques && !progFrais && (etat.restant ?? QUOTA_JOUR) > MARGE_SECURITE) {
    const { liste, restant } = await appeler(env, `fixtures?date=${jour}`);
    const avant = new Map((etat.matchs || []).map((m) => [m.id, m]));
    const prog = nosMatchs(liste).map((m) => (avant.has(m.id) || m.st !== "NS" ? avecChronologie(m, avant.get(m.id)) : m));
    Object.assign(etat, { jour, matchs: prog, relire: false, restant, programme_ms: maintenant,
      programme_utc: new Date(maintenant).toISOString(), erreur: null, erreur_ms: null });
    await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
    return etat;
  }
  if (!actif) return etat;
  if (etat.restant != null && etat.restant <= MARGE_SECURITE) return etat;
  const budget = Math.max(1, (etat.restant ?? QUOTA_JOUR) - RESERVE);
  const intervalle = Math.max(1, Math.ceil(minutes / budget));
  if (etat.direct_ms && maintenant - etat.direct_ms < intervalle * minute - 5000) return etat;
  const { liste, restant } = await appeler(env, "fixtures?live=all");
  const enDirect = new Map(nosMatchs(liste).map((m) => [m.id, m]));
  let sortis = false;
  const matchs = (etat.matchs || []).map((m) => {
    if (enDirect.has(m.id)) return avecChronologie(enDirect.get(m.id), m);
    // sorti du direct après y être entré, ou coup d'envoi passé sans avoir été vu (retard cron) : relire le score final
    if (EN_JEU.has(m.st) || (m.st === "NS" && Date.parse(m.ko) + DUREE_MATCH_MIN * minute < maintenant)) {
      sortis = true;
      return { ...m, st: "FT?" };
    }
    return m;
  });
  Object.assign(etat, { matchs, restant, direct_ms: maintenant, direct_utc: new Date(maintenant).toISOString(),
    intervalle_min: intervalle, relire: sortis && (restant ?? 0) > MARGE_SECURITE, erreur: null, erreur_ms: null });
  await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
  return etat;
}

const ENTETES = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "cache-control": "public, max-age=20",
  "x-content-type-options": "nosniff",
};

/* réponse publique : les matchs du jour de nos compétitions */
async function servir(env) {
  const etat = (await env.DIRECT.get(CLE_ETAT, { type: "json", cacheTtl: 30 })) || {};
  const corps = {
    jour: etat.jour || null, maj_utc: etat.direct_utc || etat.programme_utc || null,
    intervalle_min: etat.intervalle_min || null, source: "API-Football", erreur: etat.erreur || null, matchs: etat.matchs || [],
  };
  return new Response(JSON.stringify(corps), { headers: ENTETES });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (/^\/(ligues|comptes)(\/|$)/.test(url.pathname)) return servirLigues(req, env, url);
    if (req.method === "OPTIONS") return new Response(null, { headers: { ...ENTETES, "access-control-allow-methods": "GET" } });
    if (req.method !== "GET") return new Response("Méthode non permise", { status: 405 });
    if (url.pathname === "/direct") return servir(env);
    return new Response("Relais du direct d'Extinction des feux. Données : /direct", { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
};

export { tour, avancer, aCouvrir, fenetre, nosMatchs, servir, LIGUES, MARGE_SECURITE, RESERVE };
