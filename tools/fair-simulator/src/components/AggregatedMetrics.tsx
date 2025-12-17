import { RiskScenario } from '../App.tsx';
import { DollarSign, Target, TrendingUp, AlertCircle, Info, Copy, AlertTriangle } from 'lucide-react';
import { useState } from 'react';

interface AggregatedMetricsProps {
  scenarios: RiskScenario[];
  portfolioMetrics: {
    total_ale: number;
    expected_events_per_year: number;
    weighted_average_lm: number;
    top_scenario_share: number;
    top_scenario_id: string;
  };
}

export function AggregatedMetrics({ scenarios, portfolioMetrics }: AggregatedMetricsProps) {
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [copied, setCopied] = useState(false);

  const topScenario = scenarios.find(s => s.id === portfolioMetrics.top_scenario_id);

  // Check for edge cases
  const zeroLEF = portfolioMetrics.expected_events_per_year === 0;
  const highConcentration = portfolioMetrics.top_scenario_share > 70;

  const copyFormulas = () => {
    const formulas = `
Portfolio Metrics (USD 2025)
─────────────────────────────
Total ALE: $${(portfolioMetrics.total_ale / 1000000).toFixed(2)}M
  Formula: Σ ALE_i = ${scenarios.map(s => `ALE_${s.id}`).join(' + ')}
  
Expected Events/Year: ${portfolioMetrics.expected_events_per_year.toFixed(2)} events/yr
  Formula: Σ LEF_i = ${scenarios.map(s => `LEF_${s.id}`).join(' + ')}
  
Average LM (per event): $${(portfolioMetrics.weighted_average_lm / 1000).toFixed(0)}K
  Formula: Σ(LEF_i × LM_i) / Σ LEF_i
  
Top Scenario Share: ${portfolioMetrics.top_scenario_share.toFixed(1)}%
  Formula: max(ALE_i) / Σ ALE_i
  Top Scenario: ${topScenario?.name || 'N/A'}

Math: Linearity of expectation (no independence assumption required)
`.trim();

    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(formulas)
        .then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => {
          // Fallback: create temp textarea
          fallbackCopy(formulas);
        });
    } else {
      // Fallback for older browsers or blocked clipboard
      fallbackCopy(formulas);
    }
  };

  const fallbackCopy = (text: string) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
      document.execCommand('copy');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
      // Show the text in a modal or alert as last resort
      alert('Copy to clipboard blocked. Here are the formulas:\n\n' + text);
    } finally {
      document.body.removeChild(textarea);
    }
  };
  
  const metrics = [
    {
      label: 'Total Annual Loss Exposure (mean)',
      value: `$${(portfolioMetrics.total_ale / 1000000).toFixed(2)}M`,
      icon: DollarSign,
      color: 'text-teal-600',
      bg: 'bg-teal-50',
      formula: 'Σ ALE_i',
      explanation: 'Total expected annual loss = sum of scenario expected losses. Exact for means; independence not required.',
    },
    {
      label: 'Expected Events per Year',
      value: zeroLEF ? 'N/A' : portfolioMetrics.expected_events_per_year.toFixed(2),
      icon: Target,
      color: 'text-green-600',
      bg: 'bg-green-50',
      formula: 'Σ LEF_i',
      explanation: 'Total expected loss events across all scenarios.',
      subtitle: zeroLEF ? 'No expected events' : 'events/yr',
    },
    {
      label: 'Average Loss Magnitude',
      value: zeroLEF ? 'N/A' : `$${(portfolioMetrics.weighted_average_lm / 1000).toFixed(0)}K`,
      icon: TrendingUp,
      color: 'text-indigo-600',
      bg: 'bg-indigo-50',
      formula: zeroLEF ? 'undefined' : 'Σ(LEF_i × LM_i) / Σ LEF_i',
      explanation: zeroLEF 
        ? 'No expected events—frequency-weighted average undefined.'
        : 'Frequency-weighted average loss magnitude per event (USD 2025). More useful than simple average.',
      subtitle: zeroLEF ? '' : 'per event, USD 2025',
    },
    {
      label: 'Top Scenario Share of Total',
      value: `${portfolioMetrics.top_scenario_share.toFixed(0)}%`,
      icon: highConcentration ? AlertTriangle : AlertCircle,
      color: highConcentration ? 'text-red-600' : 'text-orange-600',
      bg: highConcentration ? 'bg-red-50' : 'bg-orange-50',
      subtitle: topScenario?.name || 'N/A',
      formula: 'max(ALE_i) / Σ ALE_i',
      explanation: 'Concentration risk: what % of total ALE comes from your biggest scenario?',
    },
  ];

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((metric, index) => (
          <div key={index} className="bg-white border border-slate-200 rounded-lg p-6 group relative">
            <div className="flex items-center justify-between mb-3">
              <div className={`w-10 h-10 rounded-lg ${metric.bg} flex items-center justify-center`}>
                <metric.icon className={`w-5 h-5 ${metric.color}`} />
              </div>
              <button 
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-slate-100 rounded"
                title={metric.explanation}
              >
                <Info className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="text-sm text-slate-600 mb-1">{metric.label}</div>
            <div className="text-2xl text-slate-900 mb-1 truncate" title={metric.value}>
              {metric.value}
            </div>
            {metric.subtitle && (
              <div className="text-xs text-slate-500 truncate" title={metric.subtitle}>
                {metric.subtitle}
              </div>
            )}
            <div className="inline-flex items-center gap-1 bg-slate-100 text-slate-600 text-xs px-2 py-0.5 rounded mt-2">
              <span className="opacity-60">fx</span>
              <span className="font-mono">{metric.formula}</span>
            </div>
          </div>
        ))}
      </div>

      {/* High Concentration Warning */}
      {highConcentration && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm text-red-900 mb-1">Risk Concentration Warning</div>
            <div className="text-sm text-red-700">
              {'>'}70% of portfolio ALE comes from one scenario (<strong>{topScenario?.name}</strong>). 
              Consider diversifying controls or breaking down into sub-scenarios.
            </div>
          </div>
        </div>
      )}

      {/* Important Assumptions Banner */}
      <div className="bg-amber-50/50 border border-amber-200/60 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <div className="bg-amber-100 text-amber-800 text-xs px-2 py-1 rounded mt-0.5">
            IMPORTANT
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-sm text-amber-900">Portfolio Sum Assumptions</h3>
              <button
                onClick={() => setShowAssumptions(!showAssumptions)}
                className="text-xs text-amber-600 hover:text-amber-800 underline"
              >
                {showAssumptions ? 'Hide assumptions' : 'Show assumptions'}
              </button>
              <button
                onClick={copyFormulas}
                className="ml-auto text-xs text-amber-600 hover:text-amber-800 flex items-center gap-1"
                title="Copy formulas & values"
              >
                <Copy className="w-3 h-3" />
                {copied ? 'Copied!' : 'Copy formulas'}
              </button>
            </div>
            <p className="text-sm text-amber-700">
              <strong>How we add things up:</strong> We add the expected loss from each scenario to get the portfolio&apos;s total expected annual loss. 
              This is mathematically exact for means (linearity of expectation); correlation only matters for percentiles/tails, not for the mean.
            </p>
            
            {showAssumptions && (
              <ul className="mt-3 space-y-1.5 text-xs text-amber-600 border-t border-amber-200/60 pt-3 list-disc list-inside">
                <li>
                  <strong className="text-amber-800">Means add:</strong> Total ALE = Σ ALE<sub>i</sub> (exact; independence not required).
                </li>
                <li>
                  <strong className="text-amber-800">Percentiles don&apos;t add:</strong> Portfolio P50/P90 come from Monte Carlo on the sum of scenarios.
                </li>
                <li>
                  <strong className="text-amber-800">Avoid double-counting:</strong> Make scenarios outcome-distinct. 
                  Example: If &quot;Ransomware&quot; includes SLEF-gated privacy costs when exfiltration occurs, don&apos;t model a separate 
                  &quot;Data Breach&quot; scenario for the same event.
                </li>
                <li>
                  <strong className="text-amber-800">Consistent units:</strong> Same currency (USD, 2025) and time basis (per year).
                </li>
                <li>
                  <strong className="text-amber-800">Scope:</strong> Portfolio reflects only the scenarios modeled here.
                </li>
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}