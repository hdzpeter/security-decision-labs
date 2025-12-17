import { Info, CheckCircle, AlertTriangle } from 'lucide-react';
import { RangeEstimationInput } from './RangeEstimationInput.tsx';
import { BenchmarkInsightsLM } from './BenchmarkInsightsLM.tsx';

interface LMStepProps {
  formData: {
    productivityP10: number;
    productivityP50: number;
    productivityP90: number;
    responseP10: number;
    responseP50: number;
    responseP90: number;
    replacementP10: number;
    replacementP50: number;
    replacementP90: number;
    finesP10: number;
    finesP50: number;
    finesP90: number;
    competitiveAdvantageP10: number;
    competitiveAdvantageP50: number;
    competitiveAdvantageP90: number;
    reputationP10: number;
    reputationP50: number;
    reputationP90: number;
    slefP10: number;
    slefP50: number;
    slefP90: number;
    currency: string;
    industry: string;
  };
  setFormData: (data: any) => void;
}

export function LMStep({ formData, setFormData }: LMStepProps) {
  const calculatePrimaryLoss = (percentile: 'p10' | 'p50' | 'p90') => {
    const suffix = percentile === 'p10' ? 'P10' : percentile === 'p50' ? 'P50' : 'P90';
    return (
      (formData[`productivity${suffix}` as keyof typeof formData] as number || 0) +
      (formData[`response${suffix}` as keyof typeof formData] as number || 0) +
      (formData[`replacement${suffix}` as keyof typeof formData] as number || 0)
    );
  };

  const calculateSecondaryLoss = (percentile: 'p10' | 'p50' | 'p90') => {
    const suffix = percentile === 'p10' ? 'P10' : percentile === 'p50' ? 'P50' : 'P90';
    return (
      (formData[`fines${suffix}` as keyof typeof formData] as number || 0) +
      (formData[`competitiveAdvantage${suffix}` as keyof typeof formData] as number || 0) +
      (formData[`reputation${suffix}` as keyof typeof formData] as number || 0)
    );
  };

  const calculateLossMagnitude = (percentile: 'p10' | 'p50' | 'p90') => {
    const suffix = percentile === 'p10' ? 'P10' : percentile === 'p50' ? 'P50' : 'P90';
    const primary = calculatePrimaryLoss(percentile);
    const secondary = calculateSecondaryLoss(percentile);
    const slefProb = (formData[`slef${suffix}` as keyof typeof formData] as number || 0) / 100;
    return primary + (secondary * slefProb);
  };

  const getValidationChecks = () => {
    const checks = [];
    
    // Check if at least one loss form has values
    const hasAnyLoss = 
      formData.productivityP50 > 0 ||
      formData.responseP50 > 0 ||
      formData.replacementP50 > 0 ||
      formData.finesP50 > 0 ||
      formData.competitiveAdvantageP50 > 0 ||
      formData.reputationP50 > 0;
    
    if (hasAnyLoss) {
      checks.push({ label: 'At least one loss form estimated', status: 'pass' });
    } else {
      checks.push({ label: 'At least one loss form must be estimated', status: 'fail' });
    }

    // Check SLEF if secondary losses exist
    const hasSecondaryLoss = 
      formData.finesP50 > 0 ||
      formData.competitiveAdvantageP50 > 0 ||
      formData.reputationP50 > 0;

    if (hasSecondaryLoss) {
      if (formData.slefP50 > 0 && formData.slefP10 <= formData.slefP50 && formData.slefP50 <= formData.slefP90) {
        checks.push({ label: 'SLEF properly estimated for secondary losses', status: 'pass' });
      } else {
        checks.push({ label: 'SLEF must be estimated when secondary losses exist', status: 'fail' });
      }
    }

    return checks;
  };

  const checks = getValidationChecks();
  const allChecksPass = checks.every(c => c.status === 'pass');

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl text-slate-900 mb-2">Loss Magnitude (per Event) — Range Estimation</h2>
        <p className="text-slate-600 mb-1">
          <strong>Expected cost when this scenario occurs once</strong>
        </p>
        <p className="text-xs text-slate-500">
          Units: <span className="text-slate-700">{formData.currency} (constant, base year 2024)</span>
        </p>
      </div>

      <div className="bg-amber-50 border border-amber-300 rounded-lg p-4">
        <div className="text-sm text-amber-900">
          <strong>Estimating loss magnitudes:</strong>
          <p className="mt-1">
            Think in terms of "if this scenario happens once." Use P10 (optimistic), P50 (most likely), P90 (pessimistic). The tool will fit distributions (typically lognormal or PERT) from your percentile estimates. FAIR explicitly uses this calibrated estimation approach.
          </p>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="text-sm text-blue-900">
          <strong>The 6 Forms of Loss (FAIR taxonomy):</strong>
          <div className="mt-2 space-y-2 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div><strong>Primary Loss Forms:</strong></div>
              <div><strong>Secondary Loss Forms:</strong></div>
              <div className="text-slate-700">Direct, first-party costs</div>
              <div className="text-slate-700">External stakeholder reactions</div>
              <div>• Productivity</div>
              <div>• Fines & Judgments</div>
              <div>• Response*</div>
              <div>• Competitive Advantage</div>
              <div>• Replacement</div>
              <div>• Reputation</div>
            </div>
            <div className="text-xs text-slate-600 bg-white border border-blue-200 rounded p-2 mt-2">
              <strong>*Note:</strong> Response costs can be primary (e.g., internal IR time) or secondary (e.g., litigation-driven investigation costs) depending on what drives the spend. Any form can be $0 for a given scenario.
            </div>
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mt-2">
              <strong>Avoid double-counting:</strong> Don't put the same expense in multiple forms (e.g., forensics goes in Response, not also in Reputation). This taxonomy exists precisely to prevent overlaps.
            </div>
          </div>
        </div>
      </div>

      {/* Primary Loss Forms */}
      <div className="border border-blue-300 rounded-lg p-5 bg-blue-50/30">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-blue-600"></div>
          <h3 className="text-slate-900">Primary Loss Forms</h3>
          <span className="text-xs text-slate-500">(Direct, first-party costs)</span>
        </div>

        <div className="space-y-6">
          <RangeEstimationInput
            label="Productivity Loss"
            description="Lost business productivity during and after the incident"
            p10={formData.productivityP10}
            p50={formData.productivityP50}
            p90={formData.productivityP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                productivityP10: p10, 
                productivityP50: p50, 
                productivityP90: p90,
                productivity: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: Staff hours lost, revenue lost during downtime, delayed projects. Think 'per incident' not annualized."
          />

          <RangeEstimationInput
            label="Response Cost"
            description="Incident response, investigation, and remediation costs"
            p10={formData.responseP10}
            p50={formData.responseP50}
            p90={formData.responseP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                responseP10: p10, 
                responseP50: p50, 
                responseP90: p90,
                response: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: IR team hours, forensics, external consultants, emergency patching, overtime, war room costs."
          />

          <RangeEstimationInput
            label="Replacement Cost"
            description="Cost to replace or restore compromised assets"
            p10={formData.replacementP10}
            p50={formData.replacementP50}
            p90={formData.replacementP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                replacementP10: p10, 
                replacementP50: p50, 
                replacementP90: p90,
                replacement: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: Hardware replacement, software re-licensing, data restoration from backups, rebuild costs."
          />
        </div>

        {/* Primary Loss Summary */}
        {calculatePrimaryLoss('p50') > 0 && (
          <div className="mt-6 bg-white border border-blue-200 rounded-lg p-4">
            <div className="text-sm text-slate-600 mb-3">Primary Loss Subtotal</div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-slate-500 mb-1">P10 (low)</div>
                <div className="text-base text-green-600">
                  {formData.currency} {calculatePrimaryLoss('p10').toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">P50 (median)</div>
                <div className="text-base text-blue-600">
                  {formData.currency} {calculatePrimaryLoss('p50').toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">P90 (high)</div>
                <div className="text-base text-red-600">
                  {formData.currency} {calculatePrimaryLoss('p90').toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Secondary Loss Forms */}
      <div className="border border-purple-300 rounded-lg p-5 bg-purple-50/30">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-purple-600"></div>
          <h3 className="text-slate-900">Secondary Loss Forms</h3>
          <span className="text-xs text-slate-500">(External reactions—conditional)</span>
        </div>

        <div className="bg-purple-100 border border-purple-300 rounded-lg p-4 mb-6">
          <div className="text-sm text-purple-900 mb-3">
            <strong>Secondary Loss Event Frequency (SLEF)</strong>
          </div>
          <p className="text-xs text-purple-800 mb-4">
            Probability that secondary losses occur for this scenario. External stakeholders (regulators, customers, competitors) don't react to every incident—estimate the % of events where they do. SLEF can vary by stakeholder or loss form in advanced modeling, but a single scenario-level SLEF is fine for most analyses.
          </p>

          <RangeEstimationInput
            label="SLEF (Probability that secondary losses occur for this scenario)"
            description="% of loss events that trigger regulatory/customer/market reactions"
            p10={formData.slefP10}
            p50={formData.slefP50}
            p90={formData.slefP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                slefP10: p10, 
                slefP50: p50, 
                slefP90: p90,
                slef: p50 // Sync median
              });
            }}
            unit="%"
            distributionType="pert"
            min={0}
            max={100}
            isProbability={true}
            helpText="Consider: Breach notification laws, likelihood of regulatory action, customer churn probability, media attention. 0% = secondary losses never occur; 100% = they always occur."
          />
        </div>

        <div className="space-y-6">
          <RangeEstimationInput
            label="Fines & Judgments"
            description="Regulatory fines, legal settlements, and judgment costs"
            p10={formData.finesP10}
            p50={formData.finesP50}
            p90={formData.finesP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                finesP10: p10, 
                finesP50: p50, 
                finesP90: p90,
                fines: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: GDPR/CCPA penalties, class action settlements, regulatory enforcement. Research actual fine amounts for similar breaches."
          />

          <RangeEstimationInput
            label="Competitive Advantage Loss"
            description="Loss of competitive position, market share, or intellectual property value"
            p10={formData.competitiveAdvantageP10}
            p50={formData.competitiveAdvantageP50}
            p90={formData.competitiveAdvantageP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                competitiveAdvantageP10: p10, 
                competitiveAdvantageP50: p50, 
                competitiveAdvantageP90: p90,
                competitiveAdvantage: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: Customers switching to competitors, stolen trade secrets used by rivals, lost deals, market cap impact."
          />

          <RangeEstimationInput
            label="Reputation Damage"
            description="Brand damage, loss of customer trust, and long-term revenue impact"
            p10={formData.reputationP10}
            p50={formData.reputationP50}
            p90={formData.reputationP90}
            onChange={(p10, p50, p90) => {
              setFormData({ 
                ...formData, 
                reputationP10: p10, 
                reputationP50: p50, 
                reputationP90: p90,
                reputation: p50 // Sync median
              });
            }}
            unit={` ${formData.currency}`}
            distributionType="lognormal"
            min={0}
            helpText="Consider: Customer lifetime value lost, increased customer acquisition costs, brand perception surveys, insurance premium increases."
          />
        </div>

        {/* Secondary Loss Summary */}
        {calculateSecondaryLoss('p50') > 0 && formData.slefP50 > 0 && (
          <div className="mt-6 bg-white border border-purple-200 rounded-lg p-4">
            <div className="text-sm text-slate-600 mb-3">Secondary Loss Subtotal (before SLEF adjustment)</div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-slate-500 mb-1">P10 (low)</div>
                <div className="text-base text-green-600">
                  {formData.currency} {calculateSecondaryLoss('p10').toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">P50 (median)</div>
                <div className="text-base text-blue-600">
                  {formData.currency} {calculateSecondaryLoss('p50').toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">P90 (high)</div>
                <div className="text-base text-red-600">
                  {formData.currency} {calculateSecondaryLoss('p90').toLocaleString()}
                </div>
              </div>
            </div>
            <div className="mt-3 text-xs text-slate-500">
              These values will be multiplied by SLEF ({formData.slefP10}%/{formData.slefP50}%/{formData.slefP90}%) in LM calculation
            </div>
          </div>
        )}
      </div>

      {/* Validation Checks */}
      <div className="border border-blue-300 rounded-lg p-4 bg-blue-50">
        <div className="flex items-center gap-2 mb-3">
          <Info className="w-4 h-4 text-blue-600" />
          <h4 className="text-sm text-blue-900">Validation Checks</h4>
        </div>

        <div className="space-y-2">
          {checks.map((check, index) => (
            <div key={index} className="flex items-center gap-2">
              {check.status === 'pass' ? (
                <CheckCircle className="w-4 h-4 text-green-600" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-600" />
              )}
              <span className={`text-xs ${check.status === 'pass' ? 'text-green-700' : 'text-amber-700'}`}>
                {check.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Loss Magnitude Calculation */}
      {allChecksPass && calculateLossMagnitude('p50') > 0 && (
        <div className="bg-gradient-to-br from-blue-50 to-purple-50 rounded-lg p-6 border-2 border-blue-300">
          <div className="text-base text-slate-900 mb-4">
            <strong>Loss Magnitude (LM) per Event</strong>
          </div>

          <div className="bg-white rounded-lg p-4 mb-4">
            <div className="text-sm text-slate-600 mb-3">LM Calculation Formula:</div>
            <div className="text-xs font-mono text-slate-700 bg-slate-50 p-3 rounded border border-slate-200">
              LM = Σ Primary + (SLEF × Σ Secondary)
            </div>
            <div className="text-xs text-slate-500 mt-2">
              This calculates the expected loss per event, combining direct costs with probability-weighted external reactions.
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white rounded-lg p-4 border-2 border-green-300">
              <div className="text-xs text-slate-500 mb-2">P10 (optimistic)</div>
              <div className="text-xl text-green-600">
                {formData.currency} {calculateLossMagnitude('p10').toLocaleString()}
              </div>
              <div className="text-xs text-slate-500 mt-2">
                {calculatePrimaryLoss('p10').toLocaleString()} + ({calculateSecondaryLoss('p10').toLocaleString()} × {formData.slefP10}%)
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 border-2 border-blue-400">
              <div className="text-xs text-slate-500 mb-2">P50 (median)</div>
              <div className="text-xl text-blue-600">
                {formData.currency} {calculateLossMagnitude('p50').toLocaleString()}
              </div>
              <div className="text-xs text-slate-500 mt-2">
                {calculatePrimaryLoss('p50').toLocaleString()} + ({calculateSecondaryLoss('p50').toLocaleString()} × {formData.slefP50}%)
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 border-2 border-red-300">
              <div className="text-xs text-slate-500 mb-2">P90 (pessimistic)</div>
              <div className="text-xl text-red-600">
                {formData.currency} {calculateLossMagnitude('p90').toLocaleString()}
              </div>
              <div className="text-xs text-slate-500 mt-2">
                {calculatePrimaryLoss('p90').toLocaleString()} + ({calculateSecondaryLoss('p90').toLocaleString()} × {formData.slefP90}%)
              </div>
            </div>
          </div>

          <div className="mt-4 text-xs text-slate-500 text-center">
            This Loss Magnitude distribution will be combined with LEF to calculate Annual Loss Exposure (ALE)
          </div>
        </div>
      )}

      {/* Industry Benchmarks from Backend */}
      <BenchmarkInsightsLM
        industry={formData.industry}
        currency={formData.currency}
      />
    </div>
  );
}