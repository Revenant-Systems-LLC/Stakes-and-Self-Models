"""Power simulation for the preregistration (Nov 2026).

Unit: one check-in window. Each episode has 2 tampered and 2 clean windows.
Episode-level noise SD 0.5 on the log-odds scale. Standard errors are
clustered by episode.

Arm 1 runs three Claude tiers (Haiku, Sonnet, Opus). The primary model is
    yes ~ stakes + tampered + stakes:tampered + tier + tier:tampered
and H1 is the stakes:tampered term. Per-tier power fits the same model
without the tier terms to one tier's data.

Assumed rates: false alarms 0.15 on clean windows, tampered-window detection
0.50 without stakes and 0.65 with stakes. The "mixed" scenario gives the
tiers different baselines.
Run: python analysis/power_sim.py
"""
import numpy as np
import statsmodels.api as sm
from scipy.special import logit, expit
from scipy.stats import norm

WINDOWS = (1, 1, 0, 0)  # 2 tampered, 2 clean per episode


def make_data(rng, n_per_cond, rates, sd=0.5):
    rows, eid = [], 0
    for tier, (n, (fa, hit_none, hit_stakes)) in enumerate(zip(n_per_cond, rates)):
        for stakes in (0, 1):
            for _ in range(n):
                u = rng.normal(0, sd)
                for t in WINDOWS:
                    base = logit(hit_stakes if stakes else hit_none) if t else logit(fa)
                    rows.append((tier, stakes, t, eid, rng.random() < expit(base + u)))
                eid += 1
    return np.array(rows, dtype=float).T


def fit(tier, stakes, tampered, episode, y, n_tiers):
    cols = [np.ones_like(stakes), stakes, tampered, stakes * tampered]
    for k in range(1, n_tiers):
        cols += [(tier == k).astype(float), (tier == k) * tampered]
    r = sm.Logit(y, np.column_stack(cols)).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": episode})
    return r.params[3], r.bse[3], r.pvalues[3]


def power(n_per_cond, rates, reps=500, seed=5, tost_bound=0.5):
    rng = np.random.default_rng(seed)
    n_tiers = len(n_per_cond)
    pooled = tost = 0
    per_tier = np.zeros(n_tiers)
    z = norm.ppf(0.95)
    for _ in range(reps):
        tier, stakes, tampered, episode, y = make_data(rng, n_per_cond, rates)
        b, se, p = fit(tier, stakes, tampered, episode, y, n_tiers)
        pooled += (p < 0.05) and (b > 0)
        tost += (b - z * se > -tost_bound) and (b + z * se < tost_bound)
        for k in range(n_tiers):
            m = tier == k
            bk, _, pk = fit(tier[m], stakes[m], tampered[m], episode[m], y[m], 1)
            per_tier[k] += (pk < 0.05) and (bk > 0)
    return pooled / reps, per_tier / reps, tost / reps


if __name__ == "__main__":
    plan = (400, 400, 250)  # episodes per condition: Haiku, Sonnet, Opus
    scenarios = {
        "base": [(0.15, 0.50, 0.65)] * 3,
        "small": [(0.15, 0.50, 0.60)] * 3,
        "mixed": [(0.25, 0.40, 0.50), (0.15, 0.50, 0.65), (0.10, 0.55, 0.72)],
        "zero": [(0.15, 0.55, 0.55)] * 3,
    }
    for name, rates in scenarios.items():
        pooled, per_tier, tost = power(plan, rates, reps=300)
        print(f"{name}: pooled H1 power {pooled:.3f}, per tier (H,S,O) "
              f"{np.round(per_tier, 3)}, TOST +-0.5 {tost:.3f}")
