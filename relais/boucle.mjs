/* Boucle du direct, lancée par .github/workflows/direct.yml : un tour par minute jusqu'au dernier match du jour
   (ou la fin du créneau), avec le stockage KV du relais lu et écrit par l'API de Cloudflare. */
import { tour, aCouvrir } from "./relais.js";

const PAS_MS = 60000;
const DUREE_MAX_MS = Number(process.env.DUREE_MAX_MIN || 330) * 60000;   // arrêt propre à 5 h 30, loin des 6 h d'un job GitHub
const { CLOUDFLARE_API_TOKEN: JETON, CLOUDFLARE_ACCOUNT_ID: COMPTE, KV_ID, API_FOOTBALL_KEY } = process.env;

for (const [nom, v] of Object.entries({ CLOUDFLARE_API_TOKEN: JETON, CLOUDFLARE_ACCOUNT_ID: COMPTE, KV_ID, API_FOOTBALL_KEY })) {
  if (!v) throw new Error(`variable manquante : ${nom}`);
}

const base = `https://api.cloudflare.com/client/v4/accounts/${COMPTE}/storage/kv/namespaces/${KV_ID}/values`;
const auth = { Authorization: `Bearer ${JETON}` };

/* même interface que le stockage KV vu depuis un Worker (get en JSON, put d'une chaîne) */
const DIRECT = {
  async get(cle) {
    const r = await fetch(`${base}/${encodeURIComponent(cle)}`, { headers: auth });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`lecture KV ${cle} : ${r.status}`);
    return r.json();
  },
  async put(cle, valeur) {
    const r = await fetch(`${base}/${encodeURIComponent(cle)}`, { method: "PUT", headers: { ...auth, "content-type": "text/plain" }, body: valeur });
    if (!r.ok) throw new Error(`écriture KV ${cle} : ${r.status}`);
  },
};

const env = { DIRECT, API_FOOTBALL_KEY };
const debut = Date.now();
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
let echecs = 0;

// on ne commence pas un tour qui finirait après la limite (appel lent, écriture KV) : marge d'une minute
while (Date.now() - debut < DUREE_MAX_MS - PAS_MS) {
  let etat;
  try {
    etat = await tour(env);
    echecs = 0;
  } catch (error) {
    // une erreur passagère (API ou KV) n'arrête pas la soirée ; trop d'échecs de suite font échouer le job, donc se voir
    echecs += 1;
    console.error(new Date().toISOString(), "tour en échec", error.cause?.message || error.message);
    if (echecs >= 10) throw new Error("Boucle du direct arrêtée après 10 échecs de suite", { cause: error });
    await dormir(PAS_MS);
    continue;
  }
  const t = Date.now(), { actif, minutes, prochainDebut } = aCouvrir(etat.matchs || [], t);
  const enJeu = (etat.matchs || []).filter((m) => ["1H", "HT", "2H", "ET", "BT", "P"].includes(m.st)).length;
  console.log(new Date(t).toISOString(), `matchs ${etat.matchs?.length ?? 0}, en jeu ${enJeu}, suivi ${actif ? "oui" : "non"}, reste ${Math.round(minutes)} min, intervalle ${etat.intervalle_min ?? "-"} min, appels restants ${etat.restant ?? "-"}`);
  if (!actif && minutes === 0 && etat.jour) break;   // plus aucun match à suivre aujourd'hui
  // si le prochain match commence après la fin de ce job (ex. cron déclenché la nuit ou en matinée), on s'arrête tout de suite
  if (!actif && prochainDebut && prochainDebut >= debut + DUREE_MAX_MS - PAS_MS) {
    console.log("Prochain match hors de ce créneau : arrêt propre sans attente à vide.");
    break;
  }
  await dormir(PAS_MS);
}
console.log("Fin de la boucle du direct.");
