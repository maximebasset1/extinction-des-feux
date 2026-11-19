"""Rapport HTML lisible dans un navigateur : reports/rapport.html (créé à chaque lancement)."""
import base64
import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import FIGURES, ROOT, TARGET_GP, TARGET_SEASON  # noqa: E402

TEAM_COLORS = {"Mercedes": "#00A19B", "Ferrari": "#E8002D", "McLaren": "#FF8000", "Red Bull Racing": "#3671C6",
               "Racing Bulls": "#6692FF", "Alpine": "#0093CC", "Aston Martin": "#229971", "Williams": "#1868DB",
               "Haas F1 Team": "#8C8F93", "Audi": "#6E7175", "Cadillac": "#1E1E1E"}
DRIVER_NAMES = {"ANT": "Kimi Antonelli", "RUS": "George Russell", "HAM": "Lewis Hamilton", "LEC": "Charles Leclerc",
                "VER": "Max Verstappen", "NOR": "Lando Norris", "PIA": "Oscar Piastri", "HAD": "Isack Hadjar",
                "LAW": "Liam Lawson", "LIN": "Arvid Lindblad", "GAS": "Pierre Gasly", "COL": "Franco Colapinto",
                "ALO": "Fernando Alonso", "STR": "Lance Stroll", "ALB": "Alexander Albon", "SAI": "Carlos Sainz",
                "OCO": "Esteban Ocon", "BEA": "Oliver Bearman", "HUL": "Nico Hülkenberg", "BOR": "Gabriel Bortoleto",
                "PER": "Sergio Pérez", "BOT": "Valtteri Bottas"}
# Horaires du week-end cible, heure de Paris (à mettre à jour pour un autre Grand Prix)
SCHEDULE = [("Essais libres 1", "ven. 20 nov., 01 h 30"), ("Essais libres 2", "ven. 20 nov., 05 h 00"),
            ("Essais libres 3", "sam. 21 nov., 01 h 30"), ("Qualifications", "sam. 21 nov., 05 h 00")]

CSS = """
:root{--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e4e7;--bg:#fafafa;--card:#fff;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:980px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px}.sub{color:var(--muted);margin:0 0 20px}
.banner{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.pill{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.pill b{display:block;font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
.row{display:grid;grid-template-columns:34px 200px 1fr 64px;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}.pos{color:var(--muted);font-variant-numeric:tabular-nums}.name b{display:block}.name span{color:var(--muted);font-size:13px}
.bar{height:14px;border-radius:7px;background:#eef0f3;overflow:hidden}.bar i{display:block;height:100%;border-radius:7px}
.pct{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}.ghost{opacity:.45}
.warn{background:#fff7e6;border:1px solid #f5d38a;border-radius:12px;padding:12px 16px;margin:16px 0}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.step{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.step b{display:block;color:var(--accent);font-size:13px;margin-bottom:4px}
table{border-collapse:collapse;width:100%}td,th{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase}code{background:#f1f1f4;padding:2px 6px;border-radius:6px;font-size:13px}
img{max-width:100%;border:1px solid var(--line);border-radius:10px;background:#fff}
details{margin-top:14px}summary{cursor:pointer;color:var(--accent);font-weight:600}
@media(max-width:700px){.row{grid-template-columns:26px 1fr 54px}.row .bar{grid-column:2/4}.steps{grid-template-columns:1fr 1fr}}
"""


def _img(name: str) -> str:
    path = FIGURES / name
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(name)}">'


def _rows(pred: pd.DataFrame, col: str, show: int = 10) -> str:
    top = pred[col].max()
    out = []
    for i, r in enumerate(pred.itertuples(), 1):
        if i == show + 1:
            out.append(f'<details><summary>Voir les {len(pred) - show} autres pilotes</summary>')
        p = getattr(r, col)
        color = TEAM_COLORS.get(r.team, "#999")
        pct = "&lt; 1 %" if p < 0.01 else f"{100 * p:.0f} %"
        ghost = " ghost" if p < 0.01 else ""
        out.append(
            f'<div class="row{ghost}"><span class="pos">{i}</span>'
            f'<span class="name"><b>{html.escape(DRIVER_NAMES.get(r.driver, r.driver))}</b>'
            f'<span>{html.escape(r.team)}</span></span>'
            f'<span class="bar"><i style="width:{100 * p / top:.1f}%;background:{color}"></i></span>'
            f'<span class="pct">{pct}</span></div>')
    if len(pred) > show:
        out.append("</details>")
    return "\n".join(out)


def build(pred: pd.DataFrame, status: str, res: pd.DataFrame, chosen: dict) -> Path:
    has_fp = "proba_pole_apres" in pred
    col = "proba_pole_apres" if has_fp else "proba_pole_avant"
    family = "après les essais libres" if has_fp else "avant le week-end"
    row = res[(res["moment"] == family) & (res["choisi"] == "oui")].iloc[0]
    rand = res[res["variables"].str.startswith("hasard")].iloc[0]
    share = res[res["variables"].str.startswith("part des poles")].iloc[0]
    gp = TARGET_GP.replace(" Grand Prix", "")
    lead = pred.iloc[0]
    n_close = int((pred[col] >= 0.5 * lead[col]).sum())
    sched = "".join(f"<tr><td>{s}</td><td>{t}</td></tr>" for s, t in SCHEDULE)
    compare = ""
    if has_fp:
        before = pred.sort_values("proba_pole_avant", ascending=False)
        compare = f"""<details><summary>Voir les probabilités d'avant le week-end</summary>
        <div class="card" style="margin-top:10px">{_rows(before, "proba_pole_avant")}</div></details>"""

    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pole {gp} {TARGET_SEASON}</title>
<style>{CSS}</style></head><body><main>
<h1>Qui fera la pole à {gp} ?</h1>
<p class="sub">Grand Prix de {gp} {TARGET_SEASON} · probabilités de pole position par pilote</p>

<div class="banner">
  <div class="pill"><b>Calculé le</b>{datetime.now():%d/%m/%Y à %H h %M}</div>
  <div class="pill"><b>Informations utilisées</b>{html.escape(status)}</div>
  <div class="pill"><b>Modèle</b>{html.escape(chosen[family]["label"])}</div>
</div>

<div class="card">{_rows(pred, col)}</div>

<div class="warn"><b>Comment lire :</b> {n_close} pilotes ont au moins la moitié des chances du premier
({html.escape(DRIVER_NAMES.get(lead.driver, lead.driver))}, {100 * lead[col]:.0f} %). Les écarts entre eux sont
plus petits que l'incertitude du modèle : la pole reste très ouverte. Sur les {int(row['qualifs_test'])} dernières
qualifs 2026, le vrai poleman était dans le top 3 du modèle {int(row['poleman_dans_top3_test'])} fois.</div>

<h2>Mettre à jour pendant le week-end</h2>
<div class="card"><p style="margin-top:0">Après chaque séance, double-clique sur <code>Lancer_mise_a_jour.bat</code>
(ou tape <code>python src/main.py --refresh</code>). Les données d'une séance sont publiées quelques heures après.
Dès qu'un essai libre est disponible, le modèle « après les essais libres » prend le relais : c'est le plus utile.</p>
<table><tr><th>Séance</th><th>Heure de Paris</th></tr>{sched}</table></div>

<h2>Comment ça marche, en 4 étapes</h2>
<div class="steps">
  <div class="step"><b>1. Données</b>Meilleurs tours de toutes les qualifs et essais libres 2025-2026.</div>
  <div class="step"><b>2. Variables</b>Forme récente du pilote et de l'équipe, type de circuit, essais du week-end. Uniquement le passé.</div>
  <div class="step"><b>3. Prédiction</b>Une régression prédit l'écart de chaque pilote au poleman, en %.</div>
  <div class="step"><b>4. Probabilités</b>On ajoute un aléa (tour raté, trafic…) et on calcule la chance de chacun d'être le plus rapide.</div>
</div>

<h2>Le modèle est-il fiable ?</h2>
<div class="card"><table>
<tr><th>Méthode</th><th>Score sur les 9 dernières qualifs 2026 (log-loss, plus bas = mieux)</th></tr>
<tr><td>Modèle {html.escape(family)}</td><td><b>{row['log_loss_test']:.2f}</b></td></tr>
<tr><td>Chances proportionnelles aux poles déjà faites</td><td>{share['log_loss_test']:.2f}</td></tr>
<tr><td>Hasard (1 chance sur 22)</td><td>{rand['log_loss_test']:.2f}</td></tr>
</table>
<p style="margin-bottom:0">Le modèle fait mieux que le hasard en moyenne, mais avec si peu de qualifs, ce gain
n'est pas démontré. Les essais libres sont l'information la plus utile. Détails dans le README.</p>
<details><summary>Graphiques de validation</summary>{_img("fig2_backtest.png")}{_img("fig3_calibration.png")}</details>
<details><summary>La saison 2026 en qualifications</summary>{_img("fig4_saison_2026.png")}</details>
</div>

<p class="sub" style="margin-top:30px">Hypothèse : qualification sur piste sèche. Sous la pluie, le modèle n'est pas fiable.
Projet pédagogique, ce n'est pas un outil de pari. Données : FastF1 / TracingInsights.</p>
</main></body></html>"""
    out = ROOT / "reports" / "rapport.html"
    out.write_text(page, encoding="utf-8")
    return out
