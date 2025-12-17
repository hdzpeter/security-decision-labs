import { CheckCircle, Info, AlertTriangle } from 'lucide-react';
import { RangeEstimationInput } from './RangeEstimationInput.tsx';
import { BenchmarkInsightsLEF } from './BenchmarkInsightsLEF.tsx';

interface LEFStepProps {
  formData: {
    tefP10: number;
    tefP50: number;
    tefP90: number;
    tefModel: 'poisson' | 'lognormal';
    tefDecompose: boolean;
    contactFreqP10: number;
    contactFreqP50: number;
    contactFreqP90: number;
    probActionP10: number;
    probActionP50: number;
    probActionP90: number;
    zeroInflation: boolean;
    susceptibilityP10: number;
    susceptibilityP50: number;
    susceptibilityP90: number;
    industry: string;
    revenueTier?: string; // Add revenue tier
  };
  setFormData: (data: any) => void;
}

export function LEFStep({ formData, setFormData }: LEFStepProps) {
  const calculateLEFPercentile = (tef: number, susc: number) => {
    return tef * (susc / 100);
  };

  const getOrderBoundsCheck = () => {
    const checks = [];

    // TEF monotonicity
    if (formData.tefP10 <= formData.tefP50 && formData.tefP50 <= formData.tefP90) {
      checks.push({ label: 'TEF values are monotonic', status: 'pass' });
    } else {
      checks.push({ label: 'TEF values must be P10 ≤ P50 ≤ P90', status: 'fail' });
    }

    // Susceptibility monotonicity and bounds
    if (formData.susceptibilityP10 <= formData.susceptibilityP50 && formData.susceptibilityP50 <= formData.susceptibilityP90) {
      checks.push({ label: 'Susceptibility values are monotonic', status: 'pass' });
    } else {
      checks.push({ label: 'Susceptibility values must be P10 ≤ P50 ≤ P90', status: 'fail' });
    }

    if (formData.susceptibilityP10 >= 0 && formData.susceptibilityP90 <= 100) {
      checks.push({ label: 'Susceptibility within [0, 100]%', status: 'pass' });
    } else {
      checks.push({ label: 'Susceptibility must be within [0, 100]%', status: 'fail' });
    }

    return checks;
  };

  const checks = getOrderBoundsCheck();
  const allChecksPass = checks.every(c => c.status === 'pass');

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl text-slate-900 mb-2">Loss Event Frequency (LEF) — Range Estimation</h2>
        <p className="text-slate-600 mb-1">
          <strong>LEF = Threat Event Frequency (TEF) × Susceptibility</strong>
        </p>
        <p className="text-xs text-slate-500">
          Units: <span className="text-slate-700">events per year</span>
        </p>
      </div>

      <div className="bg-amber-50 border border-amber-300 rounded-lg p-4">
        <div className="text-sm text-amber-900">
          <strong>Why ranges (10th/50th/90th)?</strong>
          <p className="mt-1">
            Because you don't know the exact values. Use P10 ("I'd be surprised if lower"), P50 (best single guess), P90 ("I'd be surprised if higher"). The tool converts these to probability distributions and runs simulation.
          </p>
        </div>
      </div>

      {/* TEF Section */}
      <div className="border border-slate-300 rounded-lg p-5 bg-slate-50">
        <div className="mb-4">
          <h3 className="text-slate-900 mb-2">Threat Event Frequency (TEF)</h3>
          <p className="text-sm text-slate-600">
            How often do threat actors attempt this attack per year?
          </p>
        </div>

        {/* Model Selection */}
        <div className="mb-4 bg-white rounded-lg p-3 border border-slate-200">
          <label className="text-sm text-slate-700 mb-2 block">Model</label>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={formData.tefModel === 'poisson'}
                onChange={() => setFormData({ ...formData, tefModel: 'poisson' as 'poisson' | 'lognormal' })}
                className="text-blue-600"
              />
              <span className="text-sm text-slate-900">Poisson (default)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={formData.tefModel === 'lognormal'}
                onChange={() => setFormData({ ...formData, tefModel: 'lognormal' as 'poisson' | 'lognormal' })}
                className="text-blue-600"
              />
              <span className="text-sm text-slate-900">Lognormal (advanced)</span>
            </label>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Poisson models count events; use Lognormal only if your SMEs think in continuous rates.
          </p>
        </div>

        {/* Decomposition Toggle */}
        <div className="mb-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.tefDecompose}
              onChange={(e) => setFormData({ ...formData, tefDecompose: e.target.checked })}
              className="rounded text-blue-600"
            />
            <span className="text-sm text-slate-900">Decompose TEF (recommended)</span>
          </label>
          <p className="text-xs text-slate-500 mt-1 ml-6">
            Break down into: Contact Frequency × Probability of Action
          </p>
        </div>

        {!formData.tefDecompose ? (
          <RangeEstimationInput
            label="TEF Estimate"
            description="Threat event attempts per year"
            p10={formData.tefP10}
            p50={formData.tefP50}
            p90={formData.tefP90}
            onChange={(p10, p50, p90) => {
              setFormData({
                ...formData,
                tefP10: p10,
                tefP50: p50,
                tefP90: p90
              });
            }}
            unit="/year"
            distributionType={formData.tefModel}
            min={0}
            helpText="We need your judgment because: Historical counts can lag today's incentives and controls. Even rough ranges (e.g., 'between 2 and 20 per year') are useful."
          />
        ) : (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <p className="text-xs text-blue-900">
                <strong>Decomposition helps SME accuracy:</strong> Estimate how often threat actors make contact, then separately estimate the probability they take action.
              </p>
            </div>

            <RangeEstimationInput
              label="Contact Frequency"
              description="How often do threat actors make contact with your assets?"
              p10={formData.contactFreqP10}
              p50={formData.contactFreqP50}
              p90={formData.contactFreqP90}
              onChange={(p10, p50, p90) => {
                const tefP10 = p10 * (formData.probActionP10 / 100);
                const tefP50 = p50 * (formData.probActionP50 / 100);
                const tefP90 = p90 * (formData.probActionP90 / 100);
                setFormData({
                  ...formData,
                  contactFreqP10: p10,
                  contactFreqP50: p50,
                  contactFreqP90: p90,
                  tefP10,
                  tefP50,
                  tefP90
                });
              }}
              unit="/year"
              distributionType={formData.tefModel}
              min={0}
            />

            <RangeEstimationInput
              label="Probability of Action"
              description="Given contact, what's the probability they take action?"
              p10={formData.probActionP10}
              p50={formData.probActionP50}
              p90={formData.probActionP90}
              onChange={(p10, p50, p90) => {
                const tefP10 = formData.contactFreqP10 * (p10 / 100);
                const tefP50 = formData.contactFreqP50 * (p50 / 100);
                const tefP90 = formData.contactFreqP90 * (p90 / 100);
                setFormData({
                  ...formData,
                  probActionP10: p10,
                  probActionP50: p50,
                  probActionP90: p90,
                  tefP10,
                  tefP50,
                  tefP90
                });
              }}
              unit="%"
              distributionType="pert"
              min={0}
              max={100}
              isProbability={true}
            />

            {formData.contactFreqP50 > 0 && formData.probActionP50 > 0 && (
              <div className="bg-white border border-blue-200 rounded-lg p-3">
                <div className="text-xs text-slate-600 mb-2">Calculated TEF from decomposition:</div>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <div className="text-xs text-slate-500">P10</div>
                    <div className="text-slate-900">{formData.tefP10.toFixed(2)}/year</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">P50</div>
                    <div className="text-slate-900">{formData.tefP50.toFixed(2)}/year</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">P90</div>
                    <div className="text-slate-900">{formData.tefP90.toFixed(2)}/year</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Zero-inflation */}
        <div className="mt-4">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.zeroInflation}
              onChange={(e) => setFormData({ ...formData, zeroInflation: e.target.checked })}
              className="rounded text-blue-600 mt-0.5"
            />
            <div>
              <span className="text-sm text-slate-900">Some years may have zero attempts</span>
              <p className="text-xs text-slate-500 mt-1">
                Enable zero-inflation when it's plausible there are years with no attempts; otherwise TEF distributions force {'>'} 0 every year.
              </p>
            </div>
          </label>
        </div>
      </div>

      {/* Susceptibility Section */}
      <div className="border border-slate-300 rounded-lg p-5 bg-slate-50">
        <div className="mb-4">
          <h3 className="text-slate-900 mb-2">Susceptibility</h3>
          <p className="text-sm text-slate-600">
            If a threat event occurs, what's the probability it results in a loss?
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Model: PERT/Beta (bounded 0–1)
          </p>
        </div>

        <RangeEstimationInput
          label="Susceptibility Estimate"
          description="Probability that a threat event becomes a loss event"
          p10={formData.susceptibilityP10}
          p50={formData.susceptibilityP50}
          p90={formData.susceptibilityP90}
          onChange={(p10, p50, p90) => {
            setFormData({
              ...formData,
              susceptibilityP10: p10,
              susceptibilityP50: p50,
              susceptibilityP90: p90
            });
          }}
          unit="%"
          distributionType="pert"
          min={0}
          max={100}
          isProbability={true}
          helpText="Consider: Detection/prevention gaps specific to this attack type, failure modes, staffing coverage, and known blind spots."
        />
      </div>

      {/* Instant Checks */}
      <div className="border border-blue-300 rounded-lg p-4 bg-blue-50">
        <div className="flex items-center gap-2 mb-3">
          <Info className="w-4 h-4 text-blue-600" />
          <h4 className="text-sm text-blue-900">Instant Checks</h4>
        </div>

        {/* LEF Preview */}
        {formData.tefP50 > 0 && formData.susceptibilityP50 > 0 && (
          <div className="bg-white rounded-lg p-3 mb-3">
            <div className="text-xs text-slate-600 mb-2">LEF Preview (median):</div>
            <div className="text-lg text-blue-600">
              TEF<sub>P50</sub> × Susc<sub>P50</sub> = {formData.tefP50.toFixed(2)} × {formData.susceptibilityP50}% = {' '}
              <strong>{calculateLEFPercentile(formData.tefP50, formData.susceptibilityP50).toFixed(2)} events/year</strong>
            </div>
          </div>
        )}

        {/* Order/Bounds Check */}
        <div className="space-y-2">
          <div className="text-xs text-slate-600 mb-1">Order/Bounds:</div>
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

      {/* Full LEF Calculation */}
      {allChecksPass && formData.tefP50 > 0 && formData.susceptibilityP50 > 0 && (
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-300">
          <div className="text-sm text-slate-600 mb-3">Calculated Loss Event Frequency (LEF)</div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-slate-500 mb-1">P10 (low)</div>
              <div className="text-lg text-green-600">
                {calculateLEFPercentile(formData.tefP10, formData.susceptibilityP10).toFixed(2)}
              </div>
              <div className="text-xs text-slate-500">/year</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">P50 (median)</div>
              <div className="text-lg text-blue-600">
                {calculateLEFPercentile(formData.tefP50, formData.susceptibilityP50).toFixed(2)}
              </div>
              <div className="text-xs text-slate-500">/year</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">P90 (high)</div>
              <div className="text-lg text-red-600">
                {calculateLEFPercentile(formData.tefP90, formData.susceptibilityP90).toFixed(2)}
              </div>
              <div className="text-xs text-slate-500">/year</div>
            </div>
          </div>
          <div className="mt-3 text-xs text-slate-500">
            LEF = TEF × Susceptibility (calculated for each percentile)
          </div>
        </div>
      )}

      {/* IRIS 2025 Industry Benchmarks - UPDATED */}
      <BenchmarkInsightsLEF
        industry={formData.industry}
        revenueTier={formData.revenueTier}
      />
    </div>
  );
}
