/**
 * React Hook for FAIR Calculations
 * Provides methods to calculate FAIR metrics using the risk_service API
 */

import { useState, useCallback } from 'react';
import { fairApi, type FAIRCalculationRequest, type FAIRCalculationResponse } from '@/utils/fairApi.ts';
import { RiskScenario } from '../App.tsx';

interface CalculationState {
  loading: boolean;
  error: string | null;
  result: FAIRCalculationResponse | null;
}

/**
 * Convert RiskScenario to FAIRCalculationRequest
 */
export function scenarioToCalculationRequest(scenario: Partial<RiskScenario>, useRanges: boolean = false): FAIRCalculationRequest {
  // If using range-based data (P10/P50/P90)
  if (useRanges) {
    return {
      tef: {
        percentiles: {
          p10: (scenario as any).tefP10 || scenario.threatEventFrequency! * 0.5,
          p50: (scenario as any).tefP50 || scenario.threatEventFrequency!,
          p90: (scenario as any).tefP90 || scenario.threatEventFrequency! * 2,
        },
        model: (scenario as any).tefModel || 'poisson',
        decompose: (scenario as any).tefDecompose || false,
        zero_inflation: (scenario as any).zeroInflation || false,
        p_zero: (scenario as any).pZero || 0,
      },
      susceptibility: {
        percentiles: {
          p10: (scenario as any).susceptibilityP10 || scenario.susceptibility! * 0.5,
          p50: (scenario as any).susceptibilityP50 || scenario.susceptibility!,
          p90: (scenario as any).susceptibilityP90 || Math.min(100, scenario.susceptibility! * 1.5),
        },
      },
      loss_forms: {
        productivity: scenario.productivity ? {
          p10: (scenario as any).productivityP10 || scenario.productivity * 0.5,
          p50: (scenario as any).productivityP50 || scenario.productivity,
          p90: (scenario as any).productivityP90 || scenario.productivity * 2,
        } : undefined,
        response: scenario.response ? {
          p10: (scenario as any).responseP10 || scenario.response * 0.5,
          p50: (scenario as any).responseP50 || scenario.response,
          p90: (scenario as any).responseP90 || scenario.response * 2,
        } : undefined,
        replacement: scenario.replacement ? {
          p10: (scenario as any).replacementP10 || scenario.replacement * 0.5,
          p50: (scenario as any).replacementP50 || scenario.replacement,
          p90: (scenario as any).replacementP90 || scenario.replacement * 2,
        } : undefined,
        fines: scenario.fines ? {
          p10: (scenario as any).finesP10 || scenario.fines * 0.5,
          p50: (scenario as any).finesP50 || scenario.fines,
          p90: (scenario as any).finesP90 || scenario.fines * 3,
        } : undefined,
        competitive_advantage: scenario.competitiveAdvantage ? {
          p10: (scenario as any).competitiveAdvantageP10 || scenario.competitiveAdvantage * 0.5,
          p50: (scenario as any).competitiveAdvantageP50 || scenario.competitiveAdvantage,
          p90: (scenario as any).competitiveAdvantageP90 || scenario.competitiveAdvantage * 3,
        } : undefined,
        reputation: scenario.reputation ? {
          p10: (scenario as any).reputationP10 || scenario.reputation * 0.5,
          p50: (scenario as any).reputationP50 || scenario.reputation,
          p90: (scenario as any).reputationP90 || scenario.reputation * 3,
        } : undefined,
      },
      slef: scenario.slef ? {
        percentiles: {
          p10: (scenario as any).slefP10 || scenario.slef * 0.5,
          p50: (scenario as any).slefP50 || scenario.slef,
          p90: (scenario as any).slefP90 || Math.min(100, scenario.slef * 1.5),
        },
      } : undefined,
      time_horizon_years: 1.0,
      currency: 'USD',
      n_simulations: 100000,
    };
  }

  // Fallback: create ranges from point estimates (for backward compatibility)
  return {
    tef: {
      percentiles: {
        p10: scenario.threatEventFrequency! * 0.5,
        p50: scenario.threatEventFrequency!,
        p90: scenario.threatEventFrequency! * 2,
      },
      model: 'poisson',
    },
    susceptibility: {
      percentiles: {
        p10: scenario.susceptibility! * 0.7,
        p50: scenario.susceptibility!,
        p90: Math.min(100, scenario.susceptibility! * 1.3),
      },
    },
    loss_forms: {
      productivity: scenario.productivity ? {
        p10: scenario.productivity * 0.6,
        p50: scenario.productivity,
        p90: scenario.productivity * 2.5,
      } : undefined,
      response: scenario.response ? {
        p10: scenario.response * 0.6,
        p50: scenario.response,
        p90: scenario.response * 2.5,
      } : undefined,
      replacement: scenario.replacement ? {
        p10: scenario.replacement * 0.6,
        p50: scenario.replacement,
        p90: scenario.replacement * 2.5,
      } : undefined,
      fines: scenario.fines ? {
        p10: scenario.fines * 0.4,
        p50: scenario.fines,
        p90: scenario.fines * 4,
      } : undefined,
      competitive_advantage: scenario.competitiveAdvantage ? {
        p10: scenario.competitiveAdvantage * 0.4,
        p50: scenario.competitiveAdvantage,
        p90: scenario.competitiveAdvantage * 4,
      } : undefined,
      reputation: scenario.reputation ? {
        p10: scenario.reputation * 0.4,
        p50: scenario.reputation,
        p90: scenario.reputation * 4,
      } : undefined,
    },
    slef: scenario.slef ? {
      percentiles: {
        p10: scenario.slef * 0.7,
        p50: scenario.slef,
        p90: Math.min(100, scenario.slef * 1.3),
      },
    } : undefined,
    time_horizon_years: 1.0,
    currency: 'USD',
    n_simulations: 100000,
  };
}

/**
 * Hook for FAIR calculations
 */
export function useFairCalculation() {
  const [state, setState] = useState<CalculationState>({
    loading: false,
    error: null,
    result: null,
  });

  const calculate = useCallback(async (scenario: Partial<RiskScenario>, useRanges: boolean = false) => {
    setState({ loading: true, error: null, result: null });

    try {
      const request = scenarioToCalculationRequest(scenario, useRanges);
      const result = await fairApi.calculate(request);
      
      setState({ loading: false, error: null, result });
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Calculation failed';
      setState({ loading: false, error: errorMessage, result: null });
      throw error;
    }
  }, []);

  const reset = useCallback(() => {
    setState({ loading: false, error: null, result: null });
  }, []);

  return {
    calculate,
    reset,
    loading: state.loading,
    error: state.error,
    result: state.result,
  };
}

/**
 * Client-side fallback calculations (when risk_service is unavailable)
 */
export function calculateClientSide(scenario: RiskScenario) {
  const lef = scenario.threatEventFrequency * (scenario.susceptibility / 100);
  
  const primaryLoss = scenario.productivity + scenario.response + scenario.replacement;
  const secondaryLoss = scenario.fines + scenario.competitiveAdvantage + scenario.reputation;
  const slee = primaryLoss + (secondaryLoss * (scenario.slef / 100));
  
  const ale = lef * slee;

  return {
    lef,
    slee,
    ale,
    // Approximate percentiles (client-side doesn't have Monte Carlo)
    ale_p10: ale * 0.3,
    ale_p50: ale,
    ale_p90: ale * 2.5,
    ale_p95: ale * 3.5,
    ale_p99: ale * 5.0,
  };
}
