"""
Three-anchor base rate triangulation.

Formalizes the combination rule that produces a consensus PERT from
independent estimation anchors. Each scenario defines three anchors
(operational tempo, back-calculation, insurer-adjusted); this module
computes a suggested consensus PERT and validates the analyst's
chosen consensus against it.

Combination rule:
    consensus.low  = min(all anchor lows)
    consensus.mode = arithmetic mean of anchor modes
    consensus.high = min(2.5 × consensus.mode, max(all anchor highs))

Convergence check: all anchor modes within 10× of each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tef_estimator.data.common import PERTRange


@dataclass
class TriangulationResult:
    """Output of the three-anchor triangulation."""
    suggested: PERTRange
    convergence_ratio: float
    is_convergent: bool
    validation: list[str] = field(default_factory=list)


def triangulate(
    anchors: dict[str, PERTRange],
    actual_consensus: PERTRange | None = None,
) -> TriangulationResult:
    """Compute consensus PERT from independent anchors.

    Parameters
    ----------
    anchors
        Named PERT ranges from independent estimation methods.
        Excludes the 'consensus' key itself.
    actual_consensus
        The analyst-set consensus (from scenario JSON). If provided,
        the result includes a deviation check.

    Returns
    -------
    TriangulationResult with suggested consensus, convergence check,
    and validation messages for the audit trail.
    """
    anchor_perts = list(anchors.values())
    if not anchor_perts:
        validation = ["No independent anchors provided — using analyst consensus only"]
        if actual_consensus is not None:
            validation.append(
                f"Analyst consensus: PERT({actual_consensus.low:.4f}, "
                f"{actual_consensus.mode:.4f}, {actual_consensus.high:.4f})"
            )
            return TriangulationResult(
                suggested=actual_consensus,
                convergence_ratio=1.0,
                is_convergent=True,
                validation=validation,
            )
        return TriangulationResult(
            suggested=PERTRange(0.0, 0.0, 0.0),
            convergence_ratio=1.0,
            is_convergent=True,
            validation=validation,
        )

    modes = [a.mode for a in anchor_perts]
    lows = [a.low for a in anchor_perts]
    highs = [a.high for a in anchor_perts]

    min_mode = min(modes)
    max_mode = max(modes)
    convergence_ratio = max_mode / min_mode if min_mode > 0 else float("inf")
    is_convergent = convergence_ratio <= 10.0

    suggested_low = min(lows)
    suggested_mode = sum(modes) / len(modes)
    suggested_high = min(suggested_mode * 2.5, max(highs))

    suggested_low = min(suggested_low, suggested_mode * 0.5)
    suggested_high = max(suggested_high, suggested_mode * 1.5)

    suggested = PERTRange(
        round(suggested_low, 4),
        round(suggested_mode, 4),
        round(suggested_high, 4),
    )

    validation: list[str] = []
    convergence_label = "convergent" if is_convergent else "DIVERGENT — review anchors"
    validation.append(
        f"Anchor mode convergence: {convergence_ratio:.1f}x ({convergence_label})"
    )

    for name, anchor in anchors.items():
        validation.append(
            f"  {name}: PERT({anchor.low:.4f}, {anchor.mode:.4f}, {anchor.high:.4f})"
        )

    validation.append(
        f"Suggested consensus: PERT({suggested.low:.4f}, "
        f"{suggested.mode:.4f}, {suggested.high:.4f})"
    )

    if actual_consensus is not None:
        mode_delta_pct = (
            abs(actual_consensus.mode - suggested.mode) / suggested.mode * 100
            if suggested.mode > 0
            else float("inf")
        )
        validation.append(
            f"Analyst consensus:   PERT({actual_consensus.low:.4f}, "
            f"{actual_consensus.mode:.4f}, {actual_consensus.high:.4f})"
        )
        if mode_delta_pct > 50:
            validation.append(
                f"WARNING: Analyst consensus mode deviates "
                f"{mode_delta_pct:.0f}% from suggested — verify override"
            )
        else:
            validation.append(
                f"Consensus within {mode_delta_pct:.0f}% of suggestion"
            )

    return TriangulationResult(
        suggested=suggested,
        convergence_ratio=round(convergence_ratio, 2),
        is_convergent=is_convergent,
        validation=validation,
    )


_NON_ANCHOR_KEYS = {"consensus", "susceptibility_prior"}


def extract_anchors(
    triangulation: dict[str, PERTRange],
) -> tuple[dict[str, PERTRange], PERTRange | None]:
    """Split a scenario's base_rate_triangulation into anchors + consensus.

    Returns (anchors_dict, consensus_pert_or_none).
    """
    anchors = {}
    consensus = None
    for name, pert in triangulation.items():
        if name == "consensus":
            consensus = pert
        elif name not in _NON_ANCHOR_KEYS:
            anchors[name] = pert
    return anchors, consensus
