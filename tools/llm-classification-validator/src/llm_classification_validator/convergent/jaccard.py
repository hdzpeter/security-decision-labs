"""Jaccard similarity for set comparison -- standard library only."""

from __future__ import annotations

from typing import Iterable


def jaccard_similarity(set_a: Iterable[str], set_b: Iterable[str]) -> float:
    """Compute the Jaccard similarity coefficient between two sets.

    Jaccard(A, B) = |A intersection B| / |A union B|

    Returns 1.0 when both sets are empty (trivial agreement), and 0.0
    when the intersection is empty but at least one set is non-empty.

    Parameters
    ----------
    set_a, set_b:
        Iterables of string elements to compare.

    Returns
    -------
    float
        Jaccard similarity in [0, 1].
    """
    a = set(set_a)
    b = set(set_b)

    if not a and not b:
        return 1.0

    intersection = a & b
    union = a | b

    return len(intersection) / len(union)


def jaccard_distance(set_a: Iterable[str], set_b: Iterable[str]) -> float:
    """Compute the Jaccard distance (1 - Jaccard similarity).

    Parameters
    ----------
    set_a, set_b:
        Iterables of string elements to compare.

    Returns
    -------
    float
        Jaccard distance in [0, 1].
    """
    return 1.0 - jaccard_similarity(set_a, set_b)


def mean_jaccard(pairs: list[tuple[set[str], set[str]]]) -> float:
    """Compute the mean Jaccard similarity over a list of set pairs.

    Parameters
    ----------
    pairs:
        List of (set_a, set_b) tuples.

    Returns
    -------
    float
        Mean Jaccard similarity. Returns 0.0 for an empty list.
    """
    if not pairs:
        return 0.0

    total = sum(jaccard_similarity(a, b) for a, b in pairs)
    return total / len(pairs)
