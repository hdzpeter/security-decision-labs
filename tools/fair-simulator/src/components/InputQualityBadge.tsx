import { CheckCircle, TrendingUp, Brain } from 'lucide-react';

interface InputQualityBadgeProps {
  source: 'measured' | 'benchmarked' | 'expert_judgment';
  onChange?: (source: 'measured' | 'benchmarked' | 'expert_judgment') => void;
  editable?: boolean;
}

export function InputQualityBadge({ source, onChange, editable = false }: InputQualityBadgeProps) {
  const sources = [
    { 
      value: 'measured' as const, 
      label: 'Measured', 
      icon: CheckCircle, 
      color: 'slate',
      description: 'From actual historical data or measurements'
    },
    { 
      value: 'benchmarked' as const, 
      label: 'Benchmarked', 
      icon: TrendingUp, 
      color: 'blue',
      description: 'From industry studies, claims data, or peer comparison'
    },
    { 
      value: 'expert_judgment' as const, 
      label: 'Expert Judgment', 
      icon: Brain, 
      color: 'purple',
      description: 'From SME estimation or informed opinion'
    },
  ];

  const current = sources.find(s => s.value === source);
  if (!current) return null;

  const Icon = current.icon;

  if (!editable) {
    return (
      <div 
        className={`inline-flex items-center gap-1.5 px-2 py-1 bg-${current.color}-50 text-${current.color}-700 text-xs rounded`}
        title={current.description}
      >
        <Icon className="w-3 h-3" />
        {current.label}
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      {sources.map((s) => {
        const SourceIcon = s.icon;
        const isActive = s.value === source;
        
        return (
          <button
            key={s.value}
            onClick={() => onChange?.(s.value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded transition-all ${
              isActive
                ? `bg-${s.color}-100 text-${s.color}-700 border-2 border-${s.color}-300`
                : 'bg-slate-50 text-slate-500 border-2 border-slate-200 hover:border-slate-300'
            }`}
            title={s.description}
          >
            <SourceIcon className="w-3 h-3" />
            {s.label}
          </button>
        );
      })}
    </div>
  );
}
