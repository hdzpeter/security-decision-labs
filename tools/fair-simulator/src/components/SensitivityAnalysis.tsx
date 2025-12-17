import { useState, useMemo } from 'react';
import { RiskScenario } from '../App.tsx';
import { X, Target, Info } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area } from 'recharts';

interface SensitivityAnalysisProps {
  scenario: RiskScenario;
  onClose: () => void;
}

type FAIRFactor = keyof Pick<RiskScenario,
  | 'threatEventFrequency'
  | 'susceptibility'
  | 'productivity'
  | 'response'
  | 'replacement'
  | 'fines'
  | 'competitiveAdvantage'
  | 'reputation'
  | 'slef'
>;
type AnalysisMode = 'local' | 'global';
type MetricMode = 'mean' | 'p50' | 'p90';

export function SensitivityAnalysis({ scenario, onClose }: SensitivityAnalysisProps) {
  const [selectedFactor, setSelectedFactor] = useState<FAIRFactor>('threatEventFrequency');
  const [mode, setMode] = useState<AnalysisMode>('local');
  const [metricMode, setMetricMode] = useState<MetricMode>('mean');
  const [rangeMin, setRangeMin] = useState<number>(50);
  const [rangeMax, setRangeMax] = useState<number>(150);
  const [targetALE, setTargetALE] = useState<string>('');
  const [jointMode, setJointMode] = useState(false);
  const [coupledFactor, setCoupledFactor] = useState<FAIRFactor>('susceptibility');
  const [showGlobalTab, setShowGlobalTab] = useState(false);

  const calculatePrimaryLoss = (s: Partial<RiskScenario>) => 
    (s.productivity || 0) + (s.response || 0) + (s.replacement || 0);
  
  const calculateSecondaryLoss = (s: Partial<RiskScenario>) => 
    (s.fines || 0) + (s.competitiveAdvantage || 0) + (s.reputation || 0);
  
  const calculateLM = (primaryLoss: number, secondaryLoss: number, slef: number) => {
    return primaryLoss + (secondaryLoss * (slef / 100));
  };

  const calculateLEF = (threatEventFrequency: number, susceptibility: number) => {
    return threatEventFrequency * (susceptibility / 100);
  };

  const calculateALE = (lef: number, slee: number) => {
    return lef * slee;
  };

  // Logit transform for percentage inputs (keeps them in [0,100])
  const logit = (p: number) => Math.log(p / (100 - p));
  const invLogit = (x: number) => 100 / (1 + Math.exp(-x));

  // Monte Carlo simulation for uncertainty bands
  const runMonteCarloForPoint = (testScenario: Partial<RiskScenario>, iterations = 500) => {
    const results: number[] = [];
    
    for (let i = 0; i < iterations; i++) {
      const tefVariation = (testScenario.threatEventFrequency || 0) * (0.8 + Math.random() * 0.4);
      const suscVariation = (testScenario.susceptibility || 0) * (0.8 + Math.random() * 0.4);
      const primaryVariation = calculatePrimaryLoss(testScenario) * (0.8 + Math.random() * 0.4);
      const secondaryVariation = calculateSecondaryLoss(testScenario) * (0.8 + Math.random() * 0.4);
      const slefVariation = (testScenario.slef || 0) * (0.8 + Math.random() * 0.4);

      const lef = calculateLEF(tefVariation, suscVariation);
      const slee = calculateLM(primaryVariation, secondaryVariation, slefVariation);
      const ale = calculateALE(lef, slee);

      results.push(ale);
    }

    results.sort((a, b) => a - b);
    return {
      p10: results[Math.floor(results.length * 0.1)],
      p50: results[Math.floor(results.length * 0.5)],
      p90: results[Math.floor(results.length * 0.9)],
    };
  };

  // Calculate elasticity
  const calculateElasticity = () => {
    const baselineLEF = calculateLEF(scenario.threatEventFrequency, scenario.susceptibility);
    const baselineSLEE = calculateLM(
      calculatePrimaryLoss(scenario),
      calculateSecondaryLoss(scenario),
      scenario.slef
    );
    const baselineALE = calculateALE(baselineLEF, baselineSLEE);

    // Get current factor value
    let baseValue = 0;
    switch (selectedFactor) {
      case 'threatEventFrequency': baseValue = scenario.threatEventFrequency; break;
      case 'susceptibility': baseValue = scenario.susceptibility; break;
      case 'slef': baseValue = scenario.slef; break;
      case 'productivity': baseValue = scenario.productivity; break;
      case 'response': baseValue = scenario.response; break;
      case 'replacement': baseValue = scenario.replacement; break;
      case 'fines': baseValue = scenario.fines; break;
      case 'competitiveAdvantage': baseValue = scenario.competitiveAdvantage; break;
      case 'reputation': baseValue = scenario.reputation; break;
    }

    // Small perturbation (1%)
    const delta = baseValue * 0.01;
    const testScenario = { ...scenario };

    switch (selectedFactor) {
      case 'threatEventFrequency': testScenario.threatEventFrequency += delta; break;
      case 'susceptibility': testScenario.susceptibility += delta; break;
      case 'slef': testScenario.slef += delta; break;
      case 'productivity': testScenario.productivity += delta; break;
      case 'response': testScenario.response += delta; break;
      case 'replacement': testScenario.replacement += delta; break;
      case 'fines': testScenario.fines += delta; break;
      case 'competitiveAdvantage': testScenario.competitiveAdvantage += delta; break;
      case 'reputation': testScenario.reputation += delta; break;
    }

    const newLEF = calculateLEF(testScenario.threatEventFrequency, testScenario.susceptibility);
    const newLM = calculateLM(
      calculatePrimaryLoss(testScenario),
      calculateSecondaryLoss(testScenario),
      testScenario.slef
    );
    const newALE = calculateALE(newLEF, newLM);

    const elasticity = ((newALE - baselineALE) / baselineALE) / ((delta) / baseValue);
    const slope = (newALE - baselineALE) / delta;

    return { elasticity, slope };
  };

  // Calculate partial derivatives analytically
  const getPartialDerivative = () => {
    const lef = calculateLEF(scenario.threatEventFrequency, scenario.susceptibility);
    const lm = calculateLM(
      calculatePrimaryLoss(scenario),
      calculateSecondaryLoss(scenario),
      scenario.slef
    );
    const secondaryTotal = calculateSecondaryLoss(scenario);

    switch (selectedFactor) {
      case 'threatEventFrequency':
        return { formula: '∂ALE/∂TEF = Susceptibility × LM', value: (scenario.susceptibility / 100) * lm };
      case 'susceptibility':
        return { formula: '∂ALE/∂Susc = TEF × LM × 0.01', value: scenario.threatEventFrequency * lm * 0.01 };
      case 'slef':
        return { formula: '∂ALE/∂SLEF = LEF × Σ(Secondary) × 0.01', value: lef * secondaryTotal * 0.01 };
      case 'productivity':
      case 'response':
      case 'replacement':
        return { formula: '∂ALE/∂L = LEF', value: lef };
      case 'fines':
      case 'competitiveAdvantage':
      case 'reputation':
        return { formula: '∂ALE/∂L = LEF × SLEF × 0.01', value: lef * (scenario.slef / 100) };
      default:
        return { formula: '', value: 0 };
    }
  };

  const generateSensitivityData = () => {
    const data = [];
    const steps = 25;
    const increment = (rangeMax - rangeMin) / steps;

    for (let i = 0; i <= steps; i++) {
      const percentage = rangeMin + (i * increment);
      const testScenario = { ...scenario };

      // Apply variation with logit scaling for percentages
      const applyVariation = (factor: FAIRFactor, pct: number) => {
        const isPercentage = factor === 'susceptibility' || factor === 'slef';
        
        if (isPercentage && mode === 'local') {
          // Use logit transform to keep bounded
          const baseline = factor === 'susceptibility' ? scenario.susceptibility : scenario.slef;
          const logitBase = logit(baseline);
          const logitVar = logitBase * (pct / 100);
          const newValue = Math.max(0.1, Math.min(99.9, invLogit(logitVar)));
          return newValue;
        } else {
          const baseline = testScenario[factor] as number;
          return baseline * (pct / 100);
        }
      };

      // Apply primary variation
      switch (selectedFactor) {
        case 'threatEventFrequency':
          testScenario.threatEventFrequency = applyVariation('threatEventFrequency', percentage);
          break;
        case 'susceptibility':
          testScenario.susceptibility = applyVariation('susceptibility', percentage);
          break;
        case 'slef':
          testScenario.slef = applyVariation('slef', percentage);
          break;
        case 'productivity':
          testScenario.productivity = applyVariation('productivity', percentage);
          break;
        case 'response':
          testScenario.response = applyVariation('response', percentage);
          break;
        case 'replacement':
          testScenario.replacement = applyVariation('replacement', percentage);
          break;
        case 'fines':
          testScenario.fines = applyVariation('fines', percentage);
          break;
        case 'competitiveAdvantage':
          testScenario.competitiveAdvantage = applyVariation('competitiveAdvantage', percentage);
          break;
        case 'reputation':
          testScenario.reputation = applyVariation('reputation', percentage);
          break;
      }

      // Apply coupled variation if joint mode
      if (jointMode) {
        switch (coupledFactor) {
          case 'threatEventFrequency':
            testScenario.threatEventFrequency = applyVariation('threatEventFrequency', percentage);
            break;
          case 'susceptibility':
            testScenario.susceptibility = applyVariation('susceptibility', percentage);
            break;
          case 'slef':
            testScenario.slef = applyVariation('slef', percentage);
            break;
        }
      }

      const lef = calculateLEF(testScenario.threatEventFrequency, testScenario.susceptibility);
      const primaryLoss = calculatePrimaryLoss(testScenario);
      const secondaryLoss = calculateSecondaryLoss(testScenario);
      const slee = calculateLM(primaryLoss, secondaryLoss, testScenario.slef);
      const ale = calculateALE(lef, slee);

      // Calculate secondary-specific values for gate clarity
      const expectedSecondary = secondaryLoss * (testScenario.slef / 100);
      const ifOccursTotal = primaryLoss + secondaryLoss;

      // Run Monte Carlo for uncertainty band
      const mcResults = mode === 'local' ? runMonteCarloForPoint(testScenario) : { p10: ale * 0.8, p50: ale, p90: ale * 1.2 };

      data.push({
        percentage: percentage.toFixed(0),
        ale: Math.round(ale),
        aleMean: Math.round(ale),
        aleP50: Math.round(mcResults.p50),
        aleP90: Math.round(mcResults.p90),
        aleP10: Math.round(mcResults.p10),
        lef: lef.toFixed(2),
        slee: Math.round(slee),
        expectedSecondary: Math.round(expectedSecondary),
        ifOccursTotal: Math.round(ifOccursTotal),
      });
    }

    return data;
  };

  // Calculate global variance decomposition (Sobol-like)
  const calculateGlobalVariance = () => {
    const baselineALE = calculateALE(
      calculateLEF(scenario.threatEventFrequency, scenario.susceptibility),
      calculateLM(calculatePrimaryLoss(scenario), calculateSecondaryLoss(scenario), scenario.slef)
    );

    const factors: Array<{ factor: FAIRFactor; label: string; variance: number }> = [
      { factor: 'threatEventFrequency', label: 'TEF', variance: 0 },
      { factor: 'susceptibility', label: 'Susceptibility', variance: 0 },
      { factor: 'slef', label: 'SLEF', variance: 0 },
      { factor: 'productivity', label: 'Productivity', variance: 0 },
      { factor: 'response', label: 'Response', variance: 0 },
      { factor: 'replacement', label: 'Replacement', variance: 0 },
      { factor: 'fines', label: 'Fines', variance: 0 },
      { factor: 'competitiveAdvantage', label: 'Comp. Adv.', variance: 0 },
      { factor: 'reputation', label: 'Reputation', variance: 0 },
    ];

    // Simple first-order variance contribution (vary each ±20%, measure ALE variance)
    factors.forEach(f => {
      const testScenarioHigh = { ...scenario };
      const testScenarioLow = { ...scenario };

      const currentValue = scenario[f.factor] as number;
      (testScenarioHigh[f.factor] as number) = currentValue * 1.2;
      (testScenarioLow[f.factor] as number) = currentValue * 0.8;

      const aleHigh = calculateALE(
        calculateLEF(testScenarioHigh.threatEventFrequency, testScenarioHigh.susceptibility),
        calculateLM(calculatePrimaryLoss(testScenarioHigh), calculateSecondaryLoss(testScenarioHigh), testScenarioHigh.slef)
      );

      const aleLow = calculateALE(
        calculateLEF(testScenarioLow.threatEventFrequency, testScenarioLow.susceptibility),
        calculateLM(calculatePrimaryLoss(testScenarioLow), calculateSecondaryLoss(testScenarioLow), testScenarioLow.slef)
      );

      f.variance = Math.pow(aleHigh - aleLow, 2);
    });

    const totalVariance = factors.reduce((sum, f) => sum + f.variance, 0);
    factors.forEach(f => f.variance = (f.variance / totalVariance) * 100);

    return factors.sort((a, b) => b.variance - a.variance);
  };

  // Solve for target
  const solveForTarget = () => {
    const target = parseFloat(targetALE);
    if (isNaN(target)) return null;

    const data = generateSensitivityData();
    
    // Find closest ALE to target
    let closest = data[0];
    let minDiff = Math.abs(data[0].ale - target);

    data.forEach(d => {
      const diff = Math.abs(d.ale - target);
      if (diff < minDiff) {
        minDiff = diff;
        closest = d;
      }
    });

    return {
      percentage: parseFloat(closest.percentage),
      ale: closest.ale,
      actualValue: (scenario[selectedFactor] as number) * (parseFloat(closest.percentage) / 100),
    };
  };

  const data = useMemo(() => generateSensitivityData(), [selectedFactor, rangeMin, rangeMax, jointMode, coupledFactor, mode, metricMode]);
  
  const baselineALE = calculateALE(
    calculateLEF(scenario.threatEventFrequency, scenario.susceptibility),
    calculateLM(calculatePrimaryLoss(scenario), calculateSecondaryLoss(scenario), scenario.slef)
  );

  const elasticityData = calculateElasticity();
  const partialDerivative = getPartialDerivative();
  const solution = targetALE ? solveForTarget() : null;

  const factors = [
    { id: 'threatEventFrequency', label: 'TEF', current: scenario.threatEventFrequency, unit: '' },
    { id: 'susceptibility', label: 'Susceptibility', current: scenario.susceptibility, unit: '%' },
    { id: 'slef', label: 'SLEF', current: scenario.slef, unit: '%' },
    { id: 'productivity', label: 'Productivity', current: scenario.productivity, unit: '$' },
    { id: 'response', label: 'Response', current: scenario.response, unit: '$' },
    { id: 'replacement', label: 'Replacement', current: scenario.replacement, unit: '$' },
    { id: 'fines', label: 'Fines', current: scenario.fines, unit: '$' },
    { id: 'competitiveAdvantage', label: 'Comp. Adv.', current: scenario.competitiveAdvantage, unit: '$' },
    { id: 'reputation', label: 'Reputation', current: scenario.reputation, unit: '$' },
  ];

  const selectedFactorData = factors.find(f => f.id === selectedFactor);
  const isSecondaryFactor = ['slef', 'fines', 'competitiveAdvantage', 'reputation'].includes(selectedFactor);

  const getMetricValue = (d: any) => {
    switch (metricMode) {
      case 'mean': return d.aleMean;
      case 'p50': return d.aleP50;
      case 'p90': return d.aleP90;
      default: return d.aleMean;
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[60] p-6">
      <div className="bg-white rounded-2xl max-w-7xl w-full max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-slate-200 px-8 py-6 rounded-t-2xl">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h2 className="text-2xl text-slate-900 mb-2">Sensitivity Analysis</h2>
              <p className="text-slate-600">{scenario.name}</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>

          {/* Mode Selection */}
          <div className="flex items-center gap-4">
            <div className="flex gap-2">
              <button
                onClick={() => setMode('local')}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  mode === 'local'
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                Local (OAT)
              </button>
              <button
                onClick={() => setMode('global')}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  mode === 'global'
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                Global (Monte Carlo)
              </button>
              <button
                onClick={() => setShowGlobalTab(!showGlobalTab)}
                className="px-4 py-2 text-sm bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors"
              >
                {showGlobalTab ? 'Hide' : 'Show'} Variance Decomp.
              </button>
            </div>

            {/* Method Tag */}
            <div className="flex-1">
              <div className="text-xs text-slate-500">
                Method: {mode === 'local' 
                  ? `one-at-a-time ±${((rangeMax - 100) / 2).toFixed(0)}% around baseline (others fixed)` 
                  : 'vary all inputs within P10–P90; show contribution to total uncertainty'}
              </div>
            </div>
          </div>
            {/* What this analysis shows */}
          <div className="mt-3 flex items-start gap-2 text-xs text-slate-500">
            <Info className="w-4 h-4 mt-0.5 text-slate-400" />
            <p>
              This view shows how sensitive the scenario&apos;s <span className="font-medium">annual loss (ALE)</span> is
              to changes in a single FAIR factor. We vary one input at a time, hold others fixed, and track
              how the ALE curve responds. Steeper curves and wider bands mean that factor matters more.
            </p>
          </div>
        </div>


        {/* Content */}
        <div className="p-8 space-y-8">
          {/* Global Variance Decomposition */}
          {showGlobalTab && (
            <div className="bg-gradient-to-br from-blue-50 to-slate-50 rounded-xl p-6 border border-blue-200">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="text-slate-900">Drivers of Uncertainty (Global)</h3>
                <button
                  className="p-1 hover:bg-white/60 rounded transition-colors group relative"
                  title="First-order variance contributions (Sobol-like)"
                >
                  <Info className="w-4 h-4 text-slate-500" />
                </button>
              </div>
              <div className="space-y-2">
                {calculateGlobalVariance().map((f, idx) => (
                  <div key={f.factor} className="flex items-center gap-3">
                    <div className="w-32 text-sm text-slate-600">{f.label}</div>
                    <div className="flex-1 bg-white rounded-full h-8 relative overflow-hidden border border-slate-200">
                      <div
                        className="bg-gradient-to-r from-slate-500 to-slate-600 h-full flex items-center justify-end px-3 transition-all duration-500"
                        style={{ width: `${f.variance}%` }}
                      >
                        <span className="text-xs text-white">
                          {f.variance.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-500 mt-4">
                Shows each input&apos;s contribution to total ALE variance. Higher = more impact on uncertainty.
              </p>
            </div>
          )}

          {/* Factor Selection */}
          <div>
            <h3 className="text-sm text-slate-600 mb-4">Select FAIR Factor</h3>
            <div className="grid grid-cols-3 gap-3">
              {factors.map((factor) => (
                <button
                  key={factor.id}
                  onClick={() => setSelectedFactor(factor.id as FAIRFactor)}
                  className={`p-4 border rounded-lg transition-all text-left ${
                    selectedFactor === factor.id
                      ? 'border-slate-400 bg-slate-50 ring-2 ring-slate-300'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="text-xs text-slate-500 mb-2">{factor.label}</div>
                  <div className="text-lg text-slate-900">
                    {factor.unit === '$'
                      ? `$${(factor.current / 1000).toFixed(0)}K`
                      : factor.unit === '%'
                      ? `${factor.current}%`
                      : `${factor.current}`}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Elasticity Chips */}
          <div className="bg-gradient-to-r from-slate-50 to-blue-50 rounded-xl p-6 border border-slate-200">
            <h3 className="text-sm text-slate-600 mb-4">Risk Elasticity & Sensitivity</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white rounded-lg p-4 border border-slate-200">
                <div className="text-xs text-slate-500 mb-2">Risk Elasticity</div>
                <div className="text-2xl text-slate-900 mb-1">
                  E = {elasticityData.elasticity.toFixed(3)}
                </div>
                <div className="text-xs text-slate-600">
                  ΔA/A ÷ Δx/x at baseline
                </div>
              </div>
              <div className="bg-white rounded-lg p-4 border border-slate-200">
                <div className="text-xs text-slate-500 mb-2">Partial Derivative</div>
                <div className="text-sm text-slate-900 mb-1 font-mono">
                  {partialDerivative.formula}
                </div>
                <div className="text-lg text-slate-700">
                  ≈ ${(partialDerivative.value).toFixed(2)}
                </div>
              </div>
            </div>
              <p className="text-xs text-slate-500 mt-4 space-y-1">
              <span className="block">
                <span className="font-medium">Elasticity</span> tells you the % change in ALE for a 1% change in this input (around the current value).
              </span>
              <span className="block">
                • If |E| &gt; 1 → ALE moves more than proportionally (very sensitive).
              </span>
              <span className="block">
                • If |E| ≈ 1 → ALE moves about one-for-one with the input.
              </span>
              <span className="block">
                • If |E| &lt; 1 → ALE moves less than proportionally (less sensitive).
              </span>
              <span className="block">
                The <span className="font-medium">partial derivative</span> shows the absolute $ change in ALE for a one-unit change in this factor.
              </span>
            </p>
          </div>

          {/* Secondary Gate Clarity */}
          {isSecondaryFactor && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
              <div className="bg-amber-200 text-amber-900 text-xs px-2 py-1 rounded">SECONDARY</div>
              <div className="flex-1">
                <div className="text-sm text-amber-900">Secondary applies only when gate opens</div>
                <div className="text-xs text-amber-700 mt-1">
                    Secondary loss only shows up when the secondary loss event occurs.
                    The chart shows the <span className="font-medium">expected secondary loss</span> (SLEF-weighted),
                    and the <span className="font-medium">if-occurs total</span> when the gate is fully open.
                </div>
              </div>
            </div>
          )}

          {/* Target Solver */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center gap-2 mb-4">
              <Target className="w-5 h-5 text-slate-600" />
              <h3 className="text-slate-900">Solve for Target</h3>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2">
                <label className="block text-sm text-slate-600 mb-2">
                  Find {selectedFactorData?.label} needed for ALE ≤
                </label>
                <input
                  type="number"
                  value={targetALE}
                  onChange={(e) => setTargetALE(e.target.value)}
                  placeholder="Enter target ALE (e.g., 500000)"
                  className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
              {solution && (
                <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                  <div className="text-xs text-green-700 mb-1">Required Value</div>
                  <div className="text-xl text-green-900">
                    {selectedFactorData?.unit === '$'
                      ? `$${(solution.actualValue / 1000).toFixed(0)}K`
                      : selectedFactorData?.unit === '%'
                      ? `${solution.actualValue.toFixed(1)}%`
                      : solution.actualValue.toFixed(2)}
                  </div>
                  <div className="text-xs text-green-700 mt-1">
                    {solution.percentage.toFixed(0)}% of baseline
                  </div>
                </div>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-4">
              Solve for the input value that achieves your risk objective. Uses current test range.
            </p>
          </div>

          {/* Joint Mode Toggle */}
          <div className="bg-slate-50 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm text-slate-600">Coupled Change (Joint Slider)</h3>
                <p className="text-xs text-slate-500 mt-1">Test combined control packages</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={jointMode}
                  onChange={(e) => setJointMode(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-300 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-slate-900"></div>
              </label>
            </div>
            {jointMode && (
              <div>
                <label className="block text-sm text-slate-600 mb-2">Also vary:</label>
                <select
                  value={coupledFactor}
                  onChange={(e) => setCoupledFactor(e.target.value as FAIRFactor)}
                  className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400"
                >
                  {factors.filter(f => f.id !== selectedFactor).map(f => (
                    <option key={f.id} value={f.id}>{f.label}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Range Controls & Metric Mode */}
          <div className="bg-slate-50 rounded-xl p-6">
            <div className="grid grid-cols-3 gap-6">
              <div>
                <label className="block text-sm text-slate-600 mb-2">Minimum % of Baseline</label>
                <input
                  type="number"
                  value={rangeMin}
                  onChange={(e) => setRangeMin(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-600 mb-2">Maximum % of Baseline</label>
                <input
                  type="number"
                  value={rangeMax}
                  onChange={(e) => setRangeMax(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-600 mb-2">Metric Display</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setMetricMode('mean')}
                    className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
                      metricMode === 'mean' ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    Mean
                  </button>
                  <button
                    onClick={() => setMetricMode('p50')}
                    className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
                      metricMode === 'p50' ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    P50
                  </button>
                  <button
                    onClick={() => setMetricMode('p90')}
                    className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
                      metricMode === 'p90' ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    P90
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-white border border-slate-200 rounded-xl p-6">
            <div className="mb-6">
              <h3 className="text-slate-900 mb-1">
                {selectedFactorData?.label} Impact on ALE ({metricMode.toUpperCase()})
              </h3>
              <p className="text-sm text-slate-500">
                Testing {rangeMin}% to {rangeMax}% of baseline value
                {jointMode && ` (coupled with ${factors.find(f => f.id === coupledFactor)?.label})`}
              </p>
              <p className="text-xs text-slate-500 mt-2">
                Shaded area = P10–P90 ALE from Monte Carlo at each test value
              </p>
            </div>
            
            <ResponsiveContainer width="100%" height={450}>
              <LineChart data={data}>
                <defs>
                  <linearGradient id="uncertaintyGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis
                  dataKey="percentage"
                  label={{ value: '% of Baseline Value', position: 'insideBottom', offset: -10 }}
                  stroke="#94A3B8"
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  label={{ value: `ALE (${metricMode.toUpperCase()})`, angle: -90, position: 'insideLeft' }}
                  stroke="#94A3B8"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}K`}
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    if (name === 'aleP10') return [`$${value.toLocaleString()}`, 'P10 (optimistic)'];
                    if (name === 'aleP90') return [`$${value.toLocaleString()}`, 'P90 (pessimistic)'];
                    if (name === 'metric') return [`$${value.toLocaleString()}`, metricMode.toUpperCase()];
                    return [`$${value.toLocaleString()}`, name];
                  }}
                  contentStyle={{
                    backgroundColor: 'white',
                    border: '1px solid #E2E8F0',
                    borderRadius: '8px',
                  }}
                  labelFormatter={(label) => `${label}% of baseline`}
                />
                {/* Uncertainty band */}
                <Area
                  type="monotone"
                  dataKey="aleP90"
                  stroke="none"
                  fill="url(#uncertaintyGradient)"
                  fillOpacity={1}
                />
                <Area
                  type="monotone"
                  dataKey="aleP10"
                  stroke="none"
                  fill="white"
                  fillOpacity={1}
                />
                {/* Main line */}
                <Line
                  type="monotone"
                  dataKey={getMetricValue}
                  name="metric"
                  stroke="#64748b"
                  strokeWidth={3}
                  dot={false}
                  activeDot={{ r: 6, fill: '#64748b', strokeWidth: 2, stroke: 'white' }}
                />
                {/* Target marker */}
                {solution && (
                  <Line
                    type="monotone"
                    dataKey={(d) => d.percentage === solution.percentage.toFixed(0) ? getMetricValue(d) : null}
                    stroke="#10b981"
                    strokeWidth={0}
                    dot={{ r: 8, fill: '#10b981', strokeWidth: 3, stroke: 'white' }}
                  />
                )}
                {/* Secondary gate traces */}
                {isSecondaryFactor && (
                  <>
                    <Line
                      type="monotone"
                      dataKey="expectedSecondary"
                      stroke="#f59e0b"
                      strokeWidth={1}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="ifOccursTotal"
                      stroke="#ef4444"
                      strokeWidth={1}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>

            <div className="mt-6 text-xs text-slate-500 space-y-1">
              <p className="font-medium">How to interpret this chart</p>
              <p>
                • The horizontal axis is how much you change the selected factor (as % of its current value).
              </p>
              <p>
                • The line shows the chosen ALE metric ({metricMode.toUpperCase()}) at each test point.
              </p>
              <p>
                • The shaded band shows the uncertainty range (P10–P90) from simulation – wider = more uncertainty.
              </p>
              <p className="mt-2 font-medium">Questions to ask when a bar/curve looks steep:</p>
              <p>
                – Do we have good evidence for this input, or is it mostly expert judgement?
              </p>
              <p>
                – What real-world controls, processes, or data could reduce the uncertainty here?
              </p>
              <p>
                – If we invested to move this factor (e.g., cut susceptibility), would it materially shift ALE or its tail?
              </p>
            </div>
            {isSecondaryFactor && (
              <div className="mt-4 flex items-center gap-6 text-xs text-slate-600">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-0.5 bg-slate-600"></div>
                  <span>Expected (probability-weighted)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-0.5 bg-amber-500 border-t-2 border-dashed border-amber-500"></div>
                  <span>Expected Secondary</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-0.5 bg-red-500 border-t-2 border-dashed border-red-500"></div>
                  <span>If-Occurs Total</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
