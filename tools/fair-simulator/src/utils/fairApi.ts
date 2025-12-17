/**
 * FAIR API Client
 * Connects React frontend to Python FastAPI risk_service
 */

const API_BASE_URL: string =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export interface PercentileData {
  p10: number;
  p50: number;
  p90: number;
}

export interface BenchmarkData {
  factor: string;
  p10?: number;
  p50?: number;
  p90?: number;
  mean?: number;
  unit: string;
  source: string;
  source_url?: string;
  date: string;
  sample_size?: number;
  notes: string;
}

export interface ScenarioBenchmark {
  scenario_type: string;
  industry: string;
  asset_type: string;
  factors: Record<string, BenchmarkData>;
}

export interface FAIRCalculationRequest {
  scenario_id?: string;
  tef: {
    percentiles: PercentileData;
    model: 'poisson' | 'lognormal';
    decompose?: boolean;
    contact_frequency?: PercentileData;
    prob_action?: PercentileData;
    zero_inflation?: boolean;
    p_zero?: number;
  };
  susceptibility: {
    percentiles: PercentileData;
  };
  loss_forms: {
    productivity?: PercentileData;
    response?: PercentileData;
    replacement?: PercentileData;
    fines?: PercentileData;
    competitive_advantage?: PercentileData;
    reputation?: PercentileData;
  };
  slef?: {
    percentiles: PercentileData;
  };
  time_horizon_years?: number;
  currency?: string;
  n_simulations?: number;
}

export interface FAIRCalculationResponse {
  scenario_id?: string;
  ale: {
    mean: number;
    p10: number;
    p50: number;
    p90: number;
    p95: number;
    p99: number;
  };
  lef: {
    mean: number;
    p10: number;
    p50: number;
    p90: number;
  };
  lm?: {
    mean: number;
    p10: number;
    p50: number;
    p90: number;
  };
  loss_forms: {
    productivity: number;
    response: number;
    replacement: number;
    fines: number;
    competitive_advantage: number;
    reputation: number;
  };
  metadata: {
    n_simulations: number;
    time_horizon_years: number;
    currency: string;
  };
}

export interface SensitivityAnalysisRequest {
  scenario: FAIRCalculationRequest;
  factor: string;
  variation_pct?: number;
}

export interface SensitivityAnalysisResponse {
  factor: string;
  baseline_ale: number;
  ale_down: number;
  ale_up: number;
  elasticity_down: number;
  elasticity_up: number;
  average_elasticity: number;
}

export interface PortfolioMetricsResponse {
  total_ale: number;
  expected_events_per_year: number;
  weighted_average_lm: number;
  top_scenario_share: number;
  top_scenario_id: string;
  scenario_ales: Record<string, number>;
  scenario_lefs: Record<string, number>;
  scenario_lms: Record<string, number>;
}

// IRIS 2025 LEF benchmarks (probability of an annual loss event)
export interface IrisLefDimensionBenchmark {
  probability?: number | null;
  range?: [number, number];
  confidence?: string;
  source?: string;
  description?: string;
  note?: string;
  trend?: string;
}

export interface IrisLefBenchmarkResponse {
  industry?: IrisLefDimensionBenchmark | null;
  revenue?: IrisLefDimensionBenchmark | null;
  overall_baseline: {
    probability: number;
    source: string;
  };
}

// IRIS 2025 LM benchmarks (loss magnitude)
export interface IrisLmDimensionBenchmark {
  median?: number;
  p95?: number;
  source?: string;
}

export interface IrisLmBenchmarkResponse {
  industry?: IrisLmDimensionBenchmark | null;
  revenue?: IrisLmDimensionBenchmark | null;
  overall_baseline: {
    geometric_mean?: number;
    median?: number;
    p95?: number;
    source?: string;
  };
}

class FAIRApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Check if risk_service is available
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/`);
      const data = await response.json();
      return data.status === 'operational';
    } catch {
      // Silently return false - risk_service not available
      return false;
    }
  }

  /**
   * Calculate FAIR risk for a scenario
   */
  async calculate(request: FAIRCalculationRequest): Promise<FAIRCalculationResponse> {
    const response = await fetch(`${this.baseUrl}/calculate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Calculation failed');
    }

    return response.json();
  }

  /**
   * Perform sensitivity analysis
   */
  async sensitivityAnalysis(
    request: SensitivityAnalysisRequest
  ): Promise<SensitivityAnalysisResponse> {
    const response = await fetch(`${this.baseUrl}/sensitivity`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Sensitivity analysis failed');
    }

    return response.json();
  }

  /**
   * Get benchmark data for industry and scenario type
   */
  async getBenchmark(
    industry: string,
    scenarioType: string
  ): Promise<ScenarioBenchmark | null> {
    try {
      const response = await fetch(
        `${this.baseUrl}/benchmarks/${encodeURIComponent(
          industry
        )}/${encodeURIComponent(scenarioType)}`
      );

      if (!response.ok) {
        return null;
      }

      return response.json();
    } catch {
      // Silently return null - risk_service not available
      return null;
    }
  }

  /**
   * Get all available benchmarks
   */
  async getAllBenchmarks(): Promise<Record<string, Record<string, ScenarioBenchmark>>> {
    try {
      const response = await fetch(`${this.baseUrl}/benchmarks`);

      if (!response.ok) {
        return {};
      }

      return response.json();
    } catch {
      // Silently return empty object - risk_service not available
      return {};
    }
  }

  /**
   * List available industries
   */
  async listIndustries(): Promise<string[]> {
    try {
      const response = await fetch(`${this.baseUrl}/benchmarks/industries`);

      if (!response.ok) {
        return [];
      }

      return response.json();
    } catch {
      // Silently return empty array - risk_service not available
      return [];
    }
  }

  /**
   * Validate FAIR inputs
   */
  async validate(
    request: FAIRCalculationRequest
  ): Promise<{ valid: boolean; errors: Record<string, string[]> }> {
    const response = await fetch(`${this.baseUrl}/validate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    return response.json();
  }

  /**
   * Calculate portfolio-level metrics
   */
  async portfolioMetrics(
    scenarios: Record<string, FAIRCalculationRequest>
  ): Promise<PortfolioMetricsResponse> {
    const response = await fetch(`${this.baseUrl}/portfolio/metrics`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        },
      body: JSON.stringify({ scenarios }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Portfolio metrics calculation failed');
    }

    return response.json();
  }

  /**
   * IRIS 2025 LM benchmarks (loss magnitude) by industry/revenue tier
   */
  async getIrisLMBenchmarks(
    industry?: string,
    revenue?: string
  ): Promise<IrisLmBenchmarkResponse | null> {
    try {
      const params = new URLSearchParams();
      if (industry) params.append('industry', industry);
      if (revenue) params.append('revenue', revenue);

      const response = await fetch(
        `${this.baseUrl}/api/benchmarks/lm?${params.toString()}`
      );

      if (!response.ok) {
        return null;
      }

      return response.json();
    } catch {
      // Backend offline or network error
      return null;
    }
  }

  /**
   * IRIS 2025 LEF benchmarks (annual probability) by industry/revenue tier
   */
  async getIrisLEFBenchmarks(
    industry?: string,
    revenue?: string
  ): Promise<IrisLefBenchmarkResponse | null> {
    try {
      const params = new URLSearchParams();
      if (industry) params.append('industry', industry);
      if (revenue) params.append('revenue', revenue);

      const response = await fetch(
        `${this.baseUrl}/api/benchmarks/lef?${params.toString()}`
      );

      if (!response.ok) {
        return null;
      }

      return response.json();
    } catch {
      // Backend offline or network error
      return null;
    }
  }
}

// Export singleton instance
export const fairApi = new FAIRApiClient();

// Export class for custom instances
export default FAIRApiClient;