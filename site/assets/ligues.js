/* Interface « Ligues de pronostics » : multi-ligues dans localStorage, création/adhésion,
   saisie auto-sauvegardée avec verrouillage au coup d'envoi, classement général et points provisoires en direct.
   Module ES autonome côté Football : importe le barème partagé depuis ./points.js (copié depuis relais/points.js). */
import { calculerPoints } from "./points.js";

export const API_LIGUES = "https://extinction-direct.maximebasset1.workers.dev/ligues";
export const CLE_STOCKAGE = "extinction_ligues_v1";
export const COMP_ORDRE = [
  ["E0", "premier-league", "Premier League"],
  ["D1", "bundesliga", "Bundesliga"],
  ["SP1", "liga", "Liga"],
  ["I1", "serie-a", "Serie A"],
  ["F1", "ligue-1", "Ligue 1"],
  ["LDC", "ligue-des-champions", "Ligue des champions"],
  ["LEC", "ligue-europa", "Ligue Europa"],
];
const COMP_NOMS = Object.fromEntries(COMP_ORDRE.map(([c, , n]) => [c, n]));
const FORMAT_CODE = /^[A-Z]{3}-\d{3}$/;
const PAGE_MATCHS = 24;
const HORIZON_JOURS = 14;
const DEBOUNCE_MS = 350;
const RAFRAICHIR_MS = 60e3;
const VERROU_MS = 30e3;

// ---------------------------------------------------------------- helpers purs (testables sous Node)

export function normaliserCode(texte) {
  const brut = String(texte || "").toUpperCase().replace(/[^A-Z0-9-]/g, "");
  if (FORMAT_CODE.test(brut)) return brut;
  const compact = brut.replace(/-/g, "");
  if (/^[A-Z]{3}\d{3}$/.test(compact)) return `${compact.slice(0, 3)}-${compact.slice(3)}`;
  return brut;
}

export const estCodeValide = (code) => FORMAT_CODE.test(code);

export function lireScoreSaisi(valeur) {
  const s = String(valeur ?? "").trim();
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  return Number.isInteger(n) && n >= 0 && n <= 20 ? n : null;
}

export function estVerrouille(coupEnvoiIso, maintenant = Date.now()) {
  if (!coupEnvoiIso) return true;
  const t = Date.parse(coupEnvoiIso);
  return !Number.isFinite(t) || t <= maintenant;
}

export function codeDepuisUrl(search) {
  try {
    const p = new URLSearchParams(search || "");
    const c = normaliserCode(p.get("code") || "");
    return estCodeValide(c) ? c : null;
  } catch {
    return null;
  }
}

export function lienInvitation(code, loc = globalThis.location) {
  if (!loc) return `?code=${encodeURIComponent(code)}`;
  return `${loc.origin}${loc.pathname}?code=${encodeURIComponent(code)}`;
}

// ---------------------------------------------------------------- stockage multi-ligues (localStorage)

export function chargerStockage(storage) {
  if (!storage) return { active: null, ligues: [] };
  try {
    const brut = JSON.parse(storage.getItem(CLE_STOCKAGE) || "null");
    if (!brut || !Array.isArray(brut.ligues)) return { active: null, ligues: [] };
    const ligues = brut.ligues.filter((l) => l && estCodeValide(l.code) && typeof l.jeton === "string");
    const active = ligues.some((l) => l.code === brut.active) ? brut.active : (ligues[0]?.code ?? null);
    return { active, ligues };
  } catch {
    return { active: null, ligues: [] };
  }
}

function ecrireStockage(storage, etat) {
  if (!storage) return;
  try { storage.setItem(CLE_STOCKAGE, JSON.stringify(etat)); } catch { /* stockage plein ou privé */ }
}

export function enregistrerLigue(storage, entree) {
  const etat = chargerStockage(storage);
  const code = normaliserCode(entree.code);
  const propre = { code, nom: entree.nom || code, membre_id: entree.membre_id, jeton: entree.jeton, pseudo: entree.pseudo };
  const idx = etat.ligues.findIndex((l) => l.code === code);
  if (idx >= 0) etat.ligues[idx] = { ...etat.ligues[idx], ...propre };
  else etat.ligues.push(propre);
  etat.active = code;
  ecrireStockage(storage, etat);
  return etat;
}

export function selectionnerLigue(storage, code) {
  const etat = chargerStockage(storage);
  if (etat.ligues.some((l) => l.code === code)) {
    etat.active = code;
    ecrireStockage(storage, etat);
  }
  return etat;
}

export function retirerLigue(storage, code) {
  const etat = chargerStockage(storage);
  etat.ligues = etat.ligues.filter((l) => l.code !== code);
  etat.active = etat.ligues[0]?.code ?? null;
  ecrireStockage(storage, etat);
  return etat;
}

// ---------------------------------------------------------------- calcul live (points provisoires + suivi)

export function calculerClassementLive(ligue, directParId = new Map()) {
  const base = (ligue?.classement || []).map((r) => ({ ...r, points_live: 0, live_matchs: 0 }));
  const parMembre = new Map(base.map((r) => [r.membre_id, r]));
  const matchsLigue = ligue?.matchs || {};
  let nbMatchsLive = 0;
  const matchsLiveSet = new Set();

  for (const membre of ligue?.membres || []) {
    const ligne = parMembre.get(membre.id);
    if (!ligne) continue;
    for (const p of membre.pronos || []) {
      if (p.masque || p.hors_delai || typeof p.buts_dom !== "number") continue;
      const meta = matchsLigue[p.match_id];
      if (meta?.score) continue;   // déjà jugé officiellement dans ligue.classement
      const live = directParId.get(p.match_id);
      if (!live || !Array.isArray(live.g) || !Number.isInteger(live.g[0]) || !Number.isInteger(live.g[1])) continue;
      if (live.st === "NS") continue;
      const res = calculerPoints([p.buts_dom, p.buts_ext], live.g, meta?.probas ?? null);
      ligne.points_live += res.points;
      ligne.live_matchs += 1;
      matchsLiveSet.add(p.match_id);
    }
  }
  nbMatchsLive = matchsLiveSet.size;

  const total = (r) => r.points + r.points_live;
  const ecart = (x, y) => total(y) - total(x) || y.scores_exacts - x.scores_exacts || y.bonnes_issues - x.bonnes_issues;
  const tries = [...base].sort((x, y) => ecart(x, y) || x.pseudo.localeCompare(y.pseudo, "fr"));
  let rang = 0;
  const lignes = tries.map((r, i) => {
    if (!i || ecart(tries[i - 1], r)) rang = i + 1;
    return { ...r, rang_affiche: rang, points_total: total(r) };
  });
  return { lignes, nbMatchsLive };
}

export function filtrerMatchsPronosticables(matchs, { comp = "", favoris = null, maintenant = Date.now(), horizonJours = HORIZON_JOURS } = {}) {
  const limite = maintenant + horizonJours * 86400e3;
  return matchs.filter((m) => {
    if (m.etat !== "a_venir" || !m.kickoff) return false;
    const ko = Date.parse(m.kickoff);
    if (!Number.isFinite(ko) || ko <= maintenant || ko > limite) return false;
    if (comp === "FAV") return Boolean(favoris && (favoris.has(m.home) || favoris.has(m.away)));
    if (comp && m.c !== comp) return false;
    return true;
  });
}

// ---------------------------------------------------------------- appels API

async function apiJson(chemin, { method = "GET", body = null, jeton = null } = {}) {
  const headers = {};
  if (body !== null) headers["content-type"] = "application/json";
  if (jeton) headers.authorization = `Bearer ${jeton}`;
  const r = await fetch(`${API_LIGUES}${chemin}`, { method, headers, body: body !== null ? JSON.stringify(body) : undefined, cache: "no-store" });
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    const err = new Error(data?.erreur?.message || `Erreur serveur (${r.status})`);
    err.code = data?.erreur?.code || "erreur_http";
    err.statut = r.status;
    throw err;
  }
  return data;
}

// ---------------------------------------------------------------- interface navigateur

const S = {
  stock: { active: null, ligues: [] },
  ligue: null,              // réponse GET /ligues/:code
  matchs: [],               // tous les matchs des 7 compétitions
  matchParId: new Map(),
  clubs: {},
  directParId: new Map(),   // match_id -> fixture relais
  directMaj: null,
  filtre: "",               // "", "FAV", ou code compétition
  montres: PAGE_MATCHS,
  timersSave: new Map(),
  etatsSave: new Map(),     // match_id -> { texte, cls }
  montrerEntree: false,
};

const el = (id) => document.getElementById(id);
const clubDe = (k) => S.clubs[k] || { nom: String(k || "").split(":").pop(), sigle: String(k || "").split(":").pop().slice(0, 3).toUpperCase() };
const ligueCourante = () => S.stock.ligues.find((l) => l.code === S.stock.active) || null;

function mesPronosMap() {
  const m = new Map();
  if (!S.ligue?.moi) return m;
  const moi = (S.ligue.membres || []).find((x) => x.id === S.ligue.moi);
  for (const p of moi?.pronos || []) {
    if (!p.masque && typeof p.buts_dom === "number") m.set(p.match_id, p);
  }
  return m;
}

function rendreBarre() {
  const barre = el("ligue-barre"), sel = el("ligue-select");
  if (!S.stock.ligues.length) { barre.hidden = true; return; }
  barre.hidden = false;
  sel.innerHTML = S.stock.ligues.map((l) => `<option value="${esc(l.code)}"${l.code === S.stock.active ? " selected" : ""}>${esc(l.nom)} (${esc(l.code)})</option>`).join("");
}

function basculerVues() {
  const active = ligueCourante();
  const voirEntree = !active || S.montrerEntree;
  el("ligue-entree").hidden = !voirEntree;
  el("ligue-vue").hidden = voirEntree;
  el("retour-ligue-wrap").hidden = !active;
  rendreBarre();
}

function rendreEnteteLigue() {
  const loc = ligueCourante(), d = S.ligue;
  if (!loc) return;
  el("l-nom").textContent = d?.nom || loc.nom || loc.code;
  el("l-code").textContent = loc.code;
  el("l-moi").textContent = `Connecté en tant que ${loc.pseudo} (accès enregistré dans ce navigateur).`;
  el("l-maj").textContent = d?.programme_maj_utc ? `Programme mis à jour : ${quand(d.programme_maj_utc)}` : "";
}

function rendreClassement() {
  const table = el("l-classement"), note = el("l-direct-note");
  if (!S.ligue) { table.innerHTML = ""; note.hidden = true; return; }
  const { lignes, nbMatchsLive } = calculerClassementLive(S.ligue, S.directParId);
  note.hidden = !nbMatchsLive;
  if (nbMatchsLive) {
    note.textContent = `${nbMatchsLive} match${nbMatchsLive > 1 ? "s" : ""} en cours : les points provisoires s'ajoutent en temps réel d'après le score actuel.`;
  }
  table.innerHTML = `<thead><tr><th>#</th><th>Joueur</th><th class="num">Pts</th><th class="num">Exacts</th><th class="num">Issues</th><th class="num">Poker</th><th class="num">Jugés</th></tr></thead><tbody>${
    lignes.map((r) => {
      const badges = `${r.est_bot ? '<span class="badge-bot">Bot IA</span>' : ""}${r.membre_id === S.ligue.moi ? '<span class="badge-moi">toi</span>' : ""}`;
      const live = r.points_live > 0 ? `<span class="pts-live" title="Points provisoires en direct">+${r.points_live}</span>` : "";
      return `<tr${r.membre_id === S.ligue.moi ? ' class="total"' : ""}>
        <td class="rang">${r.rang_affiche}</td>
        <td><b>${esc(r.pseudo)}</b>${badges}</td>
        <td class="num"><b>${nombre(r.points_total)}</b>${live}</td>
        <td class="num">${nombre(r.scores_exacts)}</td>
        <td class="num">${nombre(r.bonnes_issues)}</td>
        <td class="num">${nombre(r.coups_de_poker)}</td>
        <td class="num">${nombre(r.matchs_juges)}</td>
      </tr>`;
    }).join("")
  }</tbody>`;
}

function rendreSuivi() {
  const sec = el("sec-suivi"), cont = el("l-suivi");
  if (!S.ligue) { sec.hidden = true; return; }
  const now = Date.now();
  const matchsLigue = S.ligue.matchs || {};
  const ids = Object.keys(matchsLigue).filter((id) => {
    const m = matchsLigue[id];
    return m.commence || m.score != null || (m.coup_envoi && Date.parse(m.coup_envoi) <= now) || S.directParId.has(id);
  });
  if (!ids.length) { sec.hidden = true; cont.innerHTML = ""; return; }
  sec.hidden = false;

  const estLive = (id) => {
    const f = S.directParId.get(id);
    return Boolean(f && typeof DIRECT_EN_JEU !== "undefined" && DIRECT_EN_JEU.has(f.st));
  };
  ids.sort((a, b) => Number(estLive(b)) - Number(estLive(a))
    || String(matchsLigue[b].coup_envoi || "").localeCompare(String(matchsLigue[a].coup_envoi || "")));

  cont.innerHTML = ids.slice(0, 15).map((id) => {
    const meta = matchsLigue[id];
    const mSite = S.matchParId.get(id);
    const [comp, hKey, aKey] = id.split("|");
    const dom = clubDe(mSite?.home || hKey), ext = clubDe(mSite?.away || aKey);
    const live = S.directParId.get(id);
    const enCours = Boolean(live && typeof DIRECT_EN_JEU !== "undefined" && DIRECT_EN_JEU.has(live.st));
    const scoreOfficiel = meta.score;
    const scoreActuel = scoreOfficiel || (live && Number.isInteger(live.g?.[0]) ? live.g : null);
    let etatTxt = meta.coup_envoi ? esc(quand(meta.coup_envoi)) : "";
    const compLabel = esc(COMP_NOMS[comp] || comp);
    if (scoreOfficiel) etatTxt = `${compLabel} · terminé`;
    else if (enCours) {
      const t = typeof minuteMaintenant === "function" ? minuteMaintenant(live, S.directMaj) : { base: live.min, plus: live.plus };
      const mn = live.st === "HT" ? "mi-temps" : (typeof minuteTexte === "function" ? minuteTexte(t) : `${live.min ?? ""}′`);
      etatTxt = `<i class="pastille" aria-hidden="true"></i>${compLabel} · ${esc(mn)}`;
    } else if (live && typeof DIRECT_FINI !== "undefined" && DIRECT_FINI.has(live.st)) {
      etatTxt = `${compLabel} · terminé (calcul officiel en attente)`;
    }

    const lignesMembres = (S.ligue.membres || []).map((mb) => {
      const p = (mb.pronos || []).find((x) => x.match_id === id);
      if (!p || p.masque) return "";
      let ptsHtml = "";
      if (p.hors_delai) {
        ptsHtml = `<span class="note">hors délai</span>`;
      } else if (typeof p.points === "number") {
        const tag = p.score_exact ? '<span class="badge-exact">Exact</span>' : p.coup_de_poker ? '<span class="badge-poker">Poker</span>' : "";
        ptsHtml = `<span class="sp-pts">+${p.points} pt${p.points > 1 ? "s" : ""}</span>${tag}`;
      } else if (scoreActuel && Number.isInteger(scoreActuel[0])) {
        const prov = calculerPoints([p.buts_dom, p.buts_ext], scoreActuel, meta.probas);
        const tag = prov.score_exact ? '<span class="badge-exact">Exact</span>' : prov.coup_de_poker ? '<span class="badge-poker">Poker</span>' : "";
        ptsHtml = `<span class="sp-pts" title="Provisoire">~+${prov.points}</span>${tag}`;
      }
      return `<li><span>${esc(mb.pseudo)}${mb.est_bot ? '<span class="badge-bot">Bot IA</span>' : ""}</span>
        <span><span class="sp-score">${nombre(p.buts_dom)} - ${nombre(p.buts_ext)}</span> ${ptsHtml}</span></li>`;
    }).filter(Boolean).join("");

    return `<article class="suivi-carte">
      <div class="suivi-tete">
        <div class="suivi-affiche">
          <span class="club">${ecusson(dom)}${esc(dom.nom)}</span>
          <span class="suivi-score">${scoreActuel ? `${nombre(scoreActuel[0])} - ${nombre(scoreActuel[1])}` : "–"}</span>
          <span class="club">${ecusson(ext)}${esc(ext.nom)}</span>
        </div>
        <span class="note">${etatTxt}</span>
      </div>
      <ul class="suivi-pronos">${lignesMembres || '<li class="note">Aucun pronostic enregistré.</li>'}</ul>
    </article>`;
  }).join("");
}

function rendreChips() {
  const favs = typeof Favoris !== "undefined" ? Favoris.liste() : [];
  const present = new Set(filtrerMatchsPronosticables(S.matchs).map((m) => m.c));
  const chips = [["", "Toutes"], ...(favs.length ? [["FAV", "Mes favoris"]] : []), ...COMP_ORDRE.map(([c, , n]) => [c, n])];
  el("l-chips").innerHTML = chips.map(([c, label]) => {
    const actif = !c || c === "FAV" || present.has(c);
    return `<button type="button" data-comp="${esc(c)}" aria-pressed="${c === S.filtre}"${actif ? "" : " disabled"}>${esc(label)}</button>`;
  }).join("");
}

function rendrePronos() {
  const cont = el("l-pronos"), note = el("l-pronos-note"), more = el("l-more");
  if (!S.ligue) { cont.innerHTML = ""; more.hidden = true; return; }
  const favSet = typeof Favoris !== "undefined" ? new Set(Favoris.liste()) : null;
  const liste = filtrerMatchsPronosticables(S.matchs, { comp: S.filtre, favoris: favSet });
  if (!liste.length) {
    note.textContent = S.filtre === "FAV"
      ? "Aucun match de tes clubs favoris ouvert aux pronostics dans les 14 prochains jours."
      : "Aucun match ouvert aux pronostics pour ce filtre dans les 14 prochains jours.";
    cont.innerHTML = "";
    more.hidden = true;
    return;
  }
  note.textContent = `${liste.length} match${liste.length > 1 ? "s" : ""} ouvert${liste.length > 1 ? "s" : ""} aux pronostics. Sauvegarde automatique dès que les deux scores sont saisis ; verrouillage au coup d'envoi.`;
  const mes = mesPronosMap(), montres = liste.slice(0, S.montres), now = Date.now();
  let html = "", jourCourant = null, ouvert = false;
  for (const m of montres) {
    if (m.jour !== jourCourant) {
      if (ouvert) html += "</ul>";
      html += `<h3 class="jour-titre">${esc(jourLong(m.jour))}</h3><ul class="prono-liste">`;
      jourCourant = m.jour;
      ouvert = true;
    }
    const dom = clubDe(m.home), ext = clubDe(m.away);
    const p = mes.get(m.id);
    const verrou = estVerrouille(m.kickoff, now);
    const botScore = m.scores?.[0]?.score ? m.scores[0].score.replace("-", " - ") : null;
    const estFav = Boolean(favSet && (favSet.has(m.home) || favSet.has(m.away)));
    const st = S.etatsSave.get(m.id) || (verrou ? { texte: "Verrouillé", cls: "" } : p ? { texte: "Enregistré", cls: "ok" } : { texte: "", cls: "" });
    const midAttr = esc(m.id);
    html += `<li class="prono-item${estFav ? " fav" : ""}" data-match-id="${midAttr}" data-kickoff="${esc(m.kickoff)}">
      <div class="prono-grille">
        <span class="m-heure">${esc(heure(m.kickoff))}<small class="m-comp">${esc(COMP_NOMS[m.c] || m.c)}</small></span>
        <span class="m-club m-dom"><b>${esc(dom.nom)}</b>${ecusson(dom)}</span>
        <div class="prono-centre">
          <div class="prono-inputs">
            <input type="number" min="0" max="20" step="1" inputmode="numeric" data-side="dom" aria-label="Score ${esc(dom.nom)}" value="${p ? p.buts_dom : ""}"${verrou ? " disabled" : ""}>
            <span aria-hidden="true">-</span>
            <input type="number" min="0" max="20" step="1" inputmode="numeric" data-side="ext" aria-label="Score ${esc(ext.nom)}" value="${p ? p.buts_ext : ""}"${verrou ? " disabled" : ""}>
          </div>
          <div class="prono-meta">
            ${botScore ? `<span class="prono-bot">Bot IA : ${esc(botScore)}</span>` : ""}
            <span class="prono-etat ${st.cls}" data-etat>${esc(st.texte)}</span>
          </div>
        </div>
        <span class="m-club m-ext">${ecusson(ext)}<b>${esc(ext.nom)}</b></span>
      </div>
    </li>`;
  }
  if (ouvert) html += "</ul>";
  cont.innerHTML = html;
  more.hidden = liste.length <= S.montres;
}

function majEtatLigne(matchId, texte, cls = "") {
  S.etatsSave.set(matchId, { texte, cls });
  const li = document.querySelector(`li.prono-item[data-match-id="${CSS.escape(matchId)}"]`);
  const span = li?.querySelector("[data-etat]");
  if (span) { span.textContent = texte; span.className = `prono-etat ${cls}`; }
}

async function sauvegarderProno(matchId, dom, ext) {
  const loc = ligueCourante();
  if (!loc) return;
  majEtatLigne(matchId, "Enregistrement…", "");
  try {
    await apiJson(`/${encodeURIComponent(loc.code)}/pronos`, {
      method: "POST", jeton: loc.jeton, body: { match_id: matchId, buts_dom: dom, buts_ext: ext },
    });
    majEtatLigne(matchId, "Enregistré", "ok");
    // rafraîchit la ligue en arrière-plan (pour afficher le Bot IA sur ce match et synchroniser mes pronos)
    chargerLigueActive({ silencieux: true });
  } catch (err) {
    majEtatLigne(matchId, err.code === "match_verrouille" ? "Verrouillé" : err.message, "err");
    if (err.code === "match_verrouille") {
      const li = document.querySelector(`li.prono-item[data-match-id="${CSS.escape(matchId)}"]`);
      li?.querySelectorAll("input").forEach((inp) => { inp.disabled = true; });
    }
  }
}

function verrouillerEchus() {
  const now = Date.now();
  let change = false;
  for (const li of document.querySelectorAll("li.prono-item[data-kickoff]")) {
    if (estVerrouille(li.dataset.kickoff, now)) {
      const inputs = [...li.querySelectorAll("input")];
      if (inputs.some((i) => !i.disabled)) {
        inputs.forEach((i) => { i.disabled = true; });
        majEtatLigne(li.dataset.matchId, "Verrouillé", "");
        change = true;
      }
    }
  }
  if (change) chargerLigueActive({ silencieux: true });
}

// ---------------------------------------------------------------- chargement des données

async function chargerProgramme() {
  const res = await Promise.allSettled(COMP_ORDRE.map(([, slug]) => donnees(`foot/${slug}`)));
  const matchs = [], clubs = {};
  for (let i = 0; i < res.length; i++) {
    if (res[i].status !== "fulfilled") continue;
    const d = res[i].value, comp = COMP_ORDRE[i][0];
    Object.assign(clubs, d.clubs || {});
    for (const m of d.matchs || []) matchs.push({ ...m, c: comp });
  }
  matchs.sort((a, b) => String(a.kickoff || `${a.jour}T23:59`).localeCompare(String(b.kickoff || `${b.jour}T23:59`)));
  S.matchs = matchs;
  S.matchParId = new Map(matchs.map((m) => [m.id, m]));
  S.clubs = clubs;
}

async function chargerDirect() {
  if (typeof lireRelais !== "function" || typeof rattacher !== "function") return;
  try {
    const relais = await lireRelais();
    S.directMaj = relais.maj_utc || null;
    const duJour = S.matchs.filter((m) => m.kickoff);
    const lien = rattacher(duJour, relais.matchs || [], S.clubs);
    S.directParId = new Map([...lien].map(([m, f]) => [m.id, f]));
  } catch { /* direct indisponible : on reste sur les scores officiels */ }
}

async function chargerLigueActive({ silencieux = false } = {}) {
  const loc = ligueCourante();
  if (!loc) { S.ligue = null; basculerVues(); return; }
  if (!silencieux) el("l-statut").textContent = "Chargement de la ligue…";
  try {
    const data = await apiJson(`/${encodeURIComponent(loc.code)}`, { jeton: loc.jeton });
    S.ligue = data;
    if (data.nom && data.nom !== loc.nom) {
      S.stock = enregistrerLigue(localStorage, { ...loc, nom: data.nom });
    }
    el("l-statut").textContent = "";
    await chargerDirect();
    rendreBarre();
    rendreEnteteLigue();
    rendreClassement();
    rendreSuivi();
    if (!silencieux) { rendreChips(); rendrePronos(); }
  } catch (err) {
    el("l-statut").textContent = err.message;
  }
}

// ---------------------------------------------------------------- événements & démarrage

function attacherEvenements() {
  el("form-creer").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nom = el("c-nom").value.trim(), pseudo = el("c-pseudo").value.trim(), msg = el("msg-creer"), btn = el("btn-creer");
    if (nom.length < 3 || nom.length > 40) { msg.className = "form-msg err"; msg.textContent = "Le nom de la ligue doit contenir entre 3 et 40 caractères."; return; }
    if (pseudo.length < 2 || pseudo.length > 20) { msg.className = "form-msg err"; msg.textContent = "Le pseudo doit contenir entre 2 et 20 caractères."; return; }
    msg.className = "form-msg"; msg.textContent = "Création en cours…"; btn.disabled = true;
    try {
      const rep = await apiJson("", { method: "POST", body: { nom, pseudo } });
      S.stock = enregistrerLigue(localStorage, { code: rep.code, nom, membre_id: rep.membre_id, jeton: rep.jeton, pseudo });
      S.montrerEntree = false; S.etatsSave.clear();
      el("form-creer").reset(); msg.textContent = "";
      basculerVues();
      await chargerLigueActive();
    } catch (err) {
      msg.className = "form-msg err"; msg.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  el("form-rejoindre").addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = normaliserCode(el("r-code").value), pseudo = el("r-pseudo").value.trim(), msg = el("msg-rejoindre"), btn = el("btn-rejoindre");
    el("r-code").value = code;
    if (!estCodeValide(code)) { msg.className = "form-msg err"; msg.textContent = "Code invalide (format attendu : ABC-123)."; return; }
    if (pseudo.length < 2 || pseudo.length > 20) { msg.className = "form-msg err"; msg.textContent = "Le pseudo doit contenir entre 2 et 20 caractères."; return; }
    msg.className = "form-msg"; msg.textContent = "Inscription en cours…"; btn.disabled = true;
    try {
      const rep = await apiJson(`/${encodeURIComponent(code)}/rejoindre`, { method: "POST", body: { pseudo } });
      S.stock = enregistrerLigue(localStorage, { code, nom: code, membre_id: rep.membre_id, jeton: rep.jeton, pseudo });
      S.montrerEntree = false; S.etatsSave.clear();
      el("form-rejoindre").reset(); msg.textContent = "";
      basculerVues();
      await chargerLigueActive();
    } catch (err) {
      msg.className = "form-msg err"; msg.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  el("ligue-select").addEventListener("change", async (e) => {
    S.stock = selectionnerLigue(localStorage, e.target.value);
    S.montrerEntree = false; S.etatsSave.clear();
    basculerVues();
    await chargerLigueActive();
  });

  el("btn-nouvelle").addEventListener("click", () => { S.montrerEntree = true; basculerVues(); });
  el("btn-retour-ligue").addEventListener("click", () => { S.montrerEntree = false; basculerVues(); });

  el("btn-inviter").addEventListener("click", async () => {
    const loc = ligueCourante(), btn = el("btn-inviter");
    if (!loc) return;
    const url = lienInvitation(loc.code);
    try {
      await navigator.clipboard.writeText(url);
      btn.textContent = "Lien copié";
      setTimeout(() => { btn.textContent = "Copier le lien d'invitation"; }, 2200);
    } catch {
      el("l-statut").textContent = `Lien d'invitation : ${url}`;
    }
  });

  el("btn-oublier").addEventListener("click", async () => {
    const loc = ligueCourante();
    if (!loc) return;
    if (!confirm(`Retirer « ${loc.nom} » (${loc.code}) de ce navigateur ? Sans ce jeton, tu ne pourras plus modifier tes pronostics avec ce pseudo.`)) return;
    S.stock = retirerLigue(localStorage, loc.code);
    S.ligue = null; S.montrerEntree = !S.stock.active; S.etatsSave.clear();
    basculerVues();
    if (S.stock.active) await chargerLigueActive();
  });

  el("l-chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-comp]");
    if (!b || b.disabled) return;
    S.filtre = b.dataset.comp; S.montres = PAGE_MATCHS;
    rendreChips(); rendrePronos();
  });

  el("l-more").addEventListener("click", () => { S.montres += PAGE_MATCHS; rendrePronos(); });

  el("l-pronos").addEventListener("input", (e) => {
    const inp = e.target.closest("input[data-side]");
    if (!inp) return;
    const li = inp.closest("li.prono-item");
    if (!li) return;
    const matchId = li.dataset.matchId;
    if (estVerrouille(li.dataset.kickoff)) { verrouillerEchus(); return; }
    const dom = lireScoreSaisi(li.querySelector('input[data-side="dom"]').value);
    const ext = lireScoreSaisi(li.querySelector('input[data-side="ext"]').value);
    clearTimeout(S.timersSave.get(matchId));
    if (dom === null || ext === null) {
      majEtatLigne(matchId, "Saisis les deux scores (0 à 20)", "");
      return;
    }
    majEtatLigne(matchId, "Enregistrement…", "");
    S.timersSave.set(matchId, setTimeout(() => sauvegarderProno(matchId, dom, ext), DEBOUNCE_MS));
  });

  document.addEventListener("favoris", () => { if (S.ligue) { rendreChips(); rendrePronos(); } });
}

async function main() {
  S.stock = chargerStockage(localStorage);
  const codeUrl = codeDepuisUrl(location.search);
  if (codeUrl) {
    if (S.stock.ligues.some((l) => l.code === codeUrl)) {
      S.stock = selectionnerLigue(localStorage, codeUrl);
      S.montrerEntree = false;
    } else {
      el("r-code").value = codeUrl;
      S.montrerEntree = true;
    }
  }
  attacherEvenements();
  basculerVues();
  await chargerProgramme();
  if (S.stock.active && !S.montrerEntree) await chargerLigueActive();
  setInterval(verrouillerEchus, VERROU_MS);
  setInterval(async () => {
    if (document.hidden || !ligueCourante() || S.montrerEntree) return;
    await chargerDirect();
    rendreClassement();
    rendreSuivi();
  }, RAFRAICHIR_MS);
}

if (typeof document !== "undefined" && document.getElementById?.("ligue-entree")) {
  main();
}
