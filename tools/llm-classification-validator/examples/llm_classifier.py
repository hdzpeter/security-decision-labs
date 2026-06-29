"""Claude-based FAIR-CAM classifier for use with classification validation.

Replaces the keyword classifier with actual LLM calls. Requires
ANTHROPIC_API_KEY in the environment.

Usage:
    from examples.llm_classifier import make_classifier

    classify_domain, classify_full, classify_functions = make_classifier(taxonomy)
    # classify_domain("control description") -> "LEC"
    # classify_full("control description") -> {"domain": "LEC", "subdomain": "Prevention", "function": "Resistance"}
    # classify_functions("control description") -> {"Resistance", "Avoidance"}
"""

from __future__ import annotations

import json
import os
from typing import Callable

import anthropic


SYSTEM_PROMPT = """\
You are a cybersecurity risk analyst classifying controls into the FAIR-CAM taxonomy.

FAIR-CAM has three domains, each with subdomains and functions:

{taxonomy_text}

Classification rules:
- Classify by the ROLE the control plays in risk management, not by its subject matter.
- "Define policies and procedures for X" is DSC (governance), even if X is a technical topic.
- A control that directly prevents, detects, or responds to loss events is LEC.
- A control that manages vulnerability/variance lifecycle (scanning, patching, change control) is VMC.
- A control that sets direction, communicates expectations, or provides oversight is DSC.
- Choose the PRIMARY domain — the one that best describes the control's function, not all domains it touches.
- Choose the single most specific function within that domain.

Respond with valid JSON only. No explanation."""


DOMAIN_PROMPT = """\
Classify this control into a FAIR-CAM domain (LEC, VMC, or DSC).

Control: {description}

Respond with exactly one JSON object: {{"domain": "<LEC|VMC|DSC>"}}"""


FULL_PROMPT = """\
Classify this control into FAIR-CAM domain, subdomain, and function.

Control: {description}

Respond with exactly one JSON object:
{{"domain": "<LEC|VMC|DSC>", "subdomain": "<subdomain>", "function": "<function>"}}"""


FUNCTIONS_PROMPT = """\
Identify ALL FAIR-CAM functions this control serves (can be multiple).

Control: {description}

Respond with exactly one JSON object: {{"functions": ["<function1>", "<function2>", ...]}}"""


def _format_taxonomy(taxonomy: dict) -> str:
    lines = []
    for domain, info in taxonomy.items():
        lines.append(f"{domain} — {info['name']}")
        for sub, sinfo in info["subdomains"].items():
            funcs = ", ".join(sinfo["functions"])
            lines.append(f"  {sub}: {funcs}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def make_classifier(
    taxonomy: dict,
    model: str = "claude-sonnet-4-6",
    cache_responses: bool = True,
) -> tuple[Callable[[str], str], Callable[[str], dict[str, str]], Callable[[str], set[str]]]:
    """Create Claude-backed classifier functions.

    Returns (classify_domain, classify_full, classify_functions).
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system = SYSTEM_PROMPT.format(taxonomy_text=_format_taxonomy(taxonomy))
    cache: dict[str, dict] = {}

    def _call(prompt: str, cache_key: str | None = None) -> dict:
        if cache_responses and cache_key and cache_key in cache:
            return cache[cache_key]

        response = client.messages.create(
            model=model,
            max_tokens=256,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        result = _parse_json(text)

        if cache_responses and cache_key:
            cache[cache_key] = result
        return result

    def classify_domain(description: str) -> str:
        prompt = DOMAIN_PROMPT.format(description=description)
        result = _call(prompt, f"domain:{description}")
        return result["domain"]

    def classify_full(description: str) -> dict[str, str]:
        prompt = FULL_PROMPT.format(description=description)
        result = _call(prompt, f"full:{description}")
        return {
            "domain": result["domain"],
            "subdomain": result["subdomain"],
            "function": result["function"],
        }

    def classify_functions(description: str) -> set[str]:
        prompt = FUNCTIONS_PROMPT.format(description=description)
        result = _call(prompt, f"functions:{description}")
        return set(result["functions"])

    return classify_domain, classify_full, classify_functions
