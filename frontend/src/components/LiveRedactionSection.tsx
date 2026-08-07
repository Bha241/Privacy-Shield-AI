'use client';

import React, { useState, useRef } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  FileText,
  Lock,
  Eye,
  RefreshCw,
  AlertTriangle,
  Copy,
  Check,
  Sliders,
  Tag,
  Paperclip,
  Columns,
  Sparkles,
  Download,
  Layers,
  FileCheck,
} from 'lucide-react';
import { redactPII, PIIRedactResponse, extractTextFromFile } from '@/lib/api';

export function LiveRedactionSection() {
  const [inputText, setInputText] = useState<string>(
    'Patient Rajesh Kumar (Aadhaar: 4521 8901 2345, PAN: ABCDE1234F) can be reached at rajesh.kumar@gmail.com or +91 9876543210. Primary credit card on file for billing: 4532 8900 1234 5678.'
  );
  const [attachedFileName, setAttachedFileName] = useState<string | null>('sample_patient_record.txt');
  const [maskingStrategy, setMaskingStrategy] = useState<string>('REPLACE');
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<PIIRedactResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleRedact = async () => {
    if (!inputText.trim()) return;
    setLoading(true);
    try {
      const res = await redactPII(inputText, maskingStrategy);
      setResult(res);
    } catch (err) {
      console.error('Redact error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAttachedFileName(file.name);
    setLoading(true);
    try {
      const text = await extractTextFromFile(file);
      setInputText(text);
      const res = await redactPII(text, maskingStrategy);
      setResult(res);
    } catch (err) {
      console.error('File analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (result?.redacted_text) {
      navigator.clipboard.writeText(result.redacted_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const triggerFilePicker = () => {
    fileInputRef.current?.click();
  };

  // Render original text with highlighted PII spans
  const renderHighlightedOriginalText = () => {
    if (!result || result.entities.length === 0) {
      return <div className="whitespace-pre-wrap">{inputText}</div>;
    }

    const sortedEntities = [...result.entities].sort((a, b) => a.start - b.start);
    const elements = [];
    let lastIndex = 0;

    sortedEntities.forEach((ent, idx) => {
      if (ent.start > lastIndex) {
        elements.push(inputText.substring(lastIndex, ent.start));
      }
      elements.push(
        <span
          key={`highlight-${idx}`}
          className="relative inline-block px-1.5 py-0.5 mx-0.5 rounded bg-cyan-950/80 border border-cyan-500/50 text-cyan-300 font-bold group cursor-pointer"
          title={`Detected PII: ${ent.entity_type} (Confidence: ${intToPercent(ent.score)})`}
        >
          {ent.text}
          <span className="ml-1 text-[9px] px-1 py-0.2 rounded bg-cyan-800 text-cyan-200 font-mono">
            {ent.entity_type}
          </span>
        </span>
      );
      lastIndex = Math.max(lastIndex, ent.end);
    });

    if (lastIndex < inputText.length) {
      elements.push(inputText.substring(lastIndex));
    }

    return <div className="whitespace-pre-wrap leading-relaxed">{elements}</div>;
  };

  const intToPercent = (score: number) => {
    return `${Math.round(score * 100)}%`;
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        className="hidden"
        accept=".txt,.pdf,.csv,.json,.md,.doc,.docx"
      />

      {/* Top Banner & Control Bar */}
      <div className="p-6 rounded-3xl bg-gradient-to-r from-slate-950/80 via-slate-900/90 to-slate-950/80 border border-white/10 backdrop-blur-2xl shadow-[0_20px_50px_rgba(0,0,0,0.8)] flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2.5">
            <ShieldAlert className="text-cyan-400 h-6 w-6" /> Live PII Detection &amp; Redaction Engine
          </h2>
          <p className="text-slate-400 text-xs">
            Multi-engine PII detection, side-by-side original vs. masked file comparison, and DPDP / GDPR risk scoring.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={triggerFilePicker}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition shadow-md cursor-pointer"
          >
            <Paperclip className="h-4 w-4 text-cyan-400" />
            <span>{attachedFileName ? `File: ${attachedFileName}` : 'Attach File'}</span>
          </button>

          <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300">
            <Sliders className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-slate-400">Strategy:</span>
            <select
              value={maskingStrategy}
              onChange={(e) => setMaskingStrategy(e.target.value)}
              className="bg-transparent text-cyan-300 font-bold focus:outline-none cursor-pointer"
            >
              <option value="REPLACE">Token [PLACEHOLDER]</option>
              <option value="HASH">SHA-256 Hash</option>
              <option value="MASK">Asterisk (****)</option>
            </select>
          </div>

          <button
            onClick={handleRedact}
            disabled={loading || !inputText.trim()}
            className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 transition shadow-lg shadow-cyan-500/20 disabled:opacity-50 cursor-pointer"
          >
            {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
            Analyze &amp; Mask
          </button>
        </div>
      </div>

      {/* Input Edit Box */}
      <div className="p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-3 shadow-[0_15px_40px_rgba(0,0,0,0.7)]">
        <div className="flex items-center justify-between">
          <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <FileText className="h-4 w-4 text-cyan-400" /> Input Payload Text / File Source
          </label>
          <span className="text-[10px] text-slate-500 font-mono">
            {inputText.length} characters {attachedFileName ? `• ${attachedFileName}` : ''}
          </span>
        </div>
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          rows={4}
          className="w-full p-4 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 focus:outline-none focus:border-cyan-500 text-xs font-mono leading-relaxed"
          placeholder="Paste raw text or attach a file containing PII (Aadhaar, PAN, Email, Phone, Credit Cards)..."
        />
      </div>

      {/* DETAILED SIDE-BY-SIDE FILE COMPARISON PANELS */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Columns className="h-4 w-4 text-cyan-400" /> Side-by-Side Detailed File Inspection
            {result && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                {result.entities.length} PII Tokens Identified
              </span>
            )}
          </h3>

          {result && (
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5 text-cyan-400" />}
              <span>{copied ? 'Copied Masked Text' : 'Copy Redacted Output'}</span>
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Panel: Original Text with PII Highlight Tags */}
          <div className="p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-3 shadow-[0_15px_40px_rgba(0,0,0,0.7)] flex flex-col">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <FileCheck className="h-4 w-4 text-cyan-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Original Text (Raw Payload)
                </span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">
                {result ? `${result.entities.length} PII Spans Detected` : 'Unanalyzed'}
              </span>
            </div>

            <div className="flex-1 p-4 bg-slate-950 border border-slate-800/90 rounded-xl text-slate-200 text-xs font-mono leading-relaxed min-h-[180px] max-h-[360px] overflow-y-auto">
              {renderHighlightedOriginalText()}
            </div>
          </div>

          {/* Right Panel: Live Tokenized Masked Text */}
          <div className="p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-3 shadow-[0_15px_40px_rgba(0,0,0,0.7)] flex flex-col">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-300">
                  Live Tokenized Masked Output (Zero Leakage)
                </span>
              </div>
              <span className="text-[10px] text-emerald-400 font-mono font-bold">
                {result ? `${result.risk_level} Risk` : 'Ready'}
              </span>
            </div>

            <div className="flex-1 p-4 bg-slate-950 border border-slate-800/90 rounded-xl text-emerald-300 text-xs font-mono leading-relaxed min-h-[180px] max-h-[360px] overflow-y-auto whitespace-pre-wrap">
              {result ? (
                result.redacted_text
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 py-10 space-y-2">
                  <ShieldCheck className="h-8 w-8 text-slate-700" />
                  <p className="text-xs">Click &quot;Analyze &amp; Mask&quot; above to view live tokenized output</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Analytics & Risk Score Section */}
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Privacy Exposure Meter */}
          <div className="p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-4 shadow-[0_15px_40px_rgba(0,0,0,0.7)]">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400" /> Privacy Exposure Meter
            </h3>

            <div className="text-center py-5 bg-slate-950/80 rounded-xl border border-slate-800 space-y-2">
              <div className="text-4xl font-black text-white font-mono">
                {result.risk_score}
                <span className="text-xs text-slate-500 font-normal">/100</span>
              </div>
              <div>
                <span
                  className={`inline-block px-3 py-1 rounded-full text-[10px] font-extrabold font-mono tracking-wider border ${
                    result.risk_level === 'CRITICAL'
                      ? 'bg-rose-950 text-rose-400 border-rose-800'
                      : result.risk_level === 'HIGH'
                      ? 'bg-amber-950 text-amber-400 border-amber-800'
                      : 'bg-emerald-950 text-emerald-400 border-emerald-800'
                  }`}
                >
                  RISK: {result.risk_level}
                </span>
              </div>
            </div>
          </div>

          {/* Classification & Compliance Frameworks */}
          <div className="lg:col-span-2 p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-4 shadow-[0_15px_40px_rgba(0,0,0,0.7)]">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Tag className="h-4 w-4 text-cyan-400" /> Document Classification &amp; Regulatory Alignment
            </h3>

            {result.classification ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                  <div className="text-slate-400 font-medium">Category:</div>
                  <div className="text-cyan-300 font-bold font-mono text-sm">
                    {result.classification.category}
                  </div>
                  <div className="text-[11px] text-slate-400 leading-relaxed">
                    {result.classification.summary}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <div className="text-slate-400 font-medium">Compliance Frameworks:</div>
                  <div className="flex flex-wrap gap-1.5">
                    {result.classification.compliance_frameworks.map((fw, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/60 text-[10px] font-mono font-semibold"
                      >
                        {fw}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-400">Classification pending analysis...</div>
            )}

            {/* Detected Entities List Breakdown */}
            {result.entities.length > 0 && (
              <div className="space-y-2 pt-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Detected Entities Breakdown ({result.entities.length} Items)
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 max-h-40 overflow-y-auto pr-1">
                  {result.entities.map((ent, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs"
                    >
                      <span className="font-bold text-cyan-400 font-mono text-[10px]">{ent.entity_type}</span>
                      <span className="font-mono text-slate-300 truncate max-w-[120px] text-[11px]" title={ent.text}>
                        {ent.text}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
