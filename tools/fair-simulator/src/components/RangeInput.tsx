/**
 * Range Input - Edit mode with P10/P50/P90, display mode with whisker
 * Progressive disclosure for uncertainty
 */

import { useState } from 'react';
import { RangeWhisker } from './RangeWhisker.tsx';

interface RangeInputProps {
  label: string;
  p10: number;
  p50: number;
  p90: number;
  onChange?: (values: { p10: number; p50: number; p90: number }) => void;
  format?: 'currency' | 'number' | 'percentage';
  disabled?: boolean;
  hint?: string;
  step?: number;
  min?: number;
  max?: number;
}

export function RangeInput({
  label,
  p10,
  p50,
  p90,
  onChange,
  format = 'currency',
  disabled = false,
  hint,
  step = 1,
  min,
  max,
}: RangeInputProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [tempValues, setTempValues] = useState({ p10, p50, p90 });

  const handleBlur = () => {
    // Validate: P10 ≤ P50 ≤ P90
    const validated = {
      p10: Math.min(tempValues.p10, tempValues.p50),
      p50: tempValues.p50,
      p90: Math.max(tempValues.p50, tempValues.p90),
    };
    
    if (onChange) {
      onChange(validated);
    }
    setIsEditing(false);
  };

  if (disabled || !onChange) {
    // Display mode only
    return (
      <div>
        <label className="block text-sm text-slate-600 mb-2">
          {label}
          {hint && <span className="text-slate-400 ml-1">({hint})</span>}
        </label>
        <div className="px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg">
          <RangeWhisker p10={p10} p50={p50} p90={p90} format={format} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <label className="block text-sm text-slate-600 mb-2">
        {label}
        {hint && <span className="text-slate-400 ml-1">({hint})</span>}
      </label>

      {isEditing ? (
        // Edit mode: Three inputs
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">P10 (low)</label>
              <input
                type="number"
                value={tempValues.p10}
                onChange={(e) => setTempValues({ ...tempValues, p10: Number(e.target.value) })}
                onBlur={handleBlur}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                step={step}
                min={min}
                max={max}
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">P50 (median)</label>
              <input
                type="number"
                value={tempValues.p50}
                onChange={(e) => setTempValues({ ...tempValues, p50: Number(e.target.value) })}
                onBlur={handleBlur}
                className="w-full px-3 py-2 border border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-blue-50"
                step={step}
                min={min}
                max={max}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">P90 (high)</label>
              <input
                type="number"
                value={tempValues.p90}
                onChange={(e) => setTempValues({ ...tempValues, p90: Number(e.target.value) })}
                onBlur={handleBlur}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                step={step}
                min={min}
                max={max}
              />
            </div>
          </div>
          <div className="text-xs text-slate-500">
            Click outside to save. P10 ≤ P50 ≤ P90 enforced automatically.
          </div>
        </div>
      ) : (
        // Display mode: Compact with whisker
        <button
          onClick={() => {
            setTempValues({ p10, p50, p90 });
            setIsEditing(true);
          }}
          className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg hover:border-slate-300 hover:bg-slate-50 transition-colors text-left"
        >
          <RangeWhisker p10={p10} p50={p50} p90={p90} format={format} showChip={true} />
        </button>
      )}
    </div>
  );
}
