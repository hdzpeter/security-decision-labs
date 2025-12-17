/**
 * Range Slider - P50 as main thumb, P10/P90 handles on focus
 * For probabilistic inputs like SLEF (0-100%)
 */

import { useState, useRef, useEffect } from 'react';

interface RangeSliderProps {
  label: string;
  p10: number;
  p50: number;
  p90: number;
  onChange?: (values: { p10: number; p50: number; p90: number }) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  unit?: string;
}

export function RangeSlider({
  label,
  p10,
  p50,
  p90,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  unit = '%',
}: RangeSliderProps) {
  const [isFocused, setIsFocused] = useState(false);
  const [activeHandle, setActiveHandle] = useState<'p10' | 'p50' | 'p90' | null>(null);
  const sliderRef = useRef<HTMLDivElement>(null);

  const getPositionPercent = (value: number) => {
    return ((value - min) / (max - min)) * 100;
  };

  const getValueFromPosition = (clientX: number) => {
    if (!sliderRef.current) return p50;
    const rect = sliderRef.current.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const value = min + percent * (max - min);
    return Math.round(value / step) * step;
  };

  const handleMouseDown = (handle: 'p10' | 'p50' | 'p90') => (e: React.MouseEvent) => {
    if (disabled || !onChange) return;
    e.preventDefault();
    setActiveHandle(handle);
    setIsFocused(true);
  };

  useEffect(() => {
    if (!activeHandle || disabled || !onChange) return;

    const handleMouseMove = (e: MouseEvent) => {
      const value = getValueFromPosition(e.clientX);
      
      if (activeHandle === 'p10') {
        onChange({ p10: Math.min(value, p50), p50, p90 });
      } else if (activeHandle === 'p50') {
        onChange({ p10, p50: Math.max(p10, Math.min(value, p90)), p90 });
      } else if (activeHandle === 'p90') {
        onChange({ p10, p50, p90: Math.max(value, p50) });
      }
    };

    const handleMouseUp = () => {
      setActiveHandle(null);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [activeHandle, p10, p50, p90, min, max, disabled, onChange]);

  return (
    <div>
      <label className="block text-sm text-slate-600 mb-2">{label}</label>
      
      <div 
        className="relative"
        onMouseEnter={() => !disabled && setIsFocused(true)}
        onMouseLeave={() => !activeHandle && setIsFocused(false)}
      >
        {/* Value display */}
        <div className="flex justify-between items-center mb-3">
          <span className="text-xs text-slate-500">
            {isFocused && `P10: ${p10}${unit}`}
          </span>
          <span className="text-lg text-slate-900 font-mono">
            {p50}{unit}
          </span>
          <span className="text-xs text-slate-500">
            {isFocused && `P90: ${p90}${unit}`}
          </span>
        </div>

        {/* Slider track */}
        <div
          ref={sliderRef}
          className={`relative h-2 bg-slate-200 rounded-full cursor-pointer ${
            disabled ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {/* Range highlight (P10-P90) */}
          <div
            className="absolute h-full bg-blue-200 rounded-full"
            style={{
              left: `${getPositionPercent(p10)}%`,
              right: `${100 - getPositionPercent(p90)}%`,
            }}
          />

          {/* P10 handle (visible on focus) */}
          {isFocused && !disabled && (
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-blue-400 border-2 border-white rounded-full shadow-md cursor-grab active:cursor-grabbing transition-all hover:scale-110"
              style={{ left: `${getPositionPercent(p10)}%` }}
              onMouseDown={handleMouseDown('p10')}
            >
              <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-xs text-slate-600 whitespace-nowrap bg-white px-1.5 py-0.5 rounded shadow-sm">
                {p10}
              </div>
            </div>
          )}

          {/* P50 handle (main thumb) */}
          <div
            className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 bg-blue-600 border-2 border-white rounded-full shadow-lg transition-all ${
              disabled ? 'cursor-not-allowed' : 'cursor-grab active:cursor-grabbing hover:scale-110'
            }`}
            style={{ left: `${getPositionPercent(p50)}%` }}
            onMouseDown={handleMouseDown('p50')}
          >
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 text-sm text-slate-900 font-mono whitespace-nowrap bg-white px-2 py-1 rounded shadow-md border border-slate-200">
              {p50}{unit}
            </div>
          </div>

          {/* P90 handle (visible on focus) */}
          {isFocused && !disabled && (
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-blue-400 border-2 border-white rounded-full shadow-md cursor-grab active:cursor-grabbing transition-all hover:scale-110"
              style={{ left: `${getPositionPercent(p90)}%` }}
              onMouseDown={handleMouseDown('p90')}
            >
              <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-xs text-slate-600 whitespace-nowrap bg-white px-1.5 py-0.5 rounded shadow-sm">
                {p90}
              </div>
            </div>
          )}
        </div>

        {/* Helper text */}
        {isFocused && !disabled && (
          <div className="mt-2 text-xs text-slate-500 text-center animate-in fade-in duration-200">
            Drag handles to adjust P10 (low), P50 (median), or P90 (high) estimates
          </div>
        )}
      </div>
    </div>
  );
}
