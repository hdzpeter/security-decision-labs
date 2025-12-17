import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { fairApi, IrisLefBenchmarkResponse } from '@/utils/fairApi.ts';

interface BenchmarkInsightsLEFProps {
  industry: string;
  revenueTier?: string;
}

type ErrorState = 'offline' | 'no_data' | null;

export function BenchmarkInsightsLEF({
  industry,
  revenueTier,
}: BenchmarkInsightsLEFProps) {
  const [data, setData] = useState<IrisLefBenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState>(null);

  const hasInputs = Boolean(industry || revenueTier);

  useEffect(() => {
    if (!hasInputs) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    const fetchBenchmarks = async () => {
      try {
        setLoading(true);
        setError(null);

        const result = await fairApi.getIrisLEFBenchmarks(industry, revenueTier);

        if (!result) {
          setData(null);
          setError('offline');
          return;
        }

        const hasAny =
          !!(
            (result.industry &&
              result.industry.probability !== undefined &&
              result.industry.probability !== null) ||
            (result.revenue &&
              result.revenue.probability !== undefined &&
              result.revenue.probability !== null) ||
            result.overall_baseline
          );

        if (!hasAny) {
          setData(null);
          setError('no_data');
        } else {
          setData(result);
          setError(null);
        }
      } catch {
        setData(null);
        setError('offline');
      } finally {
        setLoading(false);
      }
    };

    fetchBenchmarks();
  }, [industry, revenueTier, hasInputs]);

  if (loading) return null;
  if (error === 'offline') return null;

  if (error === 'no_data' || !data) {
    if (!hasInputs) return null;

    return (
      <div className="border border-slate-300 rounded-lg p-4 bg-slate-50">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm text-slate-700 mb-1">
              LEF Benchmarks (Annual Probability)
            </h4>
            <p className="text-xs text-slate-600">
              No IRIS LEF benchmark data available for{' '}
              <strong>{industry}</strong>
              {revenueTier && <> and revenue tier &quot;{revenueTier}&quot;</>}.
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Continue with SME estimates for Threat Event Frequency and
              Susceptibility. Benchmarks will appear here when available.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const toPercent = (value?: number | null, digits = 1) =>
    value === null || value === undefined ? null : (value * 100).toFixed(digits);

  const formatRange = (range?: [number, number]) => {
    if (!range || range.length !== 2) return null;
    const [low, high] = range;
    const lowPct = toPercent(low);
    const highPct = toPercent(high);
    if (lowPct === null || highPct === null) return null;
    return `${lowPct}–${highPct}%`;
  };

  const items: {
    key: string;
    label: string;
    contextLabel: string;
    probability?: number | null;
    range?: [number, number];
    confidence?: string;
    source?: string;
    description?: string;
    note?: string;
  }[] = [];

  if (data.industry) {
    items.push({
      key: 'industry',
      label: 'Industry benchmark',
      contextLabel: industry,
      probability: data.industry.probability,
      range: data.industry.range,
      confidence: data.industry.confidence,
      source: data.industry.source,
      description: data.industry.description,
      note: data.industry.note,
    });
  }

  if (data.revenue && revenueTier) {
    items.push({
      key: 'revenue',
      label: 'Revenue-tier benchmark',
      contextLabel: revenueTier,
      probability: data.revenue.probability,
      range: data.revenue.range,
      confidence: data.revenue.confidence,
      source: data.revenue.source,
      description: data.revenue.description,
      note: data.revenue.note,
    });
  }

  items.push({
    key: 'overall',
    label: 'Overall baseline',
    contextLabel: 'All sectors',
    probability: data.overall_baseline.probability,
    range: undefined,
    confidence: undefined,
    source: data.overall_baseline.source,
    description:
      'Overall annual probability of a loss event across all sectors.',
    note: undefined,
  });

  return (
    <div className="border border-amber-300 rounded-lg p-4 bg-amber-50">
      <div className="flex items-start gap-2 mb-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm text-amber-900 mb-1">
            IRIS 2025 LEF Benchmarks (Reference Only)
          </h4>
          <p className="text-xs text-amber-800">
            These are not your inputs; use them to sanity-check your Threat
            Event Frequency and Susceptibility ranges against observed incident
            data.
          </p>
        </div>
      </div>

      {items.map((item) => {
        const probPct = toPercent(item.probability);
        const rangeLabel = formatRange(item.range);

        return (
          <div
            key={item.key}
            className="bg-white rounded-lg p-3 border border-amber-200 mb-3 last:mb-0"
          >
            <div className="text-xs text-slate-600 mb-2">
              <strong>{item.label}:</strong> {item.contextLabel}
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs mb-3">
              {probPct !== null && (
                <div>
                  <span className="text-slate-500">
                    Annual probability of loss event:
                  </span>{' '}
                  <span className="text-slate-900">≈ {probPct}%</span>
                </div>
              )}

              {rangeLabel && (
                <div>
                  <span className="text-slate-500">
                    Typical range (annual probability):
                  </span>{' '}
                  <span className="text-slate-900">{rangeLabel}</span>
                </div>
              )}

              {item.confidence && (
                <div>
                  <span className="text-slate-500">Confidence:</span>{' '}
                  <span className="text-slate-900">{item.confidence}</span>
                </div>
              )}
            </div>

            {item.description && (
              <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-2 mb-2">
                {item.description}
              </div>
            )}

            <div className="text-xs text-slate-500 mb-2">
              <strong>Source:</strong> {item.source || 'IRIS 2025'}
            </div>

            {item.note && (
              <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-2 mb-2">
                {item.note}
              </div>
            )}

            <div className="pt-2 border-t border-amber-200 flex gap-2">
              <button className="text-xs text-amber-700 hover:text-amber-900 underline">
                View source
              </button>
              <button className="text-xs text-amber-700 hover:text-amber-900 underline">
                Pin to evidence
              </button>
              <button className="text-xs text-amber-700 hover:text-amber-900 underline">
                Add note
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}