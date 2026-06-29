"""Paraphrase generation strategies and data model.

Paraphrasing rewrites an input while preserving its meaning. If an LLM
is understanding the input, paraphrased versions should produce
the same classification output.

The generator strategies defined here are templates that can be used
with any LLM API. The framework does not call LLM APIs directly;
instead, users generate paraphrases externally and pass them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FORMAL_TEMPLATE = (
    "Rewrite the following text using formal, technical language. "
    "Use passive voice and domain-standard terminology. "
    "Preserve ALL factual content. Do NOT add or remove capabilities.\n\n"
    "Original: {text}\n\n"
    "Rewritten:"
)

INFORMAL_TEMPLATE = (
    "Rewrite the following text in a more conversational, informal tone. "
    "Use active voice and plain language. "
    "Preserve ALL factual content. Do NOT add or remove capabilities.\n\n"
    "Original: {text}\n\n"
    "Rewritten:"
)

STRUCTURAL_TEMPLATE = (
    "Restructure the following text by reordering clauses and changing "
    "sentence structure. You may split or combine sentences. "
    "Preserve ALL factual content. Do NOT add or remove capabilities.\n\n"
    "Original: {text}\n\n"
    "Rewritten:"
)

PARAPHRASE_STRATEGIES: list[dict[str, str]] = [
    {
        "name": "formal",
        "description": "Formal, technical language with passive voice",
        "template": FORMAL_TEMPLATE,
    },
    {
        "name": "informal",
        "description": "Conversational tone with active voice and plain language",
        "template": INFORMAL_TEMPLATE,
    },
    {
        "name": "structural",
        "description": "Clause reordering and sentence restructuring",
        "template": STRUCTURAL_TEMPLATE,
    },
]


@dataclass
class ParaphraseVariant:
    """A semantically equivalent rewrite of an input text."""

    item_id: str
    variant_id: str
    strategy: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
