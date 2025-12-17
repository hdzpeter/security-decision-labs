import { HelpCircle } from 'lucide-react';
import { useState } from 'react';

interface FAIRTooltipProps {
  term: string;
  definition: string;
  formula?: string;
  learnMoreUrl?: string;
}

export function FAIRTooltip({ term, definition, formula, learnMoreUrl }: FAIRTooltipProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded hover:bg-blue-100 transition-colors"
      >
        {term}
        <HelpCircle className="w-3 h-3" />
      </button>

      {showTooltip && (
        <div className="absolute z-50 bottom-full left-0 mb-2 w-72 bg-slate-900 text-white text-xs rounded-lg p-3 shadow-xl">
          <div className="mb-2">
            <div className="text-blue-300 mb-1">{term}</div>
            <div className="text-slate-200">{definition}</div>
          </div>
          
          {formula && (
            <div className="mb-2 p-2 bg-slate-800 rounded font-mono text-xs">
              {formula}
            </div>
          )}
          
          {learnMoreUrl && (
            <a
              href={learnMoreUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-300 hover:text-blue-200 underline"
            >
              Learn more →
            </a>
          )}
          
          {/* Arrow */}
          <div className="absolute top-full left-4 -mt-1 w-2 h-2 bg-slate-900 transform rotate-45" />
        </div>
      )}
    </div>
  );
}
