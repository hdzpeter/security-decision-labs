import { useState, useEffect } from 'react';
import { RiskScenario } from '../App.tsx';
import { ScenarioList } from './ScenarioList.tsx';
import { ScenarioDetail } from './ScenarioDetail.tsx';
import { AggregatedMetrics } from './AggregatedMetrics.tsx';
import { ScenarioCard } from './ScenarioCard.tsx';
import { fairApi } from '@/utils/fairApi.ts';
import { scenarioToCalculationRequest, calculateClientSide } from '@/hooks/useFairCalculation.ts';
import { Loader2 } from 'lucide-react';

interface DashboardProps {
  scenarios: RiskScenario[];
  onUpdateScenario?: (scenario: RiskScenario) => void;
  onDeleteScenario?: (scenarioId: string) => void;
}

interface ScenarioCalculations {
  ale: number;
  lef: number;
  slee: number;
}

export function Dashboard({ scenarios, onUpdateScenario, onDeleteScenario }: DashboardProps) {
  const [selectedScenario, setSelectedScenario] = useState<RiskScenario | null>(null);
  const [calculations, setCalculations] = useState<Record<string, ScenarioCalculations>>({});
  const [portfolioMetrics, setPortfolioMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Calculate metrics (try risk_service first, silently fall back to client-side)
  useEffect(() => {
    async function calculateMetrics() {
      setLoading(true);
      
      try {
        // Try risk_service first
        const scenarioRequests: Record<string, any> = {};
        scenarios.forEach(scenario => {
          scenarioRequests[scenario.id] = scenarioToCalculationRequest(scenario);
        });

        const portfolioData = await fairApi.portfolioMetrics(scenarioRequests);
        setPortfolioMetrics(portfolioData);

        // Store individual calculations
        const calc: Record<string, ScenarioCalculations> = {};
        scenarios.forEach(scenario => {
          calc[scenario.id] = {
            ale: portfolioData.scenario_ales[scenario.id],
            lef: portfolioData.scenario_lefs[scenario.id],
            slee: portfolioData.scenario_lms[scenario.id],
          };
        });
        setCalculations(calc);
      } catch (err) {
        // Silently fall back to client-side calculations
        console.log('Using client-side calculations (risk_service unavailable)');
        calculateClientSideMetrics();
      }

      setLoading(false);
    }

    function calculateClientSideMetrics() {
      const calc: Record<string, ScenarioCalculations> = {};
      scenarios.forEach(scenario => {
        const result = calculateClientSide(scenario);
        calc[scenario.id] = {
          ale: result.ale,
          lef: result.lef,
          slee: result.slee,
        };
      });
      setCalculations(calc);

      // Calculate portfolio metrics client-side
      const totalALE = Object.values(calc).reduce((sum, c) => sum + c.ale, 0);
      const totalLEF = Object.values(calc).reduce((sum, c) => sum + c.lef, 0);
      
      const weightedAvgLM = totalLEF > 0
        ? Object.values(calc).reduce((sum, c) => sum + (c.lef * c.slee), 0) / totalLEF
        : 0;

      const ales = scenarios.map(s => calc[s.id]?.ale || 0);
      const maxALE = Math.max(...ales);
      const maxIndex = ales.indexOf(maxALE);
      const topScenarioShare = totalALE > 0 ? (maxALE / totalALE) * 100 : 0;
      const topScenarioId = scenarios[maxIndex]?.id || '';

      setPortfolioMetrics({
        total_ale: totalALE,
        expected_events_per_year: totalLEF,
        weighted_average_lm: weightedAvgLM,
        top_scenario_share: topScenarioShare,
        top_scenario_id: topScenarioId,
        scenario_ales: Object.fromEntries(scenarios.map(s => [s.id, calc[s.id]?.ale || 0])),
        scenario_lefs: Object.fromEntries(scenarios.map(s => [s.id, calc[s.id]?.lef || 0])),
        scenario_lms: Object.fromEntries(scenarios.map(s => [s.id, calc[s.id]?.slee || 0])),
      });
    }

    if (scenarios.length > 0) {
      calculateMetrics();
    } else {
      setLoading(false);
    }
  }, [scenarios]);

  if (scenarios.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <h3 className="text-lg text-slate-900 mb-2">No Risk Scenarios</h3>
        <p className="text-slate-600 mb-6">Create your first risk scenario to start quantifying cyber risk</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
        <span className="ml-3 text-slate-600">Calculating portfolio metrics...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Metrics */}
      {portfolioMetrics && (
        <AggregatedMetrics 
          scenarios={scenarios} 
          portfolioMetrics={portfolioMetrics}
        />
      )}

      {/* Scenario Risk Exposure with Industry Benchmarks */}
      <ScenarioList scenarios={scenarios} onSelectScenario={setSelectedScenario} />

      {/* Individual Scenarios */}
      <div>
        <h2 className="text-lg text-slate-900 mb-4">Risk Scenarios</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {scenarios.map((scenario) => (
            <ScenarioCard 
              key={scenario.id} 
              scenario={scenario} 
              ale={calculations[scenario.id]?.ale || 0}
              slee={calculations[scenario.id]?.slee || 0}
              lef={calculations[scenario.id]?.lef || 0}
              onClick={() => setSelectedScenario(scenario)}
            />
          ))}
        </div>
      </div>

      {/* Scenario Detail Modal */}
      {selectedScenario && (
        <ScenarioDetail 
          scenario={selectedScenario} 
          onClose={() => setSelectedScenario(null)} 
          onUpdate={onUpdateScenario}
          onDelete={onDeleteScenario}
        />
      )}
    </div>
  );
}
