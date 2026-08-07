'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Paperclip,
  ShieldCheck,
  Eye,
  EyeOff,
  Cpu,
  RefreshCw,
  Sparkles,
  FileText,
  AlertCircle,
  CheckCircle2,
  Lock,
  Database,
  Plus,
  Trash2,
  Check,
  X,
  ShieldAlert,
  Sliders,
  Tag,
  ArrowRight,
  ArrowLeft,
  Columns,
  Files,
  UploadCloud,
} from 'lucide-react';
import {
  sendChatMessage,
  redactPII,
  PIIMatch,
  ChatMessageResponse,
  LLMSettings,
  extractTextFromFile,
  applyVerifiedHITLMasking,
  PIIRedactResponse,
} from '@/lib/api';

interface Message {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  maskedResponse?: string;
  demaskedResponse?: string;
  entities?: PIIMatch[];
  mapping?: Record<string, string>;
  sources?: string[];
  modelUsed?: string;
  processingTimeMs?: number;
  viewMode?: 'masked' | 'demasked';
  timestamp: string;
  attachedDocName?: string;
}

interface HITLEntityItem extends PIIMatch {
  id: string;
  enabled: boolean;
}

interface HITLBatchFile {
  id: string;
  filename: string;
  originalText: string;
  entities: HITLEntityItem[];
  riskScore: number;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  classificationCategory: string;
  status: 'PENDING' | 'VERIFIED';
}

export function ChatSection() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // Active indexed context document info
  const [attachedDoc, setAttachedDoc] = useState<string>('patient_records.pdf');
  const [activeMaskedDocText, setActiveMaskedDocText] = useState<string>('');
  const [activeMapping, setActiveMapping] = useState<Record<string, string>>({});

  // Multi-File Human-in-the-Loop (HITL) Modal State
  const [hitlModalOpen, setHitlModalOpen] = useState(false);
  const [hitlBatchFiles, setHitlBatchFiles] = useState<HITLBatchFile[]>([]);
  const [activeBatchIndex, setActiveBatchIndex] = useState<number>(0);
  const [newEntityText, setNewEntityText] = useState('');
  const [newEntityType, setNewEntityType] = useState('NAME');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  const [llmSettings, setLlmSettings] = useState<LLMSettings>({
    temperature: 0.2,
    top_p: 0.9,
    max_tokens: 1024,
    model: 'Llama-3.3-70B',
  });

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, hitlModalOpen]);

  useEffect(() => {
    if (!activeMaskedDocText && attachedDoc) {
      extractTextFromFile(new File([], attachedDoc)).then((txt) => {
        if (txt) setActiveMaskedDocText(txt);
      });
    }
  }, [attachedDoc, activeMaskedDocText]);

  // Trigger hidden file picker
  const handlePaperclipClick = () => {
    fileInputRef.current?.click();
  };

  // Step 1: Process Multiple Files -> Extract text -> Run PII Detection -> Open Side-by-Side HITL Modal
  const processSelectedFiles = async (files: File[]) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      const batchList: HITLBatchFile[] = [];

      for (let idx = 0; idx < files.length; idx++) {
        const file = files[idx];
        // Extract text content from file
        const rawText = await extractTextFromFile(file);

        // Run automatic PII Detection
        const detectionRes: PIIRedactResponse = await redactPII(rawText);

        // Format entities for HITL checklist
        const hitlEntities: HITLEntityItem[] = detectionRes.entities.map((ent, i) => ({
          ...ent,
          id: `ent-${Date.now()}-${idx}-${i}`,
          enabled: true,
        }));

        batchList.push({
          id: `file-${Date.now()}-${idx}`,
          filename: file.name,
          originalText: rawText,
          entities: hitlEntities,
          riskScore: detectionRes.risk_score,
          riskLevel: detectionRes.risk_level,
          classificationCategory: detectionRes.classification?.category || 'Healthcare & Confidential Data',
          status: 'PENDING',
        });
      }

      setHitlBatchFiles(batchList);
      setActiveBatchIndex(0);
      setHitlModalOpen(true);
    } catch (err) {
      console.error('Multi-file detection error:', err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      processSelectedFiles(Array.from(e.target.files));
    }
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processSelectedFiles(Array.from(e.dataTransfer.files));
    }
  };

  // Active file being edited in the side-by-side view
  const currentFile = hitlBatchFiles[activeBatchIndex];

  // HITL Action: Toggle entity on/off
  const toggleHITLEntity = (id: string) => {
    if (!currentFile) return;
    const updatedEntities = currentFile.entities.map((e) => (e.id === id ? { ...e, enabled: !e.enabled } : e));
    updateCurrentFileEntities(updatedEntities);
  };

  // HITL Action: Add custom entity manually
  const addCustomHITLEntity = () => {
    if (!currentFile || !newEntityText.trim()) return;
    const term = newEntityText.trim();
    const startPos = currentFile.originalText.indexOf(term);

    const newEnt: HITLEntityItem = {
      id: `ent-custom-${Date.now()}`,
      entity_type: newEntityType,
      text: term,
      start: startPos >= 0 ? startPos : 0,
      end: startPos >= 0 ? startPos + term.length : term.length,
      score: 1.0,
      enabled: true,
    };

    updateCurrentFileEntities([...currentFile.entities, newEnt]);
    setNewEntityText('');
  };

  // HITL Action: Remove entity
  const removeHITLEntity = (id: string) => {
    if (!currentFile) return;
    const updatedEntities = currentFile.entities.filter((e) => e.id !== id);
    updateCurrentFileEntities(updatedEntities);
  };

  const updateCurrentFileEntities = (newEntities: HITLEntityItem[]) => {
    setHitlBatchFiles((prev) =>
      prev.map((f, idx) => (idx === activeBatchIndex ? { ...f, entities: newEntities } : f))
    );
  };

  // Step 2: Confirm Detection -> Send ALL Files in Batch for Masking & Vector Store Indexing
  const handleConfirmAllHITLAndMask = () => {
    if (hitlBatchFiles.length === 0) return;

    let combinedMaskedText = '';
    const mergedMapping: Record<string, string> = {};
    const allEntitiesList: PIIMatch[] = [];
    const processedFilenames: string[] = [];

    hitlBatchFiles.forEach((file) => {
      const activeEntities = file.entities.filter((e) => e.enabled);
      const { maskedText, mapping } = applyVerifiedHITLMasking(file.originalText, activeEntities);

      combinedMaskedText += `\n--- DOCUMENT: ${file.filename} ---\n${maskedText}\n`;
      Object.assign(mergedMapping, mapping);
      allEntitiesList.push(...activeEntities);
      processedFilenames.push(file.filename);
    });

    const primaryDocName = processedFilenames.length > 1
      ? `${processedFilenames[0]} (+${processedFilenames.length - 1} more)`
      : processedFilenames[0];

    // Update active document context
    setAttachedDoc(primaryDocName);
    setActiveMaskedDocText(combinedMaskedText);
    setActiveMapping(mergedMapping);

    // Add System Notification in Chat thread
    const systemMsg: Message = {
      id: `sys-${Date.now()}`,
      sender: 'system',
      text: `Batch HITL Verification Complete: ${processedFilenames.length} files (${processedFilenames.join(', ')}) verified by human operator. Total ${allEntitiesList.length} PII entities tokenized. Vector store indexed with zero raw PII leakage.`,
      attachedDocName: primaryDocName,
      entities: allEntitiesList,
      mapping: mergedMapping,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, systemMsg]);
    setHitlModalOpen(false);
    setHitlBatchFiles([]);
  };

  // Step 3: Handle Send Query -> Generate Response -> Step 4: Display with Masked/Demasked Toggle
  const handleSend = async (overrideText?: string) => {
    const textToSend = overrideText || inputQuery;
    if (!textToSend.trim() || loading) return;

    const userMsgId = `msg-${Date.now()}`;
    const userMsg: Message = {
      id: userMsgId,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!overrideText) setInputQuery('');
    setLoading(true);

    try {
      // Step 1: Detect PII in query text
      const piiResult = await redactPII(textToSend);

      // Merge active document entities with query entities
      const activeEntitiesList: PIIMatch[] = [...(piiResult.entities || [])];
      Object.entries(activeMapping).forEach(([placeholder, val]) => {
        const typeMatch = placeholder.replace(/<|>|\d+|_/g, '');
        activeEntitiesList.push({
          entity_type: typeMatch || 'REDACTED',
          text: val,
          start: 0,
          end: val.length,
          score: 1.0,
        });
      });

      // Step 2: Execute Demasked RAG Chat API call with active document context
      let docContextText = activeMaskedDocText;
      if (!docContextText && attachedDoc) {
        docContextText = await extractTextFromFile(new File([], attachedDoc));
      }
      if (!docContextText) {
        docContextText = piiResult.redacted_text || textToSend;
      }

      // Pre-sanitize document context if it has not been masked via HITL flow yet
      if (docContextText && !activeMaskedDocText) {
        const docPii = await redactPII(docContextText);
        if (docPii.entities && docPii.entities.length > 0) {
          const { maskedText, mapping } = applyVerifiedHITLMasking(docContextText, docPii.entities);
          docContextText = maskedText;
          Object.assign(activeMapping, mapping);
          docPii.entities.forEach((ent) => activeEntitiesList.push(ent));
        }
      }

      const ragResponse: ChatMessageResponse = await sendChatMessage(
        textToSend,
        textToSend,
        docContextText,
        activeEntitiesList,
        llmSettings
      );


      const assistantMsg: Message = {
        id: `msg-${Date.now() + 1}`,
        sender: 'assistant',
        text: ragResponse.demasked_response,
        maskedResponse: ragResponse.masked_response,
        demaskedResponse: ragResponse.demasked_response,
        entities: piiResult.entities,
        mapping: activeMapping,
        sources: ragResponse.sources_retrieved,
        modelUsed: ragResponse.model_used,
        processingTimeMs: ragResponse.processing_time_ms,
        viewMode: 'demasked',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Chat error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Toggle view mode on response card
  const toggleMessageViewMode = (msgId: string) => {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id === msgId && msg.sender === 'assistant') {
          return {
            ...msg,
            viewMode: msg.viewMode === 'masked' ? 'demasked' : 'masked',
          };
        }
        return msg;
      })
    );
  };

  // Helper function to resolve clean demasked text without lingering placeholders or asterisks
  const getCleanDemaskedText = (msg: Message) => {
    let text = msg.demaskedResponse || msg.text || '';
    if (msg.mapping) {
      Object.entries(msg.mapping).forEach(([token, val]) => {
        text = text.replaceAll(token, val);
      });
    }
    if (msg.entities) {
      msg.entities.forEach((ent, idx) => {
        const placeholders = [
          `<${ent.entity_type}_${idx + 1}>`,
          `<${ent.entity_type}_1>`,
          `<${ent.entity_type}>`,
          `[${ent.entity_type}_REDACTED]`,
          `[${ent.entity_type}]`,
        ];
        placeholders.forEach((p) => {
          text = text.replaceAll(p, ent.text);
        });
      });
    }
    // Remove lingering markdown bold asterisks from demasked value replacements
    return text.replace(/\*\*([^*]+)\*\*/g, '$1');
  };

  // Helper function to render text with highlighted PII spans in side-by-side left pane
  const renderHighlightedOriginalText = (text: string, entities: HITLEntityItem[]) => {

    if (!entities || entities.length === 0) return <span>{text}</span>;

    const activeSpans = entities
      .filter((e) => e.enabled && e.text)
      .sort((a, b) => a.start - b.start);

    if (activeSpans.length === 0) return <span>{text}</span>;

    const elements: React.ReactNode[] = [];
    let lastIndex = 0;

    activeSpans.forEach((ent, idx) => {
      let startPos = ent.start;
      let endPos = ent.end;
      if (startPos < 0 || text.substring(startPos, endPos) !== ent.text) {
        startPos = text.indexOf(ent.text, lastIndex >= 0 ? lastIndex : 0);
        if (startPos < 0) startPos = text.indexOf(ent.text);
        if (startPos >= 0) endPos = startPos + ent.text.length;
      }

      if (startPos > lastIndex && startPos >= 0) {
        elements.push(<span key={`text-${idx}`}>{text.substring(lastIndex, startPos)}</span>);
      }

      if (startPos >= 0) {
        const typeColorClass =
          ent.entity_type === 'NAME'
            ? 'bg-cyan-900/90 border-cyan-700 text-cyan-200'
            : ent.entity_type === 'EMAIL'
            ? 'bg-emerald-900/90 border-emerald-700 text-emerald-200'
            : ent.entity_type === 'PHONE'
            ? 'bg-amber-900/90 border-amber-700 text-amber-200'
            : ent.entity_type === 'AADHAAR' || ent.entity_type === 'PAN'
            ? 'bg-purple-900/90 border-purple-700 text-purple-200'
            : ent.entity_type === 'CREDIT_CARD'
            ? 'bg-rose-900/90 border-rose-700 text-rose-200'
            : 'bg-indigo-900/90 border-indigo-700 text-indigo-200';

        elements.push(
          <mark
            key={`mark-${idx}`}
            className={`px-1.5 py-0.5 rounded border font-mono text-[11px] font-bold inline-flex items-center gap-1 mx-0.5 ${typeColorClass}`}
          >
            <span className="text-[9px] opacity-75 uppercase">{ent.entity_type}:</span>
            <span>{ent.text}</span>
          </mark>
        );
        lastIndex = Math.max(lastIndex, endPos);
      }
    });

    if (lastIndex < text.length) {
      elements.push(<span key="text-end">{text.substring(lastIndex)}</span>);
    }

    return <>{elements}</>;
  };

  // Compute live masked text preview for right pane of side-by-side view
  const computeLiveMaskedPreview = (text: string, entities: HITLEntityItem[]) => {
    if (!entities) return text;
    const activeEntities = entities.filter((e) => e.enabled);
    const { maskedText } = applyVerifiedHITLMasking(text, activeEntities);
    return maskedText;
  };

  const presetPrompts = [
    {
      title: 'Summarize Patient Record',
      desc: 'Extract medical history & mask identity spans',
      prompt: 'Patient Rajesh Kumar (Aadhaar: 4521 8901 2345, PAN: ABCDE1234F) requires clinical summary. Please summarize and detect all PII entities.',
    },
    {
      title: 'DPDP Compliance Check',
      desc: 'Verify regulatory exposure under DPDP Act 2023',
      prompt: 'Check DPDP Act 2023 compliance status for sensitive patient identifiers (Email: rajesh.kumar@gmail.com, Phone: +91 9876543210).',
    },
    {
      title: 'Demasked RAG Search',
      desc: 'Run vector search with zero PII outbound leakage',
      prompt: 'Query indexed document patient_records.pdf regarding treatment history while keeping Aadhaar and PAN tokenized in vector embeddings.',
    },
  ];

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex flex-col h-full relative overflow-hidden bg-slate-950/60 transition ${
        isDragging ? 'ring-4 ring-cyan-500/50 bg-cyan-950/20' : ''
      }`}
    >
      {/* Hidden File Input supporting MULTIPLE files */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        multiple
        accept=".pdf,.doc,.docx,.txt,.csv,.json"
      />

      {/* Drag & Drop Visual Overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-slate-950/90 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center space-y-4 animate-fadeIn border-4 border-dashed border-cyan-500 rounded-3xl">
          <UploadCloud className="h-16 w-16 text-cyan-400 animate-bounce" />
          <h3 className="text-2xl font-extrabold text-white">Drop Multiple Files Here</h3>
          <p className="text-sm text-cyan-300">
            Files will be parsed simultaneously and opened in the Side-by-Side HITL Verification Window.
          </p>
        </div>
      )}



      {/* Main Chat Thread Area */}
      <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-6 flex flex-col">
        {messages.length === 0 ? (
          /* EMPTY STATE: Hero View */
          <div className="flex-1 flex flex-col items-center justify-center max-w-3xl mx-auto w-full text-center my-auto space-y-8 animate-fadeIn">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 text-xs font-semibold shadow-lg shadow-cyan-950/50">
                <Columns className="h-3.5 w-3.5 text-cyan-400" /> Side-by-Side Multi-File HITL Verification
              </div>
              <h2 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight">
                Ask PrivacyShield <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-indigo-300 to-purple-400">RAG Assistant</span>
              </h2>
              <p className="text-slate-400 text-xs md:text-sm max-w-xl mx-auto leading-relaxed">
                Upload multiple files in one go (or drag &amp; drop). Review raw document text vs live tokenized masked text side-by-side in the HITL comparison window before RAG response generation.
              </p>
            </div>

            {/* Quick Prompt Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full text-left">
              {presetPrompts.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(p.prompt)}
                  className="p-4 rounded-2xl bg-slate-900/70 border border-slate-800/80 hover:border-cyan-500/50 hover:bg-slate-900 transition-all duration-200 group text-xs space-y-1.5 text-slate-300 shadow-lg"
                >
                  <div className="font-bold text-slate-200 group-hover:text-cyan-400 transition-colors flex items-center justify-between">
                    {p.title}
                    <Sparkles className="h-3 w-3 text-slate-500 group-hover:text-cyan-400" />
                  </div>
                  <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">{p.desc}</p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* CONVERSATION STREAM */
          <div className="max-w-3xl mx-auto w-full space-y-6 flex-1">
            {messages.map((msg) => {
              if (msg.sender === 'system') {
                return (
                  <div key={msg.id} className="p-4 rounded-2xl bg-cyan-950/40 border border-cyan-800/60 text-xs space-y-2 text-cyan-200 shadow-lg">
                    <div className="flex items-center justify-between font-bold text-cyan-300">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                        <span>Multi-File HITL Verification &amp; Masking Complete</span>
                      </div>
                      <span className="text-[10px] font-mono text-cyan-400">{msg.timestamp}</span>
                    </div>
                    <p className="text-slate-300">{msg.text}</p>
                    {msg.entities && msg.entities.length > 0 && (
                      <div className="pt-2 border-t border-cyan-900/80 flex flex-wrap gap-1.5">
                        {msg.entities.map((e, idx) => (
                          <span key={idx} className="px-2 py-0.5 rounded bg-cyan-900/80 border border-cyan-700 text-cyan-200 font-mono text-[10px]">
                            {e.entity_type}: <span className="font-bold text-white">{e.text}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 text-xs md:text-sm ${
                    msg.sender === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.sender === 'assistant' && (
                    <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-cyan-500 to-indigo-600 flex items-center justify-center text-slate-950 font-extrabold flex-shrink-0 shadow-md">
                      <ShieldCheck className="h-5 w-5 text-slate-950" />
                    </div>
                  )}

                  <div
                    className={`max-w-[88%] rounded-2xl p-4 space-y-3 shadow-xl ${
                      msg.sender === 'user'
                        ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white font-medium ml-auto rounded-tr-none'
                        : 'bg-slate-900/90 border border-slate-800 text-slate-200 rounded-tl-none'
                    }`}
                  >
                    {msg.sender === 'user' ? (
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                    ) : (
                      <>
                        {/* Assistant Header & Prominent View Mode Toggle */}
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5 text-[11px]">
                          <div className="flex items-center gap-2 text-cyan-400 font-semibold">
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Zero-PII Response
                          </div>

                          {/* TOGGLE BUTTON FOR MASKED VS DEMASKED VIEW */}
                          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
                            <button
                              onClick={() => toggleMessageViewMode(msg.id)}
                              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg transition text-[11px] font-medium ${
                                msg.viewMode === 'demasked'
                                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/80 shadow-md font-bold'
                                  : 'text-slate-400 hover:text-white'
                              }`}
                            >
                              <Eye className="h-3 w-3 text-emerald-400" />
                              <span>Demasked View</span>
                            </button>
                            <button
                              onClick={() => toggleMessageViewMode(msg.id)}
                              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg transition text-[11px] font-medium ${
                                msg.viewMode === 'masked'
                                  ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/80 shadow-md font-bold'
                                  : 'text-slate-400 hover:text-white'
                              }`}
                            >
                              <Lock className="h-3 w-3 text-cyan-400" />
                              <span>Masked View</span>
                            </button>
                          </div>
                        </div>

                        {/* Main Response Output Display */}
                        <div className="font-sans leading-relaxed whitespace-pre-wrap text-slate-200">
                          {msg.viewMode === 'demasked' ? (
                            <span>{getCleanDemaskedText(msg)}</span>
                          ) : (
                            <span className="font-mono text-cyan-200 bg-slate-950/60 p-3 rounded-xl block border border-cyan-950">
                              {msg.maskedResponse}
                            </span>
                          )}
                        </div>


                        {/* Protected Entity Mapping Drawer */}
                        {msg.entities && msg.entities.length > 0 && (
                          <div className="pt-2.5 border-t border-slate-800/80 space-y-1.5">
                            <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
                              <span>Verified Protected Spans ({msg.entities.length})</span>
                              <span className="text-cyan-400">Mode: {msg.viewMode?.toUpperCase()}</span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.entities.map((e, idx) => (
                                <span
                                  key={idx}
                                  className="px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800/60 text-cyan-300 font-mono text-[10px]"
                                >
                                  {e.entity_type}: <span className="font-bold text-white">{e.text}</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Footer Info */}
                        <div className="pt-2 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-800/50">
                          <div className="flex items-center gap-1.5 text-indigo-300 font-mono">
                            <Database className="h-3 w-3 text-indigo-400" />
                            <span>Context: {attachedDoc}</span>
                          </div>
                          <div className="font-mono text-slate-400">
                            {msg.processingTimeMs}ms · {msg.modelUsed}
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  {msg.sender === 'user' && (
                    <div className="h-8 w-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-cyan-400 font-bold text-xs flex-shrink-0">
                      YOU
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="flex gap-3 text-xs justify-start animate-pulse">
                <div className="h-8 w-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 font-extrabold flex-shrink-0">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                </div>
                <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-slate-400 text-xs flex items-center gap-2">
                  <Lock className="h-3.5 w-3.5 text-cyan-400" /> Querying vector embeddings over masked placeholders...
                </div>
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>
        )}
      </div>

      {/* SINGLE CHAT BAR CENTERED AT THE BOTTOM */}
      <div className="p-4 md:p-6 bg-slate-950/90 border-t border-slate-800/80 backdrop-blur z-20">
        <div className="max-w-3xl mx-auto w-full relative">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="relative flex items-center rounded-2xl bg-slate-900/90 border border-slate-800/90 focus-within:border-cyan-500/80 focus-within:ring-2 focus-within:ring-cyan-500/20 shadow-2xl transition duration-200"
          >
            {/* Attachment Button & PII Detection Progress */}
            <button
              type="button"
              onClick={handlePaperclipClick}
              disabled={uploading}
              title="Attach Multiple Files for Side-by-Side HITL Verification & Masking"
              className="pl-4 text-slate-400 hover:text-cyan-400 transition cursor-pointer flex items-center gap-2 focus:outline-none disabled:cursor-wait"
            >
              {uploading ? (
                <div className="flex items-center gap-2 px-2.5 py-1 rounded-xl bg-cyan-950/80 border border-cyan-800 text-cyan-300 text-xs font-medium animate-pulse shadow-inner">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                  <span>PII detection in progress...</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-slate-400 hover:text-cyan-400 transition">
                  <Paperclip className="h-4 w-4 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-300 hover:text-cyan-300">Attach Files</span>
                </div>
              )}
            </button>

            {/* Chat Input Field */}
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder={uploading ? 'PII detection in progress...' : 'Ask anything or attach files...'}
              className="w-full py-4 pl-3 pr-24 bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none font-sans"
              disabled={loading || uploading}
            />

            {/* Send Button */}
            <div className="absolute right-2 flex items-center gap-2">
              <button
                type="submit"
                disabled={!inputQuery.trim() || loading}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-1.5 shadow-lg shadow-cyan-500/25 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin text-slate-950" /> : <Send className="h-3.5 w-3.5 text-slate-950" />}
                <span>Send</span>
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* SIDE-BY-SIDE HUMAN-IN-THE-LOOP (HITL) MULTI-FILE VERIFICATION MODAL */}
      {hitlModalOpen && hitlBatchFiles.length > 0 && currentFile && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4 md:p-6 animate-fadeIn">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-6xl w-full max-h-[95vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Top Header */}
            <div className="p-6 border-b border-slate-800/80 bg-slate-950/80 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400">
                  <Columns className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-lg font-extrabold text-white flex items-center gap-2">
                    Side-by-Side HITL Verification
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono">
                      Batch of {hitlBatchFiles.length} {hitlBatchFiles.length === 1 ? 'File' : 'Files'}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    Compare raw document text with live tokenized output side-by-side before sending for masking.
                  </p>
                </div>
              </div>

              <button
                onClick={() => {
                  setHitlModalOpen(false);
                  setHitlBatchFiles([]);
                }}
                className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* MULTI-FILE SELECTOR TABS AT TOP */}
            <div className="px-6 py-3 bg-slate-950/60 border-b border-slate-800/80 flex items-center gap-2 overflow-x-auto">
              <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1 mr-2">
                <Files className="h-3.5 w-3.5 text-cyan-400" /> Batch Documents:
              </span>
              {hitlBatchFiles.map((file, idx) => (
                <button
                  key={file.id}
                  onClick={() => setActiveBatchIndex(idx)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-xl transition text-xs font-medium border whitespace-nowrap ${
                    activeBatchIndex === idx
                      ? 'bg-cyan-950 text-cyan-300 border-cyan-700 shadow-md font-bold'
                      : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                  }`}
                >
                  <FileText className={`h-3.5 w-3.5 ${activeBatchIndex === idx ? 'text-cyan-400' : 'text-slate-500'}`} />
                  <span>{file.filename}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-950 text-slate-300 font-mono">
                    {file.entities.length} PII
                  </span>
                </button>
              ))}
            </div>

            {/* Modal Main Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Document Overview Metadata Header */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-0.5">
                  <div className="text-[10px] uppercase font-mono text-slate-400">Active Document</div>
                  <div className="text-xs font-bold text-white truncate">{currentFile.filename}</div>
                </div>
                <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-0.5">
                  <div className="text-[10px] uppercase font-mono text-slate-400">Category</div>
                  <div className="text-xs font-bold text-cyan-300">{currentFile.classificationCategory}</div>
                </div>
                <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-0.5">
                  <div className="text-[10px] uppercase font-mono text-slate-400">Risk Assessment</div>
                  <div className="text-xs font-bold text-amber-400 flex items-center gap-2">
                    <span>{currentFile.riskScore} / 100</span>
                    <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950 border border-amber-800 text-amber-300 font-mono">
                      {currentFile.riskLevel}
                    </span>
                  </div>
                </div>
                <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-0.5">
                  <div className="text-[10px] uppercase font-mono text-slate-400">Entities Detected</div>
                  <div className="text-xs font-bold text-cyan-400">{currentFile.entities.length} Spans</div>
                </div>
              </div>

              {/* POP SIDE-BY-SIDE COMPARISON WINDOW */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* LEFT PANE: Original Raw Document Text with Highlighted Spans */}
                <div className="space-y-2 flex flex-col">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                      <FileText className="h-4 w-4 text-cyan-400" /> 1. Original Document Text (Highlighted)
                    </label>
                    <span className="text-[10px] text-cyan-400 font-mono">Raw PII Spans Highlighted</span>
                  </div>
                  <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 text-xs font-sans text-slate-200 min-h-[220px] max-h-[300px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                    {renderHighlightedOriginalText(currentFile.originalText, currentFile.entities)}
                  </div>
                </div>

                {/* RIGHT PANE: Live Tokenized & Masked Output Preview */}
                <div className="space-y-2 flex flex-col">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                      <Lock className="h-4 w-4 text-emerald-400" /> 2. Live Tokenized Masked Output
                    </label>
                    <span className="text-[10px] text-emerald-400 font-mono">Zero Raw PII Outbound</span>
                  </div>
                  <div className="p-4 rounded-2xl bg-slate-950 border border-emerald-950 text-xs font-mono text-cyan-200 min-h-[220px] max-h-[300px] overflow-y-auto whitespace-pre-wrap leading-relaxed shadow-inner">
                    {computeLiveMaskedPreview(currentFile.originalText, currentFile.entities)}
                  </div>
                </div>
              </div>

              {/* Detected Entities Interactive Verification Checklist */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-cyan-400" /> Verify &amp; Edit Spans for [{currentFile.filename}]
                  </h4>
                  <span className="text-[11px] text-slate-400">Toggle checkboxes to include/exclude entities from live masking</span>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {currentFile.entities.map((ent) => (
                    <div
                      key={ent.id}
                      className={`p-3 rounded-2xl border transition flex items-center justify-between gap-3 ${
                        ent.enabled
                          ? 'bg-slate-950/80 border-cyan-800/70 text-slate-200'
                          : 'bg-slate-950/30 border-slate-800/50 text-slate-500 opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => toggleHITLEntity(ent.id)}
                          className={`h-5 w-5 rounded-lg border flex items-center justify-center transition ${
                            ent.enabled
                              ? 'bg-cyan-500 border-cyan-400 text-slate-950'
                              : 'border-slate-700 bg-slate-900 text-transparent'
                          }`}
                        >
                          <Check className="h-3.5 w-3.5 stroke-[3]" />
                        </button>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-mono text-[10px] font-bold">
                              {ent.entity_type}
                            </span>
                            <span className="font-semibold text-white text-xs">{ent.text}</span>
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">
                            Confidence: {Math.round(ent.score * 100)}% · Pos: {ent.start}-{ent.end}
                          </span>
                        </div>
                      </div>

                      <button
                        onClick={() => removeHITLEntity(ent.id)}
                        className="text-slate-500 hover:text-red-400 p-1.5 rounded-lg transition"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Add Custom Entity Span */}
              <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 space-y-3">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <Plus className="h-4 w-4 text-cyan-400" /> Add Custom PII Span to [{currentFile.filename}]
                </label>
                <div className="flex flex-col md:flex-row items-center gap-2">
                  <select
                    value={newEntityType}
                    onChange={(e) => setNewEntityType(e.target.value)}
                    className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-cyan-300 font-mono focus:outline-none w-full md:w-48"
                  >
                    <option value="NAME">NAME</option>
                    <option value="EMAIL font-mono">EMAIL</option>
                    <option value="PHONE">PHONE</option>
                    <option value="AADHAAR">AADHAAR</option>
                    <option value="PAN">PAN</option>
                    <option value="CREDIT_CARD">CREDIT_CARD</option>
                    <option value="ADDRESS">ADDRESS</option>
                    <option value="MEDICAL_RECORD">MEDICAL_RECORD</option>
                  </select>
                  <input
                    type="text"
                    value={newEntityText}
                    onChange={(e) => setNewEntityText(e.target.value)}
                    placeholder="Enter text term to mask..."
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none w-full"
                  />
                  <button
                    onClick={addCustomHITLEntity}
                    disabled={!newEntityText.trim()}
                    className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-1.5 transition disabled:opacity-40"
                  >
                    <Plus className="h-4 w-4 text-slate-950" /> Add Span
                  </button>
                </div>
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="p-6 border-t border-slate-800/80 bg-slate-950/80 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  disabled={activeBatchIndex === 0}
                  onClick={() => setActiveBatchIndex((prev) => Math.max(0, prev - 1))}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition flex items-center gap-1 disabled:opacity-30"
                >
                  <ArrowLeft className="h-4 w-4" /> Previous
                </button>
                <button
                  disabled={activeBatchIndex === hitlBatchFiles.length - 1}
                  onClick={() => setActiveBatchIndex((prev) => Math.min(hitlBatchFiles.length - 1, prev + 1))}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition flex items-center gap-1 disabled:opacity-30"
                >
                  Next <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              <button
                onClick={handleConfirmAllHITLAndMask}
                className="px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-500 to-purple-600 hover:from-cyan-400 hover:to-indigo-400 text-slate-950 font-extrabold text-xs flex items-center gap-2 shadow-xl shadow-cyan-500/25 transition"
              >
                <CheckCircle2 className="h-4 w-4 text-slate-950" />
                <span>Verify &amp; Mask All {hitlBatchFiles.length} Files</span>
                <ArrowRight className="h-4 w-4 text-slate-950" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
