'use client';

import React from 'react';
import {
  MessageSquareText,
  ShieldAlert,
  LayoutDashboard,
  Folder,
  ClipboardList,
  Sliders,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Database,
  Sparkles,
} from 'lucide-react';

export type NavTab = 'chat' | 'redact' | 'dashboard' | 'documents' | 'audit' | 'settings';

interface SidebarProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

export function Sidebar({ activeTab, setActiveTab, collapsed, setCollapsed }: SidebarProps) {
  const navItems = [
    {
      id: 'chat' as NavTab,
      label: 'Chat / Ask',
      icon: MessageSquareText,
      badge: 'Demasked RAG',
      highlight: true,
    },
    {
      id: 'redact' as NavTab,
      label: 'Live Redaction',
      icon: ShieldAlert,
      badge: 'PII Engine',
    },
    {
      id: 'dashboard' as NavTab,
      label: 'Dashboard',
      icon: LayoutDashboard,
    },
    {
      id: 'documents' as NavTab,
      label: 'Documents',
      icon: Folder,
      badge: 'Vector Index',
    },
    {
      id: 'audit' as NavTab,
      label: 'Audit Logs',
      icon: ClipboardList,
    },
    {
      id: 'settings' as NavTab,
      label: 'Settings',
      icon: Sliders,
    },
  ];

  return (
    <aside
      className={`relative flex flex-col h-screen bg-[#030712]/90 backdrop-blur-2xl border-r border-white/10 transition-all duration-300 z-40 select-none shadow-[5px_0_30px_rgba(0,0,0,0.8)] ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Top Header / Branding */}
      <div className="p-4 flex items-center justify-between border-b border-slate-800/60">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="relative flex-shrink-0 h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-500 via-indigo-600 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20 font-extrabold text-lg">
            <ShieldCheck className="h-6 w-6 text-white" />
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500"></span>
            </span>
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-bold text-base tracking-tight text-white flex items-center gap-1.5">
                PrivacyShield<span className="text-cyan-400">AI</span>
              </span>
              <span className="text-[10px] text-slate-400 font-mono tracking-wide">
                v5.0 Enterprise
              </span>
            </div>
          )}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>



      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto py-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 group ${
                isActive
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/80 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3 truncate">
                <Icon
                  className={`h-4 w-4 transition-colors ${
                    isActive ? 'text-cyan-400 scale-110' : 'text-slate-400 group-hover:text-slate-200'
                  }`}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </div>
              {!collapsed && item.badge && (
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                    isActive
                      ? 'bg-cyan-400 text-slate-950'
                      : 'bg-slate-800 text-slate-400 group-hover:text-slate-300'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer Profile */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950">
        <div className="flex items-center gap-3 p-2 rounded-xl bg-slate-900/60 border border-slate-800/50">
          <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white font-bold text-xs shadow-md">
            PN
          </div>
          {!collapsed && (
            <div className="flex-1 truncate">
              <div className="text-xs font-semibold text-slate-200 truncate">Priya Nair</div>
              <div className="text-[10px] text-slate-400 truncate">Data Steward</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
