'use client';

import React, { useState } from 'react';
import { Sliders, Cpu, Shield, Key, Save, Check } from 'lucide-react';

export function SettingsSection() {
  const [model, setModel] = useState('Llama-3.3-70B');
  const [temperature, setTemperature] = useState(0.2);
  const [topP, setTopP] = useState(0.9);
  const [maxTokens, setMaxTokens] = useState(1024);

  const [entities, setEntities] = useState({
    aadhaar: true,
    pan: true,
    email: true,
    phone: true,
    creditCard: true,
    ipAddress: true,
    ssn: false,
  });

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto overflow-y-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <Sliders className="h-6 w-6 text-cyan-400" /> Platform &amp; LLM Privacy Settings
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Configure PII detection rules, LLM RAG inference parameters, and tenant boundaries.
          </p>
        </div>

        <button
          onClick={handleSave}
          className="px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 transition shadow-lg shadow-cyan-500/20"
        >
          {saved ? <Check className="h-4 w-4 text-slate-950" /> : <Save className="h-4 w-4 text-slate-950" />}
          {saved ? 'Settings Saved!' : 'Save Changes'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* LLM RAG Parameters */}
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-5 shadow-lg">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Cpu className="h-4 w-4 text-indigo-400" /> Isolated LLM Inference Parameters
          </h3>

          <div className="space-y-4 text-xs">
            <div className="space-y-1.5">
              <label className="text-slate-300 font-medium">Default RAG Model</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 font-mono text-xs focus:outline-none focus:border-cyan-500"
              >
                <option value="Llama-3.3-70B">Llama-3.3-70B</option>
                <option value="Mistral-7B-Masked">Mistral-7B-Masked</option>
                <option value="GPT-4o-ZeroPII">GPT-4o-ZeroPII</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-slate-300">
                <span>Temperature ({temperature})</span>
                <span className="text-slate-500">Deterministic RAG</span>
              </div>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-cyan-500 cursor-pointer"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-slate-300">
                <span>Top P ({topP})</span>
                <span className="text-slate-500 font-mono">Nucleus Sampling</span>
              </div>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={topP}
                onChange={(e) => setTopP(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 cursor-pointer"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-slate-300 font-medium">Max Token Limit</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 512)}
                className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 font-mono text-xs focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
        </div>

        {/* PII Entity Rule Toggles */}
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-5 shadow-lg">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Shield className="h-4 w-4 text-cyan-400" /> Active PII Redaction Rules
          </h3>

          <div className="space-y-3 text-xs">
            {Object.entries(entities).map(([key, enabled]) => (
              <div key={key} className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="font-mono uppercase text-cyan-400 font-bold text-[11px]">{key}</span>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) =>
                      setEntities((prev) => ({ ...prev, [key]: e.target.checked }))
                    }
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500"></div>
                </label>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
