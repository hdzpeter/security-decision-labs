"""Cross-taxonomy mapping example: CSA AICM controls → FAIR-CAM classification.

THIS IS A DEMONSTRATION EXAMPLE, NOT A REFERENCE MAPPING. The AICM-to-FAIR-CAM
mappings here are illustrative — they show how to wire the five-dimension
framework, not how AICM controls should be mapped to FAIR-CAM. Your own
taxonomy pair, expert mappings, and transitive crosswalks will differ.

Demonstrates the 5-dimension evaluation framework on the real-world task
of mapping Cloud Security Alliance AI Controls Matrix (AICM v1.0.2)
controls to FAIR-CAM risk management categories.

Dimension wiring:
  1. Coherence    — LLM runs + human expert mappings as raters → kappa
  2. Consistency  — structural validity against FAIR-CAM taxonomy rules
  3. Convergent   — LLM direct mapping vs transitive crosswalk (AICM→CIS→FAIR-CAM)
  4. Adversarial  — minimal pairs calling the classifier live
  5. Stability    — paraphrase/perturbation calling the classifier live

Uses 20 real AICM control specifications (verbatim from AICM v1.0.2).
"""

import json
import os
from pathlib import Path

from llm_classification_validator.coherence import run_coherence_analysis
from llm_classification_validator.consistency import RuleRegistry, run_consistency_check
from llm_classification_validator.convergent import run_convergent_analysis
from llm_classification_validator.adversarial import (
    AmbiguityCase,
    MinimalPair,
    run_adversarial_analysis,
)
from llm_classification_validator.stability import (
    ExpectedDirection,
    ParaphraseVariant,
    PerturbationVariant,
    run_stability_analysis,
)
from llm_classification_validator.runner import run_evaluation
from llm_classification_validator.models import RuleResult


# ─── FAIR-CAM taxonomy (target) ────────────────────────────────────────

_TAXONOMY_PATH = Path(__file__).parent / "faircam_taxonomy.json"
if not _TAXONOMY_PATH.exists():
    raise FileNotFoundError(
        f"FAIR-CAM taxonomy not found at {_TAXONOMY_PATH}. "
        "This file is not distributed with the repository. "
        "See examples/README.md for the expected schema."
    )

with open(_TAXONOMY_PATH) as f:
    FAIRCAM_TAXONOMY = json.load(f)

VALID_DOMAINS = set(FAIRCAM_TAXONOMY.keys())
VALID_SUBDOMAINS = {
    (domain, sub)
    for domain, dinfo in FAIRCAM_TAXONOMY.items()
    for sub in dinfo["subdomains"]
}
VALID_PATHS = {
    (domain, sub, func)
    for domain, dinfo in FAIRCAM_TAXONOMY.items()
    for sub, sinfo in dinfo["subdomains"].items()
    for func in sinfo["functions"]
}


# ─── 20 AICM controls (verbatim from AICM v1.0.2) ─────────────────────

CONTROLS = [
    {"id": "MDS-01", "description": "Define, implement, and evaluate policies, procedures, and technical measures that ensure the security of the Training Pipeline. Regularly review and update policies, procedures and technical measures to address new security threats and best practices."},
    {"id": "MDS-02", "description": "Define, implement, and evaluate policies, procedures, and technical measures for the scanning of model artifacts for vulnerabilities and attacks, at each step of the service lifecycle and at each hand over point."},
    {"id": "MDS-06", "description": "Define, implement, and evaluate processes and technical measures to assess adversarial threats specific to each AI model."},
    {"id": "MDS-07", "description": "Define, implement, and evaluate processes, procedures, and technical measures for Model Hardening to mitigate relevant adversarial attacks as identified in the Threat Analysis and Adversarial Threat Analysis."},
    {"id": "MDS-08", "description": "Regularly calculate and compare checksums using cryptographic hashes of model checkpoints to detect unauthorized modifications. Apply at least annually based on the level of risk, or after any change of hands."},
    {"id": "AIS-08", "description": "Validate, filter, modify or block, as necessary, input against adversarial patterns, failure patterns and unwanted behaviour according to organisational policies and applicable laws and regulations."},
    {"id": "AIS-09", "description": "Validate, filter, modify or block, as necessary, output against adversarial patterns, failure patterns and unwanted behaviour according to organisational policies and applicable laws and regulations."},
    {"id": "AIS-05", "description": "Implement a testing strategy, including criteria for acceptance of new information systems, upgrades and new versions, which provides application security assurance and maintains compliance while meeting organizational delivery goals. Automate when applicable and possible."},
    {"id": "AIS-07", "description": "Define and implement a process to remediate application security vulnerabilities, automating remediation when possible."},
    {"id": "CEK-03", "description": "Provide data protection at-rest, in-transit and, where applicable, in-use by using cryptographic libraries certified to approved standards."},
    {"id": "LOG-05", "description": "Monitor security audit logs to detect activity outside of typical or expected patterns. Establish and follow a defined process to review and take appropriate and timely actions on detected anomalies."},
    {"id": "LOG-08", "description": "Generate audit records containing relevant security information."},
    {"id": "BCR-03", "description": "Establish strategies to reduce the impact of business disruptions, and improve resiliency and recovery from business disruptions."},
    {"id": "SEF-03", "description": "Establish, document, approve, communicate, apply, evaluate and maintain a security incident response plan."},
    {"id": "CCC-01", "description": "Establish, document, approve, communicate, apply, evaluate and maintain policies and procedures for managing the risks associated with applying changes to assets owned, controlled or used by the organization."},
    {"id": "TVM-06", "description": "Define, implement and evaluate processes, procedures and technical measures for the periodic performance of penetration testing by independent third parties."},
    {"id": "STA-09", "description": "Periodically review risk factors associated with supply chain relationships."},
    {"id": "GRC-01", "description": "Establish, document, approve, communicate, apply, evaluate and maintain policies and procedures for an information governance program, which is sponsored by the leadership of the organization and related to AI systems as well."},
    {"id": "HRS-09", "description": "Document and communicate roles and responsibilities of employees, as they relate to information assets and security."},
    {"id": "A&A-02", "description": "Conduct independent audit and assurance assessments according to relevant standards at least annually."},
]


# ─── Human expert mappings (Dimension 1: Coherence) ────────────────────
# Domain-level classifications by a human expert. Used as a rater in
# coherence analysis alongside LLM runs. Replace with your own.

EXPERT_DOMAIN_MAPPINGS = [
    "DSC",  # MDS-01: policies/procedures for training pipeline = governance
    "VMC",  # MDS-02: scanning model artifacts for vulnerabilities = vulnerability identification
    "VMC",  # MDS-06: assess adversarial threats = threat capability monitoring
    "LEC",  # MDS-07: model hardening to resist attacks = prevention/resistance
    "LEC",  # MDS-08: integrity checksums to detect unauthorized mods = detection/visibility
    "LEC",  # AIS-08: filter/block adversarial input = prevention/resistance
    "LEC",  # AIS-09: filter/block adversarial output = prevention/resistance
    "VMC",  # AIS-05: testing strategy for security assurance = controls monitoring
    "VMC",  # AIS-07: remediate vulnerabilities = correction/implementation
    "LEC",  # CEK-03: cryptographic data protection = prevention/resistance
    "LEC",  # LOG-05: monitor logs, detect anomalies = detection/monitoring+recognition
    "LEC",  # LOG-08: generate audit records = detection/visibility
    "LEC",  # BCR-03: resiliency and recovery = response/resilience
    "LEC",  # SEF-03: incident response plan = response/containment
    "VMC",  # CCC-01: change management policies = prevention/reduce change frequency
    "VMC",  # TVM-06: penetration testing = identification/controls monitoring
    "VMC",  # STA-09: supply chain risk review = identification/threat capability monitoring
    "DSC",  # GRC-01: governance program sponsored by leadership = define expectations
    "DSC",  # HRS-09: document/communicate roles and responsibilities = communicate expectations
    "DSC",  # A&A-02: independent audits annually = identification/audits
]


# ─── Transitive crosswalk (Dimension 3: Convergent validity) ───────────
# EXAMPLE ONLY — illustrates how to structure a transitive reference.
# Derived from published crosswalks:
#   Leg 1: AICM v0.0.1 (CCM v4.0.5) → CIS Controls v8.0
#   Leg 2: CIS Controls v8.0 → FAIR-CAM 1.0 (FAIR Institute, CC BY-NC-ND 4.0)
# MDS and AIS-08/09 are AICM-specific (no CCM equivalent), so no CIS mapping.
# BCR-03 and A&A-02 have no CIS mapping in the AICM v0.0.1 crosswalk.
# Replace with your own transitive crosswalk for your taxonomy pair.

TRANSITIVE_CROSSWALK_DOMAINS = [
    None,   # MDS-01: AICM-specific, no CIS mapping
    None,   # MDS-02: AICM-specific, no CIS mapping
    None,   # MDS-06: AICM-specific, no CIS mapping
    None,   # MDS-07: AICM-specific, no CIS mapping
    None,   # MDS-08: AICM-specific, no CIS mapping
    None,   # AIS-08: AICM-specific, no CIS mapping
    None,   # AIS-09: AICM-specific, no CIS mapping
    "VMC",  # AIS-05: CIS 16.12,16.13 → VMC (Controls Monitoring)
    "VMC",  # AIS-07: CIS 16.2,16.6 → VMC+DSC (majority VMC)
    "LEC",  # CEK-03: CIS 3.6,3.1,3.11,11.3,16.11 → LEC (Resistance, Loss Reduction)
    "LEC",  # LOG-05: CIS 8.8,8.11 → LEC (Monitoring, Visibility)
    "LEC",  # LOG-08: CIS 8.2 → LEC (Visibility)
    None,   # BCR-03: no CIS mapping in AICM v0.0.1
    "VMC",  # SEF-03: CIS 17.2,17.4 → VMC+DSC (disagreement with expert=LEC)
    "LEC",  # CCC-01: CIS 4.1 → LEC (Resistance) (disagreement with expert=VMC)
    "DSC",  # TVM-06: CIS 18.1,18.2 → DSC+VMC (disagreement with expert=VMC)
    "VMC",  # STA-09: CIS 15.4 → VMC (Controls Monitoring)
    "LEC",  # GRC-01: CIS 3.1 → LEC (disagreement with expert=DSC; poor CIS match)
    "DSC",  # HRS-09: CIS 14.1-14.9 → DSC (Communicate Expectations)
    None,   # A&A-02: no CIS mapping in AICM v0.0.1
]

TRANSITIVE_CROSSWALK_FUNCTIONS: list[set[str] | None] = [
    None,                                                          # MDS-01
    None,                                                          # MDS-02
    None,                                                          # MDS-06
    None,                                                          # MDS-07
    None,                                                          # MDS-08
    None,                                                          # AIS-08
    None,                                                          # AIS-09
    {"Controls Monitoring"},                                       # AIS-05
    {"Controls Monitoring", "Define Expectations", "Implementation"},  # AIS-07
    {"Resistance", "Loss Reduction", "Reduce Var Prob"},           # CEK-03
    {"Monitoring", "Visibility", "Ensure Motivation"},             # LOG-05
    {"Visibility", "Ensure Motivation"},                           # LOG-08
    None,                                                          # BCR-03
    {"Controls Monitoring", "Define Expectations", "Ensure Capability", "Implementation"},  # SEF-03
    {"Resistance"},                                                # CCC-01
    {"Controls Monitoring", "Define Expectations"},                # TVM-06
    {"Controls Monitoring", "Implementation"},                     # STA-09
    {"Resistance", "Loss Reduction"},                              # GRC-01
    {"Communicate Expectations", "Controls Monitoring", "Implementation", "Provide Data (Controls)"},  # HRS-09
    None,                                                          # A&A-02
]


# ─── Classifier selection ──────────────────────────────────────────────
# Use Claude if ANTHROPIC_API_KEY is set, otherwise fall back to keywords.

_USE_LLM = bool(os.environ.get("ANTHROPIC_API_KEY"))

if _USE_LLM:
    from examples.llm_classifier import make_classifier
    classify_domain, classify_full, classify_functions = make_classifier(FAIRCAM_TAXONOMY)

    def map_control(description: str) -> dict[str, str]:
        return classify_full(description)

    def map_control_domain(description: str) -> str:
        return classify_domain(description)

    def map_control_functions(description: str) -> set[str]:
        return classify_functions(description)
else:
    # ── Keyword fallback (deterministic, for offline testing) ──────
    _DOMAIN_SIGNALS = {
        "LEC": {
            "encrypt", "cryptograph", "block", "filter", "validate", "harden",
            "resist", "protect", "monitor", "detect", "anomal", "alert",
            "log", "audit record", "incident response", "containment",
            "resilience", "recovery", "continuity", "disrupt", "checkpoint",
            "checksum", "integrity", "unauthorized modification", "pipeline security",
            "input validation", "output validation", "adversarial attack",
        },
        "VMC": {
            "vulnerabilit", "scan", "remediat", "patch", "change management",
            "change control", "penetration test", "pen test", "threat assess",
            "adversarial threat", "threat analysis", "artifact scanning",
            "quality", "testing strategy", "acceptance", "baseline",
            "supply chain", "risk factor", "risk management",
        },
        "DSC": {
            "governance", "policy", "procedure", "document", "communicate",
            "roles and responsibilities", "training", "awareness", "leadership",
            "sponsored", "audit and assurance", "independent audit",
            "independent assess", "assurance assessment",
        },
    }

    _FUNCTION_SIGNALS = {
        "Avoidance": {"eliminat", "remov", "isolat", "pipeline security", "segregat"},
        "Deterrence": {"warn", "banner", "prohibit", "deter", "prosecut"},
        "Resistance": {
            "encrypt", "cryptograph", "block", "filter", "validate", "harden",
            "mitigat", "protect", "resist", "input validation", "output validation",
            "adversarial attack", "model hardening",
        },
        "Visibility": {"audit record", "log", "checkpoint", "checksum", "integrity", "generat"},
        "Monitoring": {"monitor", "review", "anomal", "pattern", "typical", "expected"},
        "Recognition": {"detect", "alert", "recogni", "unauthorized modification", "anomal"},
        "Containment": {"incident response", "containment", "response plan"},
        "Resilience": {"resilience", "recovery", "continuity", "disrupt", "impact", "resiliency"},
        "Loss Minimisation": {"insurance", "notification", "breach cost"},
        "Reduce Change Frequency": {"change management", "change control", "approval", "managing the risks associated with applying changes"},
        "Reduce Variance Probability": {"baseline", "quality", "configuration", "standard"},
        "Threat Capability Monitoring": {"threat assess", "adversarial threat", "threat analysis", "supply chain", "risk factor"},
        "Controls Monitoring": {"vulnerabilit", "scan", "penetration test", "pen test", "testing strategy", "acceptance", "artifact scanning"},
        "Treatment Selection & Prioritisation": {"prioriti", "risk-based", "criticality"},
        "Implementation": {"remediat", "patch", "fix", "automat", "correct"},
        "Define Expectations & Objectives": {"governance", "policy", "procedure", "establish", "document", "maintain", "leadership", "sponsored"},
        "Communicate Expectations": {"communicate", "roles and responsibilities", "training", "awareness"},
        "Provide Situational Awareness": {"briefing", "landscape", "risk posture"},
        "Ensure Capability": {"staffing", "skills", "resource", "budget"},
        "Proper Incentives": {"incentive", "bonus", "accountab"},
        "Root Cause Analyses": {"root cause"},
        "Audits": {"audit", "independent assess", "assurance assessment", "annual"},
        "Post-mortems": {"post-mortem", "lessons learned"},
    }

    _SUBDOMAIN_SIGNALS = {
        ("LEC", "Prevention"): {
            "encrypt", "cryptograph", "block", "filter", "validate", "harden",
            "resist", "protect", "pipeline security", "input validation",
            "output validation", "adversarial attack", "mitigat",
        },
        ("LEC", "Detection"): {
            "monitor", "detect", "anomal", "alert", "log", "audit record",
            "checkpoint", "checksum", "integrity", "unauthorized modification",
            "pattern", "review",
        },
        ("LEC", "Response"): {
            "incident response", "containment", "resilience", "recovery",
            "continuity", "disrupt", "impact", "business disruption",
        },
        ("VMC", "Prevention"): {
            "change management", "change control", "configuration", "quality",
            "approval", "baseline",
        },
        ("VMC", "Identification"): {
            "vulnerabilit", "scan", "penetration test", "pen test",
            "threat assess", "adversarial threat", "threat analysis",
            "artifact scanning", "testing strategy", "acceptance",
            "supply chain", "risk factor",
        },
        ("VMC", "Correction"): {
            "remediat", "patch", "fix", "automat", "correct",
        },
        ("DSC", "Prevention"): {
            "governance", "policy", "procedure", "document", "communicate",
            "roles and responsibilities", "training", "awareness", "leadership",
            "sponsored",
        },
        ("DSC", "Identification"): {
            "audit and assurance", "independent audit", "independent assess",
            "assurance assessment", "root cause", "post-mortem",
        },
    }

    def _score_signals(text: str, signals: set[str]) -> int:
        t = text.lower()
        return sum(1 for s in signals if s in t)

    def map_control_domain(description: str) -> str:
        scores = {d: _score_signals(description, sigs) for d, sigs in _DOMAIN_SIGNALS.items()}
        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "LEC"
        return best

    def map_control_functions(description: str) -> set[str]:
        scored = {
            func: _score_signals(description, sigs)
            for func, sigs in _FUNCTION_SIGNALS.items()
        }
        max_score = max(scored.values()) if scored else 0
        if max_score == 0:
            return {"Resistance"}
        threshold = max(1, max_score - 1)
        return {f for f, s in scored.items() if s >= threshold}

    def map_control(description: str) -> dict[str, str]:
        domain = map_control_domain(description)

        best_sub = list(FAIRCAM_TAXONOMY[domain]["subdomains"].keys())[0]
        best_score = 0
        for (d, sub), sigs in _SUBDOMAIN_SIGNALS.items():
            if d != domain:
                continue
            score = _score_signals(description, sigs)
            if score > best_score:
                best_score = score
                best_sub = sub

        functions = FAIRCAM_TAXONOMY[domain]["subdomains"][best_sub]["functions"]
        best_func = functions[0]
        best_fscore = 0
        for func in functions:
            if func in _FUNCTION_SIGNALS:
                fscore = _score_signals(description, _FUNCTION_SIGNALS[func])
                if fscore > best_fscore:
                    best_fscore = fscore
                    best_func = func

        return {"domain": domain, "subdomain": best_sub, "function": best_func}


# ─── Dimension 1: Coherence ─────────────────────────────────────────────
# LLM (or keyword classifier) runs + human expert as raters.

def run_coherence():
    descriptions = [c["description"] for c in CONTROLS]
    item_ids = [c["id"] for c in CONTROLS]
    n = len(CONTROLS)
    raters = {}
    for run_num in range(1, 4):
        results = []
        for i, d in enumerate(descriptions):
            print(f"         coherence run {run_num}/3: {CONTROLS[i]['id']} ({i+1}/{n})", flush=True)
            results.append(map_control_domain(d))
        raters[f"classifier_run_{run_num}"] = results
    raters["human_expert"] = EXPERT_DOMAIN_MAPPINGS
    return run_coherence_analysis(raters, item_ids=item_ids)


# ─── Dimension 2: Consistency ────────────────────────────────────────────

def run_consistency():
    print("         checking structural rules...", flush=True)
    registry = RuleRegistry()

    @registry.rule("S-001", "Domain is valid FAIR-CAM domain", severity="error")
    def valid_domain(item: dict) -> list[RuleResult]:
        valid = item["domain"] in VALID_DOMAINS
        return [RuleResult(
            rule_id="S-001", rule_name="Domain is valid FAIR-CAM domain",
            category="structural", severity="error",
            passed=valid, item_id=item["id"],
            message="OK" if valid else f"Unknown domain: {item['domain']}",
        )]

    @registry.rule("S-002", "Subdomain exists in assigned domain", severity="error")
    def valid_subdomain(item: dict) -> list[RuleResult]:
        valid = (item["domain"], item["subdomain"]) in VALID_SUBDOMAINS
        return [RuleResult(
            rule_id="S-002", rule_name="Subdomain exists in assigned domain",
            category="structural", severity="error",
            passed=valid, item_id=item["id"],
            message="OK" if valid else f"{item['subdomain']} not in {item['domain']}",
        )]

    @registry.rule("S-003", "Function exists under assigned subdomain", severity="error")
    def valid_function(item: dict) -> list[RuleResult]:
        valid = (item["domain"], item["subdomain"], item["function"]) in VALID_PATHS
        return [RuleResult(
            rule_id="S-003", rule_name="Function exists under assigned subdomain",
            category="structural", severity="error",
            passed=valid, item_id=item["id"],
            message="OK" if valid else f"{item['function']} not under {item['domain']}/{item['subdomain']}",
        )]

    @registry.rule("SEM-001", "AICM control spec substantive enough to map", severity="warning")
    def description_length(item: dict) -> list[RuleResult]:
        passed = len(item["description"]) >= 30
        return [RuleResult(
            rule_id="SEM-001", rule_name="AICM control spec substantive enough to map",
            category="semantic", severity="warning",
            passed=passed, item_id=item["id"],
            message="OK" if passed else "Control specification may be too short for reliable classification",
        )]

    @registry.rule("B-001", "No duplicate control IDs", severity="error", batch=True)
    def no_duplicate_ids(items: list[dict]) -> list[RuleResult]:
        ids = [i["id"] for i in items]
        unique = len(ids) == len(set(ids))
        return [RuleResult(
            rule_id="B-001", rule_name="No duplicate control IDs",
            category="cross_item", severity="error",
            passed=unique, item_id=None,
            message="OK" if unique else f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}",
        )]

    @registry.rule("B-002", "Domain coverage — not all in single domain", severity="warning", batch=True)
    def domain_distribution(items: list[dict]) -> list[RuleResult]:
        from collections import Counter
        counts = Counter(i["domain"] for i in items)
        max_pct = max(counts.values()) / len(items) if items else 0
        passed = max_pct <= 0.70
        return [RuleResult(
            rule_id="B-002", rule_name="Domain coverage — not all in single domain",
            category="cross_item", severity="warning",
            passed=passed, item_id=None,
            message="OK" if passed else f"Domain concentration: {dict(counts)}, max {max_pct:.0%}",
        )]

    items = []
    n = len(CONTROLS)
    for i, c in enumerate(CONTROLS):
        print(f"         classifying {c['id']} ({i+1}/{n})", flush=True)
        mapping = map_control(c["description"])
        items.append({"id": c["id"], "description": c["description"], **mapping})
    return run_consistency_check(items, registry)


# ─── Dimension 3: Convergent validity ────────────────────────────────────
# LLM direct mapping vs transitive crosswalk (AICM→CIS Controls→FAIR-CAM).

def run_convergent():
    descriptions = [c["description"] for c in CONTROLS]
    n = len(CONTROLS)

    predicted_domains = []
    for i, d in enumerate(descriptions):
        print(f"         classifying {CONTROLS[i]['id']} ({i+1}/{n})", flush=True)
        predicted_domains.append(map_control_domain(d))

    # Filter to controls where transitive crosswalk is available
    has_transitive = [i for i, t in enumerate(TRANSITIVE_CROSSWALK_DOMAINS) if t is not None]

    if not has_transitive:
        # Fall back to expert mappings if no transitive data yet
        from llm_classification_validator.models import DimensionReport, Verdict
        return DimensionReport(
            dimension="convergent",
            verdict=Verdict.SKIPPED,
            details={"reason": "No transitive crosswalk data available. Populate TRANSITIVE_CROSSWALK_DOMAINS."},
        )

    item_ids_filtered = [CONTROLS[i]["id"] for i in has_transitive]
    pred_filtered = [predicted_domains[i] for i in has_transitive]
    ref_filtered = [TRANSITIVE_CROSSWALK_DOMAINS[i] for i in has_transitive]

    pred_func_sets = None
    ref_func_sets = None
    has_func_transitive = [i for i in has_transitive if TRANSITIVE_CROSSWALK_FUNCTIONS[i] is not None]
    if has_func_transitive:
        pred_func_sets = [map_control_functions(descriptions[i]) for i in has_func_transitive]
        ref_func_sets = [TRANSITIVE_CROSSWALK_FUNCTIONS[i] for i in has_func_transitive]

    return run_convergent_analysis(
        predicted_labels=pred_filtered,
        reference_labels=ref_filtered,
        predicted_sets=pred_func_sets,
        reference_sets=ref_func_sets,
        item_ids=item_ids_filtered,
    )


# ─── Dimension 4: Adversarial edge cases ─────────────────────────────────

def run_adversarial():
    print("         testing 8 minimal pairs + 4 ambiguity cases...", flush=True)
    pairs = [
        MinimalPair(
            "mp-01",
            "Assess adversarial threats specific to each AI model to understand attack surface",
            "Harden AI models to resist adversarial attacks identified in the threat analysis",
            "VMC", "LEC",
        ),
        MinimalPair(
            "mp-02",
            "Validate and filter input against adversarial patterns and failure modes",
            "Monitor security audit logs to detect activity outside of typical patterns",
            "LEC", "LEC",
        ),
        MinimalPair(
            "mp-03",
            "Establish governance policies and procedures for AI systems sponsored by leadership",
            "Establish change management policies for managing risks of applying changes to assets",
            "DSC", "VMC",
        ),
        MinimalPair(
            "mp-04",
            "Calculate and compare cryptographic checksums of model checkpoints to detect unauthorized modifications",
            "Scan model artifacts for vulnerabilities at each step of the service lifecycle",
            "LEC", "VMC",
        ),
        MinimalPair(
            "mp-05",
            "Establish and maintain a security incident response plan with escalation paths",
            "Establish strategies to improve resiliency and recovery from business disruptions",
            "LEC", "LEC",
        ),
        MinimalPair(
            "mp-06",
            "Document and communicate employee roles and responsibilities for information security",
            "Conduct independent audit and assurance assessments according to relevant standards",
            "DSC", "DSC",
        ),
        MinimalPair(
            "mp-07",
            "Remediate application security vulnerabilities, automating remediation when possible",
            "Periodic penetration testing by independent third parties to assess control effectiveness",
            "VMC", "VMC",
        ),
        MinimalPair(
            "mp-08",
            "Ensure security of the AI training pipeline against data poisoning and supply chain attacks",
            "Review risk factors associated with third-party supply chain relationships",
            "LEC", "VMC",
        ),
    ]

    ambiguity = [
        AmbiguityCase(
            "amb-01",
            "Establish policies and procedures for the security of the AI training pipeline, "
            "including scanning for vulnerabilities and reviewing threat landscape",
            ["DSC", "VMC"],
        ),
        AmbiguityCase(
            "amb-02",
            "Monitor security logs for anomalies and generate audit records with relevant security information",
            ["LEC"],
        ),
        AmbiguityCase(
            "amb-03",
            "Establish governance policies that define change management procedures for AI system modifications",
            ["DSC", "VMC"],
        ),
        AmbiguityCase(
            "amb-04",
            "Implement application security testing strategy with automated vulnerability remediation",
            ["VMC"],
        ),
    ]

    return run_adversarial_analysis(map_control_domain, pairs, ambiguity)


# ─── Dimension 5: Stability and sensitivity ──────────────────────────────

def run_stability():
    print("         testing 8 paraphrases + 5 perturbations...", flush=True)
    base_items = {
        "MDS-06": CONTROLS[2]["description"],
        "MDS-07": CONTROLS[3]["description"],
        "AIS-08": CONTROLS[5]["description"],
        "CEK-03": CONTROLS[9]["description"],
        "LOG-05": CONTROLS[10]["description"],
        "CCC-01": CONTROLS[14]["description"],
        "GRC-01": CONTROLS[17]["description"],
        "A&A-02": CONTROLS[19]["description"],
    }

    paraphrases = [
        ParaphraseVariant("MDS-07", "MDS-07_p1", "formal",
            "Implement model hardening techniques and procedures to mitigate adversarial attacks identified through threat analysis"),
        ParaphraseVariant("MDS-07", "MDS-07_p2", "informal",
            "Make AI models resistant to the adversarial attacks found in the threat assessment"),
        ParaphraseVariant("AIS-08", "AIS-08_p1", "formal",
            "Implement input validation controls that filter or block adversarial patterns and failure modes per organisational policy"),
        ParaphraseVariant("AIS-08", "AIS-08_p2", "structural",
            "Block adversarial input. Filter failure patterns. Validate against organisational policies and regulations."),
        ParaphraseVariant("LOG-05", "LOG-05_p1", "formal",
            "Implement continuous monitoring of security audit logs to identify deviations from expected activity patterns, with defined response procedures for anomalies"),
        ParaphraseVariant("GRC-01", "GRC-01_p1", "informal",
            "Set up and maintain an info governance programme backed by leadership, covering AI systems too"),
        ParaphraseVariant("CCC-01", "CCC-01_p1", "formal",
            "Define and maintain change management policies and procedures to control risks arising from modifications to organisational assets"),
        ParaphraseVariant("A&A-02", "A&A-02_p1", "informal",
            "Get independent audits done every year according to the relevant standards"),
    ]

    perturbations = [
        PerturbationVariant(
            item_id="MDS-06", variant_id="MDS-06_pert",
            perturbation_type="domain_shift",
            text="Deploy adversarial input filters that block identified attack patterns targeting AI models in real time",
            expected_direction=ExpectedDirection(changes_expected={"domain": True}),
        ),
        PerturbationVariant(
            item_id="AIS-08", variant_id="AIS-08_pert",
            perturbation_type="subdomain_shift",
            text="Log and alert on input patterns that match known adversarial signatures without blocking them",
            expected_direction=ExpectedDirection(changes_expected={"subdomain": True}),
        ),
        PerturbationVariant(
            item_id="GRC-01", variant_id="GRC-01_pert",
            perturbation_type="domain_shift",
            text="Implement automated configuration scanning to enforce governance baselines across AI systems",
            expected_direction=ExpectedDirection(changes_expected={"domain": True}),
        ),
        PerturbationVariant(
            item_id="CEK-03", variant_id="CEK-03_noop",
            perturbation_type="noop",
            text="Use certified cryptographic libraries to protect data at rest, in transit, and where applicable in use",
            expected_direction=ExpectedDirection(),
        ),
        PerturbationVariant(
            item_id="CCC-01", variant_id="CCC-01_noop",
            perturbation_type="noop",
            text="Maintain policies and procedures for managing change-related risks to organisational assets, reviewed annually",
            expected_direction=ExpectedDirection(),
        ),
    ]

    return run_stability_analysis(
        base_items, map_control,
        paraphrases=paraphrases, perturbations=perturbations,
    )


# ─── Full orchestration ─────────────────────────────────────────────────

if __name__ == "__main__":
    mode = "LLM (Claude)" if _USE_LLM else "keyword fallback"
    print(f"Classifier: {mode}\n")

    report = run_evaluation(
        foundation=[run_coherence, run_consistency, run_convergent],
        advanced=[run_adversarial, run_stability],
        parallel_advanced=True,
    )

    print(f"Overall: {report.overall_verdict.value}\n")
    for dim in report.dimensions:
        print(f"  {dim.dimension}: {dim.verdict.value} ({dim.duration_s:.3f}s)")
        for m in dim.metrics:
            print(f"    {m.summary}")
        if dim.details.get("reason"):
            print(f"    (skipped: {dim.details['reason']})")
        print()
