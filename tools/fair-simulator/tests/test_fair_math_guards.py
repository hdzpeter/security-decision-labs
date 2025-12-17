# tests/test_fair_math_guards.py

import numpy as np

from risk_service.fair_calculator import FAIRInputs, FAIRCalculator  # adjust package path if needed


def test_secondary_losses_drop_out_when_slef_zero():
    """
    If SLEF = 0, secondary losses should not contribute to LM or ALE.
    We set non-zero secondary loss percentiles to check they are effectively gated.
    """
    inputs = FAIRInputs(
        # TEF: we just need something >0
        tef_p10=1.0,
        tef_p50=2.0,
        tef_p90=4.0,
        tef_model="poisson",

        # Susceptibility: moderate
        susc_p10=20.0,
        susc_p50=40.0,
        susc_p90=60.0,

        # Primary losses
        productivity_p10=100_000,
        productivity_p50=200_000,
        productivity_p90=400_000,
        response_p10=50_000,
        response_p50=100_000,
        response_p90=200_000,
        replacement_p10=10_000,
        replacement_p50=20_000,
        replacement_p90=40_000,

        # Secondary losses – non-zero on purpose
        fines_p10=50_000,
        fines_p50=100_000,
        fines_p90=200_000,
        competitive_adv_p10=25_000,
        competitive_adv_p50=50_000,
        competitive_adv_p90=100_000,
        reputation_p10=75_000,
        reputation_p50=150_000,
        reputation_p90=300_000,

        # SLEF = 0% (no secondary loss events)
        slef_p10=0.0,
        slef_p50=0.0,
        slef_p90=0.0,

        time_horizon_years=1.0,
        currency="USD",
    )

    calc = FAIRCalculator(n_simulations=50_000, random_state=123)
    results = calc.calculate(inputs)

    # Reconstruct primary-only LM approximation from P50 loss forms
    primary_median = (
        results.productivity_p50
        + results.response_p50
        + results.replacement_p50
    )

    # Because secondary is fully gated out, LM median should be very close to primary-only median
    assert abs(results.slee_p50 - primary_median) / primary_median < 0.05


def test_zero_susceptibility_zeroes_lef_and_ale():
    """
    If susceptibility is 0, then LEF should be 0 and ALE should be 0,
    even if TEF and Loss Magnitude are non-zero.
    """
    inputs = FAIRInputs(
        # TEF: non-zero
        tef_p10=1.0,
        tef_p50=3.0,
        tef_p90=5.0,
        tef_model="poisson",

        # Susceptibility = 0%
        susc_p10=0.0,
        susc_p50=0.0,
        susc_p90=0.0,

        # Primary losses (non-zero)
        productivity_p10=100_000,
        productivity_p50=200_000,
        productivity_p90=400_000,
        response_p10=50_000,
        response_p50=100_000,
        response_p90=200_000,
        replacement_p10=10_000,
        replacement_p50=20_000,
        replacement_p90=40_000,

        # No secondary loss to keep test simple
        fines_p10=0.0,
        fines_p50=0.0,
        fines_p90=0.0,
        competitive_adv_p10=0.0,
        competitive_adv_p50=0.0,
        competitive_adv_p90=0.0,
        reputation_p10=0.0,
        reputation_p50=0.0,
        reputation_p90=0.0,

        slef_p10=0.0,
        slef_p50=0.0,
        slef_p90=0.0,

        time_horizon_years=1.0,
        currency="USD",
    )

    calc = FAIRCalculator(n_simulations=50_000, random_state=456)
    results = calc.calculate(inputs)

    # We allow tiny numerical noise but expect results ~ 0
    assert results.lef_mean < 1e-6
    assert results.ale_mean < 1e-3  # currency units; should be effectively 0