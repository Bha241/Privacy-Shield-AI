'use client';

import React, { useState } from 'react';
import {
  MessageSquareText,
  ShieldAlert,
  Folder,
  ClipboardList,
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Settings as SettingsIcon,
  Trash2,
} from 'lucide-react';

export type NavTab = 'chat' | 'redact' | 'documents' | 'audit' | 'settings';

interface SidebarProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  theme: 'dark' | 'light';
  setTheme: (theme: 'dark' | 'light') => void;
}

export function Sidebar({ activeTab, setActiveTab, collapsed, setCollapsed, theme, setTheme }: SidebarProps) {
  const [logoHovered, setLogoHovered] = useState(false);
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
  ];

  return (
    <aside
      className={`sidebar-shell relative flex flex-col h-screen bg-[#111310]/95 backdrop-blur-2xl border-r border-white/10 transition-all duration-300 z-40 select-none ${
        collapsed ? 'sidebar-collapsed w-[76px]' : 'w-[248px]'
      }`}
    >
      {/* Top Header / Branding */}
      <div
        className="sidebar-brand p-4 flex items-center justify-between border-b border-slate-800/60 min-h-[72px]"
        >
          <div
            className="sidebar-brand-content flex items-center gap-3 overflow-hidden"
          onMouseEnter={() => setLogoHovered(true)}
          onMouseLeave={() => setLogoHovered(false)}
            onFocus={() => setLogoHovered(true)}
            onBlur={() => setLogoHovered(false)}
          >
          <div className="sidebar-logo-slot h-12 w-12">
            <div className={`sidebar-mark relative flex-shrink-0 h-12 w-12 overflow-hidden flex items-center justify-center ${collapsed && logoHovered ? 'sidebar-mark-hidden' : ''}`}>
              <img src="/privacyshield-logo.png" alt="PrivacyShieldAI logo" className="absolute left-1/2 top-1/2 h-[220%] w-[220%] max-w-none -translate-x-1/2 -translate-y-1/2 object-contain" />
            </div>
            {collapsed && (
              <button
                onClick={() => setCollapsed(false)}
                className={`sidebar-toggle p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition ${logoHovered ? 'sidebar-toggle-revealed' : 'sidebar-toggle-hidden'}`}
                title="Expand sidebar"
                aria-label="Expand sidebar"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-bold text-base tracking-tight text-white flex items-center gap-1.5">
                PrivacyShield
              </span>
              <span className="text-[10px] text-slate-400 tracking-wide">
                privacy operations
              </span>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="sidebar-toggle p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Collapse sidebar"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>



      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto py-5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 group ${
                isActive
                ? 'bg-[#aab5ff]/10 text-[#aab5ff] border border-[#aab5ff]/30 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/80 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3 truncate">
                <Icon
                  className={`h-4 w-4 transition-colors ${
                    isActive ? 'text-[#aab5ff] scale-110' : 'text-slate-400 group-hover:text-slate-200'
                  }`}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </div>
              {!collapsed && item.badge && (
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                    isActive
                      ? 'bg-[#aab5ff] text-[#171a2b]'
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
      <div className="p-3 border-t border-slate-800/80 bg-[#0d0f0d]">
        <button
          onClick={() => setActiveTab('settings')}
          className="sidebar-footer-action w-full flex items-center gap-2 p-2 mb-2 rounded-xl border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition text-xs"
          title="Data retention and deletion"
          aria-label="Data retention and deletion"
        >
          <Trash2 className="h-4 w-4 text-amber-300" />
          {!collapsed && <span>Delete data</span>}
        </button>
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="theme-toggle sidebar-footer-action w-full flex items-center gap-2 p-2 mb-2 rounded-xl border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition text-xs"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4 text-amber-300" /> : <Moon className="h-4 w-4 text-indigo-300" />}
          {!collapsed && <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>}
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className="sidebar-footer-action w-full flex items-center gap-2 p-2 rounded-xl border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition text-xs"
          title="Settings"
          aria-label="Settings"
        >
          <SettingsIcon className="h-4 w-4" />
          {!collapsed && <span>Settings</span>}
        </button>
      </div>
    </aside>
  );
}
