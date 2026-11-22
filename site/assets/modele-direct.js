/* Chances en direct : même calcul que football/live.py, fait dans le navigateur.
   Entrées : buts attendus du match (calés sur le pronostic publié), score, mi-temps et temps restant. */
"use strict";

const DIRECT = {
  MINUTES_MI_TEMPS: [48, 52],   // arrêts de jeu compris : doit rester égal à HALF_MINUTES (live.py)
  PAS_PAR_MI_TEMPS: 10,
  BUTS_MAX: 10,
};
const SCORES_MONTRES = 5;   // scores finaux les plus probables gardés (la fiche du match en montre cinq)

/* rythme selon l'écart au score vu par l'équipe (mené de 2 ou plus ... mène de 2 ou plus) */
function multiplicateur(params, ecart) {
  const m = params.rythme_selon_ecart;
  return m[Math.max(-2, Math.min(2, ecart)) + 2];
}

/* fait avancer la loi des buts ajoutés (k × k) de `minutes` à un rythme par minute `rythme` */
function avancer(loi, lh, la, ecart0, rythme, minutes, params) {
  const k = loi.length, pas = params.pas_par_mi_temps || DIRECT.PAS_PAR_MI_TEMPS, dt = minutes / pas;
  const p3 = (mu) => { const p0 = Math.exp(-mu), p1 = mu * p0; return [p0, p1, Math.max(0, 1 - p0 - p1)]; };
  const ph = [], pa = [];
  for (let i = 0; i < k; i++) {
    ph.push([]); pa.push([]);
    for (let j = 0; j < k; j++) {
      const e = ecart0 + i - j;
      ph[i].push(p3(lh * rythme * multiplicateur(params, e) * dt));
      pa[i].push(p3(la * rythme * multiplicateur(params, -e) * dt));
    }
  }
  for (let s = 0; s < pas; s++) {
    const out = Array.from({ length: k }, () => new Float64Array(k));
    for (let i = 0; i < k; i++) {
      for (let j = 0; j < k; j++) {
        const w = loi[i][j];
        if (!w) continue;
        for (let a = 0; a < 3; a++) {
          for (let b = 0; b < 3; b++) out[Math.min(i + a, k - 1)][Math.min(j + b, k - 1)] += w * ph[i][j][a] * pa[i][j][b];
        }
      }
    }
    loi = out;
  }
  return loi;
}

/* loi des buts encore à marquer ; miTemps : 0 avant le coup d'envoi, 1, 2, 3 terminé ; reste : part de la mi-temps à jouer */
function resteAJouer(lh, la, hg, ag, miTemps, reste, params) {
  const k = DIRECT.BUTS_MAX + 1;
  let loi = Array.from({ length: k }, () => new Float64Array(k));
  loi[0][0] = 1;
  if (miTemps >= 3) return loi;
  const s1 = params.part_1re_mi_temps, [m1, m2] = params.minutes_mi_temps || DIRECT.MINUTES_MI_TEMPS;
  if (miTemps <= 1) {
    loi = avancer(loi, lh, la, hg - ag, s1 / m1, (miTemps === 0 ? 1 : reste) * m1, params);
    return avancer(loi, lh, la, hg - ag, (1 - s1) / m2, m2, params);
  }
  return avancer(loi, lh, la, hg - ag, (1 - s1) / m2, reste * m2, params);
}

/* chances de victoire domicile, de nul et de victoire extérieur à la fin, et scores finaux les plus probables */
function chancesEnDirect(lh, la, hg, ag, miTemps, reste, params) {
  const loi = resteAJouer(lh, la, hg, ag, miTemps, reste, params), k = loi.length, p = [0, 0, 0], scores = [];
  for (let i = 0; i < k; i++) {
    for (let j = 0; j < k; j++) {
      const d = hg + i - (ag + j);
      p[d > 0 ? 0 : d === 0 ? 1 : 2] += loi[i][j];
      if (loi[i][j] > 0) scores.push({ score: `${hg + i}-${ag + j}`, p: loi[i][j] });
    }
  }
  scores.sort((x, y) => y.p - x.p);
  return { p, scores: scores.slice(0, SCORES_MONTRES) };
}

/* minute affichée (« 67 », « 45+2 ») -> mi-temps et part de cette mi-temps encore à jouer */
function tempsRestant(minute, miTemps, params = {}) {
  const [m1, m2] = params.minutes_mi_temps || DIRECT.MINUTES_MI_TEMPS;
  const [base = 0, plus = 0] = String(minute).split("+").map((x) => parseInt(x, 10) || 0);
  const ecoule = base + plus;
  // dans les arrêts de jeu, il reste toujours un peu de temps tant que l'arbitre n'a pas sifflé
  if (miTemps === 1) return { miTemps: 1, reste: Math.max(0.5, m1 - ecoule) / m1 };
  return { miTemps: 2, reste: Math.max(0.5, m2 - (ecoule - 45)) / m2 };
}

/* score au bout de `t` minutes de jeu d'après la chronologie `ev` ([[minute, arrêts, buts dom., buts ext.], ...]) ;
   les arrêts de jeu comptent dans la minute de leur mi-temps (45+2 -> 45), l'axe de la courbe va de 0 à 90 */
function scoreA(ev, t) {
  let s = [0, 0];
  for (const [min, , h, a] of ev) if (min <= t) s = [h, a];
  return s;
}

/* chronologie à défaut de `ev` (relais plus ancien) : score à la pause puis score du moment, ce que le relais publiait déjà */
function chronologieDe(f, minuteActuelle) {
  if (Array.isArray(f.ev)) return f.ev;
  const ev = [], entier = Number.isInteger;
  const [mh, ma] = f.mt || [];
  if (entier(mh) && entier(ma) && (mh || ma)) ev.push([45, 0, mh, ma]);
  const [h, a] = f.g || [];
  const [dh, da] = ev.length ? ev[0].slice(2) : [0, 0];
  if (entier(h) && entier(a) && (h !== dh || a !== da)) ev.push([Math.max(minuteActuelle || 0, ev.length ? 46 : 1), 0, h, a]);
  return ev;
}

/* chances 1/N/2 à chaque minute de jeu, du coup d'envoi (0') à `jusqua`, recalculées avec le score connu à ce moment-là ;
   `lh`, `la` : buts attendus du match, calés sur le pronostic publié, donc la courbe part de ce pronostic ;
   un point de plus à la minute de chaque but relevé, pour que la marche tombe au bon endroit ;
   `pause` : le dernier point est la mi-temps (seconde période entière à jouer) ; `termine` : le score à 90' est acquis */
function courbeChances(lh, la, ev, jusqua, params, { pas = 3, pause = false, termine = false } = {}) {
  const fin = Math.max(0, Math.min(90, jusqua)), minutes = new Set([fin]);
  for (let t = 0; t < fin; t += pas) minutes.add(t);
  for (const [min] of ev) if (min > 0 && min < fin) minutes.add(min);
  return [...minutes].sort((x, y) => x - y).map((t) => {
    const [hg, ag] = scoreA(ev, t);
    const mi = t === 0 ? 0 : t === 45 && t === fin && pause ? 2 : t <= 45 ? 1 : t >= 90 && termine ? 3 : 2;
    const reste = mi === 0 || mi === 3 ? 1 : tempsRestant(mi === 2 && t === 45 ? "45" : String(t), mi, params).reste;
    return { t, score: [hg, ag], p: chancesEnDirect(lh, la, hg, ag, mi, reste, params).p };
  });
}

if (typeof module !== "undefined") module.exports = { DIRECT, resteAJouer, chancesEnDirect, tempsRestant, scoreA, chronologieDe, courbeChances };
