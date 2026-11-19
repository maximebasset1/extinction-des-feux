"""Plateforme F1 : probabilités de pole et de victoire, historique prédictions vs résultats.

Lancer :  streamlit run app.py   (ou double-clic sur Lancer_plateforme.bat)
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "reports" / "results"
FIGURES = ROOT / "reports" / "figures"
PROCESSED = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "src"))
from report import DRIVER_NAMES, SCHEDULE, TEAM_COLORS  # noqa: E402

st.set_page_config(page_title="F1 · Probabilités de pole", page_icon="🏁", layout="wide")


# ------------------------------------------------------------------ données
@st.cache_data
def load(name: str) -> pd.DataFrame:
    path = RESULTS / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


@st.cache_data
def load_meta() -> dict:
    path = RESULTS / "meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@st.cache_data
def load_processed(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def name(code: str) -> str:
    return DRIVER_NAMES.get(code, code)


def pct(p: float) -> str:
    if pd.isna(p):
        return "–"
    return "< 1 %" if p < 0.01 else f"{100 * p:.0f} %"


def prob_chart(df: pd.DataFrame, col: str, top: int = 12) -> alt.Chart:
    d = df.sort_values(col, ascending=False).head(top).copy()
    d["pilote"] = d["driver"].map(name)
    d["proba"] = 100 * d[col]
    d["étiquette"] = d[col].map(pct)
    color = alt.Color("team:N", scale=alt.Scale(domain=list(TEAM_COLORS), range=list(TEAM_COLORS.values())),
                      legend=None)
    base = alt.Chart(d).encode(y=alt.Y("pilote:N", sort="-x", title=None))
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("proba:Q", title="Probabilité (%)"), color=color,
        tooltip=[alt.Tooltip("pilote:N"), alt.Tooltip("team:N", title="Équipe"), alt.Tooltip("étiquette:N", title="Probabilité")])
    text = base.mark_text(align="left", dx=4).encode(x="proba:Q", text="étiquette:N")
    return (bars + text).properties(height=34 * len(d))


def refresh() -> None:
    with st.status("Mise à jour en cours…", expanded=True) as status:
        log = st.empty()
        lines = []
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}   # accents corrects sous Windows
        proc = subprocess.Popen([sys.executable, "-X", "utf8", "-u", str(ROOT / "src" / "main.py")], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", env=env)
        start = time.time()
        for line in proc.stdout:
            if line.strip():
                lines.append(line.rstrip())
                log.code("\n".join(lines[-12:]))
            if time.time() - start > 1800:   # 30 min max (réseau coupé...)
                proc.kill()
                break
        proc.wait()
        if proc.returncode == 0:
            status.update(label="Données à jour", state="complete")
            st.cache_data.clear()
            st.rerun()
        else:
            status.update(label="La mise à jour a échoué (voir le journal ci-dessus)", state="error")


# ------------------------------------------------------------------ barre latérale
meta = load_meta()
with st.sidebar:
    st.title("🏁 F1 · Probabilités")
    st.caption("Projet de statistiques et de machine learning")
    if st.button("🔄 Recharger les données", type="primary", width="stretch"):
        refresh()
    st.caption("Télécharge les nouvelles séances puis recalcule (quelques secondes à quelques minutes).")
    if meta:
        st.markdown(f"**Dernier calcul :** {meta['calcule_le']}")
        st.markdown(f"**Informations utilisées :** {meta['statut']}")
    st.divider()
    if st.button("⏹ Arrêter la plateforme", width="stretch"):
        st.success("Plateforme arrêtée. Tu peux fermer cet onglet.")
        time.sleep(1)
        os._exit(0)
    st.divider()
    st.markdown("**Horaires (heure de Paris)**")
    for s, t in SCHEDULE:
        st.markdown(f"- {s} : {t}")

if not meta:
    st.warning("Aucun résultat pour l'instant : clique sur « Recharger les données » dans le menu de gauche.")
    st.stop()

gp, season = meta["grand_prix"], meta["saison"]
tab_next, tab_hist, tab_perf, tab_drivers, tab_method = st.tabs(
    ["Prochain GP", "Historique : prédit vs réel", "Le modèle est-il bon ?", "Pilotes", "Méthode"])

# ------------------------------------------------------------------ 1. prochain GP
with tab_next:
    pred = load("probabilites_pole.csv")
    win = load("probabilites_victoire.csv")
    st.header(f"Grand Prix de {gp} {season}")
    has_fp = "proba_pole_apres" in pred
    col = "proba_pole_apres" if has_fp else "proba_pole_avant"
    c1, c2, c3 = st.columns(3)
    lead = pred.sort_values(col, ascending=False).iloc[0]
    c1.metric("Favori pour la pole", name(lead["driver"]), pct(lead[col]))
    c2.metric("Pilotes à plus de 10 %", int((pred[col] > 0.10).sum()))
    c3.metric("Séances prises en compte", meta["statut"].replace("avant le week-end (aucun essai libre disponible)", "aucune"))

    left, right = st.columns(2)
    with left:
        st.subheader("Probabilités de pole")
        st.altair_chart(prob_chart(pred, col), width="stretch")
        if has_fp:
            with st.expander("Comparer avec la prédiction d'avant le week-end"):
                comp = pred[["driver", "team", "proba_pole_avant", "proba_pole_apres"]].copy()
                comp["pilote"] = comp["driver"].map(name)
                comp["évolution"] = (100 * (comp["proba_pole_apres"] - comp["proba_pole_avant"])).round(1)
                st.dataframe(comp[["pilote", "team", "proba_pole_avant", "proba_pole_apres", "évolution"]]
                             .style.format({"proba_pole_avant": "{:.1%}", "proba_pole_apres": "{:.1%}",
                                            "évolution": "{:+.1f} pts"}), hide_index=True, width="stretch")
    with right:
        st.subheader("Probabilités de victoire en course")
        if not meta.get("qualif_disputee"):
            st.caption("Pré-estimation : la grille n'est pas encore connue, elle est déduite du modèle de pole. "
                       "Le chiffre sera plus fiable une fois la qualif disputée.")
        st.altair_chart(prob_chart(win.rename(columns={"proba_victoire": "p"}), "p"), width="stretch")

    st.info(f"**Comment lire :** les écarts entre les premiers sont plus petits que l'incertitude du modèle. "
            f"Une probabilité de 15 % signifie que, sur 100 week-ends identiques, ce pilote ferait la pole environ 15 fois. "
            f"Hypothèse : piste sèche.")

# ------------------------------------------------------------------ 2. historique
with tab_hist:
    hist = load("historique_pole.csv")
    hrace = load("historique_course.csv")
    st.header("Ce que le modèle annonçait, et ce qui s'est passé")
    st.caption("Chaque probabilité a été calculée uniquement avec les courses précédentes, comme si on l'avait "
               "publiée avant la qualif.")
    seasons = sorted(hist["season"].unique(), reverse=True)
    s_sel = st.segmented_control("Saison", seasons, default=seasons[0])
    h = hist[hist["season"] == s_sel]
    model_col = st.radio("Modèle", ["p_apres", "p_avant"], horizontal=True,
                         format_func={"p_apres": "Après les essais libres", "p_avant": "Avant le week-end"}.get)

    # vue saison : probabilité donnée au vrai poleman, course par course
    winners = h[h["is_pole"]].copy()
    winners["rang_du_poleman"] = [
        int((h[(h["grand_prix"] == g)][model_col] > p).sum() + 1) for g, p in zip(winners["grand_prix"], winners[model_col])]
    winners["pilote"] = winners["driver"].map(name)
    winners["proba"] = 100 * winners[model_col]
    k1, k2, k3 = st.columns(3)
    k1.metric("Qualifs", len(winners))
    k2.metric("Poleman = favori du modèle", f"{int((winners['rang_du_poleman'] == 1).sum())} / {len(winners)}")
    k3.metric("Poleman dans le top 3 du modèle", f"{int((winners['rang_du_poleman'] <= 3).sum())} / {len(winners)}")
    chart = alt.Chart(winners).mark_bar().encode(
        x=alt.X("grand_prix:N", sort=alt.SortField("date"), title=None),
        y=alt.Y("proba:Q", title="Probabilité donnée au vrai poleman (%)"),
        color=alt.Color("rang_du_poleman:Q", scale=alt.Scale(scheme="redyellowgreen", reverse=True, domain=[1, 8]),
                        title="Rang dans le modèle"),
        tooltip=["grand_prix", "pilote", alt.Tooltip("proba:Q", format=".1f"), "rang_du_poleman"])
    rule = alt.Chart(pd.DataFrame({"y": [100 / 22]})).mark_rule(strokeDash=[4, 4]).encode(y="y:Q")
    st.altair_chart((chart + rule).properties(height=320), width="stretch")
    st.caption("Ligne pointillée : 4,5 %, la chance d'un pilote tiré au hasard.")

    st.subheader("Détail d'un Grand Prix")
    gps = winners.sort_values("date")["grand_prix"].tolist()
    g_sel = st.selectbox("Grand Prix", gps, index=len(gps) - 1)
    d = h[h["grand_prix"] == g_sel].copy()
    d["pilote"] = d["driver"].map(name)
    qpos = load_processed("best_laps.csv")
    qpos = qpos[(qpos["session"] == "Qualifying") & (qpos["season"] == s_sel) & (qpos["grand_prix"] == g_sel)]
    d = d.merge(qpos[["driver", "quali_pos"]], on="driver", how="left").rename(columns={"quali_pos": "position_qualif"})
    d = d.sort_values(model_col, ascending=False).reset_index(drop=True)
    r = hrace[(hrace["season"] == s_sel) & (hrace["grand_prix"] == g_sel)][["driver", "finish", "p_win"]]
    d = d.merge(r, on="driver", how="left")
    pole_flag = d["is_pole"].fillna(False).astype(bool).to_dict()
    show = d[["pilote", "team", "p_avant", "p_apres", "p_reference", "position_qualif", "p_win", "finish"]]
    st.dataframe(show.style.format({"p_avant": "{:.1%}", "p_apres": "{:.1%}", "p_reference": "{:.1%}",
                                    "p_win": "{:.1%}", "finish": "{:.0f}", "position_qualif": "{:.0f}"}, na_rep="–")
                 .apply(lambda row: ["background-color:#e5f4e4" if pole_flag.get(row.name, False) else "" for _ in row], axis=1),
                 hide_index=True, width="stretch",
                 column_config={"pilote": "Pilote", "team": "Équipe", "p_avant": "Pole : avant week-end",
                                "p_apres": "Pole : après EL", "p_reference": "Pole : référence naïve",
                                "position_qualif": "Qualif réelle", "p_win": "Victoire (grille connue)",
                                "finish": "Arrivée"})
    st.caption("Ligne verte : le vrai poleman. « Référence naïve » = chances proportionnelles aux poles déjà faites.")

# ------------------------------------------------------------------ 3. performance
with tab_perf:
    st.header("Le modèle est-il bon ?")
    bt = load("backtest.csv")
    gains = load("gains_vs_references.csv")
    st.markdown("**Méthode de test.** Avant chaque qualif, le modèle n'a vu que les courses précédentes. "
                "Le modèle est choisi sur le début de saison 2026, puis jugé sur des périodes jamais utilisées "
                "pour ce choix : 2024-2025 et la fin de saison 2026. Mesure : la **log-loss**, "
                "−log(probabilité donnée au vrai poleman). Plus bas = mieux ; le hasard donne 3,09.")
    g = gains.copy()
    g["verdict"] = np.where(g["ic95_bas"] > 0, "mieux, de façon nette",
                            np.where(g["ic95_haut"] < 0, "moins bien", "pas de différence démontrée"))
    st.subheader("Pole : le modèle bat-il les références ?")
    st.dataframe(g, hide_index=True, width="stretch",
                 column_config={"modele": "Modèle", "periode": "Période", "contre": "Face à", "qualifs": "Qualifs",
                                "gain_log_loss": st.column_config.NumberColumn("Gain de log-loss", format="%.2f"),
                                "ic95_bas": st.column_config.NumberColumn("IC 95 % bas", format="%.2f"),
                                "ic95_haut": st.column_config.NumberColumn("IC 95 % haut", format="%.2f"),
                                "verdict": "Verdict"})
    with st.expander("Tous les modèles testés"):
        cols = ["moment", "variables", "methode", "log_loss_2024_2025_info", "log_loss_choix_2026_debut",
                "log_loss_test", "poleman_dans_top3_test", "choisi"]
        st.dataframe(bt[cols], hide_index=True, width="stretch",
                     column_config={"log_loss_2024_2025_info": "Log-loss 2024-25",
                                    "log_loss_choix_2026_debut": "Log-loss début 2026 (choix)",
                                    "log_loss_test": "Log-loss fin 2026 (test)",
                                    "poleman_dans_top3_test": "Poleman dans le top 3 (test)"})
        if (FIGURES / "fig2_backtest.png").exists():
            st.image(str(FIGURES / "fig2_backtest.png"))
    st.subheader("Les probabilités sont-elles fiables ?")
    st.caption("Calibration sur toute la saison 2026 (le début de saison a aussi servi au choix du modèle).")
    if (FIGURES / "fig3_calibration.png").exists():
        st.image(str(FIGURES / "fig3_calibration.png"))
    st.subheader("Victoire en course")
    cs, cg = load("course_scores.csv"), load("course_gains.csv")
    st.dataframe(cs[["modele", "log_loss_2024_2025_choix", "log_loss_2026_test", "favori_juste_2026_test",
                     "qualifs_2026_test", "choisi"]], hide_index=True, width="stretch",
                 column_config={"log_loss_2024_2025_choix": "Log-loss 2024-25 (choix)",
                                "log_loss_2026_test": "Log-loss 2026 (test)",
                                "favori_juste_2026_test": "Favori vainqueur (2026)", "qualifs_2026_test": "Courses"})
    labels = {"2024-2025": "2024-2025 (période de choix du modèle)", "2026": "2026 (test)"}
    st.caption("Gain face à la référence « fréquence de victoire selon la place de départ » : "
               + " ; ".join(f"{labels.get(r.periode, r.periode)} : {r.gain_vs_grille:+.2f} "
                            f"(IC 95 % {r.ic95_bas:+.2f} à {r.ic95_haut:+.2f})" for r in cg.itertuples()))

# ------------------------------------------------------------------ 4. pilotes
with tab_drivers:
    st.header("Forme des pilotes en qualifications")
    best = load_processed("best_laps.csv")
    res = load_processed("race_results.csv")
    q = best[(best["session"] == "Qualifying") & (best["season"] == season)].copy()
    drivers = sorted(q["driver"].unique(), key=name)
    default = [d for d in pred.sort_values(col, ascending=False)["driver"].head(4) if d in drivers]
    sel = st.multiselect("Pilotes", drivers, default=default, format_func=name)
    d = q[q["driver"].isin(sel)].copy()
    d["pilote"] = d["driver"].map(name)
    d["écart"] = d["deficit_pct"].clip(upper=2.0)
    line = alt.Chart(d).mark_line(point=True).encode(
        x=alt.X("grand_prix:N", sort=alt.SortField("date"), title=None),
        y=alt.Y("écart:Q", title="Écart au poleman (%) : plus bas = plus rapide", scale=alt.Scale(reverse=True)),
        color=alt.Color("pilote:N", title=None),
        tooltip=["pilote", "grand_prix", alt.Tooltip("deficit_pct:Q", format=".3f", title="écart (%)")])
    st.altair_chart(line.properties(height=380), width="stretch")
    poles = q[q["pole"]].groupby("driver").size().rename("poles")
    wins = res[(res["season"] == season) & (res["finish"] == 1)].groupby("driver").size().rename("victoires")
    tbl = pd.concat([poles, wins], axis=1).fillna(0).astype(int).sort_values(["poles", "victoires"], ascending=False)
    tbl.index = tbl.index.map(name)
    st.subheader(f"Poles et victoires {season}")
    st.dataframe(tbl, width="stretch")
    st.caption("Victoires d'après le classement au drapeau à damier (disqualifications ultérieures non prises en compte).")

# ------------------------------------------------------------------ 5. méthode
with tab_method:
    st.header("Comment ça marche")
    st.markdown("""
1. **Données** : meilleurs tours de toutes les qualifications et séances d'essais libres, et classements des courses,
   de 2023 à 2026 (source : FastF1 via le dépôt public TracingInsights).
2. **Variables** (uniquement des courses passées) : forme récente du pilote et de l'équipe, forme sur les circuits
   du même type, et pendant le week-end : rythme en essais libres (meilleur tour, tours en pneus tendres, tour idéal
   = somme des meilleurs secteurs).
3. **Deux familles de modèles** comparées :
   - *régression + aléa* : on prédit l'écart de chaque pilote au poleman, on ajoute un aléa de Student
     (tour raté, trafic…) et on calcule la chance de chacun d'être le plus rapide ;
   - *logit conditionnel* : on apprend directement qui fait la pole parmi les pilotes de la course.
4. **Choix et test** : le meilleur modèle est choisi sur le début de saison 2026, puis jugé sur des courses
   jamais utilisées pour ce choix (2024-2025, fin 2026), face au hasard et à une référence naïve.
5. **Course** : la victoire est estimée surtout à partir de la place sur la grille (logit conditionnel),
   comparée à la fréquence historique de victoire selon la place de départ.

**Limites** : peu de courses par saison, hiérarchie 2026 très mouvante, pluie non modélisée, pénalités de grille
non prises en compte. Projet pédagogique : ce n'est pas un outil de pari.
""")
    st.caption(f"Modèles retenus : pole avant week-end = {meta['modele_pole'].get('avant le week-end')}, "
               f"après essais = {meta['modele_pole'].get('après les essais libres')}, course = {meta['modele_course']}.")
