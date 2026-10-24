"""Paired timing summaries. Intervals describe measurement noise, not semantic equivalence."""

import math
import random
import statistics


def geomean(values):
    values = list(values)
    if not values or any(not math.isfinite(v) or v <= 0 for v in values):
        return None
    return math.exp(statistics.mean(math.log(v) for v in values))


def paired_summary(pairs, seed=0, resamples=2000):
    ratios = [p["baseline_ns"] / p["candidate_ns"] for p in pairs]
    if not ratios or any(not math.isfinite(r) or r <= 0 for r in ratios):
        raise ValueError("timings must be positive and finite")
    rng = random.Random(seed)
    samples = sorted(statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(resamples))
    interval = [samples[int(0.025 * resamples)], samples[min(resamples - 1, int(0.975 * resamples))]]
    return {"speedup": statistics.median(ratios), "speedup_ci95": interval,
            "faster": len(pairs) >= 5 and interval[0] > 1.0,
            "baseline_ns": statistics.median(p["baseline_ns"] for p in pairs),
            "candidate_ns": statistics.median(p["candidate_ns"] for p in pairs), "pairs": pairs}
