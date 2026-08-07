'use client';

import React, { useState } from 'react';
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
} from 'lucide-react';
import { uploadDocument, DocumentItem } from '@/lib/api';

interface DocumentsSectionProps {
  onSelectDocForChat?: (docName: string) => void;
}

export function DocumentsSection({ onSelectDocForChat }: DocumentsSectionProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([
    {
      id: 'doc-1',
      filename: 'patient_records.pdf',
      size: '2.4 MB',
      category: 'Healthcare & PHI',
      sensitivity: 'RESTRICTED',
      risk_score: 85,
      char_count: 14500,
      status: 'INDEXED',
      created_at: '2026-08-05 14:30',
    },
    {
      id: 'doc-2',
      filename: 'financial_audit_2026.docx',
      size: '1.1 MB',
      category: 'Financial & Tax',
      sensitivity: 'HIGH',
      risk_score: 65,
      char_count: 8900,
      status: 'INDEXED',
      created_at: '2026-08-04 09:15',
    },
    {
      id: 'doc-3',
      filename: 'employee_roster_pan.xlsx',
      size: '850 KB',
      category: 'HR Operations',
      sensitivity: 'MEDIUM',
      risk_score: 40,
      char_count: 5200,
      status: 'INDEXED',
      created_at: '2026-08-02 11:45',
    },
  ]);

  const [searchTerm, setSearchTerm] = useState('');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const res = await uploadDocument(file);
      const newDoc: DocumentItem = {
        id: `doc-${Date.now()}`,
        filename: file.name,
        size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
        category: 'Multi-Modal Upload',
        sensitivity: 'HIGH',
        risk_score: 50,
        char_count: 3500,
        status: 'INDEXED',
        created_at: new Date().toISOString().replace('T', ' ').substring(0, 16),
      };
      setDocuments((prev) => [newDoc, ...prev]);
      setShowUploadModal(false);
    } catch (err) {
      console.error('Upload failed:', err);
    } finally {
      setUploading(false);
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
                      onClick={() => onSelectDocForChat(doc.filename)}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-cyan-400 font-sans rounded-lg transition text-[11px] inline-flex items-center gap-1"
                    >
                      <MessageSquareText className="h-3 w-3" /> RAG Chat
                    </button>
                  )}
                  <button
                    onClick={() => setDocuments(documents.filter((d) => d.id !== doc.id))}
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

      {/* Multi-Modal Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
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
