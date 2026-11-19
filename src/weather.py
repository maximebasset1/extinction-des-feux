"""Météo : prévision du week-end (Open-Meteo) et « module pluie » du modèle de pole.

Le module pluie a deux leviers, évalués sur les qualifs mouillées passées (jamais sur celle à prédire) :
- talent_pluie : certains pilotes gagnent du temps sous la pluie par rapport à leur forme sur le sec ;
- incertitude : sous la pluie, la hiérarchie est moins nette. On aplatit les probabilités :
  p_i ∝ p_i ** lambda, avec lambda < 1 recalé sur les qualifs mouillées précédentes.
Avant une qualif, on ne sait pas s'il pleuvra : on mélange les deux scénarios selon la prévision,
p = (1 - risque) * p_sec + risque * p_pluie.

Prévision : Open-Meteo (gratuit, sans clé, données CC BY 4.0, source citée sur le site).
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

LAMBDAS = np.round(np.arange(0.3, 1.51, 0.05), 2)
MIN_WET_RACES = 3
API = "https://api.open-meteo.com/v1/forecast"


# ------------------------------------------------------------------ module pluie (modèle)
def temper(p: np.ndarray, lam: float) -> np.ndarray:
    q = np.power(np.clip(p, 1e-12, 1.0), lam)
    return q / q.sum()


def _wet_races(probs: pd.DataFrame) -> list:
    w = probs[probs["wet"].astype(bool)]
    return w.drop_duplicates(["season", "grand_prix"]).sort_values("date")[["season", "grand_prix", "date"]].values.tolist()


def _loglik(probs: pd.DataFrame, races: list, lam: float) -> float:
    total = 0.0
    for season, gp, _ in races:
        g = probs[(probs["season"] == season) & (probs["grand_prix"] == gp)]
        p = temper(g["p_pole"].to_numpy(), lam)
        hit = g["is_pole"].to_numpy()
        if hit.any():
            total += float(np.log(p[hit][0] + 1e-12))
    return total


def best_lambda(probs: pd.DataFrame, races: list) -> float:
    if len(races) < MIN_WET_RACES:
        return 1.0
    return float(LAMBDAS[int(np.argmax([_loglik(probs, races, l) for l in LAMBDAS]))])


def tempered(probs: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Applique, à chaque qualif mouillée, le lambda appris sur les qualifs mouillées d'AVANT."""
    out = probs.copy()
    races = _wet_races(probs)
    for i, (season, gp, _) in enumerate(races):
        lam = best_lambda(probs, races[:i])
        idx = out.index[(out["season"] == season) & (out["grand_prix"] == gp)]
        out.loc[idx, "p_pole"] = temper(out.loc[idx, "p_pole"].to_numpy(), lam)
    return out, best_lambda(probs, races)


def wet_logloss(probs: pd.DataFrame, period: str) -> tuple[float, int]:
    w = probs[probs["wet"].astype(bool)]
    w = w[w["season"] < 2026] if period == "choix" else w[w["season"] >= 2026]
    hits = w[w["is_pole"]]["p_pole"]
    return (round(float(-np.log(hits.clip(lower=1e-6)).mean()), 3) if len(hits) else np.nan), int(len(hits))


def evaluate_module(base: pd.DataFrame, with_talent: pd.DataFrame) -> dict:
    """Compare 4 versions sur les qualifs mouillées d'avant 2026 (choix) et de 2026 (contrôle)."""
    t_base, lam_base = tempered(base)
    t_tal, lam_tal = tempered(with_talent)
    variants = {"aucun": (base, False, 1.0), "incertitude": (t_base, False, lam_base),
                "talent pluie": (with_talent, True, 1.0), "talent pluie + incertitude": (t_tal, True, lam_tal)}
    rows = []
    for name, (p, talent, lam) in variants.items():
        ll_c, n_c = wet_logloss(p, "choix")
        ll_t, n_t = wet_logloss(p, "test")
        rows.append({"version": name, "talent": talent, "lambda": lam, "log_loss_pluie_choix": ll_c,
                     "qualifs_choix": n_c, "log_loss_pluie_2026": ll_t, "qualifs_2026": n_t})
    res = pd.DataFrame(rows)
    ok = res.dropna(subset=["log_loss_pluie_choix"])
    best = ok.loc[ok["log_loss_pluie_choix"].idxmin()] if len(ok) and ok["qualifs_choix"].max() >= MIN_WET_RACES \
        else res.iloc[0]
    res["choisi"] = np.where(res["version"] == best["version"], "oui", "")
    return {"table": res, "version": best["version"], "talent": bool(best["talent"]), "lambda": float(best["lambda"])}


# ------------------------------------------------------------------ prévision (Open-Meteo)
def _parse(iso: str) -> datetime:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)  # heure sans fuseau : UTC


def summarize(hourly: dict, start: datetime, hours: float) -> dict | None:
    """Risque de pluie (max sur la séance), pluie attendue (mm) et température pendant la séance.
    Chez Open-Meteo, la pluie à l'heure T couvre l'heure qui précède T : on garde les T dans
    ]début arrondi à l'heure inférieure ; fin arrondie à l'heure supérieure]."""
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly.get("time", [])]
    lo = start.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=hours)
    hi = end if end == end.replace(minute=0, second=0, microsecond=0) else \
        end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    idx = [i for i, t in enumerate(times) if lo < t <= hi]
    if not idx:
        return None

    def pick(k):
        v = [hourly.get(k, [None] * len(times))[i] for i in idx]
        return [x for x in v if x is not None]
    prob, rain, temp = pick("precipitation_probability"), pick("precipitation"), pick("temperature_2m")
    risk = max(prob) / 100 if prob else (1.0 if rain and max(rain) >= 0.5 else 0.0)
    return {"pluie": round(float(risk), 2), "pluie_mm": round(float(sum(rain)), 1) if rain else None,
            "temperature": round(float(np.mean(temp)), 1) if temp else None}


def forecast(info: dict, now: datetime | None = None, timeout: int = 20) -> dict | None:
    """Prévision pour la qualif (Q) et la course (R) du GP cible, si elles ont lieu dans les 15 jours."""
    now = now or datetime.now(timezone.utc)
    lat, lon, ses = info.get("lat"), info.get("lon"), info.get("sessions", {})
    if lat is None or lon is None or not ses:
        return None
    wanted = {k: _parse(ses[k]) for k in ("Q", "R") if k in ses and now - timedelta(hours=3) < _parse(ses[k]) < now + timedelta(days=15)}
    if not wanted:
        return None
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "timezone": "UTC", "forecast_days": 16,
                                "hourly": "precipitation_probability,precipitation,temperature_2m"})
    try:
        with urllib.request.urlopen(f"{API}?{q}", timeout=timeout) as r:
            hourly = json.load(r)["hourly"]
    except Exception as exc:  # pas de prévision : le modèle suppose une piste sèche, et le site le dit
        print(f"Prévision météo indisponible ({exc})")
        return None
    out = {k: summarize(hourly, t, 1.0 if k == "Q" else 2.0) for k, t in wanted.items()}
    out = {k: v for k, v in out.items() if v}
    if out:
        out["source"] = "Open-Meteo"
        out["maj_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out or None
