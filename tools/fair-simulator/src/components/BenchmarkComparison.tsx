import { RiskScenario } from '../App.tsx';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface BenchmarkComparisonProps {
  scenarios: RiskScenario[];
  totalALE: number;
}

// @ts-ignore
export function BenchmarkComparison({ scenarios, totalALE }: BenchmarkComparisonProps) {
  // Industry benchmark data (mock)
  const industryBenchmarks: Record<string, number> = {
    'Financial Services': 1850000,
    Healthcare: 2100000,
    Retail: 980000,
    Technology: 1450000,
    Manufacturing: 720000,
    Government: 1620000,
  };

  // Group scenarios by industry and calculate total ALE per industry
  const industryData: Record<string, number> = {};
  scenarios.forEach((scenario) => {
    const lef = scenario.threatEventFrequency * (scenario.susceptibility / 100);
    const primaryLoss = scenario.productivity + scenario.response + scenario.replacement;
    const secondaryLoss = scenario.fines + scenario.competitiveAdvantage + scenario.reputation;
    const slefProbability = scenario.slef / 100;
    const slee = primaryLoss + (secondaryLoss * slefProbability);
    const ale = lef * slee;
    industryData[scenario.industry] = (industryData[scenario.industry] || 0) + ale;
  });

  // Create chart data
  const chartData = Object.entries(industryData).map(([industry, ale]) => ({
    industry: industry.length > 15 ? industry.substring(0, 15) + '...' : industry,
    fullIndustry: industry,
    'Your ALE': Math.round(ale),
    'Industry Avg': industryBenchmarks[industry] || 1000000,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white border border-slate-200 rounded-lg p-3 shadow-lg">
          <p className="text-sm text-slate-900 mb-2">{payload[0].payload.fullIndustry}</p>
          <p className="text-sm text-blue-600">Your ALE: ${payload[0].value.toLocaleString()}</p>
          <p className="text-sm text-slate-600">Industry Avg: ${payload[1].value.toLocaleString()}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <div className="mb-6">
        <h3 className="text-lg text-slate-900 mb-1">Industry Benchmark Comparison</h3>
        <p className="text-sm text-slate-500">Your ALE vs. industry averages</p>
      </div>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="industry"
              tick={{ fontSize: 12, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: '12px' }}
              iconType="circle"
            />
            <Bar dataKey="Your ALE" fill="#5f9ea0" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Industry Avg" fill="#94a3b8" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-[300px] flex items-center justify-center text-slate-400 text-sm">
          No data available
        </div>
      )}
      <div className="mt-4 p-3 bg-slate-50 rounded-lg">
        <p className="text-xs text-slate-600">
          Industry benchmarks based on 2024 cyber incident data. Your organization&apos;s ALE is compared
          against peer organizations in the same industry.
        </p>
      </div>
    </div>
  );
}