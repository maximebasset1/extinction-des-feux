"""Exporte les résultats en JSON pour le site statique (site/data/).

Le site n'exécute aucun calcul : il lit ces fichiers. C'est ce qui le rend gratuit à héberger
et sûr (aucun serveur, aucune base de données, rien à pirater).
"""
import json
import re
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "site" / "data"

GP_FR = {"Las Vegas": "Las Vegas", "Qatar": "Qatar", "Abu Dhabi": "Abou Dabi", "Australian": "Australie",
         "Chinese": "Chine", "Japanese": "Japon", "Bahrain": "Bahreïn", "Saudi Arabian": "Arabie saoudite",
         "Miami": "Miami", "Emilia Romagna": "Émilie-Romagne", "Monaco": "Monaco", "Spanish": "Espagne",
         "Barcelona": "Barcelone", "Canadian": "Canada", "Austrian": "Autriche", "British": "Grande-Bretagne",
         "Belgian": "Belgique", "Hungarian": "Hongrie", "Dutch": "Pays-Bas", "Italian": "Italie",
         "Azerbaijan": "Azerbaïdjan", "Singapore": "Singapour", "United States": "États-Unis",
         "Mexico City": "Mexique", "São Paulo": "São Paulo", "Portuguese": "Portugal", "Turkish": "Turquie"}


def gp_fr(season: int, gp: str) -> str:
    if season == 2026 and gp == "Spanish":
        return "Espagne (Madrid)"
    return GP_FR.get(gp, gp)


def _clean(obj):
    """JSON strict : pas de NaN (remplacés par null), nombres numpy convertis."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(obj) else round(float(obj), 5)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _write(name: str, data) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / name).write_text(json.dumps(_clean(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def driver_directory(raw_dir: Path) -> dict:
    """Nom complet et couleur d'équipe de chaque pilote, d'après les fichiers officiels (le plus récent gagne)."""
    out = {}
    files = sorted(raw_dir.glob("*/*/Qualifying/drivers.json"), key=lambda p: (p.parts[-4], p.stat().st_mtime))
    for f in files:
        try:
            for d in json.loads(f.read_text(encoding="utf-8"))["drivers"]:
                color = str(d.get("tc") or "").lstrip("#")
                if not re.fullmatch(r"[0-9A-Fa-f]{6}", color):  # donnée externe : seulement une couleur hexadécimale
                    color = "888888"
                out[d["driver"]] = {"nom": f"{d.get('fn', '')} {d.get('ln', '')}".strip() or d["driver"],
                                    "prenom": d.get("fn", ""), "famille": d.get("ln", d["driver"]),
                                    "equipe": d.get("team"), "couleur": "#" + color}
        except Exception:
            continue
    return out


def championnat_json(c: dict | None, people: dict, season: int) -> dict | None:
    """Simulation du championnat (championnat.calculer) avec noms, couleurs et écuries pour le site."""
    if not c:
        return None
    # nom et couleur d'une écurie f1db : ceux de son pilote le mieux classé (fichiers TracingInsights)
    vitrine = {}
    for d in c["pilotes"]["classement"]:
        if d["team"] and d["team"] not in vitrine and d["id"] in people:
            vitrine[d["team"]] = (people[d["id"]].get("equipe"), people[d["id"]].get("couleur", "#888888"))

    def equipe(t):
        nom, coul = vitrine.get(t, (None, "#888888"))
        return {"equipe": nom or str(t).replace("-", " ").title(), "couleur": coul}

    def pilote(code):
        p = people.get(code, {})
        return {"code": code, "nom": p.get("nom", code), "famille": p.get("famille", code),
                "couleur": p.get("couleur", "#888888")}

    blocs = {}
    for kind in ("pilotes", "constructeurs"):
        b, champ = c[kind], c[kind]["champion"]
        ident = (lambda d: pilote(d["id"]) | {"equipe": equipe(d["team"])["equipe"] if d["team"] else None}) \
            if kind == "pilotes" else (lambda d: equipe(d["id"]))
        blocs[kind] = {"joue": b["joue"], "points_max_restants": b["points_max_restants"],
                       "champion": (pilote(champ) if kind == "pilotes" else equipe(champ)) if champ else None,
                       "classement": [ident(d) | {k: d[k] for k in ("points", "points_moyens", "titre", "elimine")}
                                      for d in b["classement"]]}
    restants = [(g["gp"].replace(" Grand Prix", ""), g["sprint"]) for g in c["gp_restants"]]
    return {"saison": c["saison"], "apres_manche": c["apres_manche"], "tirages": c["tirages"],
            "taux_abandon": c.get("taux_abandon"),
            "meilleur_tour": c["meilleur_tour"],
            "gp_restants": [{"gp": g, "gp_fr": gp_fr(season, g), "sprint": s} for g, s in restants], **blocs}


def export(out: dict, race: dict, win: pd.DataFrame, best: pd.DataFrame, results: pd.DataFrame,
           journal_eval: pd.DataFrame, raw_dir: Path, cfg, forecast: dict | None = None,
           grid: pd.DataFrame | None = None, grid_source: str = "inconnue", championnat: dict | None = None) -> None:
    people = driver_directory(raw_dir)
    gp = cfg.TARGET_GP.replace(" Grand Prix", "")
    pred = out["pred"]

    def person(code):
        p = people.get(code, {})
        return {"code": code, "nom": p.get("nom", code), "famille": p.get("famille", code),
                "couleur": p.get("couleur", "#888888")}

    # ---------- prochain GP
    pole = [{**person(r["driver"]), "equipe": r["team"],
             "avant": r.get("proba_pole_avant"), "apres": r.get("proba_pole_apres"),
             "sec": r.get("proba_pole_apres_sec", r.get("proba_pole_avant_sec")),
             "pluie": r.get("proba_pole_apres_pluie", r.get("proba_pole_avant_pluie"))} for _, r in pred.iterrows()]
    g = grid.set_index("driver") if grid is not None and len(grid) else None

    def depart(code, field, default):
        return default if g is None or code not in g.index else g.at[code, field]

    # « grille » : vraie place de départ (pénalités comprises quand la grille officielle est publiée) ;
    # « qualif », « penalite », « stands » : ajoutés sans changer les champs existants (lus par PitLane Insider)
    wins = [{**person(r["driver"]), "equipe": r["team"], "proba": r["proba_victoire"],
             "grille": int(r["grille"]) if "grille" in win and pd.notna(r["grille"]) else None,
             "qualif": int(depart(r["driver"], "qualif", 0)) or None,
             "penalite": int(depart(r["driver"], "penalite", 0)),
             "stands": bool(depart(r["driver"], "stands", False))} for _, r in win.iterrows()]
    finished = results[(results["season"] == cfg.TARGET_SEASON) & (results["grand_prix"] == gp)].sort_values("finish")
    done_before = best[(best["season"] == cfg.TARGET_SEASON) & (best["session"] == "Qualifying")
                       & (best["grand_prix"] != gp)]["grand_prix"].nunique()
    quali = best[(best["season"] == cfg.TARGET_SEASON) & (best["grand_prix"] == gp) & (best["session"] == "Qualifying")]
    pole_sitter = quali.loc[quali["pole"], "driver"].tolist()
    _write("next.json", {
        "maj_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "saison": cfg.TARGET_SEASON, "gp": gp, "gp_fr": gp_fr(cfg.TARGET_SEASON, gp),
        "ville": cfg.TARGET_INFO.get("city"), "pays": cfg.TARGET_INFO.get("country"),
        "manche": cfg.TARGET_INFO.get("round"), "sessions": cfg.TARGET_INFO.get("sessions", {}),
        "horaires_estimes": cfg.TARGET_INFO.get("approx", False), "saison_terminee": cfg.SEASON_OVER,
        "statut": out["status"], "qualif_disputee": bool(len(quali)), "grille_source": grid_source,
        "poleman": person(pole_sitter[0]) if pole_sitter else None,
        "modeles": {k: v["label"] for k, v in out["chosen"].items()} | {"course": race["chosen"]},
        "pole": pole, "victoire": wins,
        "debut_saison": bool(done_before < 3),
        "meteo": forecast,
        "arrivee": [{**person(r.driver), "equipe": r.team, "place": int(r.finish)}
                    for r in finished.itertuples() if pd.notna(r.finish)][:6],
        # ajouté en novembre 2026 : chances de titre pilotes et constructeurs (null si f1db indisponible)
        "championnat": championnat_json(championnat, people, cfg.TARGET_SEASON),
    })

    # ---------- historique : prédit (avant la séance) vs réel
    h = out["history"].copy()
    hr = race["history"][["season", "grand_prix", "driver", "grille", "finish", "p_win"]]
    h = h.merge(hr, on=["season", "grand_prix", "driver"], how="left")
    qpos = best[best["session"] == "Qualifying"][["season", "grand_prix", "driver", "quali_pos"]]
    h = h.merge(qpos, on=["season", "grand_prix", "driver"], how="left")
    seasons = {}
    for (season, g), d in h.groupby(["season", "grand_prix"], sort=False):
        d = d.sort_values("p_apres" if d["p_apres"].notna().any() else "p_avant", ascending=False)
        winner = d.loc[d["finish"] == 1, "driver"]
        seasons.setdefault(int(season), []).append({
            "gp": g, "gp_fr": gp_fr(int(season), g), "date": d["date"].iloc[0], "pluie": bool(d["wet"].iloc[0]),
            "poleman": d.loc[d["is_pole"], "driver"].iloc[0] if d["is_pole"].any() else None,
            "vainqueur": winner.iloc[0] if len(winner) else None,
            "pilotes": [{"code": r.driver, "equipe": r.team, "avant": r.p_avant, "apres": r.p_apres,
                         "ref": r.p_reference, "qualif": r.quali_pos, "victoire": r.p_win, "arrivee": r.finish}
                        for r in d.itertuples()]})
    for s in seasons:
        seasons[s].sort(key=lambda x: x["date"])
    _write("history.json", {"saisons": seasons, "pilotes": people})

    # ---------- fiabilité
    res = out["res"]
    chosen_rows = res[res["choisi"] == "oui"]
    wet = {family: {"version": c["wet"]["version"], "lambda": c["wet"]["lambda"],
                    "comparaison": c["wet"]["table"].to_dict("records")} for family, c in out["chosen"].items()}
    hist_mean = res.groupby("historique")["log_loss_choix_2026_debut"].mean().round(3)
    _write("performance.json", {
        "pluie": wet,
        "historiques": {"choisi": next(iter(out["chosen"].values()))["hist_name"],
                        "log_loss_moyenne_choix": hist_mean.to_dict()},
        "gains": out["gains"].to_dict("records"),
        "modeles_choisis": chosen_rows[["moment", "variables", "methode"]].to_dict("records"),
        "nb_modeles_testes": int((res["moment"] != "référence").sum()),
        "tous": res[["historique", "moment", "variables", "methode", "log_loss_2024_2025_info", "log_loss_choix_2026_debut",
                     "log_loss_test", "poleman_dans_top3_test", "qualifs_test", "choisi"]].to_dict("records"),
        "calibration": out["calib"].to_dict("records"),
        "course": {"scores": race["scores"].to_dict("records"), "gains": race["gains"].to_dict("records"),
                   "choisi": race["chosen"], "pluie": race.get("pluie")},
    })

    # ---------- pilotes (saison en cours)
    # saison la plus récente avec au moins une qualif (en début d'année : la saison précédente)
    allq = best[(best["session"] == "Qualifying") & (best["season"] <= cfg.TARGET_SEASON)]
    season_d = int(allq["season"].max())
    q = allq[allq["season"] == season_d].sort_values("date")
    order = q.drop_duplicates("grand_prix")[["grand_prix", "date"]]
    res_s = results[results["season"] == season_d]
    drivers = []
    for code, d in q.groupby("driver"):
        drivers.append({**person(code), "equipe": d["team"].iloc[-1],
                        "poles": int(d["pole"].sum()),
                        "victoires": int(((res_s["driver"] == code) & (res_s["finish"] == 1)).sum()),
                        "podiums": int(((res_s["driver"] == code) & (res_s["finish"] <= 3)).sum()),
                        "ecarts": {r.grand_prix: r.deficit_pct for r in d.itertuples()}})
    drivers.sort(key=lambda x: (-x["poles"], -x["victoires"], -x["podiums"]))
    _write("drivers.json", {"saison": season_d,
                            "gps": [{"gp": g, "gp_fr": gp_fr(season_d, g), "date": dt} for g, dt in order.values],
                            "pilotes": drivers})

    # ---------- étude de novembre 2026 (grille officielle, rythme de course) : affichée sur « Méthode et bilan F1 »
    processed = Path(__file__).resolve().parents[1] / "data" / "processed"
    etude, etude_sprint = processed / "etude_f1.json", processed / "etude_sprint.json"
    if etude.exists():
        data = json.loads(etude.read_text(encoding="utf-8"))
        # champ « sprint » ajouté en novembre 2026 : étude des week-ends sprint (etude_sprint.py)
        if etude_sprint.exists():
            data["sprint"] = json.loads(etude_sprint.read_text(encoding="utf-8"))
        _write("etude_f1.json", data)

    # ---------- journal des prédictions publiées
    ev = journal_eval.to_dict("records") if len(journal_eval) else []
    for e in ev:
        e["gp_fr"] = gp_fr(int(e["season"]), e["grand_prix"])
    _write("journal.json", {"evaluations": ev})
