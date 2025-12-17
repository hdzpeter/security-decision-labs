/**
 * Backend Status Indicator
 * Shows if Python risk_service is available
 */

import { useState, useEffect } from 'react';
import { Server, CheckCircle } from 'lucide-react';
import { fairApi } from '@/utils/fairApi.ts';

export function BackendStatus() {
  const [status, setStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    async function checkBackend() {
      const isHealthy = await fairApi.healthCheck();
      setStatus(isHealthy ? 'connected' : 'disconnected');
    }

    checkBackend();
    
    // Check every 30 seconds
    const interval = setInterval(checkBackend, 30000);
    
    return () => clearInterval(interval);
  }, []);

  if (status === 'checking') {
    return null; // Don't show while checking
  }

  if (status === 'connected') {
    // Only show on hover for connected state
    return (
      <div 
        className="relative"
        onMouseEnter={() => setShowDetails(true)}
        onMouseLeave={() => setShowDetails(false)}
      >
        <div className="flex items-center gap-2 text-xs text-green-600 cursor-help">
          <CheckCircle className="w-4 h-4" />
          <span>Backend Connected</span>
        </div>
        
        {showDetails && (
          <div className="absolute top-full right-0 mt-2 bg-white border border-green-200 rounded-lg shadow-lg p-3 w-64 z-50">
            <div className="text-xs text-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <Server className="w-4 h-4 text-green-600" />
                <span className="font-medium">Python Backend Active</span>
              </div>
              <ul className="space-y-1 text-slate-600">
                <li>• Monte Carlo simulations enabled</li>
                <li>• Industry benchmarks available</li>
                <li>• Sensitivity analysis ready</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Disconnected state - show subtle indicator
  return (
    <div 
      className="relative"
      onMouseEnter={() => setShowDetails(true)}
      onMouseLeave={() => setShowDetails(false)}
    >
      <div className="flex items-center gap-2 text-xs text-slate-500 cursor-help hover:text-slate-700 transition-colors">
        <div className="w-2 h-2 rounded-full bg-slate-400" />
        <span>Offline Mode</span>
      </div>
      
      {showDetails && (
        <div className="absolute top-full right-0 mt-2 bg-white border border-slate-200 rounded-lg shadow-lg p-4 w-80 z-50">
          <div className="text-xs">
            <div className="flex items-center gap-2 mb-3">
              <Server className="w-4 h-4 text-slate-600" />
              <span className="font-medium text-slate-900">Python Backend Not Running</span>
            </div>
            
            <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-3">
              <p className="text-blue-800 mb-2">
                The app works fully in offline mode. For advanced features:
              </p>
              <ol className="text-blue-700 space-y-1 ml-4 list-decimal text-xs">
                <li>Open terminal in <code className="bg-blue-100 px-1 rounded">backend/</code></li>
                <li>Run <code className="bg-blue-100 px-1 rounded">python api.py</code></li>
              </ol>
            </div>
            
            <div className="text-slate-600 space-y-1">
              <div className="font-medium mb-1 text-xs">With backend you get:</div>
              <ul className="space-y-0.5 text-xs">
                <li>• Monte Carlo simulations (P10/P50/P90)</li>
                <li>• Real industry benchmarks (DBIR, IBM)</li>
                <li>• Sensitivity analysis</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}