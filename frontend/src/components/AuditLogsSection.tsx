'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ClipboardList, Search, Download, Filter, RefreshCw, AlertCircle } from 'lucide-react';
import { getAuditLogs, AuditLog } from '@/lib/api';

function detailsText(details: AuditLog['details']): string {
  if (typeof details === 'string') return details;
  return String(details.description || details.action || details.message || JSON.stringify(details));
}

export function AuditLogsSection() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterType, setFilterType] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const fetchLogs = useCallback(async () => {
    setError('');
    try {
      setLogs(await getAuditLogs());
    } catch (err) {
      console.error('Audit log load failed:', err);
      setError('Unable to load audit trail');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void fetchLogs(); }, 0);
    const interval = window.setInterval(() => { void fetchLogs(); }, 10000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [fetchLogs]);

  const eventTypes = useMemo(
    () => Array.from(new Set(logs.map((log) => log.event_type).filter(Boolean))).sort(),
    [logs]
  );

  const filteredLogs = logs.filter((log) => {
    const haystack = [
      log.event_type,
      log.document_name || '',
      log.document_id || '',
      log.user_id || log.actor_id || '',
      detailsText(log.details),
    ].join(' ').toLowerCase();
    return (filterType === 'ALL' || log.event_type === filterType)
      && haystack.includes(searchTerm.toLowerCase());
  });

  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `privacyshield-audit-log-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-cyan-400" /> Immutable DPDP / GDPR Audit Log Stream
          </h2>
          <p className="text-xs text-slate-400 mt-1">Live records from the PostgreSQL audit trail.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => void fetchLogs()} className="px-3 py-2 bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs rounded-xl flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-cyan-400" /> Refresh
          </button>
          <button onClick={exportLogs} disabled={!logs.length} className="px-4 py-2 bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs font-semibold rounded-xl flex items-center gap-2 disabled:opacity-50">
            <Download className="h-4 w-4 text-cyan-400" /> Export JSON Audit Log
          </button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row items-center gap-4">
        <div className="relative flex-1 w-full">
          <Search className="h-4 w-4 absolute left-3.5 top-3 text-slate-400" />
          <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search by document, ID, user, event, or details..." className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500" />
        </div>
        <div className="flex items-center gap-2 w-full md:w-auto">
          <Filter className="h-4 w-4 text-cyan-400" />
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)} className="bg-slate-900 border border-slate-800 text-xs text-slate-200 rounded-xl px-3 py-2 focus:outline-none cursor-pointer">
            <option value="ALL">All Event Types</option>
            {eventTypes.map((eventType) => <option key={eventType} value={eventType}>{eventType}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="p-10 rounded-2xl bg-slate-900/90 border border-slate-800 text-center text-xs text-slate-400">Loading audit trail...</div>
      ) : error ? (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-rose-900/70 text-center text-xs text-rose-300 space-y-3">
          <AlertCircle className="h-5 w-5 mx-auto" />
          <p>{error}</p>
          <button onClick={() => void fetchLogs()} className="px-3 py-2 rounded-lg bg-slate-800 text-slate-200">Retry</button>
        </div>
      ) : filteredLogs.length === 0 ? (
        <div className="p-10 rounded-2xl bg-slate-900/90 border border-slate-800 text-center text-xs text-slate-400">No audit events found</div>
      ) : (
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-lg overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800 font-mono">
              <tr><th className="py-3 px-4">Event Type</th><th className="py-3 px-4">Document</th><th className="py-3 px-4">User Identity</th><th className="py-3 px-4">Event Audit Details</th><th className="py-3 px-4">Origin IP</th><th className="py-3 px-4 text-right">Timestamp</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-800 font-mono">
              {filteredLogs.map((log) => {
                const documentName = log.document_name || log.document_id || '—';
                return (
                  <tr key={log.id || log.event_id || log.log_id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3.5 px-4 font-bold"><span className="px-2 py-0.5 rounded text-[10px] border bg-emerald-950 text-emerald-400 border-emerald-800">{log.event_type}</span></td>
                    <td className="py-3.5 px-4 max-w-[220px]" title={documentName}><span className="block truncate text-cyan-300">{documentName}</span></td>
                    <td className="py-3.5 px-4 text-slate-300 font-sans">{log.user_id || log.actor_id || '—'}</td>
                    <td className="py-3.5 px-4 text-emerald-300 font-mono leading-relaxed">{detailsText(log.details)}</td>
                    <td className="py-3.5 px-4 text-slate-500">{log.origin_ip || log.ip_address || '—'}</td>
                    <td className="py-3.5 px-4 text-right text-slate-400 text-[11px]">{new Date(log.timestamp).toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
