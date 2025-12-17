import { useState } from 'react';
import { ControlSelection } from '../App.tsx';
import { Plus, X, Shield } from 'lucide-react';

interface ControlsSelectorProps {
  controls: ControlSelection[];
  onChange: (controls: ControlSelection[]) => void;
}

// FAIR-CAM mapped controls from various frameworks
const CONTROL_FRAMEWORKS = {
  'NIST CSF': [
    { id: 'PR.AC-1', name: 'Identity Management', category: 'Protect', fairCamImpact: 25 },
    { id: 'PR.AC-3', name: 'Remote Access Management', category: 'Protect', fairCamImpact: 20 },
    { id: 'PR.AC-4', name: 'Access Permissions', category: 'Protect', fairCamImpact: 22 },
    { id: 'PR.AC-5', name: 'Network Segmentation', category: 'Protect', fairCamImpact: 30 },
    { id: 'PR.DS-1', name: 'Data at Rest Protection', category: 'Protect', fairCamImpact: 28 },
    { id: 'PR.DS-2', name: 'Data in Transit Protection', category: 'Protect', fairCamImpact: 26 },
    { id: 'PR.IP-1', name: 'Baseline Configuration', category: 'Protect', fairCamImpact: 18 },
    { id: 'PR.IP-4', name: 'Backups', category: 'Protect', fairCamImpact: 35 },
    { id: 'PR.IP-12', name: 'Vulnerability Management', category: 'Protect', fairCamImpact: 32 },
    { id: 'DE.AE-1', name: 'Network Baseline Established', category: 'Detect', fairCamImpact: 15 },
    { id: 'DE.CM-1', name: 'Network Monitoring', category: 'Detect', fairCamImpact: 28 },
    { id: 'DE.CM-4', name: 'Malicious Code Detection', category: 'Detect', fairCamImpact: 30 },
    { id: 'DE.CM-7', name: 'Unauthorized Activity Monitoring', category: 'Detect', fairCamImpact: 25 },
    { id: 'RS.RP-1', name: 'Response Plan Execution', category: 'Respond', fairCamImpact: 20 },
    { id: 'RS.MI-3', name: 'Incident Containment', category: 'Respond', fairCamImpact: 22 },
  ],
  'CIS Controls': [
    { id: 'CIS-1', name: 'Inventory of Authorized Devices', category: 'Basic', fairCamImpact: 15 },
    { id: 'CIS-2', name: 'Inventory of Authorized Software', category: 'Basic', fairCamImpact: 15 },
    { id: 'CIS-3', name: 'Data Protection', category: 'Basic', fairCamImpact: 25 },
    { id: 'CIS-4', name: 'Secure Configuration', category: 'Basic', fairCamImpact: 20 },
    { id: 'CIS-5', name: 'Account Management', category: 'Basic', fairCamImpact: 24 },
    { id: 'CIS-6', name: 'Access Control Management', category: 'Foundational', fairCamImpact: 26 },
    { id: 'CIS-8', name: 'Audit Log Management', category: 'Foundational', fairCamImpact: 18 },
    { id: 'CIS-10', name: 'Malware Defenses', category: 'Foundational', fairCamImpact: 28 },
    { id: 'CIS-11', name: 'Data Recovery', category: 'Foundational', fairCamImpact: 32 },
  ],
  'ISO 27001': [
    { id: 'A.5.1', name: 'Policies for Information Security', category: 'Organizational', fairCamImpact: 12 },
    { id: 'A.8.2', name: 'Information Classification', category: 'Asset Management', fairCamImpact: 16 },
    { id: 'A.9.1', name: 'Access Control Policy', category: 'Access Control', fairCamImpact: 22 },
    { id: 'A.9.2', name: 'User Access Management', category: 'Access Control', fairCamImpact: 25 },
    { id: 'A.9.4', name: 'System Access Control', category: 'Access Control', fairCamImpact: 24 },
    { id: 'A.10.1', name: 'Cryptographic Controls', category: 'Cryptography', fairCamImpact: 30 },
    { id: 'A.12.2', name: 'Protection from Malware', category: 'Operations', fairCamImpact: 28 },
    { id: 'A.12.3', name: 'Backup', category: 'Operations', fairCamImpact: 33 },
    { id: 'A.12.4', name: 'Logging and Monitoring', category: 'Operations', fairCamImpact: 26 },
    { id: 'A.16.1', name: 'Incident Response', category: 'Incident Management', fairCamImpact: 20 },
  ],
};

export function ControlsSelector({ controls, onChange }: ControlsSelectorProps) {
  const [selectedFramework, setSelectedFramework] = useState<string>('NIST CSF');
  const [selectedControl, setSelectedControl] = useState<string>('');
  const [effectiveness, setEffectiveness] = useState<number>(70);
  const [showCustom, setShowCustom] = useState(false);
  const [customControl, setCustomControl] = useState({ name: '', effectiveness: 70 });

  const availableControls = CONTROL_FRAMEWORKS[selectedFramework as keyof typeof CONTROL_FRAMEWORKS] || [];

  const handleAddControl = () => {
    if (!selectedControl) return;
    
    const control = availableControls.find((c) => c.id === selectedControl);
    if (!control) return;

    const newControl: ControlSelection = {
      framework: selectedFramework,
      controlId: control.id,
      controlName: control.name,
      effectiveness,
    };

    onChange([...controls, newControl]);
    setSelectedControl('');
    setEffectiveness(70);
  };

  const handleAddCustomControl = () => {
    if (!customControl.name) return;

    const newControl: ControlSelection = {
      framework: 'Custom',
      controlId: `CUSTOM-${Date.now()}`,
      controlName: customControl.name,
      effectiveness: customControl.effectiveness,
    };

    onChange([...controls, newControl]);
    setCustomControl({ name: '', effectiveness: 70 });
    setShowCustom(false);
  };

  const handleRemoveControl = (index: number) => {
    onChange(controls.filter((_, i) => i !== index));
  };

  return (
    <div className="border border-slate-200 rounded-lg p-6 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="w-5 h-5 text-blue-600" />
        <h3 className="text-slate-900">Controls (FAIR-CAM)</h3>
      </div>

      <div className="text-sm text-slate-600 mb-4">
        Select security controls to reduce susceptibility. Control effectiveness impacts the overall risk calculation.
      </div>

      {/* Framework Selector */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-slate-700 mb-2">Framework</label>
          <select
            value={selectedFramework}
            onChange={(e) => {
              setSelectedFramework(e.target.value);
              setSelectedControl('');
            }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            {Object.keys(CONTROL_FRAMEWORKS).map((framework) => (
              <option key={framework} value={framework}>
                {framework}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-slate-700 mb-2">Control</label>
          <select
            value={selectedControl}
            onChange={(e) => setSelectedControl(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value="">Select a control...</option>
            {availableControls.map((control) => (
              <option key={control.id} value={control.id}>
                {control.id} - {control.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm text-slate-700 mb-2">
          Control Effectiveness (%)
        </label>
        <input
          type="number"
          min="0"
          max="100"
          step="5"
          value={effectiveness}
          onChange={(e) => setEffectiveness(Number(e.target.value))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
        />
        <div className="mt-2 h-2 bg-slate-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-600 transition-all"
            style={{ width: `${effectiveness}%` }}
          />
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleAddControl}
          disabled={!selectedControl}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Control
        </button>
        <button
          onClick={() => setShowCustom(!showCustom)}
          className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 flex items-center gap-2 text-sm transition-colors"
        >
          <Plus className="w-4 h-4" />
          Custom Control
        </button>
      </div>

      {/* Custom Control Form */}
      {showCustom && (
        <div className="bg-slate-50 rounded-lg p-4 space-y-3">
          <div>
            <label className="block text-sm text-slate-700 mb-2">Custom Control Name</label>
            <input
              type="text"
              value={customControl.name}
              onChange={(e) => setCustomControl({ ...customControl, name: e.target.value })}
              placeholder="e.g., Employee Security Training"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-2">Effectiveness (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              step="5"
              value={customControl.effectiveness}
              onChange={(e) => setCustomControl({ ...customControl, effectiveness: Number(e.target.value) })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <button
            onClick={handleAddCustomControl}
            disabled={!customControl.name}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm transition-colors"
          >
            Add Custom Control
          </button>
        </div>
      )}

      {/* Selected Controls */}
      {controls.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm text-slate-700">Selected Controls ({controls.length})</div>
          {controls.map((control, index) => (
            <div
              key={index}
              className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-3 py-2"
            >
              <div className="flex-1">
                <div className="text-sm text-slate-900">
                  <span className="text-blue-600">{control.framework}</span> - {control.controlId}
                </div>
                <div className="text-xs text-slate-600">{control.controlName}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate-700">{control.effectiveness}%</span>
                <button
                  onClick={() => handleRemoveControl(index)}
                  className="p-1 hover:bg-blue-100 rounded transition-colors"
                >
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
