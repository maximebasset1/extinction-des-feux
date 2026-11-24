/* Barème des ligues, partagé par le Worker (relais/ligues.js) et le site. Module ES pur : aucune dépendance,
   aucun accès réseau ni stockage, il se charge tel quel dans un navigateur. */

export const BAREME = { issue: 3, ecart: 2, exact: 5 };
export const SEUIL_COUP_DE_POKER = 0.25;     // l'issue annoncée avait strictement moins de 25 % de chances
export const MULTIPLICATEUR_COUP_DE_POKER = 1.5;

/* 0 : victoire à domicile, 1 : nul, 2 : victoire à l'extérieur (même ordre que les probabilités) */
export const issue = (dom, ext) => (dom > ext ? 0 : dom === ext ? 1 : 2);

/* points d'un pronostic [domicile, extérieur] face au score après 90 minutes [domicile, extérieur] ;
   `probas` : [domicile, nul, extérieur] avant le match, ou null (alors pas de coup de poker) */
export function calculerPoints(prono, resultat, probas = null) {
  const [pDom, pExt] = prono, [rDom, rExt] = resultat;
  const obtenue = issue(rDom, rExt);
  const bonneIssue = issue(pDom, pExt) === obtenue;
  const bonEcart = bonneIssue && pDom - pExt === rDom - rExt;
  const exact = pDom === rDom && pExt === rExt;
  const chance = probas?.[obtenue];
  const poker = bonneIssue && typeof chance === "number" && chance < SEUIL_COUP_DE_POKER;
  let points = (bonneIssue ? BAREME.issue : 0) + (bonEcart ? BAREME.ecart : 0) + (exact ? BAREME.exact : 0);
  if (poker) points = Math.ceil(points * MULTIPLICATEUR_COUP_DE_POKER);
  return { points, bonne_issue: bonneIssue, bon_ecart: bonEcart, score_exact: exact, coup_de_poker: poker };
}
