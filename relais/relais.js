/* Relais du direct : interroge API-Football seulement pendant nos matchs et sert les scores au site.
   La clé reste un secret du Worker ; le site ne reçoit que des scores, des minutes et des noms de clubs. */

const API = "https://v3.football.api-sports.io";
// identifiants API-Football de nos compétitions (codes du site entre parenthèses)
const LIGUES = { 39: "E0", 78: "D1", 140: "SP1", 61: "F1", 2: "LDC", 3: "LEC" };
const QUOTA_JOUR = 100;          // offre gratuite : remis à zéro à minuit UTC
const RESERVE = 4;               // gardés pour relire le programme en fin de match
const AVANT_MATCH_MIN = 2;       // on commence à suivre un match 2 min avant le coup d'envoi
const DUREE_MATCH_MIN = 125;     // 90 min, mi-temps, arrêts de jeu ; prolongé tant que le match est en cours
const EN_JEU = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
const FINI = new Set(["FT", "AET", "PEN", "PST", "CANC", "ABD", "AWD", "WO"]);
const CLE_ETAT = "etat";
const RETARD_TOLERE_MIN = 2;     // au-delà, une visite relance le tour que la minuterie aurait dû faire
const PAUSE_ERREUR_MIN = 5;      // après une erreur de l'API, on attend avant de réessayer pour ne pas user le quota

const minute = 60000;

/* appel à API-Football ; renvoie la réponse et le nombre d'appels encore permis aujourd'hui */
async function appeler(env, chemin) {
  const r = await fetch(`${API}/${chemin}`, { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } });
  if (!r.ok) throw new Error(`API-Football ${chemin} : ${r.status}`);
  const corps = await r.json();
  const erreurs = corps.errors && (Array.isArray(corps.errors) ? corps.errors.length : Object.keys(corps.errors).length);
  if (erreurs) throw new Error(`API-Football ${chemin} : ${JSON.stringify(corps.errors)}`);
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

/* fin de la fenêtre de suivi d'un match : prolongée tant que l'API le dit encore en jeu */
function fenetre(m, maintenant) {
  const debut = Date.parse(m.ko) - AVANT_MATCH_MIN * minute;
  if (FINI.has(m.st)) return null;
  const fin = Math.max(Date.parse(m.ko) + DUREE_MATCH_MIN * minute, EN_JEU.has(m.st) ? maintenant + 15 * minute : 0);
  return [debut, fin];
}

/* minutes de suivi encore à couvrir aujourd'hui (union des fenêtres) et vrai si un match est suivi maintenant */
function aCouvrir(matchs, maintenant) {
  const f = matchs.map((m) => fenetre(m, maintenant)).filter(Boolean).sort((x, y) => x[0] - y[0]);
  let total = 0, actif = false, fin = maintenant;
  for (const [d, e] of f) {
    if (d <= maintenant && maintenant <= e) actif = true;
    const a = Math.max(d, fin);
    if (e > a) { total += e - a; fin = e; }
  }
  return { actif, minutes: total / minute };
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
  if (etat.jour !== jour || etat.relire) {
    const { liste, restant } = await appeler(env, `fixtures?date=${jour}`);
    const prog = nosMatchs(liste);
    Object.assign(etat, { jour, matchs: prog, relire: false, restant, programme_utc: new Date(maintenant).toISOString(),
      erreur: null, erreur_ms: null });
    await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
    return etat;
  }
  const { actif, minutes } = aCouvrir(etat.matchs || [], maintenant);
  if (!actif) return etat;
  const budget = Math.max(1, (etat.restant ?? QUOTA_JOUR) - RESERVE);
  const intervalle = Math.max(1, Math.ceil(minutes / budget));
  if (etat.direct_ms && maintenant - etat.direct_ms < intervalle * minute - 5000) return etat;
  const { liste, restant } = await appeler(env, "fixtures?live=all");
  const enDirect = new Map(nosMatchs(liste).map((m) => [m.id, m]));
  let sortis = false;
  const matchs = (etat.matchs || []).map((m) => {
    if (enDirect.has(m.id)) return enDirect.get(m.id);
    // sorti du direct après y être entré : terminé, le programme relu donnera le score final
    if (EN_JEU.has(m.st)) { sortis = true; return { ...m, st: "FT?" }; }
    return m;
  });
  Object.assign(etat, { matchs, restant, direct_ms: maintenant, direct_utc: new Date(maintenant).toISOString(),
    intervalle_min: intervalle, relire: sortis && (restant ?? 0) > 0, erreur: null, erreur_ms: null });
  await env.DIRECT.put(CLE_ETAT, JSON.stringify(etat));
  return etat;
}

const ENTETES = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "cache-control": "public, max-age=20",
  "x-content-type-options": "nosniff",
};

/* vrai si le tour programmé a pris du retard : programme du jour absent, ou direct plus vieux que prévu pendant un match */
function enRetard(etat, maintenant) {
  if (etat.erreur_ms && maintenant - etat.erreur_ms < PAUSE_ERREUR_MIN * minute) return false;
  if (etat.jour !== jourUtc(maintenant)) return true;
  if (!aCouvrir(etat.matchs || [], maintenant).actif) return false;
  return !etat.direct_ms || maintenant - etat.direct_ms > ((etat.intervalle_min || 1) + RETARD_TOLERE_MIN) * minute;
}

/* réponse publique : les matchs du jour de nos compétitions ; relance un tour si le programmé est en retard */
async function servir(env, ctx) {
  const etat = (await env.DIRECT.get(CLE_ETAT, { type: "json", cacheTtl: 30 })) || {};
  if (enRetard(etat, Date.now())) ctx.waitUntil(tour(env).catch((error) => console.error("Tour de secours en échec", error)));
  const corps = {
    jour: etat.jour || null, maj_utc: etat.direct_utc || etat.programme_utc || null,
    intervalle_min: etat.intervalle_min || null, source: "API-Football", erreur: etat.erreur || null, matchs: etat.matchs || [],
  };
  return new Response(JSON.stringify(corps), { headers: ENTETES });
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: { ...ENTETES, "access-control-allow-methods": "GET" } });
    if (req.method !== "GET") return new Response("Méthode non permise", { status: 405 });
    if (url.pathname === "/direct") return servir(env, ctx);
    return new Response("Relais du direct d'Extinction des feux. Données : /direct", { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
  async scheduled(_evt, env, ctx) {
    ctx.waitUntil(tour(env).catch((error) => console.error("Tour programmé en échec", error)));
  },
};

export { tour, avancer, enRetard, aCouvrir, fenetre, nosMatchs, LIGUES };
