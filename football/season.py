"""Pronostics des matchs à venir et simulation de la fin de saison."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.optimize import minimize

try:
    from football import model as M
except ImportError:
    import model as M  # type: ignore

PARIS = ZoneInfo("Europe/Paris")
LONDON = ZoneInfo("Europe/London")   # heures de football-data
N_SIM = 10000


def round_probs(p) -> list[float]:
    """Probabilités 1/N/2 au pour cent près, qui somment toujours à 1."""
    q = np.round(np.asarray(p, float) * 100)
    q[int(np.argmax(q))] += 100 - q.sum()
    return [round(float(x) / 100, 2) for x in q]


def calibrate_rates(lh: float, la: float, target: np.ndarray, rho: float) -> tuple[float, float]:
    """Ajuste les buts attendus pour que le score probable colle aux probabilités 1/N/2 retenues
    (celles du mélange avec le marché), en restant proche du modèle."""
    def loss(x):
        p = M.outcome(M.score_matrix(np.exp(x[0]), np.exp(x[1]), rho))
        return ((p - target) ** 2).sum() + 1e-3 * ((x[0] - np.log(lh)) ** 2 + (x[1] - np.log(la)) ** 2)
    r = minimize(loss, np.log([lh, la]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 400})
    return float(np.exp(r.x[0])), float(np.exp(r.x[1]))


def kickoff_utc(date: pd.Timestamp, time: str | None, tz: ZoneInfo = PARIS) -> str | None:
    """Heure locale (Paris pour le calendrier, Londres pour football-data) -> ISO UTC.
    Sans heure connue : None (la page affiche alors seulement la date)."""
    if pd.isna(date) or not time or str(time) == "nan":
        return None
    hh, mm = (str(time).split(":") + ["0"])[:2]
    local = datetime(date.year, date.month, date.day, int(hh), int(mm), tzinfo=tz)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def predict_fixtures(fx: pd.DataFrame, played: pd.DataFrame, fit: dict, settings: dict) -> pd.DataFrame:
    """Une ligne par match du calendrier : score réel s'il est joué, sinon pronostic."""
    rho, a, b = settings["rho"], settings["a"], settings["b"]
    res = played.set_index(["home", "away"])[["hg", "ag", "hxg", "axg", "date"]]
    rows = []
    for r in fx.itertuples():
        ko = kickoff_utc(r.date, r.time)
        fd_date = getattr(r, "fd_date", None)
        if fd_date is not None and not pd.isna(fd_date):
            ko = kickoff_utc(fd_date, getattr(r, "fd_time", None), LONDON)
        day = fd_date if fd_date is not None and not pd.isna(fd_date) else r.date
        row = {"round": int(r.round), "home": r.home, "away": r.away, "kickoff": ko,
               "jour": None if pd.isna(day) else day.strftime("%Y-%m-%d")}
        if (r.home, r.away) in res.index:
            x = res.loc[(r.home, r.away)]
            row.update(played=True, hg=int(x["hg"]), ag=int(x["ag"]), date=x["date"].strftime("%Y-%m-%d"),
                       hxg=None if pd.isna(x["hxg"]) else float(x["hxg"]), axg=None if pd.isna(x["axg"]) else float(x["axg"]))
        else:
            lh, la = M.rates(fit, r.home, r.away)
            p_model = M.outcome(M.score_matrix(lh, la, rho))
            odds = np.array([[r.oh, r.od, r.oa]], float)
            p_mkt = M.market_probs(odds) if np.isfinite(odds).all() else np.full((1, 3), np.nan)
            p = M.blend(p_model[None, :], p_mkt, a, b)[0]
            has_market = bool(np.isfinite(p_mkt).all())
            if has_market:
                lh, la = calibrate_rates(lh, la, p, rho)
            mat = M.score_matrix(lh, la, rho)
            flat = np.argsort(mat, axis=None)[::-1][:3]
            scores = [{"score": f"{i // mat.shape[1]}-{i % mat.shape[1]}", "p": round(float(mat.flat[i]), 2)} for i in flat]
            g = np.add.outer(np.arange(mat.shape[0]), np.arange(mat.shape[1]))
            # arrondi au pour cent : la page n'en montre pas plus, et on ne peut pas en déduire les cotes
            row.update(played=False, p=round_probs(p), with_market=has_market, xg=[round(lh, 1), round(la, 1)], scores=scores,
                       over25=round(float(mat[g > 2].sum()), 2),
                       btts=round(float(mat[1:, 1:].sum()), 2), lam_h=lh, lam_a=la)
        rows.append(row)
    return pd.DataFrame(rows)


def table(played: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    t = pd.DataFrame(0, index=teams, columns=["j", "g", "n", "p", "bp", "bc", "pts"])
    for r in played.itertuples():
        for team, gf, ga in ((r.home, r.hg, r.ag), (r.away, r.ag, r.hg)):
            if team not in t.index:
                continue
            t.loc[team, ["j", "bp", "bc"]] += [1, gf, ga]
            k = "g" if gf > ga else "n" if gf == ga else "p"
            t.loc[team, k] += 1
            t.loc[team, "pts"] += 3 if gf > ga else 1 if gf == ga else 0
    t["diff"] = t["bp"] - t["bc"]
    return t.sort_values(["pts", "diff", "bp"], ascending=False)


def simulate(played: pd.DataFrame, upcoming: pd.DataFrame, teams: list[str], rho: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """10 000 fins de saison : buts tirés selon les buts attendus de chaque match restant.
    Classement : points, différence de buts, buts marqués."""
    rng = np.random.default_rng(seed)
    idx = {t: i for i, t in enumerate(teams)}
    base = table(played, teams).reindex(teams)
    pts = np.tile(base["pts"].to_numpy(float), (N_SIM, 1))
    gd = np.tile(base["diff"].to_numpy(float), (N_SIM, 1))
    gf = np.tile(base["bp"].to_numpy(float), (N_SIM, 1))
    for r in upcoming.itertuples():
        h, a = idx[r.home], idx[r.away]
        # tirage dans la même grille de scores que le pronostic affiché (correction des nuls comprise)
        mat = M.score_matrix(r.lam_h, r.lam_a, rho)
        k = rng.choice(mat.size, N_SIM, p=mat.ravel())
        x, y = k // mat.shape[1], k % mat.shape[1]
        pts[:, h] += np.where(x > y, 3, np.where(x == y, 1, 0))
        pts[:, a] += np.where(y > x, 3, np.where(x == y, 1, 0))
        gd[:, h] += x - y; gd[:, a] += y - x
        gf[:, h] += x; gf[:, a] += y
    key = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random(pts.shape) * 1e-3
    rank = (-key).argsort(axis=1).argsort(axis=1) + 1
    n = len(teams)
    out = pd.DataFrame({"club": teams, "points_attendus": pts.mean(axis=0).round(1),
                        "titre": (rank == 1).mean(axis=0), "top3": (rank <= 3).mean(axis=0), "top4": (rank <= 4).mean(axis=0),
                        "top6": (rank <= 6).mean(axis=0), "barrage": (rank == n - 2).mean(axis=0),
                        "relegation": (rank >= n - 1).mean(axis=0), "rang_moyen": rank.mean(axis=0).round(1)})
    dist = np.stack([(rank == k).mean(axis=0) for k in range(1, n + 1)], axis=1)
    out["places"] = [list(np.round(d, 4)) for d in dist]
    return out.sort_values(["rang_moyen"]).reset_index(drop=True)
