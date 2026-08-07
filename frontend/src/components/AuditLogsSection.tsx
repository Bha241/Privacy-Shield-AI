'use client';

import React, { useState, useEffect } from 'react';
import { ClipboardList, Search, Download, ShieldCheck, Filter } from 'lucide-react';
import { getAuditLogs, AuditLog } from '@/lib/api';

export function AuditLogsSection() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterType, setFilterType] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  useEffect(() => {
    async function fetchLogs() {
      try {
        const data = await getAuditLogs();
        setLogs(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchLogs();
  }, []);

  const filteredLogs = logs.filter((log) => {
    const matchesType = filterType === 'ALL' || log.event_type === filterType;
    const matchesSearch =
      log.details.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.user_id.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesType && matchesSearch;
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-cyan-400" /> Immutable DPDP / GDPR Audit Log Stream
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Tamper-proof compliance log trail recording all PII redactions, uploads, and RAG execution boundaries.
          </p>
        </div>

        <button
          onClick={() => {
            const jsonStr = JSON.stringify(logs, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `privacyshield_audit_logs_${Date.now()}.json`;
            a.click();
          }}
          className="px-4 py-2 bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs font-semibold rounded-xl flex items-center gap-2 transition self-start md:self-auto"
        >
          <Download className="h-4 w-4 text-cyan-400" /> Export JSON Audit Log
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row items-center gap-4">
        <div className="relative flex-1 w-full">
          <Search className="h-4 w-4 absolute left-3.5 top-3 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search audit trail by User ID or event details..."
            className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <Filter className="h-4 w-4 text-cyan-400" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs text-slate-200 rounded-xl px-3 py-2 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Event Types</option>
            <option value="PII_REDACTION">PII_REDACTION</option>
            <option value="RAG_CHAT_QUERY">RAG_CHAT_QUERY</option>
            <option value="DOCUMENT_INDEXED">DOCUMENT_INDEXED</option>
            <option value="DOCUMENT_UPLOAD">DOCUMENT_UPLOAD</option>
          </select>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-lg overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800 font-mono">
            <tr>
              <th className="py-3 px-4">Event Type</th>
              <th className="py-3 px-4">User Identity</th>
              <th className="py-3 px-4">Event Audit Details</th>
              <th className="py-3 px-4">Origin IP</th>
              <th className="py-3 px-4 text-right">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 font-mono">
            {filteredLogs.map((log) => (
              <tr key={log.id} className="hover:bg-slate-800/40 transition">
                <td className="py-3.5 px-4 font-bold">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] border ${
                      log.event_type === 'PII_REDACTION'
                        ? 'bg-cyan-950 text-cyan-400 border-cyan-800'
                        : log.event_type === 'RAG_CHAT_QUERY'
                        ? 'bg-indigo-950 text-indigo-400 border-indigo-800'
                        : 'bg-emerald-950 text-emerald-400 border-emerald-800'
                    }`}
                  >
                    {log.event_type}
                  </span>
                </td>
                <td className="py-3.5 px-4 text-slate-300 font-sans">{log.user_id}</td>
                <td className="py-3.5 px-4 text-emerald-300 font-mono leading-relaxed">{log.details}</td>
                <td className="py-3.5 px-4 text-slate-500">{log.ip_address}</td>
                <td className="py-3.5 px-4 text-right text-slate-400 text-[11px]">
                  {new Date(log.timestamp).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
