import { RiskScenario } from '../App.tsx';
import { DollarSign, TrendingUp } from 'lucide-react';
import { useState } from 'react';

interface SLEFGateProps {
  scenario: RiskScenario;
  showAnimation?: boolean;
}

export function SLEFGate({ scenario, showAnimation = false }: SLEFGateProps) {
  const slefProbability = scenario.slef / 100;
  const primaryLoss = scenario.productivity + scenario.response + scenario.replacement;
  const secondaryLoss = scenario.fines + scenario.competitiveAdvantage + scenario.reputation;

  const [showHelp, setShowHelp] = useState(false);

  return (
    <div className="bg-slate-50 rounded-xl p-6">
      <div className="grid grid-cols-2 gap-8">
        {/* Primary Loss */}
        <div className="border-2 rounded-lg p-4" style={{ backgroundColor: '#0EABA906', borderColor: '#0EABA930' }}>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ backgroundColor: '#0EABA9' }}>
              <DollarSign className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="text-xs" style={{ color: '#0EABA9' }}>Primary Loss</div>
              <div className="text-sm text-slate-900">Direct, first-party loss</div>
              <div className="text-xs" style={{ color: '#0C9997' }}>(evaluated every event; may be $0)</div>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-600">Productivity</span>
              <span className="text-slate-900 font-mono">${(scenario.productivity / 1000).toFixed(0)}K</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Response</span>
              <span className="text-slate-900 font-mono">${(scenario.response / 1000).toFixed(0)}K</span>
            </div>
            <div className="text-xs text-slate-500 -mt-1 mb-1">
              <span className="opacity-75">May be primary or secondary depending on what drives the spend (internal IR vs. litigation)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Replacement</span>
              <span className="text-slate-900 font-mono">${(scenario.replacement / 1000).toFixed(0)}K</span>
            </div>
            <div className="pt-2 border-t flex justify-between" style={{ borderColor: '#0EABA930' }}>
              <span style={{ color: '#0C9997' }}>Total Primary</span>
              <span className="font-mono" style={{ color: '#0C9997' }}>${(primaryLoss / 1000).toFixed(0)}K</span>
            </div>
          </div>
        </div>

        {/* Secondary Loss */}
        <div className="border-2 rounded-lg p-4 relative" style={{ backgroundColor: '#5944C606', borderColor: '#5944C630' }}>
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all`}
              style={{ backgroundColor: slefProbability > 0.5 ? '#5944C6' : '#5944C680' }}
            >
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="text-xs" style={{ color: '#5944C6' }}>Secondary Loss</div>
              <div className="flex items-center gap-2">
                <div className="text-sm" style={{ color: '#4835B0' }}>
                  Sometimes occurs ({(slefProbability * 100).toFixed(0)}%)
                </div>
                <button 
                  onClick={() => setShowHelp(!showHelp)}
                  className="text-xs underline"
                  style={{ color: '#5944C6' }}
                >
                  Why {(slefProbability * 100).toFixed(0)}%?
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-600">Fines & Judgments</span>
              <span className="text-slate-900 font-mono">${(scenario.fines / 1000).toFixed(0)}K</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Competitive Advantage</span>
              <span className="text-slate-900 font-mono">${(scenario.competitiveAdvantage / 1000).toFixed(0)}K</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Reputation</span>
              <span className="text-slate-900 font-mono">${(scenario.reputation / 1000).toFixed(0)}K</span>
            </div>
            <div className="pt-2 border-t space-y-1" style={{ borderColor: '#5944C630' }}>
              <div className="flex justify-between" style={{ color: '#5944C6' }}>
                <span>Conditional total (if occurs)</span>
                <span className="font-mono">${(secondaryLoss / 1000).toFixed(0)}K</span>
              </div>
              <div className="flex justify-between" style={{ color: '#4835B0' }}>
                <span>Expected value</span>
                <span className="font-mono">${((secondaryLoss * slefProbability) / 1000).toFixed(0)}K</span>
              </div>
            </div>
          </div>

          {/* Gate visualization */}
          <div className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-24 rounded-l-lg flex items-center justify-center"
            style={{ backgroundColor: '#5944C680' }}
          >
            <div className="text-xs transform -rotate-90 whitespace-nowrap" style={{ color: '#4835B0' }}>
              {(slefProbability * 100).toFixed(0)}% gate
            </div>
          </div>
        </div>
      </div>

      {/* Visual representation */}
      <div className="mt-6 pt-6 border-t border-slate-200">
        <div className="text-xs text-slate-500 mb-3">Expected Loss Magnitude per Event</div>
        <div className="flex items-center gap-0">
          <div 
            className="h-8 rounded-l-lg flex items-center justify-center text-xs px-3"
            style={{ 
              width: `${(primaryLoss / (primaryLoss + secondaryLoss * slefProbability)) * 100}%`,
              background: 'linear-gradient(to right, #0EABA980, #0EABA9B3)',
              color: '#0F766E'
            }}
          >
            Primary ${(primaryLoss / 1000).toFixed(0)}K
          </div>
          <div 
            className="h-8 rounded-r-lg flex items-center justify-center text-xs px-3"
            style={{ 
              width: `${(secondaryLoss * slefProbability / (primaryLoss + secondaryLoss * slefProbability)) * 100}%`,
              background: 'linear-gradient(to right, #5944C680, #5944C6B3)',
              color: '#5B21B6'
            }}
          >
            Secondary ${((secondaryLoss * slefProbability) / 1000).toFixed(0)}K
          </div>
        </div>
        <div className="text-right mt-2 text-sm text-slate-600">
          Total LM = ${((primaryLoss + secondaryLoss * slefProbability) / 1000).toFixed(0)}K
        </div>
      </div>
    </div>
  );
}