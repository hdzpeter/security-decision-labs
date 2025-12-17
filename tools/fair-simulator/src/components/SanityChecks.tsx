import { RiskScenario } from '../App.tsx';
import { AlertTriangle } from 'lucide-react';

interface SanityChecksProps {
  scenario: RiskScenario;
}

export function SanityChecks({ scenario }: SanityChecksProps) {
  const checks: Array<{ warning: string; condition: boolean }> = [];

  // Check if SLEF > 0 but all secondary forms are $0
  const secondaryTotal = scenario.fines + scenario.competitiveAdvantage + scenario.reputation;
  if (scenario.slef > 0 && secondaryTotal === 0) {
    checks.push({
      warning: 'SLEF is gated on but all secondary loss amounts are zero—is this intended?',
      condition: true,
    });
  }

  // Check if TEF × Susceptibility is very low
  const lef = scenario.threatEventFrequency * (scenario.susceptibility / 100);
  if (lef < 0.1) {
    checks.push({
      warning: `Low-frequency scenario (LEF = ${lef.toFixed(3)}/yr). Monte Carlo sampling may be sparse in the tail.`,
      condition: true,
    });
  }

  // Check if any primary loss + any secondary loss but SLEF = 0
  const primaryTotal = scenario.productivity + scenario.response + scenario.replacement;
  if (primaryTotal > 0 && secondaryTotal > 0 && scenario.slef === 0) {
    checks.push({
      warning: 'You have secondary loss values but SLEF is 0%—secondary losses will never occur.',
      condition: true,
    });
  }

  // Check if susceptibility is 100% (unrealistic in most cases)
  if (scenario.susceptibility === 100) {
    checks.push({
      warning: 'Susceptibility is 100%—this means you have zero defensive capability. Is this realistic?',
      condition: true,
    });
  }

  // Check if TEF is 0
  if (scenario.threatEventFrequency === 0) {
    checks.push({
      warning: 'Threat Event Frequency (TEF) is 0—no loss events will occur. Consider estimating a non-zero TEF.',
      condition: true,
    });
  }

  const activeChecks = checks.filter(c => c.condition);

  if (activeChecks.length === 0) {
    return null;
  }

  return (
    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="text-yellow-900 mb-2">Sanity Checks</h3>
          <ul className="space-y-2">
            {activeChecks.map((check, idx) => (
              <li key={idx} className="text-sm text-yellow-800">
                • {check.warning}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
