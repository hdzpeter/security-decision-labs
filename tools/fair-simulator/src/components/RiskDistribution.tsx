import { RiskScenario } from '../App.tsx';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface RiskDistributionProps {
  scenarios: RiskScenario[];
  calculateALE: (scenario: RiskScenario) => number;
}

export function RiskDistribution({ scenarios, calculateALE }: RiskDistributionProps) {
  const data = scenarios.map((scenario) => ({
    name: scenario.name,
    value: calculateALE(scenario),
  }));

  const COLORS = ['#5f9ea0', '#7b68a6', '#94a3b8', '#6b9b9f', '#8b7fa8', '#64748b'];

    return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="text-lg text-slate-900 mb-6">Risk Distribution by Scenario</h3>
      {scenarios.length > 0 ? (
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${(percent * 100).toFixed(0)}%`}
              outerRadius={100}
              fill="#8884d8"
              dataKey="value"
            >_entry
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number) => `$${value.toLocaleString()}`}
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
              }}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value) => (
                <span className="text-sm text-slate-700">
                  {value.length > 25 ? value.substring(0, 25) + '...' : value}
                </span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-[300px] flex items-center justify-center text-slate-400 text-sm">
          No data available
        </div>
      )}
    </div>
  );
}