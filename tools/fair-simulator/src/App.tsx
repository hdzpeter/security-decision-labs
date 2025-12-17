import { useState } from 'react';
import { ScenarioCreation } from "@/components/ScenarioCreation";
import { Dashboard } from "@/components/Dashboard";
import { BackendStatus } from "@/components/BackendStatus";

export interface ControlSelection {
  framework: string;
  controlId: string;
  controlName: string;
  effectiveness: number;
}

export interface InputQuality {
  source: 'measured' | 'benchmarked' | 'expert_judgment';
  evidence?: string; // Why this estimate?
  confidence?: 'low' | 'medium' | 'high';
}

export interface ScenarioMetadata {
  asset?: string;
  threatActor?: string;
  attackVector?: string;
  method?: string;
  adverseOutcome?: string;
}

export interface RiskScenario {
  id: string;
  name: string;
  description: string;
  threatEventFrequency: number;
  susceptibility: number;
  productivity: number;
  response: number;
  replacement: number;
  fines: number;
  competitiveAdvantage: number;
  reputation: number;
  slef: number; // Secondary Loss Event Frequency (probability 0-100%)
  industry: string;
  controls: ControlSelection[];
  createdAt: Date;
  
  // Transparency features
  metadata?: ScenarioMetadata;
  inputQuality?: {
    tef?: InputQuality;
    susceptibility?: InputQuality;
    productivity?: InputQuality;
    response?: InputQuality;
    replacement?: InputQuality;
    fines?: InputQuality;
    competitiveAdvantage?: InputQuality;
    reputation?: InputQuality;
    slef?: InputQuality;
  };
  
  // Range support (P10/P90)
  ranges?: {
    tef?: { p10: number; p90: number };
    susceptibility?: { p10: number; p90: number };
    productivity?: { p10: number; p90: number };
    response?: { p10: number; p90: number };
    replacement?: { p10: number; p90: number };
    fines?: { p10: number; p90: number };
    competitiveAdvantage?: { p10: number; p90: number };
    reputation?: { p10: number; p90: number };
    slef?: { p10: number; p90: number };
  };
}

function App() {
  const [view, setView] = useState<'dashboard' | 'create'>('dashboard');
  const [scenarios, setScenarios] = useState<RiskScenario[]>([
    {
      id: '1',
      name: 'Data Breach — Customer Database',
      description: 'External criminal actor exfiltrates customer PII from the production database using phished credentials to a privileged data-access service.',
      threatEventFrequency: 2.5,
      susceptibility: 35,
      productivity: 400000,
      response: 250000,
      replacement: 100000,
      fines: 500000,
      competitiveAdvantage: 150000,
      reputation: 200000,
      slef: 65,
      industry: 'Financial Services',
      controls: [],
      createdAt: new Date('2025-01-15'),
      metadata: {
        asset: 'Production customer PII database (e.g., cloud RDBMS behind an internal API) containing ~2–5M records: name, email, phone, physical address, partial SSN/ID.',
        threatActor: 'Financially motivated external actor / data broker (organized crime; not nation-state).',
        attackVector: 'Targeted phishing of customer support staff → MFA push fatigue → valid credential use to internal data-access API',
        method: 'Privilege escalation via misconfigured IAM role → bulk export of PII (double-checked in logs after the fact).',
        adverseOutcome: 'Confidentiality loss: unauthorized acquisition (exfiltration) of customer PII triggering breach notification, regulator inquiries, and potential civil litigation.',
      },
      ranges: {
        tef: { p10: 1.2, p90: 4.0 },
        susceptibility: { p10: 20, p90: 55 },
        productivity: { p10: 150000, p90: 900000 },
        response: { p10: 150000, p90: 500000 },
        replacement: { p10: 25000, p90: 300000 },
        fines: { p10: 0, p90: 2000000 },
        competitiveAdvantage: { p10: 0, p90: 600000 },
        reputation: { p10: 50000, p90: 1200000 },
        slef: { p10: 35, p90: 85 },
      },
      inputQuality: {
        tef: {
          source: 'benchmarked',
          evidence: 'Internal incident tickets (auth failures, phishing, blocked malware) plus industry telemetry. P10: 1.2/yr, P50: 2.5/yr, P90: 4.0/yr',
          confidence: 'medium',
        },
        susceptibility: {
          source: 'measured',
          evidence: 'Red-team results, control failure rates, EPSS/KEV weighting for relevant assets. P10: 20%, P50: 35%, P90: 55%',
          confidence: 'medium',
        },
        productivity: {
          source: 'expert_judgment',
          evidence: 'Hours of outage/slowdown × (revenue-at-risk × margin + staff idle cost). P10: $150K, P50: $400K, P90: $900K',
          confidence: 'medium',
        },
        response: {
          source: 'benchmarked',
          evidence: 'IR hours × rate + tooling + legal + comms + notification + credit monitoring. P10: $150K, P50: $250K, P90: $500K',
          confidence: 'high',
        },
        replacement: {
          source: 'measured',
          evidence: 'Restore/rebuild/licensing/backup egress costs. P10: $25K, P50: $100K, P90: $300K',
          confidence: 'high',
        },
        fines: {
          source: 'benchmarked',
          evidence: 'Regime × case comps × outside counsel view. P10: $0, P50: $500K, P90: $2.0M',
          confidence: 'low',
        },
        competitiveAdvantage: {
          source: 'expert_judgment',
          evidence: 'Lost deals × ASP + modeled IP erosion. P10: $0, P50: $150K, P90: $600K',
          confidence: 'low',
        },
        reputation: {
          source: 'expert_judgment',
          evidence: 'Customers × churn% × CLV + CAC uplift. P10: $50K, P50: $200K, P90: $1.2M',
          confidence: 'medium',
        },
        slef: {
          source: 'benchmarked',
          evidence: 'Regulatory counsel input, record counts, historical regulator posture, media footprint. P10: 35%, P50: 65%, P90: 85%',
          confidence: 'medium',
        },
      },
    },
    {
      id: '2',
      name: 'Ransomware Attack — Critical Systems',
      description: 'Ransomware affiliate encrypts production servers after exploiting an edge VPN appliance and moving laterally; data is exfiltrated for double extortion.',
      threatEventFrequency: 1.5,
      susceptibility: 30,
      productivity: 1200000,
      response: 800000,
      replacement: 300000,
      fines: 250000,
      competitiveAdvantage: 100000,
      reputation: 200000,
      slef: 35,
      industry: 'Financial Services',
      controls: [],
      createdAt: new Date('2025-02-01'),
      metadata: {
        asset: 'Critical business systems supporting order processing and finance (VM clusters + Windows file servers; ~50–150 VMs; RPO/RTO defined but backups on same domain).',
        threatActor: 'Ransomware-as-a-Service affiliate (financially motivated) using an Initial Access Broker.',
        attackVector: 'Purchase of VPN credentials from IAB → exploitation of unpatched VPN edge appliance for session hijack',
        method: 'Domain discovery and credential theft → lateral movement (RDP/SMB) → disabling of EDR via GPO → encryption of file servers and ESXi datastores; simultaneous data exfiltration of shared drives.',
        adverseOutcome: 'Availability loss: encryption causes multi-day outage of order processing, finance, and file shares; extortion demand with credible data-leak threat; potential secondary privacy exposure if exfiltration includes PII.',
      },
      inputQuality: {
        tef: {
          source: 'benchmarked',
          evidence: 'Internal incident tickets (auth failures, VPN anomalies, blocked ransomware) plus industry telemetry. P10: 0.8/yr, P50: 1.5/yr, P90: 2.5/yr',
          confidence: 'medium',
        },
        susceptibility: {
          source: 'measured',
          evidence: 'Red-team results, control failure rates, patch cadence for edge appliances. P10: 15%, P50: 30%, P90: 50%',
          confidence: 'medium',
        },
        productivity: {
          source: 'expert_judgment',
          evidence: 'Outage days × (daily revenue × gross margin) + critical staff idle. P10: $300K, P50: $1.2M, P90: $4.0M',
          confidence: 'medium',
        },
        response: {
          source: 'benchmarked',
          evidence: 'IR + recovery + overtime + negotiation + ransom payment if paid. P10: $250K, P50: $800K, P90: $2.0M',
          confidence: 'medium',
        },
        replacement: {
          source: 'measured',
          evidence: 'Rebuild VMs, re-image endpoints, licenses, backup egress. P10: $100K, P50: $300K, P90: $900K',
          confidence: 'high',
        },
        fines: {
          source: 'benchmarked',
          evidence: 'Only if PII/regulated data exfiltrated. Regime × case comps. P10: $0, P50: $250K, P90: $1.5M',
          confidence: 'low',
        },
        competitiveAdvantage: {
          source: 'expert_judgment',
          evidence: 'Lost bids, leaked roadmaps. Lost deals × ASP. P10: $0, P50: $100K, P90: $800K',
          confidence: 'low',
        },
        reputation: {
          source: 'expert_judgment',
          evidence: 'Churn + CAC uplift from public incident. P10: $0, P50: $200K, P90: $1.5M',
          confidence: 'medium',
        },
        slef: {
          source: 'benchmarked',
          evidence: 'Secondary privacy/penalty risk depends on proven exfiltration. Counsel input. P10: 15%, P50: 35%, P90: 60%',
          confidence: 'medium',
        },
      },
      ranges: {
        tef: { p10: 0.8, p90: 2.5 },
        susceptibility: { p10: 15, p90: 50 },
        productivity: { p10: 300000, p90: 4000000 },
        response: { p10: 250000, p90: 2000000 },
        replacement: { p10: 100000, p90: 900000 },
        fines: { p10: 0, p90: 1500000 },
        competitiveAdvantage: { p10: 0, p90: 800000 },
        reputation: { p10: 0, p90: 1500000 },
        slef: { p10: 15, p90: 60 },
      },
    },
  ]);

  const handleCreateScenario = (scenario: Omit<RiskScenario, 'id' | 'createdAt'>) => {
    const newScenario: RiskScenario = {
      ...scenario,
      id: Date.now().toString(),
      createdAt: new Date(),
    };
    setScenarios([...scenarios, newScenario]);
    setView('dashboard');
  };

  const handleUpdateScenario = (updatedScenario: RiskScenario) => {
    setScenarios(scenarios.map(s => s.id === updatedScenario.id ? updatedScenario : s));
  };

  const handleDeleteScenario = (scenarioId: string) => {
    setScenarios(scenarios.filter(s => s.id !== scenarioId));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-[1400px] mx-auto px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl text-slate-900">FAIR Risk Quantification</h1>
              <p className="text-sm text-slate-500 mt-0.5">Factor Analysis of Information Risk</p>
            </div>
            <div className="flex items-center gap-6">
              <BackendStatus />
              <nav className="flex items-center gap-2">
                <button
                  onClick={() => setView('dashboard')}
                  className={`px-5 py-2 text-sm rounded-lg transition-colors ${
                    view === 'dashboard'
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  Dashboard
                </button>
                <button
                  onClick={() => setView('create')}
                  className={`px-5 py-2 text-sm rounded-lg transition-colors ${
                    view === 'create'
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  New Scenario
                </button>
              </nav>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-[1400px] mx-auto px-8 py-8">
        {view === 'dashboard' ? (
          <Dashboard scenarios={scenarios} onUpdateScenario={handleUpdateScenario} onDeleteScenario={handleDeleteScenario} />
        ) : (
          <ScenarioCreation onCreateScenario={handleCreateScenario} onCancel={() => setView('dashboard')} />
        )}
      </main>
    </div>
  );
}

export default App;