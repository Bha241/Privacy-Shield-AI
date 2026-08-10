'use client';

import React, { useEffect, useState } from 'react';
import {
  Folder,
  Upload,
  Trash2,
  MessageSquareText,
  Search,
  Plus,
  CheckCircle,
  X,
  File,
  AlertTriangle,
} from 'lucide-react';
import {
  DocumentItem,
  listDocuments,
  registerDocument,
  extractTextFromFile,
  redactPII,
  applyDocumentMasking,
  deleteDocument,
} from '@/lib/api';

interface DocumentsSectionProps {
  onSelectDocForChat?: (documentId: string) => void;
}

export function DocumentsSection({ onSelectDocForChat }: DocumentsSectionProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  const [searchTerm, setSearchTerm] = useState('');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const refreshDocuments = async () => {
    const library = await listDocuments();
    setDocuments(library.map((document) => ({
      id: document.id,
      filename: document.filename,
      size: '—',
      category: document.category || document.classification || 'General',
      sensitivity: (document.risk_score || 0) > 60 ? 'HIGH' : (document.risk_score || 0) >= 30 ? 'MEDIUM' : 'LOW',
      risk_score: document.risk_score || 0,
      char_count: 0,
      status: document.status === 'READY' ? 'INDEXED' : 'PROCESSING',
      created_at: document.created_at || '',
    })));
  };

  useEffect(() => {
    let cancelled = false;
    listDocuments().then((library) => {
      if (cancelled) return;
      setDocuments(library.map((document) => ({
        id: document.id,
        filename: document.filename,
        size: '—',
        category: document.category || document.classification || 'General',
      sensitivity: (document.risk_score || 0) > 60 ? 'HIGH' : (document.risk_score || 0) >= 30 ? 'MEDIUM' : 'LOW',
        risk_score: document.risk_score || 0,
        char_count: 0,
        status: document.status === 'READY' ? 'INDEXED' : 'PROCESSING',
        created_at: document.created_at || '',
      })));
    }).catch((err) => console.error('Document library failed:', err));
    return () => { cancelled = true; };
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const registered = await registerDocument(file.name, file.type || 'application/octet-stream');
      const text = await extractTextFromFile(file);
      const analysis = await redactPII(text);
      await applyDocumentMasking(registered.id, text, analysis.entities);
      await refreshDocuments();
      setShowUploadModal(false);
    } catch (err) {
      console.error('Upload failed:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDocument = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteDocument(deleteTarget.id);
      setDocuments((current) => current.filter((document) => document.id !== deleteTarget.id));
      if (typeof window !== 'undefined') {
        if (window.localStorage.getItem('privacyshield:selected-document-id') === deleteTarget.id) {
          window.localStorage.removeItem('privacyshield:selected-document-id');
        }
        window.dispatchEvent(new CustomEvent('privacyshield:document-deleted', { detail: deleteTarget.id }));
      }
      setDeleteTarget(null);
    } catch (error: unknown) {
      setDeleteError(error instanceof Error ? error.message : 'Unable to delete document');
    } finally {
      setDeleting(false);
    }
  };

  const filteredDocs = documents.filter(
    (d) =>
      d.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Top Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <Folder className="h-6 w-6 text-cyan-400" /> Classified Vector Document Library
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Documents indexed into privacy vector space with isolated entity placeholders.
          </p>
        </div>

        <button
          onClick={() => setShowUploadModal(true)}
          className="px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-lg shadow-cyan-500/20 transition self-start md:self-auto"
        >
          <Plus className="h-4 w-4" /> Upload Document
        </button>
      </div>

      {/* Search Bar */}
      <div className="relative max-w-md">
        <Search className="h-4 w-4 absolute left-3.5 top-3 text-slate-400" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Filter document index by filename or category..."
          className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
        />
      </div>

      {/* Table */}
      <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-lg overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800 font-mono">
            <tr>
              <th className="py-3 px-4">Document Name</th>
              <th className="py-3 px-4">Category</th>
              <th className="py-3 px-4">Sensitivity</th>
              <th className="py-3 px-4">Risk Score</th>
              <th className="py-3 px-4">Vector Status</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 font-mono">
            {filteredDocs.map((doc) => (
              <tr key={doc.id} className="hover:bg-slate-800/40 transition">
                <td className="py-3.5 px-4 font-bold text-slate-200 flex items-center gap-2">
                  <File className="h-4 w-4 text-cyan-400" />
                  <div>
                    <div>{doc.filename}</div>
                    <div className="text-[10px] text-slate-500 font-normal">{doc.size}</div>
                  </div>
                </td>
                <td className="py-3.5 px-4 text-slate-400 font-sans">{doc.category}</td>
                <td className="py-3.5 px-4">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                      doc.sensitivity === 'RESTRICTED'
                        ? 'bg-rose-950 text-rose-400 border-rose-800'
                        : doc.sensitivity === 'HIGH'
                        ? 'bg-amber-950 text-amber-400 border-amber-800'
                        : 'bg-emerald-950 text-emerald-400 border-emerald-800'
                    }`}
                  >
                    {doc.sensitivity}
                  </span>
                </td>
                <td className="py-3.5 px-4 font-bold text-slate-200">
                  {doc.risk_score} <span className="text-[10px] text-slate-500">/ 100</span>
                </td>
                <td className="py-3.5 px-4">
                  <span className="flex items-center gap-1.5 text-emerald-400 text-[11px] font-sans">
                    <CheckCircle className="h-3.5 w-3.5" /> Redacted &amp; Vectorized
                  </span>
                </td>
                <td className="py-3.5 px-4 text-right space-x-2">
                  {onSelectDocForChat && (
                    <button
                      onClick={() => onSelectDocForChat(doc.id)}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-cyan-400 font-sans rounded-lg transition text-[11px] inline-flex items-center gap-1"
                    >
                      <MessageSquareText className="h-3 w-3" /> RAG Chat
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setDeleteError('');
                      setDeleteTarget(doc);
                    }}
                    className="p-1 text-slate-500 hover:text-rose-400 transition"
                    title="Delete document"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {deleteTarget && (
        <div className="workspace-modal fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-labelledby="delete-document-title">
          <div className="bg-slate-900 border border-rose-900/70 p-6 rounded-2xl max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-rose-950/60 p-2 text-rose-300"><AlertTriangle className="h-5 w-5" /></div>
              <div>
                <h3 id="delete-document-title" className="text-lg font-bold text-white">Delete document permanently?</h3>
                <p className="text-xs text-slate-400 mt-1 break-all">{deleteTarget.filename}</p>
              </div>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">This document and all associated protected data will be deleted immediately, including original and masked text, PII mappings, entities, and vector chunks. This action cannot be undone.</p>
            {deleteError && <p className="text-xs text-rose-300 border border-rose-900/60 bg-rose-950/30 rounded-lg p-3">{deleteError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setDeleteTarget(null)} disabled={deleting} className="px-4 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs hover:bg-slate-800 disabled:opacity-50">Cancel</button>
              <button onClick={() => void handleDeleteDocument()} disabled={deleting} className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold disabled:opacity-50">{deleting ? 'Deleting...' : 'Delete permanently'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Multi-Modal Upload Modal */}
      {showUploadModal && (
        <div className="workspace-modal fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl max-w-md w-full space-y-4 shadow-2xl relative">
            <button
              onClick={() => setShowUploadModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>

            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Upload className="h-5 w-5 text-cyan-400" /> Upload Multi-Modal File
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Supports PDF, DOCX, PNG, JPG. Documents undergo local OCR entity detection and zero-PII embedding vectorization.
            </p>

            <div className="border-2 border-dashed border-slate-700 hover:border-cyan-500 rounded-2xl p-8 text-center transition cursor-pointer bg-slate-950/50 space-y-3">
              <Upload className="h-8 w-8 text-cyan-400 mx-auto animate-bounce" />
              <div className="text-xs text-slate-300">
                Drag &amp; drop file here, or{' '}
                <label className="text-cyan-400 font-bold underline cursor-pointer">
                  browse
                  <input
                    type="file"
                    className="hidden"
                    onChange={handleFileUpload}
                    accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
                  />
                </label>
              </div>
              <div className="text-[10px] text-slate-500 font-mono">Max file size: 50MB</div>
            </div>

            {uploading && (
              <div className="text-center text-xs text-cyan-400 font-mono animate-pulse">
                Processing file &amp; generating redacted vector index...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
