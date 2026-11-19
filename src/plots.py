"""Graphiques du rapport (reports/figures/)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from config import FIGURES, TARGET_GP, TARGET_SEASON  # noqa: E402

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 150, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "axes.titleweight": "bold"})
TEAM_COLORS = {"Mercedes": "#27F4D2", "Ferrari": "#E8002D", "McLaren": "#FF8000", "Red Bull Racing": "#3671C6",
               "Racing Bulls": "#6692FF", "Alpine": "#0093CC", "Aston Martin": "#229971", "Williams": "#64C4FF",
               "Haas F1 Team": "#B6BABD", "Audi": "#8A8D8F", "Cadillac": "#1E1E1E"}


def _save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    path = FIGURES / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def pole_chances(pred: pd.DataFrame, status: str, res: pd.DataFrame, top: int = 10) -> Path:
    col = "proba_pole_apres" if "proba_pole_apres" in pred else "proba_pole_avant"
    family = "après les essais libres" if col.endswith("apres") else "avant le week-end"
    row = res[(res["moment"] == family) & (res["choisi"] == "oui")].iloc[0]
    top3, n = int(row["poleman_dans_top3_test"]), int(row["qualifs_test"])
    d = pred.sort_values(col, ascending=False)
    head = d.head(top)
    rest = d[col].iloc[top:].sum()
    labels = [f"{r.driver} ({r.team})" for r in head.itertuples()] + ["Les 12 autres" if len(d) - top == 12 else "Autres"]
    vals = list(head[col]) + [rest]
    colors = [TEAM_COLORS.get(t, "#999") for t in head["team"]] + ["#cccccc"]
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(vals))[::-1]
    ax.barh(y, np.array(vals) * 100, color=colors, edgecolor="#333", linewidth=0.4)
    for yi, v in zip(y, vals):
        ax.text(v * 100 + 0.4, yi, f"{100 * v:.0f} %" if v >= 0.01 else "< 1 %", va="center", fontsize=9)
    ax.set_yticks(y, labels)
    ax.set_xlabel("Probabilité de pole position (%)")
    ax.set_title(f"{TARGET_GP.replace(' Grand Prix', '')} {TARGET_SEASON} : probabilités de pole, {status}\n"
                 f"Test fin 2026 : le poleman figurait dans le top 3 du modèle {top3} fois sur {n}", fontsize=10)
    ax.grid(axis="y", visible=False)
    return _save(fig, "fig1_probabilites_pole.png")


def backtest_chart(res: pd.DataFrame) -> Path:
    d = res.copy()
    short = {"avant le week-end": "avant", "après les essais libres": "après EL"}
    d["label"] = np.where(d["moment"] == "référence", d["variables"],
                          d["moment"].map(short).fillna("") + " : " + d["variables"] + " / " + d["methode"])
    fig, ax = plt.subplots(figsize=(9, 9))
    y = np.arange(len(d))[::-1]
    colors = np.where(d["moment"] == "référence", "#999", np.where(d["choisi"] == "oui", "#2ca02c", "#4c72b0"))
    ax.barh(y, d["log_loss_test"], color=colors)
    n = int(d["qualifs_test"].max())
    for yi, v, top3 in zip(y, d["log_loss_test"], d["poleman_dans_top3_test"]):
        ax.text(v + 0.03, yi, f"{v:.2f}  (poleman dans le top 3 : {int(top3)}/{n})", va="center", fontsize=7.5)
    ax.set_yticks(y, d["label"], fontsize=7.5)
    ax.set_xlim(0, d["log_loss_test"].max() * 1.5)
    ax.set_xlabel(f"Log-loss sur les {n} dernières qualifications 2026 (plus petit = meilleur)")
    ax.axvline(float(d.loc[d["variables"].str.startswith("hasard"), "log_loss_test"].iloc[0]), color="#999", ls=":", lw=1)
    ax.set_title("Test sur la fin de saison 2026 (vert = modèle choisi sur le début de saison)", fontsize=10)
    ax.grid(axis="y", visible=False)
    return _save(fig, "fig2_backtest.png")


def calibration_chart(calib: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
    for ax, (model, d) in zip(axes, calib.groupby("modele", sort=False)):
        ax.plot([0, 0.7], [0, 0.7], ls="--", color="black", lw=0.8, label="Calibration parfaite")
        ax.scatter(d["proba_moyenne"], d["frequence_reelle"], s=d["predictions"] ** 0.5 * 14, color="#4c72b0")
        for r in d.itertuples():
            ax.annotate(f"{int(r.poles)} pole(s) / {r.predictions}", (r.proba_moyenne, r.frequence_reelle),
                        xytext=(6, -4), textcoords="offset points", fontsize=8)
        ax.set_title(f"Modèle {model}", fontsize=10)
        ax.set_xlabel("Probabilité annoncée")
    axes[0].set_ylabel("Fréquence réelle de pole")
    axes[0].legend(fontsize=8, frameon=False, loc="upper left")
    fig.suptitle("Les probabilités sont-elles fiables ? Saison 2026, prédictions faites avant chaque qualif\n"
                 "(peu de cas dans les tranches hautes : à lire avec prudence)", fontsize=10, fontweight="bold")
    return _save(fig, "fig3_calibration.png")


def season_heatmap(best: pd.DataFrame, pred: pd.DataFrame, n: int = 10) -> Path:
    q = best[(best["season"] == TARGET_SEASON) & (best["session"] == "Qualifying")]
    order = q.drop_duplicates("grand_prix").sort_values("date")["grand_prix"].tolist()
    drivers = pred["driver"].head(n).tolist()
    m = q.pivot_table(index="driver", columns="grand_prix", values="deficit_pct").reindex(index=drivers, columns=order)
    wet = q.drop_duplicates("grand_prix").set_index("grand_prix")["wet"].reindex(order)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    im = ax.imshow(m.clip(upper=1.5).to_numpy(), cmap="viridis_r", aspect="auto", vmin=0, vmax=1.5)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            if not np.isnan(v) and v < 1e-9:
                ax.text(j, i, "P", ha="center", va="center", color="black", fontweight="bold", fontsize=9)
    ax.set_xticks(range(len(order)), [g + (" (pluie)" if wet[g] else "") for g in order], rotation=50, ha="right", fontsize=8)
    ax.set_yticks(range(len(drivers)), drivers)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025)
    cb.set_label("Écart au poleman (%)")
    ax.set_title(f"Saison {TARGET_SEASON} en qualifications : écart au plus rapide (P = pole)", fontsize=10)
    return _save(fig, "fig4_saison_2026.png")
