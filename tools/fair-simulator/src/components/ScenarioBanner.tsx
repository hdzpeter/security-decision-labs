import { RiskScenario } from '../App.tsx';
import { Shield, User, Zap, Target, AlertTriangle } from 'lucide-react';

interface ScenarioBannerProps {
  scenario: RiskScenario;
  compact?: boolean;
}

export function ScenarioBanner({ scenario, compact = false }: ScenarioBannerProps) {
  const metadata = scenario.metadata || {};

  if (compact) {
    return (
      <div className="bg-slate-50 border border-slate-300 rounded-lg px-4 py-3">
        <div className="text-xs text-slate-600 mb-1">Scenario Definition</div>
        <div className="text-sm text-slate-700">
          {metadata.asset || 'Asset'} + {metadata.threatActor || 'Threat Actor'} + {metadata.attackVector || 'Attack Vector'} + {metadata.method || 'Method'} → {metadata.adverseOutcome || 'Adverse Outcome'}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-slate-50 to-slate-100 border-2 border-slate-300 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="w-5 h-5 text-slate-600" />
        <h3 className="text-slate-700">Scenario Definition</h3>
        <span className="text-xs text-slate-500">(Asset + Threat + Effect + Method)</span>
      </div>

      <div className="grid grid-cols-5 gap-4">
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Target className="w-4 h-4 text-slate-500" />
            <div className="text-xs text-slate-500">Asset</div>
          </div>
          <div className="text-sm text-slate-900">
            {metadata.asset || <span className="text-slate-400 italic">Not specified</span>}
          </div>
        </div>

        <div className="flex items-center justify-center text-slate-300">
          +
        </div>

        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <User className="w-4 h-4 text-slate-500" />
            <div className="text-xs text-slate-500">Threat Actor</div>
          </div>
          <div className="text-sm text-slate-900">
            {metadata.threatActor || <span className="text-slate-400 italic">Not specified</span>}
          </div>
        </div>

        <div className="flex items-center justify-center text-slate-300">
          +
        </div>

        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Zap className="w-4 h-4 text-slate-500" />
            <div className="text-xs text-slate-500">Attack Vector / Method</div>
          </div>
          <div className="text-sm text-slate-900">
            {metadata.attackVector || metadata.method || <span className="text-slate-400 italic">Not specified</span>}
          </div>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-slate-300 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-slate-600 mt-0.5 flex-shrink-0" />
        <div>
          <div className="text-xs text-slate-600 mb-1">Adverse Outcome</div>
          <div className="text-sm text-slate-700">
            {metadata.adverseOutcome || <span className="text-slate-400 italic">Not specified</span>}
          </div>
        </div>
      </div>
    </div>
  );
}