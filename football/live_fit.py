"""Règle le modèle du direct sur l'historique, puis le juge à la mi-temps sur des saisons jamais vues.

Données : football-data.co.uk (12 championnats, score à la pause, score final, cotes d'avant-match).
Réglage sur 2010-2021 ; jugement sur 2022 et après : à la pause, quelle chance de victoire,
de nul et de défaite, comparée au résultat final.

    EU_DATA_DIR=... python football/live_fit.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from football import data as D, leagues, live as L, model as M  # noqa: E402

RAW = Path(os.environ.get("EU_DATA_DIR", Path(__file__).resolve().parent.parent / "data/football/eu"))
CHOICE = range(2010, 2022)
FIT_SAMPLE = 8000
CHUNK = 6000
HALF_K = 8


def load() -> pd.DataFrame:
    rows = []
    for code in leagues.MAIN:
        for y in range(2010, 2030):
            f = RAW / f"{code}_{y}.csv"
            if not f.exists():
                continue
            df = pd.read_csv(io.StringIO(f.read_bytes().decode("latin-1").lstrip("﻿")), on_bad_lines="skip")
            if "HTHG" not in df:
                continue
            o = D._odds(df, D.PRE_MATCH)
            num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
            rows.append(pd.DataFrame({"league": code, "season": y, "hg": num("FTHG"), "ag": num("FTAG"),
                                      "hh": num("HTHG"), "ha": num("HTAG"), "oh": o[:, 0], "od": o[:, 1], "oa": o[:, 2]}))
    d = pd.concat(rows, ignore_index=True).dropna()
    d = d[(d["hh"] <= d["hg"]) & (d["ha"] <= d["ag"])].astype({c: int for c in ("hg", "ag", "hh", "ha")})
    p = M.market_probs(d[["oh", "od", "oa"]].to_numpy(float))
    d[["p1", "pn", "p2"]] = p
    return d.reset_index(drop=True)


def chunked(fn, n: int, *arrays):
    return np.concatenate([fn(*(a[i:i + CHUNK] for a in arrays)) for i in range(0, n, CHUNK)])


def lam_for(p: np.ndarray, params: dict) -> np.ndarray:
    return chunked(lambda q: L.calibrate(q, params), len(p), p)


def unpack(theta: np.ndarray) -> dict:
    """Trois réglages : part des buts en 1re mi-temps, rythme d'une équipe menée, rythme d'une équipe qui mène."""
    mt, ml = float(np.exp(theta[1])), float(np.exp(theta[2]))
    return {"part_1re_mi_temps": float(1 / (1 + np.exp(-theta[0]))), "rythme_selon_ecart": [mt, mt, 1.0, ml, ml]}


def neg_loglik(theta: np.ndarray, lam: np.ndarray, d: pd.DataFrame) -> float:
    params = unpack(theta)
    n = len(d)
    zeros = np.zeros(n, int)
    # première mi-temps depuis 0-0 : probabilité du score à la pause
    first = L._run(_start(n, HALF_K), lam[:, 0], lam[:, 1], zeros, params["part_1re_mi_temps"] / L.HALF_MINUTES[0],
                   np.full(n, L.HALF_MINUTES[0]), params, L.STEPS_PER_HALF)
    hh, ha = np.minimum(d["hh"].to_numpy(), HALF_K - 1), np.minimum(d["ha"].to_numpy(), HALF_K - 1)
    ll = np.log(np.maximum(first[np.arange(n), hh, ha], 1e-12)).sum()
    # seconde mi-temps depuis le score de la pause : probabilité des buts marqués ensuite
    second = L._run(_start(n, HALF_K), lam[:, 0], lam[:, 1], (d["hh"] - d["ha"]).to_numpy(),
                    (1 - params["part_1re_mi_temps"]) / L.HALF_MINUTES[1], np.full(n, L.HALF_MINUTES[1]), params,
                    L.STEPS_PER_HALF)
    gh, ga = np.minimum((d["hg"] - d["hh"]).to_numpy(), HALF_K - 1), np.minimum((d["ag"] - d["ha"]).to_numpy(), HALF_K - 1)
    ll += np.log(np.maximum(second[np.arange(n), gh, ga], 1e-12)).sum()
    return -ll / n


def _start(n: int, k: int) -> np.ndarray:
    s = np.zeros((n, k, k))
    s[:, 0, 0] = 1.0
    return s


def fit(train: pd.DataFrame) -> dict:
    """Maximum de vraisemblance des scores à la pause puis en fin de match. Les buts attendus de chaque match
    sont recalculés à chaque essai de réglages : ils doivent toujours redonner les cotes au coup d'envoi."""
    rng = np.random.default_rng(0)
    sub = train.iloc[rng.choice(len(train), min(FIT_SAMPLE, len(train)), replace=False)].reset_index(drop=True)
    p = sub[["p1", "pn", "p2"]].to_numpy()
    seen = {"n": 0}

    def objective(t):
        lam = chunked(lambda q: L.calibrate(q, unpack(t), iters=8), len(p), p)   # départ fixe : calcul reproductible
        seen["n"] += 1
        return neg_loglik(t, lam, sub)

    start = np.array([np.log(0.44 / 0.56), 0.0, 0.0])
    res = minimize(objective, start, method="Nelder-Mead",
                   options={"maxfev": 70, "xatol": 0.01, "fatol": 1e-5, "initial_simplex": start + np.vstack([np.zeros(3), 0.15 * np.eye(3)])})
    print(f"   log-vraisemblance moyenne {-res.fun:.4f} après {seen['n']} essais ; réglages {json.dumps(unpack(res.x))}")
    return unpack(res.x)


def halftime_probs(d: pd.DataFrame, params: dict) -> np.ndarray:
    lam = lam_for(d[["p1", "pn", "p2"]].to_numpy(), params)
    hh, ha = d["hh"].to_numpy(), d["ha"].to_numpy()

    def one(lh, la, h, a):
        return L.outcome_from(L.remaining(lh, la, h, a, 2, 1.0, params), h, a)

    return chunked(one, len(d), lam[:, 0], lam[:, 1], hh, ha)


def scores(p: np.ndarray, y: np.ndarray) -> dict:
    ll = M.logloss(p, y).mean()
    return {"log_loss": round(float(ll), 4), "rps": round(float(M.rps(p, y).mean()), 4),
            "favori_juste": round(float((p.argmax(1) == y).mean()), 3)}


def main() -> None:
    d = load()
    y = np.select([d["hg"] > d["ag"], d["hg"] == d["ag"]], [0, 1], 2)
    train, test = d[d["season"].isin(CHOICE)], d[~d["season"].isin(CHOICE)]
    yt = y[~d["season"].isin(CHOICE)]
    print(f"{len(train)} matchs pour régler, {len(test)} pour juger")
    params = fit(train)
    s1 = float((train["hh"] + train["ha"]).sum() / (train["hg"] + train["ag"]).sum())
    variants = {
        "avant le match (le score de la pause est ignoré)": None,
        "temps restant seulement, buts répartis à parts égales": {"part_1re_mi_temps": 0.5, "rythme_selon_ecart": [1.0] * 5},
        "temps restant, part réelle de chaque mi-temps": {"part_1re_mi_temps": s1, "rythme_selon_ecart": [1.0] * 5},
        "modèle complet (temps restant et écart au score)": params,
    }
    table = []
    for name, prm in variants.items():
        p = test[["p1", "pn", "p2"]].to_numpy() if prm is None else halftime_probs(test, prm)
        sc = scores(p, yt)
        table.append({"methode": name, **sc})
        print(f"   {name} : {sc}")
        if prm is params:
            full = p
    # fiabilité : chances annoncées à la pause, regroupées, contre la fréquence observée
    bins = np.linspace(0, 1, 11)
    calib = []
    for k, lab in enumerate(("domicile", "nul", "exterieur")):
        idx = np.clip(np.digitize(full[:, k], bins) - 1, 0, 9)
        for b in range(10):
            sel = idx == b
            if sel.sum() >= 100:
                calib.append({"issue": lab, "annonce": round(float(full[sel, k].mean()), 3),
                              "observe": round(float((yt[sel] == k).mean()), 3), "matchs": int(sel.sum())})
    out = {**params, "periode_choix": f"{CHOICE.start}-{CHOICE.stop - 1}",
           "periode_test": f"{int(test['season'].min())}-{int(test['season'].max())}", "matchs_test": int(len(test)),
           "jugement_mi_temps": table, "fiabilite_mi_temps": calib}
    L.PARAMS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"réglages écrits dans {L.PARAMS_FILE.name}")


if __name__ == "__main__":
    main()
