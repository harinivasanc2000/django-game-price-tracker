"""
Depth-1 gradient booster.

Same training loop as XGBoost / LightGBM, cut down so the site can fit a
yes/no model on one product's own history without a native library:

  score starts at the base-rate log-odds
  each round fits a single if/else (a stump) to the gradient y - p
  the stump's leaf values are a Newton step, shrunk by the learning rate

Feature columns are plain floats. Any catalogue (games, trainers, books)
can reuse StumpBooster if it builds a numeric matrix and 0/1 labels.
"""

from __future__ import annotations

import math

FEATURE_NAMES: tuple[str, ...] = (
    "discount_pct",
    "pct_under_reference",
    "days_since_last_drop",
    "days_until_promo",
    "inside_promo",
    "change_14d_pct",
    "stock_trend",
)


def sigmoid(score: float) -> float:
    if score >= 20:
        return 1.0
    if score <= -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-score))


class StumpBooster:
    def __init__(
        self,
        n_rounds: int = 16,
        learning_rate: float = 0.25,
        min_leaf: int = 2,
        l2: float = 1.0,
    ):
        self.n_rounds = n_rounds
        self.learning_rate = learning_rate
        self.min_leaf = min_leaf
        self.l2 = l2
        self.bias = 0.0
        self.stumps: list[tuple[int, float, float, float]] = []
        self.n_rows = 0

    def fit(self, rows: list[list[float]], labels: list[int]) -> StumpBooster:
        n = len(labels)
        self.n_rows = n
        self.stumps = []
        if n < max(4, self.min_leaf * 2) or not rows or len(rows) != n:
            self.bias = 0.0
            return self
        width = len(rows[0])
        positives = sum(1 for y in labels if y)
        rate = min(max(positives / n, 1e-3), 1 - 1e-3)
        self.bias = math.log(rate / (1 - rate))
        scores = [self.bias] * n

        for _ in range(self.n_rounds):
            probs = [sigmoid(s) for s in scores]
            grads = [labels[i] - probs[i] for i in range(n)]
            hess = [max(probs[i] * (1.0 - probs[i]), 1e-3) for i in range(n)]
            stump = _best_stump(rows, grads, hess, width, n, self.min_leaf, self.l2)
            if stump is None:
                break
            feature, threshold, left, right = stump
            self.stumps.append(stump)
            step = self.learning_rate
            for i in range(n):
                scores[i] += step * (left if rows[i][feature] <= threshold else right)
        return self

    def predict_log_odds(self, row: list[float]) -> float:
        score = self.bias
        step = self.learning_rate
        for feature, threshold, left, right in self.stumps:
            score += step * (left if row[feature] <= threshold else right)
        return score

    def predict_proba(self, row: list[float]) -> float:
        return sigmoid(self.predict_log_odds(row))


def _best_stump(rows, grads, hess, width, n, min_leaf, l2):
    total_g = sum(grads)
    total_h = sum(hess)
    best_gain = 1e-6
    best = None
    for feature in range(width):
        order = sorted(range(n), key=lambda i: rows[i][feature])
        groups: list[tuple[float, list[int]]] = []
        for i in order:
            value = rows[i][feature]
            if not groups or value != groups[-1][0]:
                groups.append((value, []))
            groups[-1][1].append(i)
        g_left = 0.0
        h_left = 0.0
        count_left = 0
        for group_index in range(len(groups) - 1):
            for i in groups[group_index][1]:
                g_left += grads[i]
                h_left += hess[i]
                count_left += 1
            count_right = n - count_left
            if count_left < min_leaf or count_right < min_leaf:
                continue
            g_right = total_g - g_left
            h_right = total_h - h_left
            gain = 0.5 * (
                (g_left * g_left) / (h_left + l2)
                + (g_right * g_right) / (h_right + l2)
                - (total_g * total_g) / (total_h + l2)
            )
            if gain > best_gain:
                threshold = 0.5 * (groups[group_index][0] + groups[group_index + 1][0])
                left = g_left / (h_left + l2)
                right = g_right / (h_right + l2)
                best_gain = gain
                best = (feature, threshold, left, right)
    return best
