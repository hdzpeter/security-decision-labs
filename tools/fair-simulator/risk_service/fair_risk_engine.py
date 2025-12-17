"""
REST API for FAIR Risk Quantification Tool
FastAPI-based risk_service service
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationInfo
from typing import Optional, Dict, List
import numpy as np

from fair_calculator import FAIRInputs, FAIRCalculator, FAIRResults
from fair_aggregation import FAIRAggregator, ScenarioMetadata
from fair_distributions import validate_percentiles
from benchmark_library import get_lef_benchmark, get_lm_benchmark

# Global seed so Monte Carlo is stable across calls with same inputs
RISK_ENGINE_SEED = 42

# Initialize FastAPI
app = FastAPI(
    title="FAIR Risk Quantification API",
    description="Backend API for FAIR-based cyber risk quantification",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class PercentileInput(BaseModel):
    """Percentile inputs (P10, P50, P90)"""
    p10: float = Field(..., ge=0, description="10th percentile")
    p50: float = Field(..., description="50th percentile (median)")
    p90: float = Field(..., description="90th percentile")

    @field_validator("p50")
    @classmethod
    def validate_p50(cls, v: float, info: ValidationInfo) -> float:
        # info.data contains already-validated fields (like p10)
        p10 = (info.data or {}).get("p10")
        if p10 is not None and v < p10:
            raise ValueError("p50 must be >= p10")
        return v

    @field_validator("p90")
    @classmethod
    def validate_p90(cls, v: float, info: ValidationInfo) -> float:
        p50 = (info.data or {}).get("p50")
        if p50 is not None and v < p50:
            raise ValueError("p90 must be >= p50")
        return v


class TEFInput(BaseModel):
    """Threat Event Frequency inputs"""
    percentiles: PercentileInput
    model: str = Field("poisson", pattern="^(poisson|lognormal)$")
    decompose: bool = False
    contact_frequency: Optional[PercentileInput] = None
    prob_action: Optional[PercentileInput] = None
    zero_inflation: bool = False
    p_zero: float = Field(0.0, ge=0, le=1)


class SusceptibilityInput(BaseModel):
    """Susceptibility inputs (0–100%)"""
    percentiles: PercentileInput

    @field_validator("percentiles")
    @classmethod
    def validate_bounds(cls, v: PercentileInput) -> PercentileInput:
        if v.p10 < 0 or v.p90 > 100:
            raise ValueError("Susceptibility must be in [0, 100]%")
        return v


class LossPercentileInput(BaseModel):
    """
    Percentiles for a single loss form, with optional zero-rate knob.

    p_zero: Zero-rate (advanced) — probability this loss form is $0 when an
    event occurs (only used if P10 = 0 and P50 > 0). If omitted, a default
    zero-rate is used in the engine (typically 10%).
    """
    p10: float = Field(..., ge=0, description="10th percentile")
    p50: float = Field(..., description="50th percentile (median)")
    p90: float = Field(..., description="90th percentile")
    p_zero: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=0.9,
        description=(
            "Zero-rate (advanced): Probability this loss form is $0 when an "
            "event occurs (only used if P10 = 0)."
        ),
    )

    @field_validator("p50")
    @classmethod
    def validate_p50(cls, v: float, info: ValidationInfo) -> float:
        p10 = (info.data or {}).get("p10")
        if p10 is not None and v < p10:
            raise ValueError("p50 must be >= p10")
        return v

    @field_validator("p90")
    @classmethod
    def validate_p90(cls, v: float, info: ValidationInfo) -> float:
        p50 = (info.data or {}).get("p50")
        if p50 is not None and v < p50:
            raise ValueError("p90 must be >= p50")
        return v

    @field_validator("p_zero")
    @classmethod
    def clamp_p_zero(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        # Clamp to [0, 0.90] to avoid degenerate "almost always zero" forms.
        return max(0.0, min(0.90, float(v)))


class LossFormInput(BaseModel):
    """Loss form inputs for all 6 forms of loss."""
    productivity: Optional[LossPercentileInput] = None
    response: Optional[LossPercentileInput] = None
    replacement: Optional[LossPercentileInput] = None
    fines: Optional[LossPercentileInput] = None
    competitive_advantage: Optional[LossPercentileInput] = None
    reputation: Optional[LossPercentileInput] = None


class SLEFInput(BaseModel):
    """Secondary Loss Event Frequency inputs (0–100%)"""
    percentiles: PercentileInput

    @field_validator("percentiles")
    @classmethod
    def validate_bounds(cls, v: PercentileInput) -> PercentileInput:
        if v.p10 < 0 or v.p90 > 100:
            raise ValueError("SLEF must be in [0, 100]%")
        return v


class ScenarioCalculationRequest(BaseModel):
    """Request for FAIR scenario calculation"""
    scenario_id: Optional[str] = None
    tef: TEFInput
    susceptibility: SusceptibilityInput
    loss_forms: LossFormInput
    slef: Optional[SLEFInput] = None
    time_horizon_years: float = Field(1.0, gt=0)
    currency: str = "USD"
    n_simulations: int = Field(100000, ge=10000, le=1000000)


class ScenarioCalculationResponse(BaseModel):
    """Response from FAIR scenario calculation"""
    scenario_id: Optional[str]
    ale: Dict[str, float]
    lef: Dict[str, float]
    lm: Dict[str, float]
    loss_forms: Dict[str, float]
    metadata: Dict


class SensitivityAnalysisRequest(BaseModel):
    """Request for sensitivity analysis"""
    scenario: ScenarioCalculationRequest
    factor: str = Field(..., description="Factor to vary (e.g., 'tef_p50')")
    variation_pct: float = Field(20.0, ge=0, le=100)


class SensitivityAnalysisResponse(BaseModel):
    """Response from sensitivity analysis"""
    factor: str
    baseline_ale: float
    ale_down: float
    ale_up: float
    elasticity_down: float
    elasticity_up: float
    average_elasticity: float


class AggregationRequest(BaseModel):
    """Request for portfolio aggregation"""
    scenarios: Dict[str, ScenarioCalculationRequest]
    correlation: float = Field(0.0, ge=0, le=1)
    n_simulations: int = Field(100000, ge=10000, le=1000000)


class AggregationResponse(BaseModel):
    """Response from portfolio aggregation"""
    total_ale: Dict[str, float]
    scenario_contributions: Dict[str, float]
    top_scenarios: List[Dict]
    assumed_correlation: float


class PortfolioMetricsRequest(BaseModel):
    """Request for portfolio-level metrics"""
    scenarios: Dict[str, ScenarioCalculationRequest]
    n_simulations: int = Field(100000, ge=10000, le=1000000)


class PortfolioMetricsResponse(BaseModel):
    """Response with portfolio-level metrics"""
    total_ale: float
    expected_events_per_year: float
    weighted_average_lm: float
    top_scenario_share: float
    top_scenario_id: str
    scenario_ales: Dict[str, float]
    scenario_lefs: Dict[str, float]
    scenario_lms: Dict[str, float]


# Helper functions
def request_to_fair_inputs(req: ScenarioCalculationRequest) -> FAIRInputs:
    """Convert API request to FAIRInputs dataclass"""

    def get_percentiles(input_obj: Optional[PercentileInput]) -> tuple[float, float, float]:
        if input_obj is None:
            return 0.0, 0.0, 0.0
        return input_obj.p10, input_obj.p50, input_obj.p90

    def get_loss_percentiles(
        input_obj: Optional[LossPercentileInput],
    ) -> tuple[float, float, float, Optional[float]]:
        if input_obj is None:
            return 0.0, 0.0, 0.0, None
        return input_obj.p10, input_obj.p50, input_obj.p90, input_obj.p_zero

    # TEF
    tef_p10, tef_p50, tef_p90 = get_percentiles(req.tef.percentiles)

    # Contact frequency and prob. of action (for decomposed TEF)
    cf_p10, cf_p50, cf_p90 = get_percentiles(req.tef.contact_frequency)
    pa_p10, pa_p50, pa_p90 = get_percentiles(req.tef.prob_action)

    # Susceptibility
    susc_p10, susc_p50, susc_p90 = get_percentiles(req.susceptibility.percentiles)

    # Loss forms (primary & secondary), with optional zero-rate knobs
    prod_p10, prod_p50, prod_p90, prod_p_zero = get_loss_percentiles(req.loss_forms.productivity)
    resp_p10, resp_p50, resp_p90, resp_p_zero = get_loss_percentiles(req.loss_forms.response)
    repl_p10, repl_p50, repl_p90, repl_p_zero = get_loss_percentiles(req.loss_forms.replacement)
    fines_p10, fines_p50, fines_p90, fines_p_zero = get_loss_percentiles(req.loss_forms.fines)
    comp_p10, comp_p50, comp_p90, comp_p_zero = get_loss_percentiles(
        req.loss_forms.competitive_advantage
    )
    rep_p10, rep_p50, rep_p90, rep_p_zero = get_loss_percentiles(req.loss_forms.reputation)

    # SLEF
    slef_p10, slef_p50, slef_p90 = get_percentiles(req.slef.percentiles if req.slef else None)

    return FAIRInputs(
        # TEF
        tef_p10=tef_p10,
        tef_p50=tef_p50,
        tef_p90=tef_p90,
        tef_model=req.tef.model,
        tef_decompose=req.tef.decompose,
        contact_freq_p10=cf_p10,
        contact_freq_p50=cf_p50,
        contact_freq_p90=cf_p90,
        prob_action_p10=pa_p10,
        prob_action_p50=pa_p50,
        prob_action_p90=pa_p90,
        zero_inflation=req.tef.zero_inflation,
        p_zero=req.tef.p_zero,

        # Susceptibility
        susc_p10=susc_p10,
        susc_p50=susc_p50,
        susc_p90=susc_p90,

        # Primary losses
        productivity_p10=prod_p10,
        productivity_p50=prod_p50,
        productivity_p90=prod_p90,
        productivity_p_zero=prod_p_zero,
        response_p10=resp_p10,
        response_p50=resp_p50,
        response_p90=resp_p90,
        response_p_zero=resp_p_zero,
        replacement_p10=repl_p10,
        replacement_p50=repl_p50,
        replacement_p90=repl_p90,
        replacement_p_zero=repl_p_zero,

        # Secondary losses
        fines_p10=fines_p10,
        fines_p50=fines_p50,
        fines_p90=fines_p90,
        fines_p_zero=fines_p_zero,
        competitive_adv_p10=comp_p10,
        competitive_adv_p50=comp_p50,
        competitive_adv_p90=comp_p90,
        competitive_adv_p_zero=comp_p_zero,
        reputation_p10=rep_p10,
        reputation_p50=rep_p50,
        reputation_p90=rep_p90,
        reputation_p_zero=rep_p_zero,

        # SLEF
        slef_p10=slef_p10,
        slef_p50=slef_p50,
        slef_p90=slef_p90,

        # Metadata
        time_horizon_years=req.time_horizon_years,
        currency=req.currency,
    )


# API Endpoints
@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "service": "FAIR Risk Quantification API",
        "version": "1.0.0",
        "status": "operational",
    }


@app.post("/calculate", response_model=ScenarioCalculationResponse)
def calculate_scenario(request: ScenarioCalculationRequest):
    """
    Calculate risk for a single FAIR scenario.
    Performs Monte Carlo simulation to compute ALE, LEF, and LM distributions.
    """
    try:
        # Convert request to FAIRInputs
        inputs = request_to_fair_inputs(request)

        # Run calculation with stable seed
        calculator = FAIRCalculator(
            n_simulations=request.n_simulations,
            random_state=RISK_ENGINE_SEED,
        )
        results: FAIRResults = calculator.calculate(inputs)

        # In FAIRResults, this is the per-event loss magnitude (LM)
        return ScenarioCalculationResponse(
            scenario_id=request.scenario_id,
            ale={
                "mean": results.ale_mean,
                "p10": results.ale_p10,
                "p50": results.ale_p50,
                "p90": results.ale_p90,
                "p95": results.ale_p95,
                "p99": results.ale_p99,
            },
            lef={
                "mean": results.lef_mean,
                "p10": results.lef_p10,
                "p50": results.lef_p50,
                "p90": results.lef_p90,
            },
            lm={
                "mean": results.lm_mean,
                "p10": results.lm_p10,
                "p50": results.lm_p50,
                "p90": results.lm_p90,
            },
            loss_forms={
                "productivity": results.productivity_p50,
                "response": results.response_p50,
                "replacement": results.replacement_p50,
                "fines": results.fines_p50,
                "competitive_advantage": results.competitive_adv_p50,
                "reputation": results.reputation_p50,
            },
            metadata={
                "n_simulations": results.n_simulations,
                "time_horizon_years": results.time_horizon_years,
                "currency": results.currency,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {str(e)}")


@app.post("/sensitivity", response_model=SensitivityAnalysisResponse)
def sensitivity_analysis(request: SensitivityAnalysisRequest):
    """
    Perform sensitivity analysis on a FAIR factor.
    Varies the specified factor by ±variation_pct and calculates impact on ALE.
    """
    try:
        inputs = request_to_fair_inputs(request.scenario)

        calculator = FAIRCalculator(
            n_simulations=request.scenario.n_simulations,
            random_state=RISK_ENGINE_SEED,
        )
        sensitivity = calculator.sensitivity_analysis(
            inputs,
            request.factor,
            request.variation_pct,
        )

        return SensitivityAnalysisResponse(**sensitivity)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sensitivity analysis error: {str(e)}")


@app.post("/aggregate", response_model=AggregationResponse)
def aggregate_scenarios(request: AggregationRequest):
    """
    Aggregate multiple scenarios into portfolio-level risk.
    Supports both independent and correlated aggregation.
    """
    try:
        scenario_inputs: Dict[str, FAIRInputs] = {}
        for scenario_id, scenario_req in request.scenarios.items():
            scenario_inputs[scenario_id] = request_to_fair_inputs(scenario_req)

        aggregator = FAIRAggregator(
            n_simulations=request.n_simulations,
            random_state=RISK_ENGINE_SEED,
        )

        if request.correlation == 0:
            results = aggregator.aggregate_independent(scenario_inputs)
        else:
            results = aggregator.aggregate_with_correlation(
                scenario_inputs,
                correlation=request.correlation,
            )

        return AggregationResponse(
            total_ale={
                "mean": results.total_ale_mean,
                "p10": results.total_ale_p10,
                "p50": results.total_ale_p50,
                "p90": results.total_ale_p90,
                "p95": results.total_ale_p95,
                "p99": results.total_ale_p99,
            },
            scenario_contributions=results.scenario_contributions,
            top_scenarios=[
                {
                    "scenario_id": sid,
                    "ale_p50": ale,
                    "pct_of_total": pct,
                }
                for sid, ale, pct in results.top_scenarios
            ],
            assumed_correlation=results.assumed_correlation,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aggregation error: {str(e)}")


@app.post("/portfolio/metrics", response_model=PortfolioMetricsResponse)
def calculate_portfolio_metrics(request: PortfolioMetricsRequest):
    """
    Calculate portfolio-level metrics (sum of ALEs via linearity of expectation).

    Returns:
    - Total ALE (sum of scenario ALEs)
    - Expected events per year (sum of LEFs)
    - Weighted average LM (Σ(LEF_i × LM_i) / Σ LEF_i)
    - Top scenario share (max(ALE_i) / Σ ALE_i)
    """
    try:
        calculator = FAIRCalculator(
            n_simulations=request.n_simulations,
            random_state=RISK_ENGINE_SEED,
        )

        scenario_ales: Dict[str, float] = {}
        scenario_lefs: Dict[str, float] = {}
        scenario_lms: Dict[str, float] = {}

        for scenario_id, scenario_req in request.scenarios.items():
            inputs = request_to_fair_inputs(scenario_req)
            results: FAIRResults = calculator.calculate(inputs)

            scenario_ales[scenario_id] = results.ale_mean
            scenario_lefs[scenario_id] = results.lef_mean
            scenario_lms[scenario_id] = results.lm_mean

        # Portfolio metrics (linearity of expectation)
        total_ale = sum(scenario_ales.values())
        total_lef = sum(scenario_lefs.values())

        # Weighted average LM
        weighted_avg_lm = 0.0
        if total_lef > 0:
            weighted_avg_lm = sum(
                scenario_lefs[sid] * scenario_lms[sid]
                for sid in scenario_lefs.keys()
            ) / total_lef

        # Top scenario share
        max_ale = max(scenario_ales.values()) if scenario_ales else 0.0
        top_scenario_share = (max_ale / total_ale * 100.0) if total_ale > 0 else 0.0
        top_scenario_id = max(scenario_ales, key=scenario_ales.get) if scenario_ales else ""

        return PortfolioMetricsResponse(
            total_ale=total_ale,
            expected_events_per_year=total_lef,
            weighted_average_lm=weighted_avg_lm,
            top_scenario_share=top_scenario_share,
            top_scenario_id=top_scenario_id,
            scenario_ales=scenario_ales,
            scenario_lefs=scenario_lefs,
            scenario_lms=scenario_lms,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Portfolio metrics error: {str(e)}")


@app.post("/validate")
def validate_inputs(request: ScenarioCalculationRequest):
    """
    Validate FAIR inputs without running full calculation.
    Returns validation errors if any.
    """
    try:
        inputs = request_to_fair_inputs(request)

        # Validate TEF
        is_valid, errors = validate_percentiles(
            inputs.tef_p10,
            inputs.tef_p50,
            inputs.tef_p90,
            min_val=0,
        )
        if not is_valid:
            return {"valid": False, "errors": {"tef": errors}}

        # Validate Susceptibility
        is_valid, errors = validate_percentiles(
            inputs.susc_p10,
            inputs.susc_p50,
            inputs.susc_p90,
            min_val=0,
            max_val=100,
            is_probability=True,
        )
        if not is_valid:
            return {"valid": False, "errors": {"susceptibility": errors}}

        # Validate SLEF if secondary losses exist
        has_secondary = any(
            [
                inputs.fines_p50 > 0,
                inputs.competitive_adv_p50 > 0,
                inputs.reputation_p50 > 0,
            ]
        )

        if has_secondary:
            is_valid, errors = validate_percentiles(
                inputs.slef_p10,
                inputs.slef_p50,
                inputs.slef_p90,
                min_val=0,
                max_val=100,
                is_probability=True,
            )
            if not is_valid:
                return {"valid": False, "errors": {"slef": errors}}

        return {"valid": True, "errors": {}}

    except Exception as e:
        return {"valid": False, "errors": {"general": [str(e)]}}


# IRIS 2025 Benchmark Endpoints
@app.get("/api/benchmarks/lef")
def get_iris_lef_benchmarks(industry: Optional[str] = None, revenue: Optional[str] = None):
    """
    Get IRIS 2025 LEF (Loss Event Frequency) benchmarks

    Query Parameters:
    - industry: Industry sector (e.g., "Healthcare", "Financial Services")
    - revenue: Revenue tier (e.g., "$1B to $10B", "Less than $10M")

    Returns separate benchmarks for industry and revenue tier
    """
    try:
        result = get_lef_benchmark(industry, revenue)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching LEF benchmark: {str(e)}")


@app.get("/api/benchmarks/lm")
def get_iris_lm_benchmarks(industry: Optional[str] = None, revenue: Optional[str] = None):
    """
    Get IRIS 2025 LM (Loss Magnitude) benchmarks

    Query Parameters:
    - industry: Industry sector (e.g., "Healthcare", "Financial Services")
    - revenue: Revenue tier (e.g., "$1B to $10B", "Less than $10M")

    Returns separate benchmarks for industry and revenue tier
    """
    try:
        result = get_lm_benchmark(industry, revenue)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching LM benchmark: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)