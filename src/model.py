"""Étape 4 (ML engineer) : du rythme prédit aux probabilités de pole.

1. Régression : prédire l'écart de chaque pilote au poleman (en %) à partir des variables.
2. Incertitude : écart réel = écart prédit + sigma x bruit, bruits indépendants entre pilotes
   (un tour raté, un drapeau jaune, le trafic...). Bruit normal, ou de Student (queues plus
   épaisses : les surprises sont moins improbables).
3. Probabilité de pole du pilote i = probabilité que son écart tiré au sort soit le plus petit,
   calculée exactement par intégration numérique :
       P(i) = intégrale de  densite_i(x) * produit_{j != i} P(écart_j > x)  dx
4. sigma est recalé AVANT chaque qualification sur les qualifications précédentes (les plus
   récentes comptent davantage) : il s'adapte quand la saison devient plus imprévisible.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.stats import t as student_t
from sklearn.linear_model import LinearRegression

SIGMA_GRID = np.round(np.arange(0.05, 1.51, 0.02), 2)
SIGMA_HALF_LIFE = 6      # en courses : poids des qualifs passées pour recaler sigma
SIGMA_MIN_RACES = 5      # en dessous, sigma par défaut
SIGMA_DEFAULT = 0.30
# Loi de bruit imposée : Student à 4 degrés de liberté. Avec une loi normale, une surprise comme
# Gasly en pole à Monza devient quasi impossible (probabilité ~0), ce qui détruit la log-loss.
# (Version précédente : choix normale / Student laissé aux données, abandonné après relecture.)
NOISE_LAWS = {"Student (4 ddl)": 4}


def pole_probabilities(mu: np.ndarray, sigma: float, df: int | None = None, n_grid: int = 4000) -> np.ndarray:
    mu = np.asarray(mu, dtype=float)
    dist = norm if df is None else student_t(df)
    x = np.linspace(mu.min() - 12 * sigma, mu.max() + 12 * sigma, n_grid)
    z = (x[None, :] - mu[:, None]) / sigma
    pdf = dist.pdf(z) / sigma                                   # densité de chaque pilote
    log_sf = dist.logsf(z)                                      # log P(écart > x)
    others = np.exp(log_sf.sum(axis=0)[None, :] - log_sf)       # produit sur les autres pilotes
    integrate = getattr(np, "trapezoid", None) or np.trapz
    p = integrate(pdf * others, x, axis=1)
    return p / p.sum()


def fit_regression(train: pd.DataFrame, features: list[str]) -> LinearRegression:
    # on n'apprend pas sur les incidents (crash, pas de tour) : ils ne disent rien du rythme
    ok = train[~train["incident"]]
    return LinearRegression().fit(ok[features], ok["target"])


def rolling_predictions(table: pd.DataFrame, features: list[str], min_train_races: int = 8) -> pd.DataFrame:
    """Backtest « comme en vrai » : pour chaque qualif, le modèle n'est entraîné que sur les
    qualifs précédentes (toutes saisons confondues), puis il prédit celle-ci."""
    races = table.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    out = []
    for i, (_, r) in enumerate(races.iterrows()):
        if i < min_train_races:
            continue
        train = table[table["date"] < r["date"]]
        test = table[(table["season"] == r["season"]) & (table["grand_prix"] == r["grand_prix"])].copy()
        test["pred"] = fit_regression(train, features).predict(test[features])
        out.append(test)
    return pd.concat(out, ignore_index=True)


def pole_probabilities_grid(mu: np.ndarray, sigmas: np.ndarray, df: int | None, n_grid: int = 600) -> np.ndarray:
    """Même calcul que pole_probabilities, pour toute une grille de sigma d'un coup (rapide).
    Renvoie un tableau (nombre de sigma, nombre de pilotes)."""
    mu = np.asarray(mu, dtype=float)
    dist = norm if df is None else student_t(df)
    sig = np.asarray(sigmas, dtype=float)[:, None]
    x = np.linspace(mu.min() - 12 * sig, mu.max() + 12 * sig, n_grid, axis=-1)[:, 0, :]        # (S, G)
    z = (x[:, None, :] - mu[None, :, None]) / sig[:, :, None]                              # (S, N, G)
    pdf = dist.pdf(z) / sig[:, :, None]
    log_sf = dist.logsf(z)
    others = np.exp(log_sf.sum(axis=1, keepdims=True) - log_sf)
    integrate = getattr(np, "trapezoid", None) or np.trapz
    p = integrate(pdf * others, x[:, None, :], axis=2)
    return p / p.sum(axis=1, keepdims=True)


def race_loglik_matrix(pred: pd.DataFrame, df: int | None) -> tuple[pd.DataFrame, np.ndarray]:
    """Pour chaque qualif (ligne) et chaque sigma de la grille (colonne) : log P(vrai poleman)."""
    races = pred.drop_duplicates(["season", "grand_prix"]).sort_values("date")[["season", "grand_prix", "date"]]
    mat = np.zeros((len(races), len(SIGMA_GRID)))
    for i, r in enumerate(races.itertuples()):
        g = pred[(pred["season"] == r.season) & (pred["grand_prix"] == r.grand_prix)]
        win = np.flatnonzero(g["is_pole"].to_numpy())[0]
        mat[i] = np.log(np.maximum(pole_probabilities_grid(g["pred"].to_numpy(), SIGMA_GRID, df)[:, win], 1e-9))
    return races.reset_index(drop=True), mat


def rolling_sigma(mat: np.ndarray) -> np.ndarray:
    """sigma utilisé pour la qualif i = celui qui maximise la vraisemblance des qualifs 0..i-1,
    pondérées par leur ancienneté (demi-vie SIGMA_HALF_LIFE courses)."""
    sig = np.full(len(mat), SIGMA_DEFAULT)
    for i in range(SIGMA_MIN_RACES, len(mat)):
        w = 0.5 ** ((i - 1 - np.arange(i)) / SIGMA_HALF_LIFE)
        sig[i] = SIGMA_GRID[int(np.argmax(w @ mat[:i]))]
    return sig


def latest_sigma(mat: np.ndarray) -> float:
    """sigma pour la prochaine qualif (après toutes celles connues)."""
    n = len(mat)
    w = 0.5 ** ((n - 1 - np.arange(n)) / SIGMA_HALF_LIFE)
    return float(SIGMA_GRID[int(np.argmax(w @ mat))])


def probabilities_with(pred: pd.DataFrame, sigma_by_race: dict, df: int | None) -> pd.DataFrame:
    pred = pred.copy()
    pred["p_pole"] = np.nan
    for (season, gp), idx in pred.groupby(["season", "grand_prix"]).groups.items():
        pred.loc[idx, "p_pole"] = pole_probabilities(pred.loc[idx, "pred"].to_numpy(), sigma_by_race[(season, gp)], df)
    return pred


def season_share_baseline(table: pd.DataFrame) -> pd.DataFrame:
    """Référence naïve : chance proportionnelle au nombre de poles déjà faites cette saison (+ 0,5)."""
    out = []
    poles = table[table["is_pole"]][["season", "date", "driver"]]
    for (season, gp), g in table.groupby(["season", "grand_prix"]):
        past = poles[(poles["season"] == season) & (poles["date"] < g["date"].iloc[0])]
        w = g["driver"].map(past["driver"].value_counts()).fillna(0).to_numpy() + 0.5
        out.append(g.assign(p_pole=w / w.sum()))
    return pd.concat(out, ignore_index=True)


def per_race_logloss(p: pd.DataFrame) -> pd.Series:
    w = p[p["is_pole"]].set_index(["season", "grand_prix"])["p_pole"]
    return -np.log(w.clip(lower=1e-9))


def scores(p: pd.DataFrame) -> dict:
    """Métriques sur les qualifs testées :
    - log-loss : -log(probabilité donnée au vrai poleman), plus petit = mieux
      (un tirage au hasard parmi 22 pilotes donne ln(22) = 3,09) ;
    - Brier : écart quadratique entre probabilités et résultat (0 = parfait) ;
    - favori juste : le pilote le plus probable a fait la pole ;
    - dans le top 3 : le poleman était parmi les 3 pilotes les plus probables."""
    p = p.copy()
    p["rank"] = p.groupby(["season", "grand_prix"])["p_pole"].rank(ascending=False, method="first")
    winners = p[p["is_pole"]]
    brier = ((p["p_pole"] - p["is_pole"].astype(float)) ** 2).groupby([p["season"], p["grand_prix"]]).sum()
    return {
        "qualifs": len(winners),
        "log_loss": round(float(per_race_logloss(p).mean()), 3),
        "brier": round(float(brier.mean()), 3),
        "favori_juste": int((winners["rank"] == 1).sum()),
        "poleman_dans_top3": int((winners["rank"] <= 3).sum()),
        "proba_moyenne_du_poleman": round(float(winners["p_pole"].mean()), 3),
    }


def bootstrap_gain(a: pd.Series, b: pd.Series, n: int = 5000, seed: int = 0) -> tuple[float, float, float]:
    """Gain moyen de log-loss de a par rapport à b (b - a, positif = a meilleur) et IC 95 %
    par bootstrap sur les qualifs (on retire au hasard des qualifs avec remise)."""
    d = (b - a.reindex(b.index)).to_numpy()
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, size=(n, len(d)), replace=True).mean(axis=1)
    return round(float(d.mean()), 3), round(float(np.quantile(boots, 0.025)), 3), round(float(np.quantile(boots, 0.975)), 3)


# ---------------------------------------------------------------------------------------------
# Autre approche : logit conditionnel (modèle de choix). On apprend DIRECTEMENT qui fait la pole :
#   P(i fait la pole) = exp(-score_i) / somme_j exp(-score_j),   score_i = somme_k w_k * x_ik
# Les variables sont exprimées par rapport au meilleur pilote de la course (x - min).
# Contrairement à la régression, seuls les pilotes de tête pèsent dans l'apprentissage.
# ---------------------------------------------------------------------------------------------
from scipy.optimize import minimize  # noqa: E402

LOGIT_L2 = 0.01


def _centered(g: pd.DataFrame, features: list[str]) -> np.ndarray:
    x = g[features].to_numpy(dtype=float)
    return x - x.min(axis=0, keepdims=True)


def fit_logit(train: pd.DataFrame, features: list[str]) -> np.ndarray:
    groups = [(_centered(g, features), g["is_pole"].to_numpy()) for _, g in train.groupby(["season", "grand_prix"])
              if g["is_pole"].sum() == 1]

    def nll(w):
        total, grad = 0.0, np.zeros_like(w)
        for x, y in groups:
            s = -x @ w
            s -= s.max()
            p = np.exp(s) / np.exp(s).sum()
            total -= np.log(p[y][0] + 1e-12)
            grad += x[y][0] - p @ x
        return total + LOGIT_L2 * w @ w, grad + 2 * LOGIT_L2 * w

    res = minimize(nll, np.ones(len(features)), jac=True, method="L-BFGS-B")
    return res.x


def logit_probabilities(g: pd.DataFrame, features: list[str], w: np.ndarray) -> np.ndarray:
    s = -_centered(g, features) @ w
    s -= s.max()
    return np.exp(s) / np.exp(s).sum()


def rolling_logit(table: pd.DataFrame, features: list[str], min_train_races: int = 8) -> pd.DataFrame:
    races = table.drop_duplicates(["season", "grand_prix"]).sort_values("date")
    out = []
    for i, (_, r) in enumerate(races.iterrows()):
        if i < min_train_races:
            continue
        w = fit_logit(table[table["date"] < r["date"]], features)
        g = table[(table["season"] == r["season"]) & (table["grand_prix"] == r["grand_prix"])].copy()
        g["p_pole"] = logit_probabilities(g, features, w)
        out.append(g)
    return pd.concat(out, ignore_index=True)
