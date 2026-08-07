'use client';

import React from 'react';
import {
  Folder,
  ShieldCheck,
  Zap,
  Activity,
  CheckCircle,
  TrendingUp,
  Lock,
  Layers,
} from 'lucide-react';

export function DashboardSection() {
  const stats = [
    {
      label: 'Total Documents Indexed',
      value: '1,248',
      change: '+14.2% this month',
      icon: Folder,
      color: 'text-cyan-400',
    },
    {
      label: 'PII Spans Masked',
      value: '14,920',
      change: 'Zero raw leakage',
      icon: ShieldCheck,
      color: 'text-emerald-400',
    },
    {
      label: 'Demasked RAG Queries',
      value: '3,840',
      change: 'Avg latency 140ms',
      icon: Zap,
      color: 'text-indigo-400',
    },
    {
      label: 'Compliance Health',
      value: '99.4%',
      change: 'DPDP / GDPR Compliant',
      icon: Activity,
      color: 'text-purple-400',
    },
  ];

  const categories = [
    { name: 'Healthcare & PHI (Aadhaar, Diagnosis)', count: 540, percentage: 43, color: 'bg-cyan-500' },
    { name: 'Financial Records (PAN, Accounts)', count: 380, percentage: 30, color: 'bg-indigo-500' },
    { name: 'HR & Employee Data (Emails, Phones)', count: 210, percentage: 17, color: 'bg-emerald-500' },
    { name: 'Technical Logs & IP Addresses', count: 118, percentage: 10, color: 'bg-amber-500' },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Page Title */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-cyan-400" /> Privacy Posture &amp; Analytics Dashboard
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Enterprise overview across document indexes, PII entity risk, and RAG execution boundaries.
          </p>
        </div>
        <span className="px-3 py-1 rounded-full bg-emerald-950 border border-emerald-800/60 text-emerald-400 text-xs font-mono font-bold">
          ● Privacy Shield Active
        </span>
      </div>

      {/* Top 4 Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <div
              key={idx}
              className="p-5 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 shadow-[0_15px_35px_rgba(0,0,0,0.7)] space-y-3 transition hover:border-cyan-500/40"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400">{stat.label}</span>
                <Icon className={`h-5 w-5 ${stat.color}`} />
              </div>
              <div className="text-2xl font-black text-white font-mono">{stat.value}</div>
              <div className="text-[10px] text-slate-400 font-mono">{stat.change}</div>
            </div>
          );
        })}
      </div>

      {/* Charts & Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Distribution Breakdown (2 cols) */}
        <div className="lg:col-span-2 p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-5 shadow-[0_15px_40px_rgba(0,0,0,0.7)]">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Layers className="h-4 w-4 text-cyan-400" /> Indexed Content &amp; Entity Distribution
          </h3>

          <div className="space-y-4">
            {categories.map((cat, idx) => (
              <div key={idx} className="space-y-1.5">
                <div className="flex justify-between text-xs text-slate-300 font-medium">
                  <span>{cat.name}</span>
                  <span className="font-mono text-cyan-400">
                    {cat.count} docs ({cat.percentage}%)
                  </span>
                </div>
                <div className="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                  <div
                    className={`h-full rounded-full ${cat.color} transition-all duration-500`}
                    style={{ width: `${cat.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Compliance Status Card (1 col) */}
        <div className="p-6 rounded-3xl bg-slate-900/50 backdrop-blur-2xl border border-white/10 space-y-4 shadow-[0_15px_40px_rgba(0,0,0,0.7)]">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Lock className="h-4 w-4 text-emerald-400" /> Regulatory Framework Status
          </h3>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-200">DPDP Act 2023</div>
                <div className="text-[10px] text-slate-400">India Digital Personal Data Protection</div>
              </div>
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-200">GDPR Art. 9</div>
                <div className="text-[10px] text-slate-400">EU Special Category Personal Data</div>
              </div>
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-200">HIPAA PHI Rules</div>
                <div className="text-[10px] text-slate-400">US Health Insurance Portability</div>
              </div>
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-200">PCI-DSS v4.0</div>
                <div className="text-[10px] text-slate-400">Payment Card Industry Data Security</div>
              </div>
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
