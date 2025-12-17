import { useState } from 'react';
import { ChevronDown, ChevronUp, Calculator, Copy, Check } from 'lucide-react';

interface MathToggleProps {
  title: string;
  result: string | number;
  formula: string;
  breakdown?: Array<{ label: string; value: string | number }>;
  explanation?: string;
}

export function MathToggle({ title, result, formula, breakdown, explanation }: MathToggleProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    const text = `${title}\n${formula}\n\n${breakdown?.map(b => `${b.label}: ${b.value}`).join('\n') || ''}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <Calculator className="w-4 h-4 text-slate-500" />
          <div className="text-left">
            <div className="text-sm text-slate-900">{title}</div>
            <div className="text-lg text-slate-900 mt-0.5">{result}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-blue-600">Show math</span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="bg-white p-4 border-t border-slate-200 space-y-3">
          {/* Formula */}
          <div>
            <div className="text-xs text-slate-500 mb-1">Formula</div>
            <div className="p-3 bg-slate-50 rounded font-mono text-sm text-slate-900 overflow-x-auto">
              {formula}
            </div>
          </div>

          {/* Breakdown */}
          {breakdown && breakdown.length > 0 && (
            <div>
              <div className="text-xs text-slate-500 mb-2">Breakdown</div>
              <div className="space-y-1">
                {breakdown.map((item, idx) => (
                  <div key={idx} className="flex justify-between items-center text-sm py-1 border-b border-slate-100 last:border-0">
                    <span className="text-slate-600">{item.label}</span>
                    <span className="text-slate-900 font-mono">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Explanation */}
          {explanation && (
            <div className="pt-2 border-t border-slate-200">
              <div className="text-xs text-slate-600">{explanation}</div>
            </div>
          )}

          {/* Copy Button */}
          <button
            onClick={copyToClipboard}
            className="w-full px-4 py-2 bg-blue-500 hover:bg-blue-600 transition-colors text-white text-sm flex items-center justify-center"
          >
            {copied ? (
              <Check className="w-4 h-4 mr-2" />
            ) : (
              <Copy className="w-4 h-4 mr-2" />
            )}
            Copy to clipboard
          </button>
        </div>
      )}
    </div>
  );
}