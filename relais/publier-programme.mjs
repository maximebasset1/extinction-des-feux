/* Met à jour le programme des ligues dans KV à partir des JSON publiés par le site.
   Lancé par .github/workflows/relais.yml (après chaque déploiement, puis toutes les 30 minutes) : le calcul se fait ici,
   pas dans le Worker, dont le temps processeur est très limité sur l'offre gratuite. */
import { pathToFileURL } from "node:url";
import { CLE_PROGRAMME, FICHIERS, fusionner } from "./programme.js";

const SITE = "https://maximebasset1.github.io/extinction-des-feux/data/foot";

export async function publier({ stockage, lireFichier, maintenant = Date.now() }) {
  const ancien = await stockage.get(CLE_PROGRAMME);       // une lecture en panne arrête tout : l'historique n'est pas écrasé
  const fichiers = {};
  for (const [code, nom] of Object.entries(FICHIERS)) {
    try {
      fichiers[code] = await lireFichier(nom);
    } catch (error) {
      console.warn(`${nom} illisible, ses matchs sont gardés tels quels :`, error.message);
      fichiers[code] = null;
    }
  }
  const absents = Object.keys(FICHIERS).filter((code) => !fichiers[code]);
  if (absents.length === Object.keys(FICHIERS).length) throw new Error("programme inchangé : aucun fichier du site n'a pu être lu");
  const programme = fusionner(ancien, fichiers, maintenant);
  await stockage.put(CLE_PROGRAMME, JSON.stringify(programme));
  return { matchs: Object.keys(programme.matchs).length, lus: Object.keys(FICHIERS).length - absents.length, absents };
}

async function lireSite(nom) {
  // ?t= : GitHub Pages garde ses réponses 10 minutes en cache
  const r = await fetch(`${SITE}/${nom}.json?t=${Math.floor(Date.now() / 60000)}`, { signal: AbortSignal.timeout(30000) });
  if (!r.ok) throw new Error(`réponse ${r.status}`);
  return r.json();
}

/* même interface que le stockage KV vu depuis un Worker, par l'API de Cloudflare */
function stockageCloudflare({ CLOUDFLARE_API_TOKEN: jeton, CLOUDFLARE_ACCOUNT_ID: compte, KV_ID: kv }) {
  for (const [nom, v] of Object.entries({ CLOUDFLARE_API_TOKEN: jeton, CLOUDFLARE_ACCOUNT_ID: compte, KV_ID: kv })) {
    if (!v) throw new Error(`variable manquante : ${nom}`);
  }
  const base = `https://api.cloudflare.com/client/v4/accounts/${compte}/storage/kv/namespaces/${kv}/values`;
  const auth = { Authorization: `Bearer ${jeton}` };
  return {
    async get(cle) {
      const r = await fetch(`${base}/${cle}`, { headers: auth });
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`lecture KV ${cle} : ${r.status}`);
      return r.json();
    },
    async put(cle, valeur) {
      const r = await fetch(`${base}/${cle}`, { method: "PUT", headers: { ...auth, "content-type": "text/plain" }, body: valeur });
      if (!r.ok) throw new Error(`écriture KV ${cle} : ${r.status}`);
    },
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const bilan = await publier({ stockage: stockageCloudflare(process.env), lireFichier: lireSite });
  console.log(`programme des ligues : ${bilan.matchs} matchs, ${bilan.lus} fichiers lus`
    + (bilan.absents.length ? `, absents : ${bilan.absents.join(", ")}` : ""));
}
