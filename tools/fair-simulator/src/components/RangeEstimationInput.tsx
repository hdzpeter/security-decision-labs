import { useState, useEffect } from 'react';
import { AlertCircle, TrendingUp, AlertTriangle } from 'lucide-react';

interface RangeEstimationInputProps {
  label: string;
  description: string;
  p10: number;
  p50: number;
  p90: number;
  onChange: (p10: number, p50: number, p90: number) => void;
  unit?: string;
  distributionType: 'poisson' | 'lognormal' | 'pert' | 'beta';
  min?: number;
  max?: number;
  helpText?: string;
  isProbability?: boolean;
}

export function RangeEstimationInput({
  label,
  description,
  p10,
  p50,
  p90,
  onChange,
  unit = '',
  distributionType,
  min,
  max,
  helpText,
  isProbability = false,
}: RangeEstimationInputProps) {
  const [showValidation, setShowValidation] = useState(false);
  const [displayP10, setDisplayP10] = useState('');
  const [displayP50, setDisplayP50] = useState('');
  const [displayP90, setDisplayP90] = useState('');

  // Format number with thousand separators
  const formatNumber = (num: number | string): string => {
    if (num === '' || num === null || num === undefined) return '';
    const numStr = String(num);
    // Handle decimals
    const parts = numStr.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
  };

  // Parse formatted number back to plain number
  const parseNumber = (str: string): number => {
    if (!str) return 0;
    return Number(str.replace(/,/g, ''));
  };

  // Update display values when props change
  useEffect(() => {
    setDisplayP10(formatNumber(p10));
    setDisplayP50(formatNumber(p50));
    setDisplayP90(formatNumber(p90));
  }, [p10, p50, p90]);

  const handleP10Change = (value: string) => {
    setDisplayP10(value);
    const numValue = parseNumber(value);
    onChange(numValue, p50, p90);
  };

  const handleP50Change = (value: string) => {
    setDisplayP50(value);
    const numValue = parseNumber(value);
    onChange(p10, numValue, p90);
  };

  const handleP90Change = (value: string) => {
    setDisplayP90(value);
    const numValue = parseNumber(value);
    onChange(p10, p50, numValue);
  };

  const handleP10Blur = () => {
    setDisplayP10(formatNumber(p10));
    setShowValidation(true);
  };

  const handleP50Blur = () => {
    setDisplayP50(formatNumber(p50));
    setShowValidation(true);
  };

  const handleP90Blur = () => {
    setDisplayP90(formatNumber(p90));
    setShowValidation(true);
  };

  const validateRange = () => {
    const errors: string[] = [];
    const warnings: string[] = [];
    
    // Monotonicity check
    if (p10 > p50) {
      errors.push('10th percentile must be ≤ 50th percentile');
    }
    if (p50 > p90) {
      errors.push('50th percentile must be ≤ 90th percentile');
    }
    
    // Probability bounds
    if (isProbability) {
      if (p10 < 0 || p50 < 0 || p90 < 0) {
        errors.push('Probabilities must be ≥ 0%');
      }
      if (p10 > 100 || p50 > 100 || p90 > 100) {
        errors.push('Probabilities must be ≤ 100%');
      }
      if (p90 === 100) {
        warnings.push('Upper bound at 100% implies certainty—consider ≤99% unless you have strong evidence');
      }
    }
    
    // General bounds
    if (min !== undefined && p10 < min) {
      errors.push(`10th percentile must be at least ${min}`);
    }
    if (max !== undefined && p90 > max) {
      errors.push(`90th percentile must be at most ${max}`);
    }
    
    return { errors, warnings };
  };

  const { errors: validationErrors, warnings: validationWarnings } = validateRange();
  const isValid = validationErrors.length === 0 && p10 >= 0 && p50 >= 0 && p90 >= 0;

  const getDistributionColor = () => {
    switch (distributionType) {
      case 'poisson':
        return 'emerald';
      case 'lognormal':
        return 'blue';
      case 'pert':
      case 'beta':
        return 'purple';
      default:
        return 'blue';
    }
  };

  const getDistributionLabel = () => {
    switch (distributionType) {
      case 'poisson':
        return 'Poisson';
      case 'lognormal':
        return 'Lognormal';
      case 'pert':
        return 'PERT/Beta';
      case 'beta':
        return 'Beta';
      default:
        return distributionType;
    }
  };

  const color = getDistributionColor();

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-start justify-between mb-2">
          <div>
            <label className="block text-sm text-slate-900">{label}</label>
            <p className="text-xs text-slate-500 mt-1">{description}</p>
          </div>
          <div className={`px-2 py-1 bg-${color}-100 text-${color}-700 text-xs rounded`}>
            {getDistributionLabel()}
          </div>
        </div>
        {helpText && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
            <p className="text-xs text-slate-600">{helpText}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs text-slate-600 mb-1">
            P10 <span className="text-slate-400">(low)</span>
          </label>
          <div className="relative">
            <input
              type="text"
              step="any"
              value={displayP10}
              onChange={(e) => handleP10Change(e.target.value)}
              onBlur={handleP10Blur}
              placeholder="Low estimate"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {unit && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
                {unit}
              </span>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-600 mb-1">
            P50 <span className="text-slate-400">(median)</span>
          </label>
          <div className="relative">
            <input
              type="text"
              step="any"
              value={displayP50}
              onChange={(e) => handleP50Change(e.target.value)}
              onBlur={handleP50Blur}
              placeholder="Best guess"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {unit && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
                {unit}
              </span>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-600 mb-1">
            P90 <span className="text-slate-400">(high)</span>
          </label>
          <div className="relative">
            <input
              type="text"
              step="any"
              value={displayP90}
              onChange={(e) => handleP90Change(e.target.value)}
              onBlur={handleP90Blur}
              placeholder="High estimate"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {unit && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
                {unit}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Visual Distribution Indicator */}
      {p10 >= 0 && p50 >= 0 && p90 >= 0 && isValid && p10 <= p50 && p50 <= p90 && (
        <div className="bg-slate-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-slate-500" />
            <span className="text-xs text-slate-600">Distribution Preview</span>
          </div>
          <div className="relative h-12 flex items-end">
            {/* Simple visual representation */}
            <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-green-200 via-blue-300 to-red-200 rounded-full" />
            <div className="absolute left-0 bottom-0 w-px h-8 bg-green-600" />
            <div className="absolute left-1/2 -translate-x-1/2 bottom-0 w-px h-12 bg-blue-600" />
            <div className="absolute right-0 bottom-0 w-px h-8 bg-red-600" />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-xs text-green-600">{p10}{unit}</span>
            <span className="text-xs text-blue-600">{p50}{unit}</span>
            <span className="text-xs text-red-600">{p90}{unit}</span>
          </div>
        </div>
      )}

      {/* Validation Errors */}
      {showValidation && validationErrors.length > 0 && (
        <div className="bg-red-50 border border-red-300 rounded-lg p-3">
          {validationErrors.map((error, index) => (
            <div key={index} className="flex items-start gap-2 text-sm text-red-800">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          ))}
        </div>
      )}

      {/* Validation Warnings */}
      {showValidation && isValid && validationWarnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-3">
          {validationWarnings.map((warning, index) => (
            <div key={index} className="flex items-start gap-2 text-sm text-amber-800">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}