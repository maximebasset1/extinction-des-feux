/* Compte personnel, facultatif (football) : clubs favoris et ligues retrouvés sur tous les appareils connectés.
   Sans compte, rien n'est envoyé : tout reste dans ce navigateur. Avec un compte, la liste des favoris est enregistrée
   par le Worker (routes /comptes, relais/ligues.js) et `localStorage` n'en est plus que la copie lue par les pages.
   Ce fichier tient aussi le bouton de la barre principale, son menu et la fenêtre « Connexion / Créer un compte ». */
"use strict";

const Compte = (() => {
  const API = "https://extinction-direct.maximebasset1.workers.dev/comptes";
  const CLE_COMPTE = "extinction.compte.v1";
  const CLE_LIGUES = "extinction_ligues_v1";     // même stockage que ligues.js
  const MAX_FAVORIS = 20;                        // par compte (relais/ligues.js)
  const MAX_FAVORIS_LOCAUX = 100;                // sans compte (favoris.js)
  const RATTACHER_MAX = 20;                      // ligues par demande
  const FORMAT_CLUB = /^[A-Z]{2,4}:[^\p{C}<>]{1,60}$/u;

  const estClub = (v) => typeof v === "string" && FORMAT_CLUB.test(v);
  const signature = (stock) => JSON.stringify([stock.active, stock.ligues.map((l) => [l.code, l.nom, l.membre_id, l.pseudo, l.jeton, l.compte || null])]);

  /* ---------- ligues gardées par le navigateur : la liste du serveur fait foi pour celles du compte */
  function fusionnerLigues(stock, duCompte, compteId) {
    const recues = new Map(duCompte.map((l) => [l.code, l]));
    const ligues = [];
    const rattachee = (locale, s) => {
      // un autre joueur gardé par ce navigateur dans la même ligue : mis de côté, rendu à la déconnexion
      const anonyme = locale?.anonyme || (locale && !locale.compte && locale.membre_id !== s.membre_id
        ? { membre_id: locale.membre_id, jeton: locale.jeton, pseudo: locale.pseudo } : null);
      return { ...locale, code: s.code, nom: s.nom, membre_id: s.membre_id, pseudo: s.pseudo, jeton: s.jeton, compte: compteId,
        ...(anonyme ? { anonyme } : {}) };
    };
    for (const l of stock.ligues) {
      const s = recues.get(l.code);
      if (s) { ligues.push(rattachee(l, s)); recues.delete(l.code); }
      else if (l.compte !== compteId) ligues.push(l);
      else if (l.anonyme) ligues.push({ code: l.code, nom: l.nom, ...l.anonyme });
    }
    for (const s of recues.values()) ligues.push(rattachee(null, s));
    const active = ligues.some((l) => l.code === stock.active) ? stock.active : (ligues[0]?.code ?? null);
    return { active, ligues };
  }
  const retirerLiguesDuCompte = (stock, compteId) => fusionnerLigues(stock, [], compteId);

  /* ---------- le compte, sans rien du navigateur (testé sous Node avec le vrai Worker)
     `favoris` : { liste(), remplacer(liste) } ; `signaler` reçoit "compte", "ligues", "session_expiree", "favoris_coupes" */
  function creerClientCompte({ stockage, requete, favoris, signaler = () => {} }) {
    let touches = 0;            // favoris modifiés ici : une réponse demandée avant ne les écrase pas
    let liguesTouchees = 0;     // ligue créée, rejointe ou quittée ici : même principe
    let file = Promise.resolve();   // un seul envoi de favoris à la fois, dans l'ordre

    const lireJson = (cle) => { try { return JSON.parse(stockage.getItem(cle) || "null"); } catch { return null; } };
    const ecrireJson = (cle, v) => { try { stockage.setItem(cle, JSON.stringify(v)); } catch { /* stockage plein ou privé */ } };
    const lire = () => { const c = lireJson(CLE_COMPTE); return c?.compte_id && c?.jeton ? c : null; };
    const modifier = (champs) => ecrireJson(CLE_COMPTE, { ...lire(), ...champs });
    const effacer = () => { try { stockage.removeItem(CLE_COMPTE); } catch { /* rien à effacer */ } };
    const memeSession = (jeton) => lire()?.jeton === jeton;
    const lireLigues = () => { const s = lireJson(CLE_LIGUES); return Array.isArray(s?.ligues) ? s : { active: null, ligues: [] }; };
    function garderLigues(neuf) {
      if (signature(neuf) === signature(lireLigues())) return;
      ecrireJson(CLE_LIGUES, neuf);
      signaler("ligues");
    }
    const clubsLocaux = () => favoris.liste().filter(estClub);

    async function appel(chemin, { method = "GET", corps, jeton } = {}) {
      const headers = {};
      if (corps !== undefined) headers["content-type"] = "application/json";
      if (jeton) headers.authorization = `Bearer ${jeton}`;
      let r;
      try {
        // keepalive : un favori envoyé juste avant de changer de page arrive quand même
        r = await requete(`${API}${chemin}`, { method, headers, body: corps === undefined ? undefined : JSON.stringify(corps),
          cache: "no-store", keepalive: method === "PUT" });
      } catch {
        throw Object.assign(new Error("Connexion impossible. Vérifie ton réseau."), { code: "hors_ligne", statut: 0 });
      }
      const data = await r.json().catch(() => null);
      if (!r.ok) {
        throw Object.assign(new Error(data?.erreur?.message || `Erreur serveur (${r.status})`),
          { code: data?.erreur?.code || "erreur_http", statut: r.status });
      }
      return data;
    }

    /* session fermée côté serveur : les ligues du compte quittent le navigateur, les favoris y restent */
    function expirer() {
      const c = lire();
      if (!c) return;
      garderLigues(retirerLiguesDuCompte(lireLigues(), c.compte_id));
      effacer();
      signaler("session_expiree");
      signaler("compte");
    }
    const surEchec = (err, jeton) => { if (err.statut === 401 && memeSession(jeton)) expirer(); };

    function envoyerEnAttente() {
      file = file.then(async () => {
        const c = lire();
        // tant que le rattachement n'est pas fait, un envoi écraserait les favoris du compte avant la fusion
        if (!c?.a_envoyer || c.a_rattacher) return;
        const avant = touches;
        try {
          await appel("/favoris", { method: "PUT", jeton: c.jeton, corps: { favoris: clubsLocaux().slice(0, MAX_FAVORIS) } });
          if (memeSession(c.jeton) && avant === touches) modifier({ a_envoyer: false });
        } catch (err) {
          surEchec(err, c.jeton);   // hors ligne : repris à la prochaine synchronisation
        }
      });
      return file;
    }

    /* un favori ajouté ou retiré par l'utilisateur */
    function favorisModifies() {
      if (!lire()) return Promise.resolve();
      touches += 1;
      modifier({ a_envoyer: true });
      return envoyerEnAttente();
    }

    /* ligues et favoris de ce navigateur joints au compte ; la réponse donne la liste complète du compte */
    async function rattacher() {
      const c = lire();
      if (!c) return;
      const anonymes = lireLigues().ligues.filter((l) => !l.compte && l.jeton).map((l) => ({ code: l.code, jeton: l.jeton }));
      const locaux = clubsLocaux().slice(0, MAX_FAVORIS_LOCAUX);
      const avant = touches, liguesAvant = liguesTouchees;
      let rep = null;
      for (let i = 0; !rep || i < anonymes.length; i += RATTACHER_MAX) {
        rep = await appel("/rattacher", { method: "POST", jeton: c.jeton,
          corps: { ligues: anonymes.slice(i, i + RATTACHER_MAX), favoris: i ? [] : locaux } });
        if (!memeSession(c.jeton)) return;
      }
      modifier({ a_rattacher: false, a_envoyer: avant !== touches });
      if (avant === touches) {
        if (locaux.some((k) => !rep.favoris.includes(k))) signaler("favoris_coupes");
        favoris.remplacer(rep.favoris);
      } else {
        favoris.remplacer([...new Set([...clubsLocaux(), ...rep.favoris])].slice(0, MAX_FAVORIS));
        envoyerEnAttente();
      }
      if (liguesAvant === liguesTouchees) garderLigues(fusionnerLigues(lireLigues(), rep.ligues, c.compte_id));
    }

    /* à l'ouverture d'une page : envoie ce qui attend, puis reprend favoris et ligues du compte */
    async function synchroniser() {
      const c = lire();
      if (!c) return;
      try {
        if (c.a_rattacher) { await rattacher(); await file; return; }
        await envoyerEnAttente();
        if (!memeSession(c.jeton)) return;
        const avant = touches, liguesAvant = liguesTouchees;
        const rep = await appel("/moi", { jeton: c.jeton });
        if (!memeSession(c.jeton)) return;
        if (avant === touches && !lire().a_envoyer) favoris.remplacer(rep.favoris);
        if (liguesAvant === liguesTouchees) garderLigues(fusionnerLigues(lireLigues(), rep.ligues, c.compte_id));
      } catch (err) {
        surEchec(err, c.jeton);   // relais injoignable : le navigateur garde ce qu'il a
      }
    }

    async function ouvrir(route, pseudo, motDePasse) {
      const rep = await appel(`/${route}`, { method: "POST", corps: { pseudo, mot_de_passe: motDePasse } });
      const ancien = lire();
      if (ancien && ancien.compte_id !== rep.compte_id) garderLigues(retirerLiguesDuCompte(lireLigues(), ancien.compte_id));
      ecrireJson(CLE_COMPTE, { compte_id: rep.compte_id, pseudo: rep.pseudo, jeton: rep.jeton_compte, a_rattacher: true, a_envoyer: false });
      signaler("compte");
      try {
        await rattacher();
      } catch (err) {
        // connecté malgré tout : on montre déjà ce que le compte contient, le rattachement sera repris
        favoris.remplacer([...new Set([...clubsLocaux(), ...(rep.favoris || [])])]);
        garderLigues(fusionnerLigues(lireLigues(), rep.ligues || [], rep.compte_id));
        surEchec(err, rep.jeton_compte);
      }
    }

    async function deconnecter() {
      if (!lire()) return;
      await envoyerEnAttente();
      const c = lire();
      if (!c) return;                              // session expirée pendant l'envoi : déjà nettoyé
      const toutEnvoye = !c.a_envoyer && !c.a_rattacher;
      try { await appel("/deconnexion", { method: "POST", corps: {}, jeton: c.jeton }); } catch { /* le navigateur oublie quand même */ }
      garderLigues(retirerLiguesDuCompte(lireLigues(), c.compte_id));
      effacer();
      if (toutEnvoye) favoris.remplacer([]);       // ils sont sur le compte : rien à laisser sur un appareil partagé
      signaler("compte");
    }

    async function detacher(code) {
      const c = lire();
      if (!c) return;
      try {
        await appel("/detacher", { method: "POST", corps: { code }, jeton: c.jeton });
      } catch (err) {
        surEchec(err, c.jeton);
        throw err;
      }
      liguesTouchees += 1;
    }

    return {
      lire, synchroniser, favorisModifies, deconnecter, detacher, expirer,
      inscrire: (pseudo, motDePasse) => ouvrir("inscription", pseudo, motDePasse),
      connecter: (pseudo, motDePasse) => ouvrir("connexion", pseudo, motDePasse),
      jeton: () => lire()?.jeton ?? null,
      liguesModifiees: () => { liguesTouchees += 1; },
    };
  }

  const outils = { API, CLE_COMPTE, CLE_LIGUES, MAX_FAVORIS, fusionnerLigues, retirerLiguesDuCompte, creerClientCompte };
  if (typeof document === "undefined") return outils;

  /* ---------------------------------------------------------------- dans la page */
  const el = (id) => document.getElementById(id);

  /* stockage refusé par le navigateur : le compte tient jusqu'à la fermeture de la page */
  function stockageSur() {
    const memoire = new Map();
    return {
      getItem: (k) => { try { return localStorage.getItem(k); } catch { return memoire.get(k) ?? null; } },
      setItem: (k, v) => { try { localStorage.setItem(k, v); } catch { memoire.set(k, v); } },
      removeItem: (k) => { memoire.delete(k); try { localStorage.removeItem(k); } catch { /* déjà absent */ } },
    };
  }

  let minuterie = null;
  function annoncer(texte) {
    const avis = el("avis-compte");
    if (!avis) return;
    avis.textContent = texte;
    avis.classList.add("visible");
    clearTimeout(minuterie);
    minuterie = setTimeout(() => { avis.classList.remove("visible"); avis.textContent = ""; }, 5000);
  }

  const AVIS = {
    session_expiree: "Session expirée : reconnecte-toi.",
    favoris_coupes: `Ton compte garde ${MAX_FAVORIS} clubs au plus : les suivants n'ont pas été repris.`,
  };
  const client = creerClientCompte({
    stockage: stockageSur(),
    requete: (url, init) => fetch(url, init),
    favoris: typeof Favoris !== "undefined" ? Favoris : { liste: () => [], remplacer: () => {} },
    signaler: (quoi) => {
      if (AVIS[quoi]) annoncer(AVIS[quoi]);
      if (quoi === "compte") { rendreBouton(); document.dispatchEvent(new CustomEvent("compte")); }
      if (quoi === "ligues") document.dispatchEvent(new CustomEvent("ligues-compte"));
    },
  });

  function fermerMenu() {
    const menu = el("menu-compte"), bouton = el("btn-compte");
    if (!menu || menu.hidden) return false;
    menu.hidden = true;
    bouton.setAttribute("aria-expanded", "false");
    return true;
  }

  /* « Connexion », ou le pseudo qui ouvre le menu du compte */
  function rendreBouton() {
    const bouton = el("btn-compte");
    if (!bouton) return;
    const c = client.lire();
    fermerMenu();
    bouton.hidden = false;
    bouton.textContent = c ? c.pseudo : "Connexion";
    bouton.classList.toggle("connecte", Boolean(c));
    if (c) {
      bouton.setAttribute("aria-expanded", "false");
      bouton.setAttribute("aria-controls", "menu-compte");
      bouton.setAttribute("aria-label", `Compte de ${c.pseudo}`);
      bouton.removeAttribute("aria-haspopup");
    } else {
      bouton.setAttribute("aria-haspopup", "dialog");
      for (const a of ["aria-expanded", "aria-controls", "aria-label"]) bouton.removeAttribute(a);
    }
  }

  const MODES = {
    connexion: { titre: "Connexion", valider: "Se connecter", saisie: "current-password", aide: "" },
    inscription: { titre: "Créer un compte", valider: "Créer le compte", saisie: "new-password",
      aide: "4 caractères au minimum. Sans adresse e-mail, un mot de passe oublié est perdu. N'en reprends pas un qui sert ailleurs." },
  };
  let mode = "connexion";
  function choisirMode(neuf) {
    mode = neuf;
    const m = MODES[mode];
    el("dlg-compte-titre").textContent = m.titre;
    el("btn-compte-valider").textContent = m.valider;
    el("compte-mdp").setAttribute("autocomplete", m.saisie);
    el("compte-aide").textContent = m.aide;
    el("compte-aide").hidden = !m.aide;
    el("compte-msg").textContent = "";
    for (const b of el("dlg-compte").querySelectorAll("button[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
  }

  function ouvrirFenetre() {
    const dlg = el("dlg-compte");
    if (!dlg || dlg.open) return;
    el("form-compte").reset();
    choisirMode("connexion");
    dlg.showModal();
    el("compte-pseudo").focus();
  }

  async function valider(e) {
    e.preventDefault();
    const msg = el("compte-msg"), bouton = el("btn-compte-valider");
    const pseudo = el("compte-pseudo").value.trim(), mdp = el("compte-mdp").value;
    const refuser = (texte) => { msg.className = "form-msg err"; msg.textContent = texte; };
    if (pseudo.length < 2 || pseudo.length > 24) return refuser("Pseudo : de 2 à 24 caractères.");
    if (mdp.length < 4) return refuser("Mot de passe : 4 caractères au minimum.");
    msg.className = "form-msg";
    msg.textContent = mode === "inscription" ? "Création en cours…" : "Connexion en cours…";
    bouton.disabled = true;
    try {
      await client[mode === "inscription" ? "inscrire" : "connecter"](pseudo, mdp);
      el("form-compte").reset();
      el("dlg-compte").close();
      el("btn-compte").focus();
    } catch (err) {
      refuser(err.message);
    } finally {
      bouton.disabled = false;
    }
  }

  function brancher() {
    const bouton = el("btn-compte");
    if (!bouton) return;
    bouton.addEventListener("click", () => {
      if (!client.lire()) { ouvrirFenetre(); return; }
      if (fermerMenu()) return;
      el("menu-compte").hidden = false;
      bouton.setAttribute("aria-expanded", "true");
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".compte-zone") || e.target.closest(".compte-menu a")) fermerMenu(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && fermerMenu()) bouton.focus(); });
    el("menu-compte")?.parentElement.addEventListener("focusout", (e) => {
      if (e.relatedTarget && !e.relatedTarget.closest(".compte-zone")) fermerMenu();
    });
    el("btn-deconnexion")?.addEventListener("click", async () => {
      fermerMenu();
      await client.deconnecter();
      bouton.focus();
    });

    const dlg = el("dlg-compte");
    dlg?.addEventListener("click", (e) => {
      if (e.target === dlg || e.target.closest(".compte-fermer")) dlg.close();     // clic hors de la fenêtre : fermeture
      const b = e.target.closest("button[data-mode]");
      if (b) choisirMode(b.dataset.mode);
    });
    dlg?.addEventListener("close", () => el("form-compte").reset());               // le mot de passe ne reste pas dans la page
    el("form-compte")?.addEventListener("submit", valider);
    rendreBouton();
  }

  if (typeof Favoris !== "undefined") {
    Favoris.fixerLimite(() => (client.lire() ? MAX_FAVORIS : MAX_FAVORIS_LOCAUX));
    // seuls les gestes de l'utilisateur portent un club : une liste reçue du compte n'est pas renvoyée
    document.addEventListener("favoris", (e) => { if (e.detail?.club) client.favorisModifies(); });
    document.addEventListener("favoris-plein", (e) => annoncer(`${e.detail.max} clubs favoris au maximum.`));
  }
  // connexion ou déconnexion faite dans un autre onglet
  window.addEventListener("storage", (e) => {
    if (e.key !== CLE_COMPTE) return;
    rendreBouton();
    document.dispatchEvent(new CustomEvent("compte"));
    document.dispatchEvent(new CustomEvent("ligues-compte"));
  });
  brancher();
  client.synchroniser();

  return { ...outils, ...client };
})();

if (typeof module !== "undefined") module.exports = Compte;
