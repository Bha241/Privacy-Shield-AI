'use client';

import React, { useState } from 'react';
import { Sidebar, NavTab } from '@/components/Sidebar';
import { ChatSection } from '@/components/ChatSection';
import { LiveRedactionSection } from '@/components/LiveRedactionSection';
import { DocumentsSection } from '@/components/DocumentsSection';
import { AuditLogsSection } from '@/components/AuditLogsSection';
import { SettingsSection } from '@/components/SettingsSection';

export default function Home() {
  // STARTING PAGE OF UI IS CHAT SECTION AS REQUESTED
  const [activeTab, setActiveTab] = useState<NavTab>('chat');
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [gridEnabled, setGridEnabled] = useState(true);

  const handleSelectDocForChat = (documentId: string) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('privacyshield:selected-document-id', documentId);
      window.dispatchEvent(new CustomEvent('privacyshield:document-selection', { detail: documentId }));
    }
    setActiveTab('chat');
  };

  return (
    <div
      className={`app-shell flex h-screen w-screen overflow-hidden bg-[#030712] text-slate-100 antialiased relative ${theme === 'light' ? 'theme-light' : ''}`}
      style={{ '--sidebar-width': collapsed ? '76px' : '248px' } as React.CSSProperties}
    >
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        theme={theme}
        setTheme={setTheme}
      />

      <main className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
        <div className={`flex-1 min-h-0 overflow-hidden ${gridEnabled && ['chat', 'redact', 'documents', 'audit'].includes(activeTab) ? 'workspace-grid' : ''}`}>
          <div className={activeTab === 'chat' ? 'h-full' : 'hidden'} aria-hidden={activeTab !== 'chat'}>
            <ChatSection />
          </div>
          {activeTab === 'redact' && <LiveRedactionSection />}
          {activeTab === 'documents' && <DocumentsSection onSelectDocForChat={handleSelectDocForChat} />}
          {activeTab === 'audit' && (
            <div className="h-full min-h-0 overflow-y-auto">
              <AuditLogsSection />
            </div>
          )}
          {activeTab === 'settings' && <SettingsSection gridEnabled={gridEnabled} setGridEnabled={setGridEnabled} />}
        </div>
      </main>
    </div>
  );
}
