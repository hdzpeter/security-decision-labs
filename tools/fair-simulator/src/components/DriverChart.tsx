import { RiskScenario } from '../App.tsx';
import { TrendingUp, Info } from 'lucide-react';
import { useState } from 'react';

interface DriverChartProps {
  scenario: RiskScenario;
  ale: number;
}

export function DriverChart({ scenario, ale }: DriverChartProps) {
  const calculatePrimaryLoss = () => 
    scenario.productivity + scenario.response + scenario.replacement;
  
  const calculateSecondaryLoss = () => 
    scenario.fines + scenario.competitiveAdvantage + scenario.reputation;

  // @ts-ignore
    const lef = scenario.threatEventFrequency * (scenario.susceptibility / 100);
  const primaryLoss = calculatePrimaryLoss();
  const secondaryLoss = calculateSecondaryLoss();
  const slefProbability = scenario.slef / 100;
  const expectedSecondaryLoss = secondaryLoss * slefProbability;
  const totalLM = primaryLoss + expectedSecondaryLoss;

  // Calculate contribution to ALE
  const drivers = [
    { 
      name: 'Productivity Loss', 
      value: scenario.productivity,
      contribution: (scenario.productivity / totalLM) * ale,
      type: 'primary' as const
    },
    { 
      name: 'Response Costs', 
      value: scenario.response,
      contribution: (scenario.response / totalLM) * ale,
      type: 'primary' as const
    },
    { 
      name: 'Replacement Costs', 
      value: scenario.replacement,
      contribution: (scenario.replacement / totalLM) * ale,
      type: 'primary' as const
    },
    { 
      name: 'Fines & Judgments', 
      value: scenario.fines * slefProbability,
      contribution: (scenario.fines * slefProbability / totalLM) * ale,
      type: 'secondary' as const
    },
    { 
      name: 'Competitive Advantage', 
      value: scenario.competitiveAdvantage * slefProbability,
      contribution: (scenario.competitiveAdvantage * slefProbability / totalLM) * ale,
      type: 'secondary' as const
    },
    { 
      name: 'Reputation Damage', 
      value: scenario.reputation * slefProbability,
      contribution: (scenario.reputation * slefProbability / totalLM) * ale,
      type: 'secondary' as const
    },
  ].filter(d => d.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution);

  const maxContribution = Math.max(...drivers.map(d => d.contribution));

  const [showInfo, setShowInfo] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-600" />
          <div>
            <h3 className="text-slate-900">What Drives the Risk?</h3>
            <p className="text-sm text-slate-500">Contribution to Annual Loss Exposure (ALE)</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">
            Method: ALE share at baseline (expected-value decomposition)
          </span>
          <button 
            onClick={() => setShowInfo(!showInfo)}
            className="p-1 hover:bg-slate-100 rounded"
            title="Show method details"
          >
            <Info className="w-4 h-4 text-slate-500" />
          </button>
        </div>
      </div>

      {showInfo && (
        <div className="mb-4 p-3 bg-slate-50 rounded-lg text-sm text-slate-600 border border-slate-200">
          <p className="mb-2">
            <strong>Method:</strong> Each bar = LEF × expected form amount ÷ total ALE at baseline.
          </p>
          <p>
            This shows expected-value decomposition at the point estimate. 
            One-at-a-time sensitivity is not shown here (see Sensitivity Analysis).
          </p>
        </div>
      )}

      <div className="space-y-4">
        {drivers.map((driver, idx) => {
          const percentage = (driver.contribution / ale) * 100;
          const barWidth = (driver.contribution / maxContribution) * 100;

          return (
            <div key={idx}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-700">{driver.name}</span>
                  <span 
                    className="px-1.5 py-0.5 text-xs rounded text-white"
                    style={{ backgroundColor: driver.type === 'primary' ? '#0EABA9' : '#5944C6' }}
                  >
                    {driver.type === 'primary' ? 'Primary' : 'Secondary'}
                  </span>
                </div>
                <div className="text-sm text-slate-900 font-mono">
                  ${(driver.contribution / 1000).toFixed(0)}K ({percentage.toFixed(1)}%)
                </div>
              </div>
              <div className="h-8 bg-slate-100 rounded-lg overflow-hidden">
                <div 
                  className="h-full flex items-center justify-end px-3 text-xs transition-all"
                  style={{ 
                    width: `${barWidth}%`,
                    background: driver.type === 'primary' 
                      ? 'linear-gradient(to right, #0EABA980, #0EABA9B3)' 
                      : 'linear-gradient(to right, #5944C680, #5944C6B3)',
                    color: driver.type === 'primary' ? '#0F766E' : '#5B21B6'
                  }}
                >
                  {barWidth > 20 && `${percentage.toFixed(0)}%`}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 pt-4 border-t border-slate-200">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-slate-500 mb-1">Primary Loss</div>
            <div className="text-slate-900">${(primaryLoss / 1000).toFixed(0)}K (evaluated every event; may be $0)</div>
          </div>
          <div>
            <div className="text-slate-500 mb-1">Secondary Loss</div>
            <div className="text-slate-900">
              ${(secondaryLoss / 1000).toFixed(0)}K × {(slefProbability * 100).toFixed(0)}% = ${(expectedSecondaryLoss / 1000).toFixed(0)}K
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}