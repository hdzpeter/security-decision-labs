import { useState, useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import { fairApi, IrisLmBenchmarkResponse } from '@/utils/fairApi.ts';

interface BenchmarkInsightsLMProps {
  industry: string;
  revenueTier?: string;
  scenarioType?: string;
  currency: string;
}

type ErrorState = 'offline' | 'no_data' | null;

export function BenchmarkInsightsLM({
  industry,
  revenueTier,
  scenarioType,
  currency,
}: BenchmarkInsightsLMProps) {
  const [data, setData] = useState<IrisLmBenchmarkResponse | null>(null);
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

        const result = await fairApi.getIrisLMBenchmarks(industry, revenueTier);

        if (!result) {
          setData(null);
          setError('offline');
          return;
        }

        const hasAny =
          !!(
            (result.industry &&
              (result.industry.median !== undefined ||
                result.industry.p95 !== undefined)) ||
            (result.revenue &&
              (result.revenue.median !== undefined ||
                result.revenue.p95 !== undefined)) ||
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

  // Don’t render anything while loading
  if (loading) {
    return null;
  }

  // Don’t render if risk_service is offline
  if (error === 'offline') {
    return null;
  }

  // Show "no insights available" message
  if (error === 'no_data' || !data) {
    if (!hasInputs) return null;

    return (
      <div className="border border-slate-300 rounded-lg p-4 bg-slate-50">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm text-slate-700 mb-1">Industry Benchmarks</h4>
            <p className="text-xs text-slate-600">
              No IRIS loss magnitude benchmark data available for{' '}
              <strong>{industry}</strong>
              {revenueTier && <> and revenue tier &quot;{revenueTier}&quot;</>}
              {scenarioType && <> (scenario type &quot;{scenarioType}&quot;)</>}.
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Benchmark insights will appear here when available from the IRIS
              research library.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const formatCurrency = (value?: number) => {
    if (value === undefined || value === null) return null;
    return `${currency} ${value.toLocaleString()}`;
  };

  const items: {
    key: string;
    label: string;
    contextLabel: string;
    median?: number;
    p95?: number;
    source?: string;
  }[] = [];

  if (data.industry) {
    items.push({
      key: 'industry',
      label: 'Industry benchmark',
      contextLabel: industry,
      median: data.industry.median,
      p95: data.industry.p95,
      source: data.industry.source,
    });
  }

  if (data.revenue && revenueTier) {
    items.push({
      key: 'revenue',
      label: 'Revenue-tier benchmark',
      contextLabel: revenueTier,
      median: data.revenue.median,
      p95: data.revenue.p95,
      source: data.revenue.source,
    });
  }

  items.push({
    key: 'overall',
    label: 'Overall baseline',
    contextLabel: 'All sectors',
    median: data.overall_baseline.median,
    p95: data.overall_baseline.p95,
    source: data.overall_baseline.source,
  });

  return (
    <div className="border border-amber-300 rounded-lg p-4 bg-amber-50">
      <div className="flex items-start gap-2 mb-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm text-amber-900 mb-1">
            IRIS 2025 Loss Magnitude Benchmarks (Reference Only)
          </h4>
          <p className="text-xs text-amber-800 mb-3">
            These are not your inputs; use them to sanity-check your loss
            magnitude ranges against observed incident data. Values are reported
            in 2024 USD.
          </p>
        </div>
      </div>

      {items.map((item) => {
        const medianLabel = formatCurrency(item.median);
        const p95Label = formatCurrency(item.p95);

        return (
          <div
            key={item.key}
            className="bg-white rounded-lg p-3 border border-amber-200 mb-3 last:mb-0"
          >
            <div className="text-xs text-slate-600 mb-2">
              <strong>{item.label}:</strong> {item.contextLabel}
              {scenarioType && item.key === 'industry' && (
                <> • {scenarioType}</>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs mb-3">
              {medianLabel && (
                <div>
                  <span className="text-slate-500">Median loss magnitude:</span>{' '}
                  <span className="text-slate-900">≈ {medianLabel}</span>
                </div>
              )}
              {p95Label && (
                <div>
                  <span className="text-slate-500">95th percentile:</span>{' '}
                  <span className="text-slate-900">≈ {p95Label}</span>
                </div>
              )}
            </div>

            <div className="text-xs text-slate-500 mb-2">
              <strong>Source:</strong> {item.source || 'IRIS 2025'}
            </div>

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