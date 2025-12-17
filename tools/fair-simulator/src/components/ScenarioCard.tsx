import { RiskScenario } from '../App.tsx';

interface ScenarioCardProps {
  scenario: RiskScenario;
  ale: number;
  slee: number;
  lef: number;
  onClick?: () => void;
}

export function ScenarioCard({ scenario, ale, slee, lef, onClick }: ScenarioCardProps) {
  return (
    <div 
      className="bg-white border border-slate-200 rounded-xl p-6 hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer"
      onClick={onClick}
    >
      <div className="mb-4">
        <h3 className="text-lg text-slate-900 mb-1">{scenario.name}</h3>
        <p className="text-sm text-slate-500">{scenario.description}</p>
      </div>

      <div className="space-y-2 mb-4 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Industry</span>
          <span className="text-slate-700">{scenario.industry}</span>
        </div>
        {scenario.controls.length > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Controls</span>
            <span className="text-slate-700">{scenario.controls.length} applied</span>
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 pt-4 space-y-3">
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <div className="text-slate-500 mb-1">LEF</div>
            <div className="text-slate-900">{lef.toFixed(2)}/yr</div>
          </div>
          <div>
            <div className="text-slate-500 mb-1">LM</div>
            <div className="text-slate-900">${(slee / 1000).toFixed(0)}K</div>
          </div>
          <div>
            <div className="text-slate-500 mb-1">Susceptibility</div>
            <div className="text-slate-900">{scenario.susceptibility.toFixed(0)}%</div>
          </div>
        </div>
        
        <div className="flex justify-between items-baseline pt-3 border-t border-slate-200">
          <span className="text-sm text-slate-500">ALE</span>
          <span className="text-xl text-slate-900">${(ale / 1000).toFixed(0)}K</span>
        </div>
      </div>
    </div>
  );
}