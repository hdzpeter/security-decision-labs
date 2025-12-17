import { useState, useEffect } from 'react';
import { RiskScenario } from '../App.tsx';
import { Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Scatter, ComposedChart, Legend } from 'recharts';

const COLORS = ['#64748b', '#94a3b8', '#475569', '#6b7280', '#71717a', '#78716c', '#737373', '#52525b'];

// @ts-ignore
const API_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ScenarioListProps {
  scenarios: RiskScenario[];
  onSelectScenario: (scenario: RiskScenario) => void;
}

type IndustryBenchmark = {
  median: number;
  p95?: number;
};

const DEFAULT_IRIS_MEDIAN = 603000; // IRIS 2025 overall baseline

export function ScenarioList({ scenarios, onSelectScenario }: ScenarioListProps) {
  const [benchmarks, setBenchmarks] = useState<Record<string, IndustryBenchmark>>({});
  const [loadingBenchmarks, setLoadingBenchmarks] = useState(false);

  useEffect(() => {
    async function fetchBenchmarks() {
      setLoadingBenchmarks(true);
      try {
        // Get unique industries from scenarios
        const uniqueIndustries = [...new Set(scenarios.map(s => s.industry))];

        // Fetch LM benchmarks for each industry from IRIS 2025
        const benchmarkPromises = uniqueIndustries.map(async (industry) => {
          try {
            const response = await fetch(
                `${API_BASE_URL}/api/benchmarks/lm?industry=${encodeURIComponent(industry)}`
            );
            const result = await response.json();

            // if (result.success && result.data.industry) {
            //   return {
            //     industry,
            //     median: result.data.industry.median,
            //   };
            // }
            const lm = result.industry || result.overall_baseline || null;

            if (lm && typeof lm.median === 'number') {
              return {
                industry,
                median: lm.median,
                p95: typeof lm.p95 === 'number' ? lm.p95 : undefined,
              };
            }
            // Fallback to IRIS 2025 overall baseline
            return {
              industry,
              median: result.data.overall_baseline?.median || 603000,
            };
          } catch (err) {
            console.error(`Failed to fetch benchmark for ${industry}:`, err);
            // Use IRIS 2025 overall baseline as fallback
            return {
              industry,
              median: 603000, // IRIS 2025 overall median
            };
          }
        });

        const results = await Promise.all(benchmarkPromises);

        const benchmarkMap = results.reduce((acc, { industry, median }) => {
          acc[industry] = median;
          return acc;
        }, {} as Record<string, number>);

        // @ts-ignore
          setBenchmarks(benchmarkMap);
      } catch (error) {
        console.error('Failed to fetch benchmarks:', error);
        // Use IRIS 2025 overall baseline as ultimate fallback
        const fallback = scenarios.reduce((acc, scenario) => {
          acc[scenario.industry] = 603000; // IRIS 2025 overall median
          return acc;
        }, {} as Record<string, number>);
        // @ts-ignore
          setBenchmarks(fallback);
      } finally {
        setLoadingBenchmarks(false);
      }
    }

    if (scenarios.length > 0) {
      fetchBenchmarks();
    }
  }, [scenarios]);

  // Get industry benchmark - use median LM from IRIS 2025
  // const getIndustryBenchmark = (scenario: RiskScenario): number => {
  //   return benchmarks[scenario.industry] || 603000; // IRIS 2025 overall median
  // };

  const getIndustryBenchmark = (scenario: RiskScenario): IndustryBenchmark => {
    const b = benchmarks[scenario.industry];
    if (b && typeof b.median === 'number') {
        return b;
    }
    return { median: DEFAULT_IRIS_MEDIAN };
  };

  // Calculate metrics for each scenario
  const chartData = scenarios.map((scenario, index) => {
    const lef = scenario.threatEventFrequency * (scenario.susceptibility / 100);
    const primaryLoss = scenario.productivity + scenario.response + scenario.replacement;
    const secondaryLoss = scenario.fines + scenario.competitiveAdvantage + scenario.reputation;
    const slefProbability = scenario.slef / 100;
    const slee = primaryLoss + (secondaryLoss * slefProbability);
    const ale = lef * slee;
    const industryBenchmark = getIndustryBenchmark(scenario);

    return {
      name: scenario.name.length > 20 ? scenario.name.substring(0, 20) + '...' : scenario.name,
      fullName: scenario.name,
      industry: scenario.industry,
      lef: parseFloat(lef.toFixed(2)),
      ale: Math.round(ale),
      benchmark: industryBenchmark.median,      // for the scatter & difference
      benchmarkP95:
        typeof industryBenchmark.p95 === 'number' ? industryBenchmark.p95 : null,
      scenario,
      color: COLORS[index % COLORS.length],
    };
  });

  return (
    <div className="space-y-6">
      {/* Scenario Risk Exposure */}
      <div className="bg-white border border-slate-200 rounded-xl p-8">
        <div className="mb-6">
          <h2 className="text-lg text-slate-900 mb-1">Scenario Risk Exposure</h2>
          <p className="text-sm text-slate-500">
            Annual loss exposure per scenario with IRIS 2025 industry benchmarks - click to view details
          </p>
        </div>
          {loadingBenchmarks && (
            <div className="mb-4 text-xs text-slate-500">
                Fetching IRIS 2025 industry benchmarks…
            </div>
          )}

        {scenarios.length === 0 ? (
          <div className="text-center py-16 text-slate-400">
            <p className="text-sm">No scenarios yet. Create your first risk scenario to see exposure analysis.</p>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(300, scenarios.length * 80)}>
              <ComposedChart
                data={chartData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={true} vertical={false} />
                <XAxis
                  type="number"
                  stroke="#94A3B8"
                  label={{ value: 'Annual Loss Exposure ($)', position: 'insideBottom', offset: -5, style: { fontSize: 12 } }}
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}K`}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  stroke="#64748b"
                  width={180}
                  tick={{ fontSize: 13 }}
                />
                <Tooltip
  cursor={{ fill: '#F8FAFC' }}
  content={({ active, payload }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;

      const ale =
        typeof data.ale === 'number' ? data.ale : 0;
      const benchmark =
        typeof data.benchmark === 'number' ? data.benchmark : DEFAULT_IRIS_MEDIAN;
      const benchmarkP95 =
        typeof data.benchmarkP95 === 'number' ? data.benchmarkP95 : null;

      const difference = ale - benchmark;
      const percentDiff =
        benchmark > 0 ? ((difference / benchmark) * 100).toFixed(1) : '0.0';

      return (
        <div className="bg-white border border-slate-200 shadow-lg rounded-lg p-4">
          <div className="text-sm text-slate-900 mb-1">{data.fullName}</div>
          <div className="text-xs text-slate-500 mb-2">{data.industry}</div>
          <div className="text-xs text-slate-600 space-y-1 mb-2">
            <div className="flex justify-between gap-6">
              <span>Your ALE:</span>
              <span className="text-slate-900">
                ${ale.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between gap-6">
              <span>IRIS median (P50):</span>
              <span className="text-slate-700">
                ${benchmark.toLocaleString()}
              </span>
            </div>
            {benchmarkP95 !== null && (
              <div className="flex justify-between gap-6">
                <span>IRIS 95th percentile:</span>
                <span className="text-slate-700">
                  ${benchmarkP95.toLocaleString()}
                </span>
              </div>
            )}
            <div className="flex justify-between gap-6 pt-1 border-t border-slate-200">
              <span>Difference vs median:</span>
              <span className={difference > 0 ? 'text-slate-800' : 'text-slate-600'}>
                {difference > 0 ? '+' : ''}
                {percentDiff}%
              </span>
            </div>
          </div>
          <div className="text-xs text-slate-500 border-t border-slate-200 pt-2">
            Click to view details →
          </div>
        </div>
      );
    }
    return null;
  }}
/>
                <Legend
                  wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}
                  iconType="circle"
                />
                <Bar
                  dataKey="ale"
                  name="Your ALE"
                  radius={[0, 4, 4, 0]}
                  onClick={(data) => onSelectScenario(data.scenario)}
                  cursor="pointer"
                >
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.color}
                      className="hover:opacity-70 transition-opacity"
                    />
                  ))}
                </Bar>
                <Scatter
                  dataKey="benchmark"
                  name="IRIS 2025 Benchmark"
                  fill="#0EABA9"
                  shape="circle"
                  r={6}
                />
              </ComposedChart>
            </ResponsiveContainer>

            <div className="mt-4 p-3 bg-slate-50 rounded-lg">
              <p className="text-xs text-slate-600">
                <strong>IRIS 2025 benchmarks</strong> (turquoise dots) show typical loss magnitude values
                for incidents in each sector based on 150,000+ real-world cyber events (2008-2024).
                Bars extending beyond the benchmark indicate higher-than-average loss estimates.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}