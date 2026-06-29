"""Cohen's kappa and Fleiss' kappa -- implemented from scratch (no scipy)."""

from __future__ import annotations

from collections import Counter
from typing import Sequence


def cohens_kappa(
    rater_a: Sequence[str],
    rater_b: Sequence[str],
) -> float:
    """Compute Cohen's kappa for two raters.

    Parameters
    ----------
    rater_a, rater_b:
        Sequences of categorical labels of equal length. Each element
        at the same index represents the classification of the same item.

    Returns
    -------
    float
        Cohen's kappa coefficient in [-1, 1]. Returns 0.0 when both
        raters agree perfectly on a single category (Pe == 1).
    """
    n = len(rater_a)
    if n != len(rater_b):
        raise ValueError(
            f"Length mismatch: rater_a has {n} items, rater_b has {len(rater_b)}"
        )
    if n == 0:
        return 0.0

    # Observed agreement (Po)
    agreements = sum(1 for a, b in zip(rater_a, rater_b) if a == b)
    po = agreements / n

    # Marginal distributions
    all_labels = sorted(set(rater_a) | set(rater_b))
    counts_a = Counter(rater_a)
    counts_b = Counter(rater_b)

    # Expected agreement (Pe) under independence
    pe = sum((counts_a[label] / n) * (counts_b[label] / n) for label in all_labels)

    if pe >= 1.0:
        # Both raters assigned the same single category to every item
        return 1.0 if po >= 1.0 else 0.0

    kappa = (po - pe) / (1.0 - pe)
    return kappa


def fleiss_kappa(
    ratings_matrix: list[list[int]],
) -> float:
    """Compute Fleiss' kappa for multiple raters.

    Parameters
    ----------
    ratings_matrix:
        A matrix of shape (N, k) where N is the number of items
        and k is the number of categories. Each cell [i][j] contains
        the number of raters who assigned category j to item i.

    Returns
    -------
    float
        Fleiss' kappa coefficient. Returns 0.0 when all items have the
        same distribution across categories.
    """
    if not ratings_matrix:
        return 0.0

    n_items = len(ratings_matrix)
    n_categories = len(ratings_matrix[0])

    if n_categories == 0:
        return 0.0

    # Total number of raters per item (should be constant)
    n_raters = sum(ratings_matrix[0])
    if n_raters <= 1:
        return 0.0

    # Proportion of all assignments to each category
    p_j: list[float] = []
    for j in range(n_categories):
        col_sum = sum(ratings_matrix[i][j] for i in range(n_items))
        p_j.append(col_sum / (n_items * n_raters))

    # P_e_bar: expected agreement by chance
    p_e_bar = sum(pj * pj for pj in p_j)

    if p_e_bar >= 1.0:
        return 1.0

    # P_i: extent of agreement for item i
    p_i_values: list[float] = []
    for i in range(n_items):
        row = ratings_matrix[i]
        sum_sq = sum(nij * nij for nij in row)
        p_i = (sum_sq - n_raters) / (n_raters * (n_raters - 1))
        p_i_values.append(p_i)

    # P_bar: mean of P_i
    p_bar = sum(p_i_values) / n_items

    kappa = (p_bar - p_e_bar) / (1.0 - p_e_bar)
    return kappa


def build_ratings_matrix(
    all_raters_labels: list[list[str]],
) -> tuple[list[list[int]], list[str]]:
    """Build a Fleiss-compatible ratings matrix from per-rater label lists.

    Parameters
    ----------
    all_raters_labels:
        A list of label sequences, one per rater. All sequences must
        be the same length (one label per item).

    Returns
    -------
    (matrix, categories):
        The ratings matrix and the ordered list of category names.
    """
    if not all_raters_labels:
        return [], []

    n_items = len(all_raters_labels[0])
    for rater_labels in all_raters_labels:
        if len(rater_labels) != n_items:
            raise ValueError(
                f"Rater has {len(rater_labels)} labels but {n_items} items expected"
            )

    # Collect all unique categories
    categories = sorted(
        {label for rater_labels in all_raters_labels for label in rater_labels}
    )
    cat_index = {cat: idx for idx, cat in enumerate(categories)}

    n_categories = len(categories)
    matrix: list[list[int]] = []

    for i in range(n_items):
        row = [0] * n_categories
        for rater_labels in all_raters_labels:
            label = rater_labels[i]
            row[cat_index[label]] += 1
        matrix.append(row)

    return matrix, categories
