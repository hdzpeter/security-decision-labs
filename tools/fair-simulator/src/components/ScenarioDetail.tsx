import { SensitivityAnalysis } from './SensitivityAnalysis.tsx';
import { ScenarioBanner } from './ScenarioBanner.tsx';
import { MathToggle } from './MathToggle.tsx';
import { DriverChart } from './DriverChart.tsx';
import { SLEFGate } from './SLEFGate.tsx';
import { SanityChecks } from './SanityChecks.tsx';
import { RangeWhisker } from './RangeWhisker.tsx';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { RiskScenario } from '../App.tsx';
import { useState } from 'react';
import { X, Edit2, TrendingUp, Trash2, Eye, EyeOff } from 'lucide-react';

interface ScenarioDetailProps {
  scenario: RiskScenario;
  onClose: () => void;
  onUpdate?: (scenario: RiskScenario) => void;
  onDelete?: (scenarioId: string) => void;
}

export function ScenarioDetail({ scenario, onClose, onUpdate, onDelete }: ScenarioDetailProps) {
  const [editMode, setEditMode] = useState(false);
  const [editedScenario, setEditedScenario] = useState(scenario);
  const [showSensitivity, setShowSensitivity] = useState(false);
  const [simulations, setSimulations] = useState(10000);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showRanges, setShowRanges] = useState(false);

  const calculatePrimaryLoss = (s: RiskScenario) => s.productivity + s.response + s.replacement;
  const calculateSecondaryLoss = (s: RiskScenario) => s.fines + s.competitiveAdvantage + s.reputation;
  
  const calculateSLEE = (s: RiskScenario) => {
    const primaryLoss = calculatePrimaryLoss(s);
    const secondaryLoss = calculateSecondaryLoss(s);
    return primaryLoss + (secondaryLoss * (s.slef / 100));
  };

  const calculateLEF = (s: RiskScenario) => {
    return s.threatEventFrequency * (s.susceptibility / 100);
  };

  const calculateALE = (s: RiskScenario) => {
    return calculateLEF(s) * calculateSLEE(s);
  };

  // Monte Carlo simulation
  const runMonteCarloSimulation = () => {
    const results: number[] = [];
    const s = editedScenario;

    for (let i = 0; i < simulations; i++) {
      // Add variability (±20% for each factor)
      const tefVariation = s.threatEventFrequency * (0.8 + Math.random() * 0.4);
      const suscVariation = s.susceptibility * (0.8 + Math.random() * 0.4);
      const primaryVariation = calculatePrimaryLoss(s) * (0.8 + Math.random() * 0.4);
      const secondaryVariation = calculateSecondaryLoss(s) * (0.8 + Math.random() * 0.4);
      const slefVariation = s.slef * (0.8 + Math.random() * 0.4);

      const lef = tefVariation * (suscVariation / 100);
      const slee = primaryVariation + (secondaryVariation * (slefVariation / 100));
      const ale = lef * slee;

      results.push(ale);
    }

    return results.sort((a, b) => b - a);
  };

  // Generate Loss Exceedance Curve (LEC)
  const generateLEC = () => {
    const results = runMonteCarloSimulation();
    const lecData = [];
    const step = Math.floor(results.length / 50); // 50 data points

    for (let i = 0; i < results.length; i += step) {
      const exceedanceProbability = (i / results.length) * 100;
      lecData.push({
        probability: exceedanceProbability.toFixed(1),
        loss: Math.round(results[i]),
      });
    }

    return lecData;
  };

  const lecData = generateLEC();
  const ale = calculateALE(editedScenario);
  const lef = calculateLEF(editedScenario);
  const slee = calculateSLEE(editedScenario);

  // Calculate percentiles from Monte Carlo
  const results = runMonteCarloSimulation();
  const p50 = results[Math.floor(results.length * 0.5)];
  const p90 = results[Math.floor(results.length * 0.1)];
  const p99 = results[Math.floor(results.length * 0.01)];

  const handleSave = () => {
    if (onUpdate) {
      onUpdate(editedScenario);
    }
    setEditMode(false);
  };

  const handleCancel = () => {
    setEditedScenario(scenario);
    setEditMode(false);
  };

  const handleDelete = () => {
    if (onDelete) {
      onDelete(scenario.id);
    }
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-6">
        <div className="bg-white rounded-2xl max-w-7xl w-full max-h-[90vh] overflow-y-auto shadow-2xl">
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-slate-200 px-8 py-6 rounded-t-2xl flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <h2 className="text-2xl text-slate-900">{scenario.name}</h2>
                <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">USD (2025)</span>
                <button
                  onClick={() => setEditMode(!editMode)}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1.5 ${
                    editMode
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <Edit2 className="w-3 h-3" />
                  {editMode ? 'Editing' : 'Edit'}
                </button>
                <button
                  onClick={() => setShowRanges(!showRanges)}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1.5 ${
                    showRanges
                      ? 'bg-slate-700 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                  title="Toggle range visibility for print/report mode"
                >
                  {showRanges ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                  {showRanges ? 'Hide Ranges' : 'Show Ranges'}
                </button>
              </div>
              <p className="text-slate-600">{scenario.description}</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>

          {/* Content */}
          <div className="p-8">
            {/* Scenario Banner - Always Visible */}
            <div className="mb-8">
              <ScenarioBanner scenario={scenario} />
            </div>

            {/* Sanity Checks */}
            <div className="mb-8">
              <SanityChecks scenario={editedScenario} />
            </div>

            {/* Range Mode Indicator */}
            {showRanges && (
              <div className="mb-6 bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-center gap-3">
                <Eye className="w-5 h-5 text-slate-600" />
                <div>
                  <div className="text-sm text-slate-700">Range Display Mode: ON</div>
                  <div className="text-xs text-slate-600">Showing P10/P50/P90 uncertainty ranges for all FAIR factors</div>
                </div>
              </div>
            )}

            {/* Math Toggles - Show Calculations */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              <MathToggle
                title="Loss Event Frequency (LEF)"
                result={`${lef.toFixed(2)}/yr`}
                formula="LEF = TEF × Susceptibility"
                breakdown={[
                  { label: 'TEF (events/year)', value: editedScenario.threatEventFrequency.toFixed(2) },
                  { label: 'Susceptibility', value: `${editedScenario.susceptibility}%` },
                  { label: 'LEF (events/year)', value: lef.toFixed(2) },
                ]}
                explanation="LEF represents how often loss events actually occur, combining threat frequency with your ability to resist."
              />
              
              <MathToggle
                title="Loss Magnitude (LM)"
                result={`$${(slee / 1000).toFixed(0)}K`}
                formula="LM = Σ(Primary) + SLEF × Σ(Secondary)"
                breakdown={[
                  { label: 'Primary Loss', value: `$${(calculatePrimaryLoss(editedScenario) / 1000).toFixed(0)}K` },
                  { label: 'SLEF Probability', value: `${editedScenario.slef}%` },
                  { label: 'Secondary Loss (if occurs)', value: `$${(calculateSecondaryLoss(editedScenario) / 1000).toFixed(0)}K` },
                  { label: 'Expected Secondary', value: `$${((calculateSecondaryLoss(editedScenario) * editedScenario.slef / 100) / 1000).toFixed(0)}K` },
                  { label: 'Total LM', value: `$${(slee / 1000).toFixed(0)}K` },
                ]}
                explanation="Loss Magnitude is the financial impact per event. Primary losses always occur; secondary losses are probabilistic (SLEF gate)."
              />
              
              <MathToggle
                title="Annual Loss Exposure (ALE)"
                result={`$${(ale / 1000).toFixed(0)}K`}
                formula="ALE = LEF × LM"
                breakdown={[
                  { label: 'LEF (events/year)', value: lef.toFixed(2) },
                  { label: 'LM (per event)', value: `$${(slee / 1000).toFixed(0)}K` },
                  { label: 'ALE (annual)', value: `$${(ale / 1000).toFixed(0)}K` },
                ]}
                explanation="ALE is the expected annual loss, combining event frequency with magnitude."
              />
            </div>

            {/* SLEF Gate Visualization */}
            <div className="mb-8">
              <SLEFGate scenario={editedScenario} />
            </div>

            {/* Driver Chart */}
            <div className="mb-8">
              <DriverChart scenario={editedScenario} ale={ale} />
            </div>

            {/* Monte Carlo Simulation Controls */}
            <div className="bg-slate-50 rounded-xl p-6 mb-8">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-slate-900 mb-1">Monte Carlo Simulation</h3>
                  <p className="text-sm text-slate-500">Simulating loss distribution with ±20% variability</p>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    value={simulations}
                    onChange={(e) => setSimulations(Number(e.target.value))}
                    className="w-32 px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                    min="1000"
                    max="50000"
                    step="1000"
                  />
                  <span className="text-sm text-slate-500">runs</span>
                </div>
              </div>

              {/* Key Metrics */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-white rounded-lg p-4 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">Mean (ALE)</div>
                  <div className="text-2xl text-slate-900">${(ale / 1000).toFixed(0)}K</div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">Median (P50)</div>
                  <div className="text-2xl text-slate-900">${(p50 / 1000).toFixed(0)}K</div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">90th Percentile</div>
                  <div className="text-2xl text-slate-700">${(p90 / 1000).toFixed(0)}K</div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">99th Percentile</div>
                  <div className="text-2xl text-slate-700">${(p99 / 1000).toFixed(0)}K</div>
                </div>
              </div>
            </div>

            {/* Loss Exceedance Curve (LEC) */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
              <h3 className="text-slate-900 mb-6">Loss Exceedance Curve</h3>
              <ResponsiveContainer width="100%" height={400}>
                <AreaChart data={lecData} margin={{ top: 10, right: 30, left: 20, bottom: 20 }}>
                  <defs>
                    <linearGradient id="lossGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#64748b" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#64748b" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis
                    dataKey="probability"
                    label={{ value: 'Exceedance Probability (%)', position: 'insideBottom', offset: -10 }}
                    stroke="#94A3B8"
                    tick={{ fontSize: 12 }}
                    height={60}
                  />
                  <YAxis
                    label={{ value: 'Annual Loss ($)', angle: -90, position: 'insideLeft', offset: 10 }}
                    stroke="#94A3B8"
                    tickFormatter={(value) => `$${(value / 1000).toFixed(0)}K`}
                    tick={{ fontSize: 12 }}
                    width={80}
                  />
                  <Tooltip
                    formatter={(value: number) => [`$${value.toLocaleString()}`, 'Loss']}
                    labelFormatter={(label) => `${label}% chance of exceeding`}
                    contentStyle={{
                      backgroundColor: 'white',
                      border: '1px solid #E2E8F0',
                      borderRadius: '8px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="loss"
                    stroke="#64748b"
                    strokeWidth={2}
                    fill="url(#lossGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* FAIR Factors - Editable */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-slate-900">FAIR Factors</h3>
                {editMode && (
                  <div className="flex gap-2">
                    <button
                      onClick={handleCancel}
                      className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors"
                    >
                      Save Changes
                    </button>
                  </div>
                )}
              </div>
              
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm text-slate-600 mb-2">
                    Threat Event Frequency <span className="text-slate-400">(events/year)</span>
                  </label>
                  {!editMode && showRanges && editedScenario.ranges?.tef ? (
                    <div className="px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <RangeWhisker
                        p10={editedScenario.ranges.tef.p10}
                        p50={editedScenario.threatEventFrequency}
                        p90={editedScenario.ranges.tef.p90}
                        format="number"
                      />
                    </div>
                  ) : (
                    <input
                      type="number"
                      value={editedScenario.threatEventFrequency}
                      onChange={(e) => setEditedScenario({...editedScenario, threatEventFrequency: Number(e.target.value)})}
                      disabled={!editMode}
                      className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                      step="0.1"
                    />
                  )}
                </div>
                
                <div>
                  <label className="block text-sm text-slate-600 mb-2">
                    Susceptibility <span className="text-slate-400">(%) — P(loss | threat event)</span>
                  </label>
                  {!editMode && showRanges && editedScenario.ranges?.susceptibility ? (
                    <div className="px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <RangeWhisker
                        p10={editedScenario.ranges.susceptibility.p10}
                        p50={editedScenario.susceptibility}
                        p90={editedScenario.ranges.susceptibility.p90}
                        format="percentage"
                      />
                    </div>
                  ) : (
                    <input
                      type="number"
                      value={editedScenario.susceptibility}
                      onChange={(e) => setEditedScenario({...editedScenario, susceptibility: Number(e.target.value)})}
                      disabled={!editMode}
                      className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                      min="0"
                      max="100"
                    />
                  )}
                </div>

                <div>
                  <label className="block text-sm text-slate-600 mb-2">
                    Secondary LEF <span className="text-slate-400">(%)</span>
                  </label>
                  {!editMode && showRanges && editedScenario.ranges?.slef ? (
                    <div className="px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <RangeWhisker
                        p10={editedScenario.ranges.slef.p10}
                        p50={editedScenario.slef}
                        p90={editedScenario.ranges.slef.p90}
                        format="percentage"
                      />
                    </div>
                  ) : (
                    <input
                      type="number"
                      value={editedScenario.slef}
                      onChange={(e) => setEditedScenario({...editedScenario, slef: Number(e.target.value)})}
                      disabled={!editMode}
                      className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                      min="0"
                      max="100"
                    />
                  )}
                </div>

                <div>
                  <div className="text-sm text-slate-600 mb-2">Calculated LEF</div>
                  <div className="px-4 py-2 bg-slate-100 border border-slate-200 rounded-lg text-slate-900">
                    {lef.toFixed(2)} events/year
                  </div>
                </div>
              </div>
            </div>

            {/* Loss Values - Editable */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
              <h3 className="text-slate-900 mb-6">Loss Magnitudes</h3>
              
              <div className="space-y-6">
                {/* Primary Loss */}
                <div>
                  <div className="text-sm text-slate-600 mb-4">Primary Loss</div>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Productivity</label>
                      {!editMode && showRanges && editedScenario.ranges?.productivity ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.productivity.p10}
                            p50={editedScenario.productivity}
                            p90={editedScenario.ranges.productivity.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.productivity}
                          onChange={(e) => setEditedScenario({...editedScenario, productivity: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Response</label>
                      {!editMode && showRanges && editedScenario.ranges?.response ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.response.p10}
                            p50={editedScenario.response}
                            p90={editedScenario.ranges.response.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.response}
                          onChange={(e) => setEditedScenario({...editedScenario, response: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Replacement</label>
                      {!editMode && showRanges && editedScenario.ranges?.replacement ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.replacement.p10}
                            p50={editedScenario.replacement}
                            p90={editedScenario.ranges.replacement.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.replacement}
                          onChange={(e) => setEditedScenario({...editedScenario, replacement: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                  </div>
                </div>

                {/* Secondary Loss */}
                <div>
                  <div className="text-sm text-slate-600 mb-4">Secondary Loss</div>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Fines & Judgments</label>
                      {!editMode && showRanges && editedScenario.ranges?.fines ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.fines.p10}
                            p50={editedScenario.fines}
                            p90={editedScenario.ranges.fines.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.fines}
                          onChange={(e) => setEditedScenario({...editedScenario, fines: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Competitive Advantage</label>
                      {!editMode && showRanges && editedScenario.ranges?.competitiveAdvantage ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.competitiveAdvantage.p10}
                            p50={editedScenario.competitiveAdvantage}
                            p90={editedScenario.ranges.competitiveAdvantage.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.competitiveAdvantage}
                          onChange={(e) => setEditedScenario({...editedScenario, competitiveAdvantage: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-2">Reputation</label>
                      {!editMode && showRanges && editedScenario.ranges?.reputation ? (
                        <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
                          <RangeWhisker
                            p10={editedScenario.ranges.reputation.p10}
                            p50={editedScenario.reputation}
                            p90={editedScenario.ranges.reputation.p90}
                            format="currency"
                          />
                        </div>
                      ) : (
                        <input
                          type="number"
                          value={editedScenario.reputation}
                          onChange={(e) => setEditedScenario({...editedScenario, reputation: Number(e.target.value)})}
                          disabled={!editMode}
                          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
                          step="1000"
                        />
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Button */}
            <div className="flex justify-between gap-3">
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="px-6 py-3 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete Scenario
              </button>
              <button
                onClick={() => setShowSensitivity(true)}
                className="px-6 py-3 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 transition-colors flex items-center gap-2"
              >
                <TrendingUp className="w-4 h-4" />
                Sensitivity Analysis
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Sensitivity Analysis Modal */}
      {showSensitivity && (
        <SensitivityAnalysis scenario={editedScenario} onClose={() => setShowSensitivity(false)} />
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center z-[60] p-6">
          <div className="bg-white rounded-2xl max-w-md w-full shadow-2xl">
            <div className="bg-white border-b border-slate-200 px-6 py-4 rounded-t-2xl flex items-start justify-between">
              <h3 className="text-lg text-slate-900">Delete Scenario</h3>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="p-1 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            <div className="p-6">
              <p className="text-slate-600 mb-6">
                Are you sure you want to delete <strong>{scenario.name}</strong>? This action cannot be undone.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete Scenario
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}