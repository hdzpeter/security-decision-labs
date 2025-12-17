import { useState } from 'react';
import { RiskScenario, ControlSelection } from '../App.tsx';
import {
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Check,
  Shield,
  Users,
  Zap,
  Target,
  AlertTriangle,
  FileText,
  Clock,
  FileWarning,
} from 'lucide-react';
import { ComboBox } from './ComboBox.tsx';
import { LEFStep } from './LEFStep.tsx';
import { LMStep } from './LMStep.tsx';

interface ScenarioCreationProps {
  onCreateScenario: (scenario: Omit<RiskScenario, 'id' | 'createdAt'>) => void;
  onCancel: () => void;
}

type Step =
  | 'metadata'
  | 'asset'
  | 'threat'
  | 'vector'
  | 'method'
  | 'outcome'
  | 'assumptions'
  | 'statement'
  | 'lef'
  | 'lm'
  | 'review';

export function ScenarioCreation({ onCreateScenario, onCancel }: ScenarioCreationProps) {
  const [currentStep, setCurrentStep] = useState<Step>('metadata');
  const [formData, setFormData] = useState({
    // Metadata
    timeHorizon: 12,
    timeUnit: 'months',
    currency: 'USD',
    threatCommunity: '',
    assumptions: '',
    // Scenario Definition
    asset: '',
    assetType: 'Data - Customer/Client Records',
    threatActor: '',
    threatActorType: 'External - Cybercriminal Group',
    attackVector: '',
    attackVectorType: 'Network - Phishing/Spear Phishing',
    attackMethod: '',
    adverseOutcome: '',
    industry: 'Financial Services',
    revenueTier: '$1B to $10B', // Add revenue tier for IRIS 2025 benchmarks
    // FAIR Factors - Range Estimates
    tefP10: 0,
    tefP50: 0,
    tefP90: 0,
    tefModel: 'poisson' as 'poisson' | 'lognormal',
    tefDecompose: false,
    contactFreqP10: 0,
    contactFreqP50: 0,
    contactFreqP90: 0,
    probActionP10: 0,
    probActionP50: 0,
    probActionP90: 0,
    zeroInflation: false,
    susceptibilityP10: 0,
    susceptibilityP50: 50,
    susceptibilityP90: 100,
    productivityP10: 0,
    productivityP50: 0,
    productivityP90: 0,
    responseP10: 0,
    responseP50: 0,
    responseP90: 0,
    replacementP10: 0,
    replacementP50: 0,
    replacementP90: 0,
    finesP10: 0,
    finesP50: 0,
    finesP90: 0,
    competitiveAdvantageP10: 0,
    competitiveAdvantageP50: 0,
    competitiveAdvantageP90: 0,
    reputationP10: 0,
    reputationP50: 0,
    reputationP90: 0,
    slefP10: 0,
    slefP50: 50,
    slefP90: 100,
    // Legacy point estimates for backward compatibility
    threatEventFrequency: 0,
    susceptibility: 50,
    productivity: 0,
    response: 0,
    replacement: 0,
    fines: 0,
    competitiveAdvantage: 0,
    reputation: 0,
    slef: 50,
    controls: [] as ControlSelection[],
  });

  const steps = [
    { id: 'metadata', label: 'Metadata', description: 'Time horizon & context', icon: Clock },
    { id: 'asset', label: 'Asset', description: 'What is at risk?', icon: Shield },
    { id: 'threat', label: 'Threat Actor', description: 'Who/what threatens it?', icon: Users },
    { id: 'vector', label: 'Attack Vector', description: 'Entry point?', icon: Zap },
    { id: 'method', label: 'Method', description: 'Attack technique?', icon: Target },
    { id: 'outcome', label: 'Adverse Outcome', description: 'What bad thing happens?', icon: AlertTriangle },
    { id: 'assumptions', label: 'Assumptions', description: "What we're not modeling", icon: FileWarning },
    { id: 'statement', label: 'Review Statement', description: 'Verify scenario', icon: FileText },
    { id: 'lef', label: 'Loss Event Frequency', description: 'TEF × Susceptibility', icon: null },
    { id: 'lm', label: 'Loss Magnitude', description: '6 Forms of Loss', icon: null },
    { id: 'review', label: 'Final Review', description: 'Confirm & create', icon: Check },
  ];

  const assetTypes = [
    'Data - Customer/Client Records',
    'Data - Employee Records',
    'Data - Financial Data',
    'Data - Intellectual Property',
    'Data - Trade Secrets',
    'Systems - Production Systems',
    'Systems - Development Environment',
    'Systems - Corporate Network',
    'Systems - Cloud Infrastructure',
    'Services - Customer-Facing Services',
    'Services - Internal Business Services',
  ];

  const threatActorTypes = [
    'External - Nation State',
    'External - Cybercriminal Group',
    'External - Hacktivist',
    'External - Competitor',
    'Internal - Malicious Insider',
    'Internal - Negligent Employee',
    'Internal - Privileged User',
    'Third Party - Vendor/Supplier',
    'Third Party - Business Partner',
  ];

  const attackVectorTypes = [
    'Network - Phishing/Spear Phishing',
    'Network - Unpatched Vulnerability',
    'Network - Zero-Day Exploit',
    'Network - Brute Force Attack',
    'Physical - Unauthorized Access',
    'Physical - Stolen Device',
    'Human - Social Engineering',
    'Human - Credential Compromise',
    'Supply Chain - Third-Party Compromise',
    'Supply Chain - Software Vulnerability',
    'Insider - Privileged Access Abuse',
    'Insider - Accidental Exposure',
  ];

  const currencies = ['USD', 'EUR', 'GBP', 'CHF', 'JPY', 'AUD', 'CAD', 'CNY', 'INR', 'SEK', 'NOK', 'DKK'];

  const industries = [
    'Financial Services',
    'Healthcare',
    'Retail',
    'Technology',
    'Manufacturing',
    'Government',
    'Education',
    'Energy',
    'Telecommunications',
    'Professional Services',
  ];

  const revenueTiers = [
    'Less than $10M',
    '$10M to $100M',
    '$100M to $1B',
    '$1B to $10B',
    '$10B to $100B',
    'More than $100B',
  ];

  const generateScenarioStatement = () => {
    const parts: string[] = [];

    if (formData.threatActor) {
      parts.push(`A **${formData.threatActor}** (${formData.threatActorType})`);
    } else {
      parts.push('A threat actor');
    }

    if (formData.attackVector) {
      parts.push(`gains access via **${formData.attackVector}** (${formData.attackVectorType})`);
    }

    if (formData.attackMethod) {
      parts.push(`and uses **${formData.attackMethod}**`);
    }

    if (formData.adverseOutcome) {
      parts.push(`to cause **${formData.adverseOutcome}**`);
    }

    if (formData.asset) {
      parts.push(`affecting **${formData.asset}** (${formData.assetType})`);
    }

    return parts.join(' ');
  };

  const generateScenarioName = () => {
    const outcome = formData.adverseOutcome || 'Security Incident';
    const asset = formData.asset || 'Asset';
    return `${outcome} - ${asset}`;
  };

  // @ts-ignore
    const calculateSusceptibility = () => {
    // Use the median of the susceptibility range
    return formData.susceptibilityP50;
  };

  const calculateLEF = () => {
    // LEF = TEF (median) × Susceptibility (median as %)
    return formData.tefP50 * (formData.susceptibilityP50 / 100);
  };

  const calculatePrimaryLoss = () =>
    formData.productivity + formData.response + formData.replacement;

  const calculateSecondaryLoss = () =>
    formData.fines + formData.competitiveAdvantage + formData.reputation;

  const calculateLM = () => {
    const primaryLoss = calculatePrimaryLoss();
    const secondaryLoss = calculateSecondaryLoss();
    const slefProbability = formData.slef / 100;
    return primaryLoss + secondaryLoss * slefProbability;
  };

  const calculateALE = () => calculateLEF() * calculateLM();

  const handleNext = () => {
    const stepIndex = steps.findIndex((s) => s.id === currentStep);
    if (stepIndex < steps.length - 1) {
      setCurrentStep(steps[stepIndex + 1].id as Step);
    }
  };

  const handleBack = () => {
    const stepIndex = steps.findIndex((s) => s.id === currentStep);
    if (stepIndex > 0) {
      setCurrentStep(steps[stepIndex - 1].id as Step);
    }
  };

  const handleSubmit = () => {
    const scenarioName = generateScenarioName();
    const scenarioDescription = generateScenarioStatement();

    // Sync range medians to legacy fields for backward compatibility
    const legacyTEF = formData.tefP50;
    const legacySusceptibility = formData.susceptibilityP50;

    onCreateScenario({
      name: scenarioName,
      description: scenarioDescription,
      industry: formData.industry,
      threatEventFrequency: legacyTEF,
      susceptibility: legacySusceptibility,
      productivity: formData.productivity,
      response: formData.response,
      replacement: formData.replacement,
      fines: formData.fines,
      competitiveAdvantage: formData.competitiveAdvantage,
      reputation: formData.reputation,
      slef: formData.slef,
      controls: formData.controls,
    });
  };

  const isStepComplete = (step: Step): boolean => {
    switch (step) {
      case 'metadata':
        return formData.timeHorizon > 0 && formData.currency.trim().length > 0;
      case 'asset':
        return formData.asset.trim().length >= 3;
      case 'threat':
        return formData.threatActor.trim().length >= 3;
      case 'vector':
        return formData.attackVector.trim().length >= 3;
      case 'method':
        return formData.attackMethod.trim().length >= 3;
      case 'outcome':
        return formData.adverseOutcome.trim().length >= 3;
      case 'assumptions':
        return true;
      case 'statement':
        return true;
      case 'lef':
        return (
          formData.tefP50 > 0 &&
          formData.susceptibilityP50 > 0 &&
          formData.tefP10 >= 0 &&
          formData.tefP90 > 0 &&
          formData.susceptibilityP10 >= 0 &&
          formData.susceptibilityP90 > 0 &&
          formData.tefP10 <= formData.tefP50 &&
          formData.tefP50 <= formData.tefP90 &&
          formData.susceptibilityP10 <= formData.susceptibilityP50 &&
          formData.susceptibilityP50 <= formData.susceptibilityP90
        );
      case 'lm':
        return calculateLM() > 0;
      case 'review':
        return true;
      default:
        return false;
    }
  };

  const getValidationMessage = (step: Step): string | null => {
    switch (step) {
      case 'metadata':
        if (formData.timeHorizon <= 0) return 'Time horizon must be greater than 0';
        if (formData.currency.trim().length === 0) return 'Currency is required';
        return null;
      case 'asset':
        if (formData.asset.trim().length === 0) return 'Asset name is required';
        if (formData.asset.trim().length < 3)
          return 'Please be more specific (minimum 3 characters)';
        return null;
      case 'threat':
        if (formData.threatActor.trim().length === 0)
          return 'Threat actor description is required';
        if (formData.threatActor.trim().length < 3)
          return 'Please be more specific (minimum 3 characters)';
        return null;
      case 'vector':
        if (formData.attackVector.trim().length === 0) return 'Attack vector is required';
        if (formData.attackVector.trim().length < 3)
          return 'Please be more specific (minimum 3 characters)';
        return null;
      case 'method':
        if (formData.attackMethod.trim().length === 0) return 'Attack method is required';
        if (formData.attackMethod.trim().length < 3)
          return 'Please be more specific (minimum 3 characters)';
        return null;
      case 'outcome':
        if (formData.adverseOutcome.trim().length === 0) return 'Adverse outcome is required';
        if (formData.adverseOutcome.trim().length < 3)
          return 'Please be more specific (minimum 3 characters)';
        return null;
      default:
        return null;
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Progress Steps */}
      <div className="mb-8 overflow-x-auto">
        <div className="flex items-center justify-between min-w-max">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <div key={step.id} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
                      currentStep === step.id
                        ? 'bg-slate-700 text-white'
                        : isStepComplete(step.id as Step)
                        ? 'bg-green-500 text-white'
                        : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    {isStepComplete(step.id as Step) && currentStep !== step.id ? (
                      <Check className="w-5 h-5" />
                    ) : Icon ? (
                      <Icon className="w-5 h-5" />
                    ) : (
                      <span className="text-sm">{index + 1}</span>
                    )}
                  </div>
                  <div className="mt-2 text-center">
                    <div className="text-xs text-slate-900 whitespace-nowrap">
                      {step.label}
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">
                      {step.description}
                    </div>
                  </div>
                </div>
                {index < steps.length - 1 && (
                  <div
                    className={`h-0.5 w-12 flex-shrink-0 ${
                      isStepComplete(step.id as Step) ? 'bg-green-500' : 'bg-slate-200'
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Form Content */}
      <div className="bg-white rounded-xl border border-slate-200 p-8">
        {/* Metadata */}
        {currentStep === 'metadata' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">Scenario Metadata</h2>
              <p className="text-slate-600">
                Define the time horizon, currency, and context for this risk scenario
              </p>
            </div>
            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Be specific about the time horizon and currency.</strong> This will
                help in calculating the Annual Loss Exposure (ALE).
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Industry Context*</label>
              <ComboBox
                value={formData.industry}
                onChange={(value) => setFormData({ ...formData, industry: value })}
                options={industries}
              />
              <p className="text-xs text-slate-500 mt-1">
                Used for IRIS 2025 benchmark comparison
              </p>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Annual Revenue*</label>
              <ComboBox
                value={formData.revenueTier}
                onChange={(value) => setFormData({ ...formData, revenueTier: value })}
                options={revenueTiers}
              />
              <p className="text-xs text-slate-500 mt-1">
                Organization&apos;s annual revenue - used for IRIS 2025 benchmark comparison
              </p>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Time Horizon*</label>
              <input
                type="number"
                value={formData.timeHorizon}
                onChange={(e) =>
                  setFormData({ ...formData, timeHorizon: Number(e.target.value) })
                }
                placeholder="12"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('metadata') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('metadata')}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Time Unit*</label>
              <select
                value={formData.timeUnit}
                onChange={(e) => setFormData({ ...formData, timeUnit: e.target.value })}
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option>months</option>
                <option>years</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Currency*</label>
              <ComboBox
                value={formData.currency}
                onChange={(value) => setFormData({ ...formData, currency: value })}
                options={currencies}
              />
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Threat Community</label>
              <input
                type="text"
                value={formData.threatCommunity}
                onChange={(e) =>
                  setFormData({ ...formData, threatCommunity: e.target.value })
                }
                placeholder="e.g., Cybercriminals targeting financial services"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Assumptions</label>
              <textarea
                value={formData.assumptions}
                onChange={(e) =>
                  setFormData({ ...formData, assumptions: e.target.value })
                }
                placeholder="e.g., No insider threats, no third-party compromises"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        )}

        {/* Asset Definition */}
        {currentStep === 'asset' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">What Asset Is At Risk?</h2>
              <p className="text-slate-600">
                Be specific about the data, system, or service that could be affected
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Avoid vague descriptions.</strong> Instead of &quot;customer
                data&quot;, specify &quot;Customer PII database containing names, SSNs, and
                payment information&quot; or &quot;Production customer authentication
                system&quot;.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Asset Type*</label>
              <ComboBox
                value={formData.assetType}
                onChange={(value) => setFormData({ ...formData, assetType: value })}
                options={assetTypes}
              />
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">
                Specific Asset Description*
              </label>
              <input
                type="text"
                value={formData.asset}
                onChange={(e) => setFormData({ ...formData, asset: e.target.value })}
                placeholder="e.g., Customer PII database containing SSNs and payment card data"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('asset') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('asset')}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Threat Actor */}
        {currentStep === 'threat' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">
                Who or What Threatens This Asset?
              </h2>
              <p className="text-slate-600">
                Identify the type of threat actor and their characteristics
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Be specific about the threat agent.</strong> Instead of &quot;hackers&quot;,
                specify &quot;Financially motivated cybercriminal groups&quot; or &quot;Nation-state
                actors focused on espionage&quot;.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">
                Threat Actor Type*
              </label>
              <ComboBox
                value={formData.threatActorType}
                onChange={(value) =>
                  setFormData({ ...formData, threatActorType: value })
                }
                options={threatActorTypes}
              />
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">
                Specific Threat Actor Description*
              </label>
              <input
                type="text"
                value={formData.threatActor}
                onChange={(e) =>
                  setFormData({ ...formData, threatActor: e.target.value })
                }
                placeholder="e.g., Financially motivated ransomware groups targeting healthcare"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('threat') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('threat')}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Attack Vector */}
        {currentStep === 'vector' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">What Is The Entry Point?</h2>
              <p className="text-slate-600">
                How does the threat actor initially gain access or initiate the attack?
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Specify the attack vector.</strong> Instead of &quot;network
                attack&quot;, describe &quot;Spear phishing emails targeting finance department
                employees&quot; or &quot;Exploitation of unpatched VPN concentrator&quot;.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">
                Attack Vector Type*
              </label>
              <ComboBox
                value={formData.attackVectorType}
                onChange={(value) =>
                  setFormData({ ...formData, attackVectorType: value })
                }
                options={attackVectorTypes}
              />
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">
                Specific Attack Vector Description*
              </label>
              <input
                type="text"
                value={formData.attackVector}
                onChange={(e) =>
                  setFormData({ ...formData, attackVector: e.target.value })
                }
                placeholder="e.g., Credential phishing targeting employees with access to financial systems"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('vector') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('vector')}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Attack Method */}
        {currentStep === 'method' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">
                What Technique Will They Use?
              </h2>
              <p className="text-slate-600">
                What specific method or technique does the threat actor employ after
                gaining access?
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Describe the attack technique.</strong> Examples: &quot;Deploy
                ransomware to encrypt file servers&quot;, &quot;Exfiltrate data via encrypted
                channels to external servers&quot;, &quot;Escalate privileges to domain admin
                level&quot;.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Attack Method*</label>
              <input
                type="text"
                value={formData.attackMethod}
                onChange={(e) =>
                  setFormData({ ...formData, attackMethod: e.target.value })
                }
                placeholder="e.g., Deploy ransomware to encrypt production databases and file servers"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('method') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('method')}
                </p>
              )}
            </div>

            <div className="bg-slate-50 rounded-lg p-4">
              <div className="text-sm text-slate-600 mb-2">Common Attack Methods</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-slate-700">
                <div>• Ransomware deployment</div>
                <div>• Data exfiltration</div>
                <div>• Privilege escalation</div>
                <div>• Lateral movement</div>
                <div>• Data destruction</div>
                <div>• Service disruption</div>
                <div>• Credential harvesting</div>
                <div>• Backdoor installation</div>
              </div>
            </div>
          </div>
        )}

        {/* Adverse Outcome */}
        {currentStep === 'outcome' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">What Bad Thing Happens?</h2>
              <p className="text-slate-600">
                What is the ultimate adverse outcome or impact to the organization?
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Define the business impact.</strong> Examples: &quot;Unauthorized
                disclosure of 100K customer records&quot;, &quot;72-hour outage of
                customer-facing systems&quot;, &quot;Theft of proprietary source code&quot;.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Adverse Outcome*</label>
              <input
                type="text"
                value={formData.adverseOutcome}
                onChange={(e) =>
                  setFormData({ ...formData, adverseOutcome: e.target.value })
                }
                placeholder="e.g., Unauthorized disclosure of customer PII and payment card data"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {getValidationMessage('outcome') && (
                <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {getValidationMessage('outcome')}
                </p>
              )}
            </div>

            <div className="bg-slate-50 rounded-lg p-4">
              <div className="text-sm text-slate-600 mb-2">Common Adverse Outcomes</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-slate-700">
                <div>• Data breach / disclosure</div>
                <div>• Service unavailability</div>
                <div>• Data destruction / corruption</div>
                <div>• Unauthorized modification</div>
                <div>• Financial theft / fraud</div>
                <div>• Intellectual property theft</div>
                <div>• Regulatory non-compliance</div>
                <div>• Reputational damage</div>
              </div>
            </div>
          </div>
        )}

        {/* Assumptions */}
        {currentStep === 'assumptions' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">Assumptions</h2>
              <p className="text-slate-600">
                Define any assumptions that are not being modeled in this risk scenario
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Be specific about the assumptions.</strong> This will help in
                understanding the limitations of the risk scenario.
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2">Assumptions</label>
              <textarea
                value={formData.assumptions}
                onChange={(e) =>
                  setFormData({ ...formData, assumptions: e.target.value })
                }
                placeholder="e.g., No insider threats, no third-party compromises"
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        )}

        {/* Scenario Statement Review */}
        {currentStep === 'statement' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">Review Your Risk Scenario</h2>
              <p className="text-slate-600">
                Verify the complete scenario statement before proceeding to estimation
              </p>
            </div>

            <div className="bg-amber-50 border-2 border-amber-300 rounded-lg p-6">
              <div className="flex items-start gap-3 mb-4">
                <AlertCircle className="w-6 h-6 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-900 mb-2">
                  <strong>Read this scenario carefully.</strong> If anything seems vague or
                  unclear, go back and refine your definitions. Precise scenarios lead to
                  better risk estimates.
                </div>
              </div>

              <div className="bg-white rounded-lg p-5 border border-amber-200">
                <div
                  className="text-slate-900 leading-relaxed"
                  dangerouslySetInnerHTML={{
                    __html: generateScenarioStatement().replace(
                      /\*\*(.*?)\*\*/g,
                      '<strong class="text-slate-700">$1</strong>',
                    ),
                  }}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-500 mb-1">Asset</div>
                <div className="text-sm text-slate-900">{formData.asset}</div>
                <div className="text-xs text-slate-500 mt-1">{formData.assetType}</div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-500 mb-1">Threat Actor</div>
                <div className="text-sm text-slate-900">{formData.threatActor}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {formData.threatActorType}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-500 mb-1">Attack Vector</div>
                <div className="text-sm text-slate-900">{formData.attackVector}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {formData.attackVectorType}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-500 mb-1">Attack Method</div>
                <div className="text-sm text-slate-900">{formData.attackMethod}</div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4 col-span-2">
                <div className="text-xs text-slate-500 mb-1">Adverse Outcome</div>
                <div className="text-sm text-slate-900">{formData.adverseOutcome}</div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4 col-span-2">
                <div className="text-xs text-slate-500 mb-1">Industry Context</div>
                <div className="text-sm text-slate-900">{formData.industry}</div>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-slate-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">
                <strong>Next Steps:</strong> You&apos;ll now estimate the frequency and
                magnitude of this scenario using FAIR methodology. The scenario statement
                above will be saved as your risk scenario description.
              </div>
            </div>
          </div>
        )}

        {/* Loss Event Frequency (LEF) */}
        {currentStep === 'lef' && <LEFStep formData={formData} setFormData={setFormData} />}

        {/* Loss Magnitude */}
        {currentStep === 'lm' && <LMStep formData={formData} setFormData={setFormData} />}

        {/* Final Review */}
        {currentStep === 'review' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl text-slate-900 mb-2">Final Review</h2>
              <p className="text-slate-600">Verify all details before creating the risk scenario</p>
            </div>

            {/* Validation Warnings */}
            {(formData.tefP50 === 0 || calculateLM() === 0) && (
              <div className="bg-red-50 border-2 border-red-300 rounded-lg p-4 flex items-start gap-3">
                <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-sm text-red-900 mb-2">
                    <strong>Incomplete Risk Estimation</strong>
                  </div>
                  <div className="text-sm text-red-800 space-y-1">
                    {formData.tefP50 === 0 && (
                      <p>
                        • <strong>Threat Event Frequency (TEF) is 0.</strong> Go back to the
                        LEF step and estimate how often threat events occur.
                      </p>
                    )}
                    {calculateLM() === 0 && (
                      <p>
                        • <strong>Loss Magnitude is 0.</strong> Go back to the LM step and
                        estimate at least one loss form.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="bg-slate-50 border border-slate-300 rounded-lg p-4">
              <div className="text-sm text-slate-700 mb-2">
                <strong>Risk Scenario Statement</strong>
              </div>
              <div
                className="bg-white rounded-lg p-4 text-slate-900"
                dangerouslySetInnerHTML={{
                  __html: generateScenarioStatement().replace(
                    /\*\*(.*?)\*\*/g,
                    '<strong class="text-slate-700">$1</strong>',
                  ),
                }}
              />
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-600 mb-1">
                    What this scenario measures
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                    This scenario estimates the <span className="font-medium">annualized loss</span> from the
                    described adverse outcome once the loss event actually occurs – not just probes,
                    scans, or failed attempts. The FAIR math combines:
                    <br />
                    <span className="font-medium">TEF</span> (events/year) ×{' '}
                    <span className="font-medium">Susceptibility</span> (%) →{' '}
                    <span className="font-medium">LEF</span> (loss events/year), and
                    <br />
                    <span className="font-medium">LEF</span> ×{' '}
                    <span className="font-medium">Loss Magnitude</span> ($/event) →{' '}
                    <span className="font-medium">ALE</span> ($/year).
                </p>
            </div>
            <div className="border border-slate-200 rounded-lg p-6 space-y-4">
              <h3 className="text-slate-900">FAIR Calculation</h3>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">Threat Event Frequency (median)</span>
                  <span className="text-slate-900">{formData.tefP50}/year</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">Susceptibility (median)</span>
                  <span className="text-slate-900">{formData.susceptibilityP50}%</span>
                </div>
                <div className="flex justify-between items-center bg-slate-100 px-3 py-2 rounded">
                  <span className="text-slate-700">Loss Event Frequency (TEF × Susc.)</span>
                  <span className="text-slate-900">
                    {calculateLEF().toFixed(2)}/year
                  </span>
                </div>
              </div>

              <div className="h-px bg-slate-200" />

              <div className="space-y-3">
                <div className="text-sm text-slate-600 mb-2">6 Forms of Loss</div>
                {formData.productivity > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Productivity</span>
                    <span className="text-slate-900">
                      ${formData.productivity.toLocaleString()}
                    </span>
                  </div>
                )}
                {formData.response > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Response</span>
                    <span className="text-slate-900">
                      ${formData.response.toLocaleString()}
                    </span>
                  </div>
                )}
                {formData.replacement > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Replacement</span>
                    <span className="text-slate-900">
                      ${formData.replacement.toLocaleString()}
                    </span>
                  </div>
                )}
                {formData.fines > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Fines &amp; Judgments</span>
                    <span className="text-slate-900">
                      ${formData.fines.toLocaleString()}
                    </span>
                  </div>
                )}
                {formData.competitiveAdvantage > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Competitive Advantage</span>
                    <span className="text-slate-900">
                      ${formData.competitiveAdvantage.toLocaleString()}
                    </span>
                  </div>
                )}
                {formData.reputation > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">Reputation</span>
                    <span className="text-slate-900">
                      ${formData.reputation.toLocaleString()}
                    </span>
                  </div>
                )}
                {calculateSecondaryLoss() > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-600">
                      SLEF (Secondary Loss Probability)
                    </span>
                    <span className="text-slate-900">{formData.slef}%</span>
                  </div>
                )}
                <div className="flex justify-between items-center bg-slate-100 px-3 py-2 rounded">
                  <span className="text-slate-700">LM (Loss Magnitude)</span>
                  <span className="text-slate-900">
                    ${calculateLM().toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="h-px bg-slate-200" />

              {/* Softer ALE card, using calculated ALE */}
              <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 flex items-baseline justify-between">
                <div className="flex flex-col gap-0.5">
                  <span className="text-xs font-medium tracking-wide uppercase text-slate-500">
                    Annual Loss Exposure (ALE)
                  </span>
                  <span className="text-[11px] text-slate-400">
                    LEF × Loss Magnitude (median)
                  </span>
                </div>
                <span className="text-lg font-semibold text-slate-900 tabular-nums">
                  ${Math.round(calculateALE()).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-8 pt-6 border-t border-slate-200">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <div className="flex gap-3">
            {currentStep !== 'metadata' && (
              <button
                onClick={handleBack}
                className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 flex items-center gap-2 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Back
              </button>
            )}
            {currentStep !== 'review' ? (
              <button
                onClick={handleNext}
                disabled={!isStepComplete(currentStep)}
                className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
              >
                Next
                <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2 transition-colors"
              >
                <Check className="w-4 h-4" />
                Create Scenario
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}