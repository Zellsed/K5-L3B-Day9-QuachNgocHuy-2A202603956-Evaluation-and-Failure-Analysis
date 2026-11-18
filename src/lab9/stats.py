
from __future__ import annotations

from collections.abc import Sequence
from math import comb

import numpy as np
from scipy.stats import bootstrap

POS = "FAIL"  

def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    out = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for actual, predicted in zip(human, judge, strict=True):
        a_fail, j_fail = actual.upper() == POS, predicted.upper() == POS
        if a_fail and j_fail:
            out["tp"] += 1
        elif not a_fail and j_fail:
            out["fp"] += 1
        elif a_fail:
            out["fn"] += 1
        else:
            out["tn"] += 1
    return out


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    if len(human) != len(judge) or not human:
        raise ValueError("human and judge must be non-empty and have the same length")
    human = [x.upper() for x in human]
    judge = [x.upper() for x in judge]
    p_observed = sum(h == j for h, j in zip(human, judge, strict=True)) / len(human)
    human_fail = sum(x == POS for x in human) / len(human)
    judge_fail = sum(x == POS for x in judge) / len(judge)
    p_expected = human_fail * judge_fail + (1 - human_fail) * (1 - judge_fail)
    if np.isclose(p_expected, 1.0):
        raise ValueError("kappa is undefined when expected agreement is 1")
    return (p_observed - p_expected) / (1 - p_expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denominator = sensitivity + specificity - 1
    if np.isclose(denominator, 0.0):
        raise ValueError("Rogan-Gladen is undefined when sensitivity + specificity == 1")
    return float(np.clip((observed_rate + specificity - 1) / denominator, 0.0, 1.0))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:

    if len(a) != len(b) or not a:
        raise ValueError("paired bootstrap needs equally-sized, non-empty samples")
    left, right = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if np.array_equal(left, right):
        return 0.0, 0.0, 0.0
    result = bootstrap(
        (left, right),
        lambda x, y, axis: np.mean(x - y, axis=axis),
        paired=True,
        vectorized=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return float(np.mean(left - right)), float(result.confidence_interval.low), float(result.confidence_interval.high)


def pass_at_k(n: int, c: int, k: int) -> float:

    _validate_pass_args(n, c, k)
    return 1.0 - comb(n - c, k) / comb(n, k) if n - c >= k else 1.0


def pass_hat_k(n: int, c: int, k: int) -> float:

    _validate_pass_args(n, c, k)
    return comb(c, k) / comb(n, k) if c >= k else 0.0


def _validate_pass_args(n: int, c: int, k: int) -> None:
    if not all(isinstance(v, int) for v in (n, c, k)) or n <= 0 or not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("require n > 0, 0 <= c <= n, and 1 <= k <= n")
