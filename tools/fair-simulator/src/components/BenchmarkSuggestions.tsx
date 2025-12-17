import { AlertCircle, ExternalLink, TrendingUp } from 'lucide-react';
import { useState, useEffect } from 'react';
import { fairApi, type ScenarioBenchmark } from '@/utils/fairApi.ts';

interface BenchmarkSuggestionsProps {
  industry: string;
  threatType: string;
  currentEstimate?: number;
  estimateType: 'tef' | 'susceptibility' | 'productivity' | 'response' | 'replacement' | 'fines' | 'reputation' | 'competitiveAdvantage' | 'slef';
}

export function BenchmarkSuggestions({ 
  industry, 
  threatType, 
  currentEstimate,
  estimateType 
}: BenchmarkSuggestionsProps) {
  const [benchmark, setBenchmark] = useState<ScenarioBenchmark | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchBenchmark() {
      setLoading(true);
      setError(null);
      
      try {
        // Map threatType to scenario_type for risk_service
        const scenarioTypeMap: Record<string, string> = {
          'Ransomware': 'ransomware',
          'Data Breach': 'data_breach',
          'DDoS Attack': 'ddos',
          'POS Malware': 'pos_malware',
          'Phishing': 'ransomware', // fallback
          'Insider Threat': 'data_breach', // fallback
        };
        
        const scenarioType = scenarioTypeMap[threatType] || 'ransomware';
        const data = await fairApi.getBenchmark(industry, scenarioType);
        
        setBenchmark(data);
      } catch (err) {
        // Silently handle error - risk_service not available
        setError('Benchmark data temporarily unavailable');
      } finally {
        setLoading(false);
      }
    }

    if (industry && threatType) {
      fetchBenchmark();
    }
  }, [industry, threatType]);

  if (loading) {
    return (
      <div className="border border-amber-300 rounded-lg p-4 bg-amber-50">
        <div className="text-sm text-amber-700">Loading industry benchmarks...</div>
      </div>
    );
  }

  if (error || !benchmark) {
    return (
      <div className="border border-slate-300 rounded-lg p-4 bg-slate-50">
        <div className="text-sm text-slate-600">
          No benchmark data available for {industry} / {threatType}
        </div>
      </div>
    );
  }

  // Map estimateType to factor name in benchmark
  const factorMap: Record<string, string> = {
    'tef': 'tef',
    'susceptibility': 'susceptibility',
    'productivity': 'productivity',
    'response': 'response',
    'replacement': 'replacement',
    'fines': 'fines',
    'reputation': 'reputation',
    'competitiveAdvantage': 'competitive_advantage',
    'slef': 'slef',
  };

  const factorName = factorMap[estimateType];
  const benchmarkData = benchmark.factors[factorName];

  if (!benchmarkData || benchmarkData.p50 === null) {
    return null;
  }

  // Determine if current estimate is within reasonable range
  let comparison = '';
  if (currentEstimate !== undefined && currentEstimate > 0) {
    if (currentEstimate < (benchmarkData.p10 || 0)) {
      comparison = 'below industry range';
    } else if (currentEstimate > (benchmarkData.p90 || Infinity)) {
      comparison = 'above industry range';
    } else if (currentEstimate >= (benchmarkData.p10 || 0) && currentEstimate <= (benchmarkData.p90 || Infinity)) {
      comparison = 'within industry range';
    }
  }

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <TrendingUp className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm text-amber-900 mb-2">
            <strong>Industry Benchmark — {industry}</strong>
          </div>
          
          <div className="text-sm text-amber-800 space-y-2">
            <div className="flex justify-between items-center">
              <span>P10:</span>
              <span className="font-mono">{benchmarkData.p10}{benchmarkData.unit}</span>
            </div>
            <div className="flex justify-between items-center">
              <span>P50 (Median):</span>
              <span className="font-mono">{benchmarkData.p50}{benchmarkData.unit}</span>
            </div>
            <div className="flex justify-between items-center">
              <span>P90:</span>
              <span className="font-mono">{benchmarkData.p90}{benchmarkData.unit}</span>
            </div>
            
            {comparison && (
              <div className={`text-xs mt-2 p-2 rounded ${
                comparison === 'within industry range' 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-amber-100 text-amber-800'
              }`}>
                Your estimate is {comparison}
              </div>
            )}
            
            <div className="text-xs text-amber-700 mt-3 pt-2 border-t border-amber-200">
              <div className="mb-1"><strong>Source:</strong> {benchmarkData.source}</div>
              {benchmarkData.date && <div className="mb-1"><strong>Date:</strong> {benchmarkData.date}</div>}
              {benchmarkData.sample_size && <div className="mb-1"><strong>Sample Size:</strong> {benchmarkData.sample_size.toLocaleString()}</div>}
              {benchmarkData.notes && <div className="mt-2">{benchmarkData.notes}</div>}
              {benchmarkData.source_url && (
                <a 
                  href={benchmarkData.source_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-amber-700 hover:text-amber-900 underline mt-2"
                >
                  View source <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
      
      <div className="mt-3 pt-3 border-t border-amber-300">
        <div className="flex items-center gap-2 text-xs text-amber-700">
          <AlertCircle className="w-4 h-4" />
          <span>Benchmarks are for reference only — use your organization's context</span>
        </div>
      </div>
    </div>
  );
}