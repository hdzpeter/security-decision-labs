"""
Contact / breach processing.

Key semantics:
- "Contact attempts" are scheduled by Threat Agents.
- "Avoidance" LECs can prevent contact from occurring.
- "Deterrence" LECs (typically insider-focused) can deter action after contact.
- "Resistance" LECs can prevent a breach after action.
- Control "variant" state lowers *current efficacy* (set when becoming variant, held until remediated).
- Breaches on technical assets with no hosted business assets are "orphan breaches" and do NOT create loss events.

LEC Efficacy Method behaviors (from JSON):
- "comparison to threat sophistication": compare efficacy [0-1] against threat sophistication
  - Blocks threat if sophistication <= efficacy
- "random draw, success/failure outcome": Bernoulli trial with probability [0-1] from Beta-PERT
  - Blocks threat if Bernoulli trial succeeds (returns True)
- Time-based methods (detection sweep, termination, recovery) are handled by loss event processing,
  not contact processing.

This module is intentionally defensive to differences in network/topology helper return types
(e.g., controls upstream returned as list vs dict).

Debugging:
- If the model has `debug_print_controls = True`, this module will print, once per target TA,
  a recursive control tree: TA -> LECs -> (VMC/DSC upstream of each LEC).
- Optionally, we can restrict printing to specific TA IDs by setting
  `model.debug_print_controls_assets = {"TA1","TA2",...}` (set or list).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)


def _lower(s: Any) -> str:
    return str(s).strip().lower()


def _get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def _params_dict(agent: Any) -> Dict[str, Any]:
    p = _get_attr(agent, "params", "_params", default=None)
    return p if isinstance(p, dict) else {}


def _agent_id(agent: Any) -> str:
    return str(_get_attr(agent, "unique_id", "id", default=""))


def _effective_efficacy(agent: Any) -> float:
    """
    Get the control's current efficacy (degraded if the control is variant).
    """
    for name in ("get_effective_efficacy", "effective_efficacy", "current_efficacy", "efficacy"):
        val = _get_attr(agent, name, default=None)
        if callable(val):
            try:
                v = float(val())
                return max(0.0, min(1.0, v))
            except Exception:
                pass
        else:
            if val is not None:
                try:
                    v = float(val)
                    return max(0.0, min(1.0, v))
                except Exception:
                    pass
    intended = _get_attr(agent, "intended_efficacy", default=None)
    try:
        return max(0.0, min(1.0, float(intended)))
    except Exception:
        return 0.0


def _lec_stage(agent: Any) -> Optional[str]:
    """
    Determine which Loss Event Prevention stage a LEC implements.
    Returns one of: "avoidance", "deterrence", "resistance" or None.
    """
    p = _params_dict(agent)
    candidates = [
        p.get("Control Type"),
        p.get("Loss Event Prevention Function"),
        p.get("Loss Event Prevention"),
        p.get("Prevention Function"),
        p.get("Function"),
    ]
    for c in candidates:
        v = _lower(c)
        if v in ("avoidance", "avoid", "avd"):
            return "avoidance"
        if v in ("deterrence", "deter", "det"):
            return "deterrence"
        if v in ("resistance", "resist", "res"):
            return "resistance"
    return None


def _combine_defense_in_depth(effs: Sequence[float]) -> float:
    """
    Defense-in-depth combination for layered resistance controls.

    Per the FAIR-CAM:

        Combined_Susceptibility = Π(1 - OpEff_i)
        RS = 1 - Combined_Susceptibility = 1 - Π(1 - eff_i)

    Each control is an independent sequential hurdle the attacker must
    overcome.  The probability of breaching ALL controls is the product
    of per-control pass-through probabilities (1 - eff_i).

    Properties:
      - If any control has efficacy 1.0 → RS = 1.0 (impenetrable layer).
      - Adding more controls always increases RS (defense-in-depth).
      - RS ≥ max(eff_i).
    """
    combined_susceptibility = 1.0
    for e in effs:
        e = max(0.0, min(1.0, float(e)))
        combined_susceptibility *= (1.0 - e)
    return max(0.0, min(1.0, 1.0 - combined_susceptibility))


def _lec_blocks_threat(lec: Any, sophistication: float, model: Any = None) -> bool:
    """
    Evaluate whether a LEC blocks a threat based on its Efficacy Method.

    For "comparison to threat sophistication" (compare_sophistication behavior):
    - Returns True if sophistication <= efficacy (threat blocked)

    For "random draw, success/failure outcome" (bernoulli_trial behavior):
    - Performs a Bernoulli trial with the LEC's sampled probability
    - Returns True if trial succeeds (threat blocked)

    For time-based LECs (detection, termination, recovery):
    - These don't directly block threats during contact processing
    - They affect loss event timing, handled elsewhere
    - Returns False (doesn't block during contact)

    For human-type resistance LECs, the DSC decision model determines
    whether the control blocks the threat, based on associated personnel alignment.
    """
    behavior = _get_attr(lec, "_efficacy_behavior", default=None)
    semantic_type = _get_attr(lec, "_efficacy_semantic_type", default=None)

    # Human actor type LECs use DSC decision model
    actor_type = _lower(_get_attr(lec, "actor_type", default="technology"))
    if actor_type == "human" and model is not None:
        lec_id = _agent_id(lec)
        dsc_model = _get_attr(model, "dsc_decision_model", default=None)
        net = _get_attr(model, "network", default=None)
        if dsc_model is not None and net is not None and lec_id:
            personnel = net.get_personnel_for_control(lec_id)
            if personnel:
                try:
                    aligned = dsc_model.query_decision_alignment(personnel[0])
                    return aligned  # aligned = blocks threat, misaligned = fails
                except Exception as exc:
                    logger.warning(
                        "DSC decision failed for LEC %s personnel %s: %s",
                        lec_id, getattr(personnel[0], "unique_id", "?"), exc,
                    )
            # No personnel linked — fall through to standard efficacy check

    # Bernoulli trial behavior: sample probability from Beta-PERT, perform trial
    if behavior == "bernoulli_trial" and semantic_type == "probability":
        # Use the LEC's perform_bernoulli_trial() method if available
        if hasattr(lec, "perform_bernoulli_trial"):
            result = lec.perform_bernoulli_trial()
            if result is not None:
                return result  # True = blocked, False = passed

        # Fallback: sample probability and do trial manually
        if hasattr(lec, "sample_success_probability"):
            p = lec.sample_success_probability()
            if p is not None:
                # Keyed to LEC id so removing another control doesn't
                # shift this draw (see STREAM_ISOLATION.md)
                lec_id_str = _agent_id(lec)
                m = _get_attr(lec, "model", default=None)
                streams = _get_attr(m, "streams", default=None) if m else None
                rng = streams.get(f"contact_bernoulli:{lec_id_str}") if streams else _rng(m)
                return float(rng.random()) < p

    # Time-based LECs don't block during contact (they affect loss event timing)
    if semantic_type == "time_hours":
        return False

    # Default: comparison to threat sophistication.
    # Efficacy is set-and-hold (sampled at init and after remediation).
    # Variation in outcomes comes from threat sophistication, not re-sampling efficacy.
    eff = _effective_efficacy(lec)
    return sophistication <= eff


def _rng(model: Any):
    r = _get_attr(model, "random", default=None)
    if r is None:
        import random as _py_random
        return _py_random
    return r


@dataclass
class ContactOutcome:
    attempted: bool = True
    contacted: bool = False
    deterred: bool = False
    resisted: bool = False
    breached: bool = False
    orphan_breach: bool = False


# Backwards-compat import used by src/processing/__init__.py
ContactResult = ContactOutcome


def _split_controls(result: Any) -> Tuple[List[Any], List[Any], List[Any]]:
    """
    Normalize upstream controls return value to (lecs, vmcs, dscs).
    Accepts:
      - dict: {"lecs":[...], "vmcs":[...], "dscs":[...]}
      - list/tuple: mixed control agents
    """
    if isinstance(result, dict):
        return (list(result.get("lecs", []) or []),
                list(result.get("vmcs", []) or []),
                list(result.get("dscs", []) or []))
    if isinstance(result, (list, tuple)):
        lecs: List[Any] = []
        vmcs: List[Any] = []
        dscs: List[Any] = []
        for a in result:
            uid = _agent_id(a).upper()
            if uid.startswith("LEC"):
                lecs.append(a)
            elif uid.startswith("VMC"):
                vmcs.append(a)
            elif uid.startswith("DSC"):
                dscs.append(a)
        return (lecs, vmcs, dscs)
    return ([], [], [])


def print_controls_tree(model: Any, tech_asset_id: str, max_depth: int = 2) -> None:
    """
    Print recursive control dependencies for a given TA:
      TA -> LECs -> (VMC/DSC upstream of each LEC)

    This assumes the topology includes nodes/edges for controls as well.
    If it doesn't, we'll see empty upstream lists for the LEC level.
    """
    net = _get_attr(model, "network", "topology", default=None)
    if net is None:
        print(f"[controls] {tech_asset_id}: no network/topology on model")
        return

    get_upstream = _get_attr(net, "get_controls_upstream", default=None)
    if not callable(get_upstream):
        print(f"[controls] {tech_asset_id}: topology has no get_controls_upstream()")
        return

    visited: Set[str] = set()

    def _print_node(node_id: str, depth: int) -> None:
        indent = "  " * depth
        if node_id in visited:
            print(f"{indent}{node_id} (already shown)")
            return
        visited.add(node_id)

        try:
            res = get_upstream(node_id)
        except Exception as e:
            print(f"{indent}{node_id}: get_controls_upstream failed: {e}")
            return

        lecs, vmcs, dscs = _split_controls(res)

        if depth == 0:
            print(f"[controls] {node_id}")
        if lecs:
            print(f"{indent}  LECs:")
            for lec in lecs:
                lec_id = _agent_id(lec)
                stage = _lec_stage(lec) or "unknown"
                eff = _effective_efficacy(lec)
                state = _get_attr(lec, "state", default=None)
                state_s = str(state) if state is not None else "?"
                print(f"{indent}    - {lec_id} stage={stage} state={state_s} eff={eff:.3f}")
                if depth + 1 < max_depth:
                    _print_node(lec_id, depth + 1)
        else:
            print(f"{indent}  LECs: []")

        if vmcs:
            print(f"{indent}  VMCs: {[ _agent_id(x) for x in vmcs ]}")
        if dscs:
            print(f"{indent}  DSCs: {[ _agent_id(x) for x in dscs ]}")

    _print_node(tech_asset_id, 0)


class ContactProcessor:
    def __init__(self, model: Any):
        self.model = model

    def _upstream_controls(self, node_id: str) -> Tuple[List[Any], List[Any], List[Any]]:
        net = _get_attr(self.model, "network", "topology", default=None)
        if net is None:
            return ([], [], [])
        fn = _get_attr(net, "get_controls_upstream", default=None)
        if not callable(fn):
            return ([], [], [])
        return _split_controls(fn(node_id))

    def _hosted_business_assets(self, tech_asset_id: str) -> List[str]:
        net = _get_attr(self.model, "network", "topology", default=None)
        if net is None:
            return []
        for name in ("get_hosted_business_assets", "get_business_assets", "hosted_business_assets_for"):
            fn = _get_attr(net, name, default=None)
            if callable(fn):
                try:
                    res = fn(tech_asset_id)
                    if res is None:
                        return []
                    out: List[str] = []
                    for x in res:
                        out.append(x if isinstance(x, str) else _agent_id(x))
                    return out
                except Exception:
                    continue
        return []

    def _maybe_debug_print(self, tech_asset_id: str) -> None:
        m = self.model
        if not bool(_get_attr(m, "debug_print_controls", default=False)):
            return

        allowed = _get_attr(m, "debug_print_controls_assets", default=None)
        if allowed is not None:
            if isinstance(allowed, (list, tuple, set)):
                if tech_asset_id not in set(str(x) for x in allowed):
                    return
            else:
                # single string
                if tech_asset_id != str(allowed):
                    return

        if not hasattr(m, "_debug_printed_assets"):
            m._debug_printed_assets = set()
        if tech_asset_id in m._debug_printed_assets:
            return
        m._debug_printed_assets.add(tech_asset_id)

        print_controls_tree(m, tech_asset_id, max_depth=2)

    def process_contact(self, threat_agent: Any, target_tech_asset: Any) -> ContactOutcome:
        """
        Process a contact event:
        1. Draw threat sophistication (0-1)
        2. For each LEC stage (avoidance, deterrence, resistance):
           - Compare sophistication against each control's efficacy
           - Threat must breach ALL controls (sophistication > efficacy) to pass that stage
        3. If threat breaches all controls -> breach occurs
        """
        m = self.model
        ms = _get_attr(m, "metrics_state", default=None)

        # Update metrics_state if available
        if ms is not None:
            ms.total_contact_attempts += 1
        else:
            if not hasattr(m, "total_contact_attempts"):
                m.total_contact_attempts = 0
            m.total_contact_attempts += 1
        out = ContactOutcome(attempted=True)

        target_id = _agent_id(target_tech_asset)

        # Debug: print control tree once per TA
        self._maybe_debug_print(target_id)

        lecs, _vmcs, _dscs = self._upstream_controls(target_id)

        # Draw threat sophistication once per contact (per spec)
        sophistication = 0.5  # default
        sample_fn = _get_attr(threat_agent, "sample_sophistication", default=None)
        if callable(sample_fn):
            try:
                sophistication = float(sample_fn())
            except Exception:
                pass
        else:
            # Fallback: try to get from params or use default
            params = _get_attr(threat_agent, "params", default={}) or {}
            sophistication = float(params.get("sophistication", 0.5))

        # Partition LECs by stage, keeping the agent references for efficacy comparison
        avoidance_lecs: List[Any] = []
        deterrence_lecs: List[Any] = []
        resistance_lecs: List[Any] = []

        for lec in lecs:
            stage = _lec_stage(lec)
            if stage == "avoidance":
                avoidance_lecs.append(lec)
            elif stage == "deterrence":
                deterrence_lecs.append(lec)
            elif stage == "resistance":
                resistance_lecs.append(lec)
            # else: LECs with unrecognized stages (visibility, monitoring,
            # recognition, event_termination, resilience) are loss-event-phase
            # controls and do NOT participate in contact/breach prevention.

        # scale parameter loop. The spec says contact processing iterates
        # tech_asset.scale_param times. Each iteration is an independent breach attempt.
        scale_param = int(getattr(target_tech_asset, "scale_param",
                         _get_attr(target_tech_asset, "params", default={}).get("Scale_Param",
                         _get_attr(target_tech_asset, "params", default={}).get("Scale Param", 1)) or 1))
        scale_param = max(1, scale_param)

        # deterrence applicability. Config-driven: apply to all threats or internal-only.
        from ..config import get_config as _get_cfg
        _cfg = _get_cfg()
        deterrence_internal_only = bool(_cfg.get("threats.contact.deterrence_internal_only", True))

        origin = _lower(_get_attr(threat_agent, "origin", default=_get_attr(threat_agent, "threat_origin", default="external")))
        is_internal = origin in ("internal", "insider")

        breach_in_any_iteration = False
        for _scale_iter in range(scale_param):
            # Re-draw sophistication per iteration (per spec: one draw per scale iteration)
            iter_soph = sophistication
            if _scale_iter > 0:
                sample_fn2 = _get_attr(threat_agent, "sample_sophistication", default=None)
                if callable(sample_fn2):
                    try:
                        iter_soph = float(sample_fn2())
                    except Exception:
                        pass

            # Count every contact attempt (first scale iteration only) so all
            # stage rates share the same denominator.
            if _scale_iter == 0 and ms is not None:
                ms.total_contact_events += 1

            # Avoidance stage: if any avoidance control blocks, this iteration fails
            avoided = False
            for lec in avoidance_lecs:
                if _lec_blocks_threat(lec, iter_soph, model=m):
                    avoided = True
                    break

            if avoided:
                if ms is not None and _scale_iter == 0:
                    ms.total_avoided_contacts += 1
                if scale_param == 1:
                    return out
                continue

            # Track first successful pass through avoidance
            if not out.contacted:
                out.contacted = True

            # Deterrence stage
            deterred = False
            if (deterrence_internal_only and is_internal) or (not deterrence_internal_only):
                for lec in deterrence_lecs:
                    if _lec_blocks_threat(lec, iter_soph, model=m):
                        deterred = True
                        break

            if deterred:
                if ms is not None and not out.deterred:
                    ms.total_deterred_events += 1
                out.deterred = True
                if scale_param == 1:
                    return out
                continue

            # Resistance stage: FAIR-CAM susceptibility formula.
            #
            #   Combined_Susceptibility = Π(1 - OpEff_i)
            #   RS = 1 - Combined_Susceptibility
            #   Susceptibility = P(TCap > RS)
            #
            # Each resistive control is an independent sequential hurdle.
            # Defense-in-depth combines their efficacies multiplicatively
            # into a single RS value.  Breach occurs when the threat's
            # sophistication (TCap) exceeds the combined RS — i.e., the
            # threat is capable enough to overcome all layered controls.
            #
            # Susceptibility emerges from the comparison of TCap
            # vs. RS.  A control with RS of 70%-90% "successfully repels
            # attackers below this capability range" and "fails against
            # attackers above the 90th percentile."
            resisted = False
            _breach_mechanics: Dict[str, Any] = {}
            _res_control_detail: List[Dict[str, Any]] = []
            if resistance_lecs:
                # Collect per-control efficacy (sampled fresh per contact)
                control_effs: List[float] = []
                for lec in resistance_lecs:
                    behavior = _get_attr(lec, "_efficacy_behavior", default=None)
                    semantic_type = _get_attr(lec, "_efficacy_semantic_type", default=None)

                    # Time-based LECs don't participate in contact resistance
                    if semantic_type == "time_hours":
                        continue

                    lec_id = _agent_id(lec)
                    lec_state = str(_get_attr(lec, "state", default="normal")).lower()
                    lec_intended = float(_get_attr(lec, "intended_efficacy", default=0.0))

                    # Human-actor LECs use DSC decision model
                    # When the control is variant (degraded training/procedures),
                    # personnel DSC attributes are scaled by the degradation ratio,
                    # making aligned decisions harder. Even when aligned, the
                    # degraded control provides only partial protection.
                    actor_type = _lower(_get_attr(lec, "actor_type", default="technology"))
                    if actor_type == "human" and m is not None:
                        dsc_model = _get_attr(m, "dsc_decision_model", default=None)
                        net = _get_attr(m, "network", default=None)
                        if dsc_model is not None and net is not None and lec_id:
                            personnel = net.get_personnel_for_control(lec_id)
                            if personnel:
                                try:
                                    # Scale DSC attributes by control degradation
                                    lec_current_eff = float(_effective_efficacy(lec))
                                    degradation_factor = (
                                        (lec_current_eff / lec_intended)
                                        if lec_intended > 0 else 1.0
                                    )
                                    effective_attrs = None
                                    if degradation_factor < 1.0:
                                        base_attrs = personnel[0].get_effective_attributes()
                                        effective_attrs = {
                                            k: v * degradation_factor
                                            for k, v in base_attrs.items()
                                        }

                                    aligned = dsc_model.query_decision_alignment(
                                        personnel[0],
                                        effective_attributes=effective_attrs,
                                    )
                                    # Fetch DSC detail first — needed for residual calc
                                    dsc_detail = dsc_model.get_last_decision_detail()

                                    if aligned:
                                        # Aligned: use actual control efficacy
                                        eff_val = lec_current_eff
                                        dsc_residual = None
                                    else:
                                        # Misaligned: partial protection based on
                                        # how many DSC dimensions still passed.
                                        # Rationale: a person who fails only on
                                        # incentive but passes awareness/capability/
                                        # situational still mostly knows what to do —
                                        # they just didn't prioritize it.
                                        #   0/4 pass → residual 0.00 → no protection
                                        #   1/4 pass → residual 0.25
                                        #   2/4 pass → residual 0.50
                                        #   3/4 pass → residual 0.75
                                        dims_passed = 0
                                        total_dims = 4
                                        if dsc_detail:
                                            dims = dsc_detail.get("dimensions", {})
                                            total_dims = max(1, len(dims))
                                            dims_passed = sum(
                                                1 for d in dims.values()
                                                if d.get("final_success", False)
                                            )
                                        dsc_residual = dims_passed / total_dims
                                        eff_val = lec_current_eff * dsc_residual

                                    control_effs.append(eff_val)
                                    detail = {
                                        "control_id": lec_id, "stage": "resistance",
                                        "state": lec_state, "sampled_efficacy": eff_val,
                                        "effective_efficacy": lec_current_eff,
                                        "intended_efficacy": lec_intended,
                                        "behavior": "human_dsc", "actor_type": actor_type,
                                        "dsc_degradation_factor": round(degradation_factor, 4),
                                    }
                                    if dsc_residual is not None:
                                        detail["dsc_residual"] = round(dsc_residual, 4)
                                    if dsc_detail:
                                        detail["dsc_detail"] = dsc_detail
                                    _res_control_detail.append(detail)
                                    continue
                                except Exception as exc:
                                    logger.warning(
                                        "DSC decision failed for LEC %s personnel %s: %s",
                                        lec_id, getattr(personnel[0], "unique_id", "?"), exc,
                                    )

                    # Bernoulli trial LECs: use sampled probability as efficacy
                    if behavior == "bernoulli_trial" and semantic_type == "probability":
                        if hasattr(lec, "sample_success_probability"):
                            p = lec.sample_success_probability()
                            if p is not None:
                                eff_val = max(0.0, min(1.0, float(p)))
                                control_effs.append(eff_val)
                                _res_control_detail.append({
                                    "control_id": lec_id, "stage": "resistance",
                                    "state": lec_state, "sampled_efficacy": eff_val,
                                    "intended_efficacy": lec_intended,
                                    "behavior": "bernoulli_trial", "actor_type": actor_type,
                                })
                                continue

                    # Compare-sophistication LECs: use set-and-hold efficacy
                    eff = _effective_efficacy(lec)
                    eff_val = max(0.0, min(1.0, eff))
                    control_effs.append(eff_val)
                    _res_control_detail.append({
                        "control_id": lec_id, "stage": "resistance",
                        "state": lec_state, "sampled_efficacy": eff_val,
                        "intended_efficacy": lec_intended,
                        "behavior": str(behavior or "compare_sophistication"),
                        "actor_type": actor_type,
                    })

                if control_effs:
                    # FAIR-CAM formula: Combined_Susceptibility = Π(1 - eff_i)
                    combined_rs = _combine_defense_in_depth(control_effs)
                    combined_susceptibility = 1.0 - combined_rs

                    # TCap vs RS comparison:
                    # Breach occurs when threat sophistication exceeds combined RS.
                    # When TCap == RS exactly, the threat fails (defender wins ties).
                    resisted = iter_soph <= combined_rs

                    # Store breach mechanics for narrative
                    _breach_mechanics = {
                        "combined_susceptibility": combined_susceptibility,
                        "combined_rs": combined_rs,
                        "susceptibility": combined_susceptibility,
                        "threat_sophistication": iter_soph,
                    }
                else:
                    # No applicable resistance controls -> breach
                    resisted = False

            if resisted:
                if ms is not None and not out.resisted:
                    ms.total_resisted_events += 1
                out.resisted = True
                if scale_param == 1:
                    return out
                continue

            # This iteration resulted in breach
            breach_in_any_iteration = True
            break  # One successful breach is enough

        # If no iteration breached, return the best outcome recorded
        if not breach_in_any_iteration:
            # Ensure we recorded at least avoided if contact never happened
            if not out.contacted and ms is not None:
                ms.total_avoided_contacts += 1
            return out

        # Breach: threat passed all controls
        out.breached = True
        if ms is not None:
            ms.total_breach_events += 1

        # Track the compromised tech asset
        threat_id = _agent_id(threat_agent)
        compromised_set = _get_attr(m, "compromised_tech_assets", default=None)
        if isinstance(compromised_set, set):
            compromised_set.add(target_id)

        # Collect failed controls (all LECs that were breached), variant controls, and efficacies
        failed_controls: List[str] = []
        variant_controls: List[str] = []
        control_efficacies: Dict[str, float] = {}

        all_lecs = avoidance_lecs + deterrence_lecs + resistance_lecs
        for lec in all_lecs:
            lec_id = _agent_id(lec)
            if lec_id:
                failed_controls.append(lec_id)
                # Record efficacy at time of breach
                eff = _effective_efficacy(lec)
                control_efficacies[lec_id] = eff
                # Check if control is in variant or remediating state (not at intended efficacy)
                state = _get_attr(lec, "state", default=None)
                if state is not None:
                    state_str = str(state).lower()
                    if state_str in ("variant", "remediating"):
                        variant_controls.append(lec_id)

        # Build per-control detail for avoidance and deterrence stages too
        per_control_detail = list(_res_control_detail)  # start with resistance detail
        for stage_name, stage_lecs in [("avoidance", avoidance_lecs), ("deterrence", deterrence_lecs)]:
            for lec in stage_lecs:
                lid = _agent_id(lec)
                if lid:
                    per_control_detail.append({
                        "control_id": lid, "stage": stage_name,
                        "state": str(_get_attr(lec, "state", default="normal")).lower(),
                        "sampled_efficacy": float(_effective_efficacy(lec)),
                        "intended_efficacy": float(_get_attr(lec, "intended_efficacy", default=0.0)),
                        "behavior": str(_get_attr(lec, "_efficacy_behavior", default="compare_sophistication")),
                        "actor_type": _lower(_get_attr(lec, "actor_type", default="technology")),
                    })

        # Get threat origin
        threat_origin = _lower(_get_attr(threat_agent, "origin", default=_get_attr(threat_agent, "threat_origin", default="external")))

        # Record breach in narrative with control info + mechanics
        nar = _get_attr(m, "narrative", default=None)
        if nar is not None and hasattr(nar, "record_breach"):
            tick = int(_get_attr(_get_attr(m, "schedule", default=None), "steps", default=0))
            try:
                nar.record_breach(
                    threat_id=threat_id,
                    tech_asset_id=target_id,
                    tick=tick,
                    failed_controls=failed_controls,
                    variant_controls=variant_controls,
                    threat_sophistication=sophistication,
                    control_efficacies=control_efficacies,
                    threat_origin=threat_origin,
                    breach_mechanics=_breach_mechanics,
                    per_control_detail=per_control_detail,
                )
            except Exception:
                pass

        # Hosted BAs => loss events; else orphan breach
        bas = self._hosted_business_assets(target_id)
        if not bas:
            out.orphan_breach = True
            if ms is not None:
                ms.orphan_breach_events += 1
                # Track compromised TA hours for orphan breaches too
                ms.compromised_ta_hours += 1
                if target_id not in ms.compromised_ta_hours_by_ta:
                    ms.compromised_ta_hours_by_ta[target_id] = 0
                ms.compromised_ta_hours_by_ta[target_id] += 1
            return out

        # Schedule loss events for breach - pass failed/variant controls for narrative attribution
        # and threat_agent for velocity/exponent parameters
        lep = _get_attr(m, "loss_event_processor", default=None)
        if lep is not None:
            sched = _get_attr(lep, "schedule_loss_events_for_breach", default=None)
            if callable(sched):
                tick = int(_get_attr(_get_attr(m, "schedule", default=None), "steps", default=0))
                try:
                    sched(
                        threat_id=threat_id,
                        tech_asset_id=target_id,
                        breach_tick=tick,
                        failed_controls=failed_controls,
                        variant_controls=variant_controls,
                        threat_agent=threat_agent,
                    )
                except TypeError:
                    # Fallback to without threat_agent (older API)
                    try:
                        sched(
                            threat_id=threat_id,
                            tech_asset_id=target_id,
                            breach_tick=tick,
                            failed_controls=failed_controls,
                            variant_controls=variant_controls,
                        )
                    except TypeError:
                        # Final fallback to minimal API
                        try:
                            sched(threat_id, target_id, tick)
                        except Exception:
                            pass

        return out
