"""Étape 5 : comparer les modèles, choisir, tester, puis prédire le GP cible.

Protocole (identique pour tous les modèles) :
- backtest glissant sur 2023-2026 : avant chaque qualif, le modèle ne voit que les qualifs précédentes ;
- CHOIX du modèle sur le début de saison 2026 (courses 4 à 11), même réglementation que la cible ;
- TEST sur la fin de saison 2026 (courses 12 et suivantes), jamais utilisée pour choisir ;
- 2024-2025 sont montrées pour information (autre génération de voitures).
Les saisons servant à apprendre (2023+, ou depuis 2018 avec ou sans poids dégressif) sont elles
aussi choisies sur la période de choix : moyenne de tous les modèles, pour ne pas se fier à un seul.
Le module pluie (weather.py) est jugé à part, sur les qualifs mouillées.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import MAX_DEFICIT_PCT, TARGET_GP, TARGET_SEASON, circuit_type  # noqa: E402
from features import (  # noqa: E402
    CANDIDATES_FP, CANDIDATES_PRE, FP_COLUMNS, current_wet_skill, features_for_race, practice_deficit,
    qualifying_table, training_table,
)
import sprint  # noqa: E402
import weather  # noqa: E402
from model import (  # noqa: E402
    HISTORIES, NOISE_LAWS, bootstrap_gain, fit_logit, fit_regression, latest_sigma, logit_probabilities, per_race_logloss,
    pole_probabilities, probabilities_with, race_loglik_matrix, rolling_logit, rolling_predictions,
    rolling_sigma, scores, season_share_baseline,
)

TEST_SEASON = 2026
SPLIT_RACE = 12
FAMILIES = [("avant le week-end", CANDIDATES_PRE), ("après les essais libres", CANDIDATES_FP)]
METHODS = ["régression + aléa", "logit conditionnel"]
# Étude de novembre 2026 (etude_sprint.py) : l'écart en qualif sprint, en plus des essais, améliore la log-loss et le
# Brier de la pole sur les week-ends sprint 2024-2025 et se confirme sur 2026. Il est ajouté au modèle choisi
# « après les essais libres » ; il vaut 0 hors week-end sprint et tant que la qualif sprint n'a pas eu lieu.
SPRINT_POLE = "ecart_qualif_sprint"
NOISE_DF = list(NOISE_LAWS.values())[0]


def split(p: pd.DataFrame):
    info = p[p["season"].isin([2024, 2025])]
    choice = p[(p["season"] == TEST_SEASON) & (p["race_idx"] < SPLIT_RACE)]
    # le test s'enrichit automatiquement de chaque nouvelle course (fin 2026, puis 2027...)
    test = p[((p["season"] == TEST_SEASON) & (p["race_idx"] >= SPLIT_RACE)) | (p["season"] > TEST_SEASON)]
    return info, choice, test


def run_method(table: pd.DataFrame, feats: list[str], method: str, hist: dict) -> dict:
    if method == "logit conditionnel":
        return {"probs": rolling_logit(table, feats, hist=hist), "sigma": np.nan}
    pred = rolling_predictions(table, feats, hist=hist)
    races, mat = race_loglik_matrix(pred, NOISE_DF)
    sig = rolling_sigma(mat)
    by_race = {(r.season, r.grand_prix): s for r, s in zip(races.itertuples(), sig)}
    return {"probs": probabilities_with(pred, by_race, NOISE_DF), "sigma": latest_sigma(mat)}


def backtest(table: pd.DataFrame):
    rows, store = [], {}
    for hname, hist in HISTORIES.items():
        for family, candidates in FAMILIES:
            for name, feats in candidates.items():
                for method in METHODS:
                    r = run_method(table, feats, method, hist)
                    info, choice, test = split(r["probs"])
                    rows.append({"historique": hname, "moment": family, "variables": name, "methode": method,
                                 "log_loss_2024_2025_info": scores(info)["log_loss"],
                                 "log_loss_choix_2026_debut": scores(choice)["log_loss"],
                                 **{f"{k}_test": v for k, v in scores(test).items()}})
                    store[(hname, family, name, method)] = r | {"feats": feats, "method": method, "hist": hist,
                                                               "hist_name": hname, "label": f"{name} ({method})"}
    res = pd.DataFrame(rows)
    res["choisi"] = ""
    # 1) quelles saisons pour apprendre ? la moyenne de TOUS les modèles sur la période de choix décide
    hname = res.groupby("historique")["log_loss_choix_2026_debut"].mean().idxmin()
    chosen = {}
    for family, _ in FAMILIES:
        sub = res[(res["moment"] == family) & (res["historique"] == hname)]
        best = sub.loc[sub["log_loss_choix_2026_debut"].idxmin()]
        res.loc[best.name, "choisi"] = "oui"
        chosen[family] = store[(hname, family, best["variables"], best["methode"])] | {
            "key": (family, best["variables"], best["methode"])}
    # 1 bis) qualif sprint ajoutée au modèle choisi après les essais (voir SPRINT_POLE)
    fp = chosen["après les essais libres"]
    if SPRINT_POLE in table and SPRINT_POLE not in fp["feats"]:
        feats_s = fp["feats"] + [SPRINT_POLE]
        chosen["après les essais libres"] = fp | run_method(table, feats_s, fp["method"], fp["hist"]) | {
            "feats": feats_s, "label": fp["label"].replace(" (", " + qualif sprint (", 1), "sprint": True}
    # 2) module pluie : jugé sur les qualifs mouillées (avant 2026 pour choisir, 2026 pour contrôler).
    #    Il y en a peu : on rejoue le même modèle depuis 2018 pour en avoir une quinzaine au lieu de cinq.
    long = HISTORIES["depuis 2018"]
    for family, c in chosen.items():
        feats_w = c["feats"] + ["pluie_talent"]
        base_long = store[("depuis 2018",) + c["key"]]["probs"] if not c.get("sprint") else \
            run_method(table, c["feats"], c["method"], long)["probs"]
        w_long = run_method(table, feats_w, c["method"], long)
        c["wet"] = weather.evaluate_module(base_long, w_long["probs"])
        c["wet"] |= {"feats": feats_w, "hist": long, "sigma": w_long["sigma"]}
    base = {"hasard (1 chance sur 22)": table.assign(
                p_pole=1 / table.groupby(["season", "grand_prix"])["driver"].transform("size")),
            "part des poles déjà faites": season_share_baseline(table)}
    for name, p in base.items():
        info, choice, test = split(p)
        res = pd.concat([res, pd.DataFrame([{"moment": "référence", "variables": name, "methode": "",
                                             "log_loss_2024_2025_info": scores(info)["log_loss"],
                                             "log_loss_choix_2026_debut": scores(choice)["log_loss"],
                                             **{f"{k}_test": v for k, v in scores(test).items()}}])],
                        ignore_index=True)
    # le modèle choisi bat-il les références ? IC 95 % par bootstrap, sur deux périodes jamais
    # utilisées pour le choix : 2024-2025 (beaucoup de courses) et la fin 2026 (même réglementation)
    gains = []
    for family, c in chosen.items():
        for period, k in [("2024-2025", 0), ("fin 2026", 2)]:
            mine = per_race_logloss(split(c["probs"])[k])
            for name, p in base.items():
                g, lo, hi = bootstrap_gain(mine, per_race_logloss(split(p)[k]))
                gains.append({"modele": family, "periode": period, "contre": name, "qualifs": len(mine),
                              "gain_log_loss": g, "ic95_bas": lo, "ic95_haut": hi})
    return res, chosen, pd.DataFrame(gains), base


def history_table(chosen: dict, base: dict) -> pd.DataFrame:
    """Pour chaque qualif depuis 2024 : probabilités annoncées AVANT (hors échantillon) et vrai résultat."""
    cols = ["season", "date", "grand_prix", "race_idx", "driver", "team", "deficit_pct", "is_pole", "wet"]
    h = None
    for family, c in chosen.items():
        tag = "avant" if family.startswith("avant") else "apres"
        p = c["probs"][cols + ["p_pole"]].rename(columns={"p_pole": f"p_{tag}"})
        h = p if h is None else h.merge(p[["season", "grand_prix", "driver", f"p_{tag}"]],
                                       on=["season", "grand_prix", "driver"], how="outer")
    share = base["part des poles déjà faites"][["season", "grand_prix", "driver", "p_pole"]]
    h = h.merge(share.rename(columns={"p_pole": "p_reference"}), on=["season", "grand_prix", "driver"], how="left")
    return h[h["season"] >= 2024].sort_values(["date", "deficit_pct"]).reset_index(drop=True)


def entry_list(best: pd.DataFrame) -> pd.DataFrame:
    """Engagés : EL2 / EL3 / qualif du week-end cible (les EL1 accueillent des rookies),
    sinon ceux de la dernière qualification disputée."""
    gp = TARGET_GP.replace(" Grand Prix", "")
    wk = best[(best["season"] == TARGET_SEASON) & (best["grand_prix"] == gp)]
    for ses in ["Qualifying", "Practice 3", "Practice 2"]:
        d = wk[wk["session"] == ses]
        if len(d) >= 18:
            return d.drop_duplicates("driver")[["driver", "team"]]
    # sinon la dernière qualif disputée, même si elle date de la saison précédente (1re course de l'année)
    q = best[(best["season"] <= TARGET_SEASON) & (best["session"] == "Qualifying")
             & ~((best["season"] == TARGET_SEASON) & (best["grand_prix"] == gp))]
    return q[q["date"] == q["date"].max()].drop_duplicates("driver")[["driver", "team"]]


def predict_target(best: pd.DataFrame, table: pd.DataFrame, chosen: dict, forecast: dict | None = None):
    gp = TARGET_GP.replace(" Grand Prix", "")
    q = qualifying_table(best, MAX_DEFICIT_PCT)
    q = q[~((q["season"] == TARGET_SEASON) & (q["grand_prix"] == gp))]
    done = q.loc[q["season"] == TARGET_SEASON, "race_idx"]
    next_idx = int(done.max()) + 1 if done.notna().any() else 1  # 1re course de la saison : aucune qualif encore
    fq = (forecast or {}).get("Q") or {}
    weekend = best[(best["season"] == TARGET_SEASON) & (best["grand_prix"] == gp)]
    # température attendue pendant la qualif : prévision, sinon celle relevée aux essais du week-end
    temp = fq.get("temperature")
    if temp is None and "air_temp" in weekend and weekend["air_temp"].notna().any():
        temp = float(weekend["air_temp"].median())
    rain = float(fq.get("pluie") or 0.0)
    f = features_for_race(q, TARGET_SEASON, next_idx, gp, circuit_type(TARGET_SEASON, gp)[0], entry_list(best), temp)
    f["pluie_talent"] = f["driver"].map(current_wet_skill(table)).fillna(0.0)
    fp = practice_deficit(best)
    fp = fp[(fp["season"] == TARGET_SEASON) & (fp["grand_prix"] == gp)]
    has_fp = len(fp) > 0
    f = f.merge(fp[["driver"] + FP_COLUMNS], on="driver", how="left")
    for c in FP_COLUMNS:
        f[c] = f[c].fillna(f[c].median() if has_fp else 1.5)
    f["season"], f["grand_prix"] = TARGET_SEASON, gp
    f = sprint.add_quali_sprint(f, best, ["essais"])      # qualif sprint du week-end, si elle a déjà eu lieu
    has_sq = bool(f["sprint_connu"].any())

    out = f[["driver", "team"]].copy()
    for family, c in chosen.items():
        if family == "après les essais libres" and not has_fp:
            continue
        tag = "avant" if family.startswith("avant") else "apres"

        def probs(feats, sigma, hist):
            if c["method"] == "logit conditionnel":
                return logit_probabilities(f, feats, fit_logit(table, feats, hist, TARGET_SEASON))
            mu = fit_regression(table, feats, hist, TARGET_SEASON).predict(f[feats])
            return pole_probabilities(mu, sigma, NOISE_DF)
        dry = probs(c["feats"], c["sigma"], c["hist"])
        wm = c["wet"]
        wet = probs(wm["feats"], wm["sigma"], wm["hist"]) if wm["talent"] else dry
        wet = weather.temper(wet, wm["lambda"])
        out[f"proba_pole_{tag}_sec"] = dry
        out[f"proba_pole_{tag}_pluie"] = wet
        out[f"proba_pole_{tag}"] = (1 - rain) * dry + rain * wet
    main_col = "proba_pole_apres" if has_fp else "proba_pole_avant"
    out = out.sort_values(main_col, ascending=False).reset_index(drop=True)
    sessions = sorted(best.loc[(best["season"] == TARGET_SEASON) & (best["grand_prix"] == gp)
                               & best["session"].str.startswith("Practice"), "session"].unique())
    status = ("après " + ", ".join(s.replace("Practice ", "EL") for s in sessions)) if has_fp \
        else "avant le week-end (aucun essai libre disponible)"
    if has_fp and has_sq:
        status += " et la qualif sprint"
    return out, status


def calibration_table(chosen: dict) -> pd.DataFrame:
    """Fiabilité sur toute la saison 2026 : quand le modèle annonce 30 %, la pole arrive-t-elle ~3 fois sur 10 ?"""
    rows = []
    bins = [0, 0.05, 0.15, 0.3, 1.0]
    for family, c in chosen.items():
        p = c["probs"][c["probs"]["season"] == TEST_SEASON].copy()
        p["tranche"] = pd.cut(p["p_pole"], bins, include_lowest=True)
        g = p.groupby("tranche", observed=True).agg(predictions=("p_pole", "size"), proba_moyenne=("p_pole", "mean"),
                                                     poles=("is_pole", "sum"))
        g["frequence_reelle"] = g["poles"] / g["predictions"]
        rows.append(g.reset_index().assign(modele=family, tranche=lambda d: d["tranche"].astype(str)))
    return pd.concat(rows, ignore_index=True).round(3)


def cached_backtest(table: pd.DataFrame):
    """Le backtest (plusieurs minutes) ne dépend que des courses passées : on le garde en cache
    tant qu'elles ne changent pas. Pendant le week-end, une mise à jour ne recalcule donc que la cible."""
    import hashlib
    import pickle
    from config import DATA_PROCESSED
    h = hashlib.sha1(pd.util.hash_pandas_object(table, index=False).values.tobytes())
    for f in sorted(Path(__file__).parent.glob("*.py")):   # tout changement de code invalide le cache
        h.update(f.read_bytes())
    key = h.hexdigest()
    path = DATA_PROCESSED / "cache_backtest.pkl"
    if path.exists():
        try:
            with open(path, "rb") as fh:
                saved = pickle.load(fh)
            if saved.get("key") == key:
                return saved["value"]
        except Exception:  # cache illisible (autre version de pandas...) : on recalcule
            pass
    value = backtest(table)
    with open(path, "wb") as fh:
        pickle.dump({"key": key, "value": value}, fh)
    return value


def run(best: pd.DataFrame, forecast: dict | None = None):
    gp = TARGET_GP.replace(" Grand Prix", "")
    table = sprint.add_quali_sprint(training_table(best, MAX_DEFICIT_PCT, exclude=(TARGET_SEASON, gp)), best, ["essais"])
    res, chosen, gains, base = cached_backtest(table)
    pred, status = predict_target(best, table, chosen, forecast)
    return {"table": table, "res": res, "chosen": chosen, "pred": pred, "status": status,
            "calib": calibration_table(chosen), "gains": gains, "history": history_table(chosen, base)}
