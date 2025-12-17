/**
 * Range Whisker - Compact uncertainty visualization
 * Shows P10-P90 range with P50 tick mark
 */

import { useState } from 'react';
import { Info } from 'lucide-react';

interface RangeWhiskerProps {
  p10: number;
  p50: number;
  p90: number;
  format?: 'currency' | 'number' | 'percentage';
  showChip?: boolean;
  compact?: boolean;
}

export function RangeWhisker({ p10, p50, p90, format = 'currency', showChip = true, compact = false }: RangeWhiskerProps) {
  const [showDetails, setShowDetails] = useState(false);

  const formatValue = (value: number): string => {
    switch (format) {
      case 'currency':
        return value >= 1000000 
          ? `$${(value / 1000000).toFixed(1)}M`
          : value >= 1000 
          ? `$${(value / 1000).toFixed(0)}K`
          : `$${value.toFixed(0)}`;
      case 'percentage':
        return `${value.toFixed(0)}%`;
      case 'number':
        return value.toFixed(2);
      default:
        return value.toString();
    }
  };

  // Calculate P50 position (0-100%)
  const range = p90 - p10;
  const p50Position = range > 0 ? ((p50 - p10) / range) * 100 : 50;

  // Calculate uncertainty level
  const uncertainty = range > 0 ? (p90 - p10) / p50 : 0;
  const uncertaintyLevel = uncertainty < 1 ? 'Low' : uncertainty < 3 ? 'Med' : 'High';

  return (
    <div className="inline-flex flex-col gap-1">
      {/* Main value (P50) */}
      <div className="flex items-center gap-2">
        <span className="text-slate-900 font-mono">{formatValue(p50)}</span>
        {showChip && (
          <button
            onClick={() => setShowDetails(!showDetails)}
            onMouseEnter={() => !compact && setShowDetails(true)}
            onMouseLeave={() => !compact && setShowDetails(false)}
            className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded hover:bg-slate-200 transition-colors flex items-center gap-1"
          >
            <span className="opacity-70">±</span>
            <span className="opacity-70">{uncertaintyLevel}</span>
            <Info className="w-3 h-3 opacity-50" />
          </button>
        )}
      </div>

      {/* Whisker visualization */}
      <div className="relative w-32 h-1.5 group">
        {/* Background line (P10-P90) */}
        <div className="absolute inset-0 bg-slate-200 rounded-full" />
        
        {/* P50 tick mark */}
        <div 
          className="absolute top-0 bottom-0 w-0.5 bg-slate-600 rounded-full"
          style={{ left: `${p50Position}%` }}
        />
        
        {/* End caps */}
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-slate-300 rounded-l-full" />
        <div className="absolute right-0 top-0 bottom-0 w-1 bg-slate-300 rounded-r-full" />

        {/* Hover tooltip */}
        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          <div className="bg-slate-900 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
            P10: {formatValue(p10)} | P50: {formatValue(p50)} | P90: {formatValue(p90)}
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {showDetails && (
        <div className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="flex justify-between items-center">
            <span className="text-slate-600">P10 (optimistic)</span>
            <span className="font-mono text-slate-900">{formatValue(p10)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-600">P50 (median)</span>
            <span className="font-mono text-slate-900">{formatValue(p50)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-600">P90 (pessimistic)</span>
            <span className="font-mono text-slate-900">{formatValue(p90)}</span>
          </div>
          <div className="pt-2 border-t border-slate-200">
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Spread</span>
              <span className="text-slate-700">{uncertaintyLevel}</span>
            </div>
          </div>
          <div className="text-slate-500 text-[10px] leading-tight pt-1 border-t border-slate-200">
            We fit a distribution from P10/P50/P90. The whisker shows P10–P90; the tick marks P50.
          </div>
        </div>
      )}
    </div>
  );
}
