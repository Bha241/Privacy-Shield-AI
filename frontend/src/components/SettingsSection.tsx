'use client';

import React, { useEffect, useState } from 'react';
import { Sliders, Cpu, Save, Check, CalendarClock, Trash2, AlertTriangle } from 'lucide-react';
import { deleteAllWorkspaceData, getRetentionSettings, RetentionSettings, updateRetentionSettings } from '../lib/api';

interface SettingsSectionProps {
  gridEnabled: boolean;
  setGridEnabled: (enabled: boolean) => void;
}

export function SettingsSection({ gridEnabled, setGridEnabled }: SettingsSectionProps) {
  const [model, setModel] = useState('Llama-3.3-70B');
  const [temperature, setTemperature] = useState(0.2);
  const [topP, setTopP] = useState(0.9);
  const [maxTokens, setMaxTokens] = useState(1024);

  const [saved, setSaved] = useState(false);
  const [retention, setRetention] = useState<RetentionSettings | null>(null);
  const [retentionDays, setRetentionDays] = useState(7);
  const [retentionBusy, setRetentionBusy] = useState(false);
  const [retentionMessage, setRetentionMessage] = useState('');
  const [retentionError, setRetentionError] = useState('');
  const [pendingRetentionAction, setPendingRetentionAction] = useState<'reduce' | null>(null);
  const [deleteAllStep, setDeleteAllStep] = useState<'confirm' | 'type' | null>(null);
  const [deleteAllText, setDeleteAllText] = useState('');
  const [deleteAllBusy, setDeleteAllBusy] = useState(false);
  const [deleteAllMessage, setDeleteAllMessage] = useState('');

  useEffect(() => {
    void getRetentionSettings()
      .then((data) => {
        setRetention(data);
        setRetentionDays(data.retention_days);
      })
      .catch((error: unknown) => setRetentionError(error instanceof Error ? error.message : 'Unable to load retention settings'));
  }, []);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const saveRetention = async (confirmed = false) => {
    if (!retention) return;
    if (retentionDays < retention.retention_days && !confirmed) {
      setPendingRetentionAction('reduce');
      return;
    }
    setRetentionBusy(true);
    setRetentionMessage('');
    setRetentionError('');
    try {
      const updated = await updateRetentionSettings(retentionDays);
      setRetention(updated);
      setRetentionMessage('Retention policy saved.');
      setPendingRetentionAction(null);
    } catch (error: unknown) {
      setRetentionError(error instanceof Error ? error.message : 'Unable to save retention policy');
    } finally {
      setRetentionBusy(false);
    }
  };

  const openDeleteAll = () => {
    setDeleteAllText('');
    setDeleteAllMessage('');
    setDeleteAllStep('confirm');
  };

  const deleteAllData = async () => {
    if (deleteAllText !== 'DELETE ALL DATA') return;
    setDeleteAllBusy(true);
    setDeleteAllMessage('Deleting workspace data...');
    try {
      const result = await deleteAllWorkspaceData();
      setDeleteAllMessage(`All workspace document data has been deleted. ${result.documents_deleted} document(s) removed.`);
      setDeleteAllStep(null);
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem('privacyshield:selected-document-id');
        window.dispatchEvent(new CustomEvent('privacyshield:all-data-deleted'));
      }
    } catch (error: unknown) {
      setDeleteAllMessage(error instanceof Error ? error.message : 'Unable to delete workspace data');
    } finally {
      setDeleteAllBusy(false);
    }
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

        <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-5 shadow-lg">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-cyan-400" /> Data retention
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Automatically remove protected document data after a fixed number of calendar days.
              </p>
            </div>
            <span className="text-[10px] uppercase tracking-wider text-emerald-400 border border-emerald-900 bg-emerald-950/40 rounded-full px-2 py-1">Backend controlled</span>
          </div>

          {retention ? (
            <>
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between rounded-xl bg-slate-950 border border-slate-800 p-3">
                  <span className="text-slate-400">Current retention</span>
                  <span className="text-slate-100 font-semibold">{retention.retention_days} days</span>
                </div>
                <label className="text-xs text-slate-300 space-y-1.5 block">
                  <span className="block font-medium">Retention period</span>
                  <select value={retentionDays} onChange={(e) => setRetentionDays(Number(e.target.value))} className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 focus:outline-none focus:border-cyan-500">
                    {Array.from({ length: 15 }, (_, index) => index + 7).map((days) => <option key={days} value={days}>{days} days</option>)}
                  </select>
                </label>
              </div>
              <button onClick={() => void saveRetention()} disabled={retentionBusy || retentionDays === retention.retention_days} className="w-full px-4 py-2.5 rounded-xl bg-cyan-500 text-slate-950 text-xs font-bold disabled:opacity-50">Save retention</button>
              <p className="text-[11px] text-slate-500">Allowed range: {retention.min_days}–{retention.max_days} days · Timezone: {retention.timezone}</p>
              {retentionMessage && <p className="text-xs text-emerald-300 flex items-center gap-2"><Check className="h-4 w-4" /> {retentionMessage}</p>}
              {retentionError && <p className="text-xs text-rose-300 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> {retentionError}</p>}
            </>
          ) : retentionError ? (
            <p className="text-xs text-rose-300 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> {retentionError}</p>
          ) : <p className="text-xs text-slate-500">Loading retention policy...</p>}
        </div>

      </div>

      <div className="p-6 rounded-2xl bg-rose-950/15 border border-rose-900/70 space-y-4 shadow-lg">
        <div className="flex items-start gap-3">
          <Trash2 className="h-5 w-5 text-rose-300 mt-0.5" />
          <div>
            <h3 className="text-sm font-bold text-rose-100">Danger Zone</h3>
            <p className="text-xs text-rose-200/70 mt-1">Permanently delete all protected document data from this workspace.</p>
          </div>
        </div>
        <button onClick={openDeleteAll} className="w-full px-4 py-2.5 rounded-xl border border-rose-700 bg-rose-950/60 text-rose-100 text-xs font-bold hover:bg-rose-900/70 transition">
          Delete all data now
        </button>
        {deleteAllMessage && <p className="text-xs text-emerald-300 flex items-center gap-2"><Check className="h-4 w-4" /> {deleteAllMessage}</p>}
      </div>

      <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-lg">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-slate-200">Workspace grid</h3>
            <p className="text-xs text-slate-400 mt-1">
              Show the subtle technical grid behind Chat and Live Redaction workspaces.
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input
              type="checkbox"
              checked={gridEnabled}
              onChange={(e) => setGridEnabled(e.target.checked)}
              className="sr-only peer"
              aria-label="Toggle workspace grid"
            />
            <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500"></div>
          </label>
        </div>
      </div>

      {pendingRetentionAction === 'reduce' && retention && (
        <div className="workspace-modal fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-labelledby="retention-confirm-title">
          <div className="bg-slate-900 border border-amber-800/70 p-6 rounded-2xl max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-amber-950/60 p-2 text-amber-300"><AlertTriangle className="h-5 w-5" /></div>
              <div>
                <h3 id="retention-confirm-title" className="text-lg font-bold text-white">Confirm retention action</h3>
                <p className="text-xs text-slate-400 mt-1">Changing retention from {retention.retention_days} to {retentionDays} days may make older documents eligible for deletion during the next cleanup.</p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setPendingRetentionAction(null)} disabled={retentionBusy} className="px-4 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs hover:bg-slate-800 disabled:opacity-50">Cancel</button>
              <button onClick={() => void saveRetention(true)} disabled={retentionBusy} className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold disabled:opacity-50">{retentionBusy ? 'Processing...' : 'Continue'}</button>
            </div>
          </div>
        </div>
      )}

      {deleteAllStep && (
        <div className="workspace-modal fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-labelledby="delete-all-title">
          <div className="bg-slate-900 border border-rose-800/80 p-6 rounded-2xl max-w-lg w-full space-y-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-rose-950/70 p-2 text-rose-300"><Trash2 className="h-5 w-5" /></div>
              <div>
                <h3 id="delete-all-title" className="text-lg font-bold text-white">{deleteAllStep === 'confirm' ? 'Delete all workspace data?' : 'Confirm permanent deletion'}</h3>
                <p className="text-xs text-slate-400 mt-1">This permanently removes uploaded documents, masked data, PII mappings, vector data, and related processing state. Retention settings, users, and audit metadata are preserved.</p>
              </div>
            </div>
            {deleteAllStep === 'confirm' ? (
              <div className="flex justify-end gap-2">
                <button onClick={() => setDeleteAllStep(null)} className="px-4 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs hover:bg-slate-800">Cancel</button>
                <button onClick={() => setDeleteAllStep('type')} className="px-4 py-2 rounded-xl bg-rose-700 hover:bg-rose-600 text-white text-xs font-bold">Continue</button>
              </div>
            ) : (
              <>
                <label className="block text-xs text-slate-300">Type <span className="font-mono font-bold text-rose-300">DELETE ALL DATA</span> to enable deletion.
                  <input autoFocus value={deleteAllText} onChange={(event) => setDeleteAllText(event.target.value)} className="mt-2 w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-700 text-slate-100 font-mono text-sm focus:outline-none focus:border-rose-500" placeholder="DELETE ALL DATA" />
                </label>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setDeleteAllStep(null)} disabled={deleteAllBusy} className="px-4 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs hover:bg-slate-800 disabled:opacity-50">Cancel</button>
                  <button onClick={() => void deleteAllData()} disabled={deleteAllText !== 'DELETE ALL DATA' || deleteAllBusy} className="px-4 py-2 rounded-xl bg-rose-700 hover:bg-rose-600 text-white text-xs font-bold disabled:opacity-50">{deleteAllBusy ? 'Deleting...' : 'Delete all data permanently'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
