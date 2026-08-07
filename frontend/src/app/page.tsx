'use client';

import React, { useState } from 'react';
import { Sidebar, NavTab } from '@/components/Sidebar';
import { ChatSection } from '@/components/ChatSection';
import { LiveRedactionSection } from '@/components/LiveRedactionSection';
import { DashboardSection } from '@/components/DashboardSection';
import { DocumentsSection } from '@/components/DocumentsSection';
import { AuditLogsSection } from '@/components/AuditLogsSection';
import { SettingsSection } from '@/components/SettingsSection';

export default function Home() {
  // STARTING PAGE OF UI IS CHAT SECTION AS REQUESTED
  const [activeTab, setActiveTab] = useState<NavTab>('chat');
  const [collapsed, setCollapsed] = useState<boolean>(false);

  const handleSelectDocForChat = (docName: string) => {
    setActiveTab('chat');
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#030712] text-slate-100 font-sans antialiased relative">
      {/* Glossy Ambient Glow Background Effects */}
      <div className="fixed top-[-10%] left-[20%] w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[140px] pointer-events-none z-0"></div>
      <div className="fixed bottom-[-10%] right-[10%] w-[600px] h-[600px] bg-indigo-600/10 rounded-full blur-[160px] pointer-events-none z-0"></div>

      {/* Left Sidebar containing all features */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
      />

      {/* Main View Area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden bg-gradient-to-b from-[#030712] via-[#090d16] to-[#030712] relative z-10">
        {activeTab === 'chat' && <ChatSection />}
        {activeTab === 'redact' && <LiveRedactionSection />}
        {activeTab === 'dashboard' && <DashboardSection />}
        {activeTab === 'documents' && (
          <DocumentsSection onSelectDocForChat={handleSelectDocForChat} />
        )}
        {activeTab === 'audit' && <AuditLogsSection />}
        {activeTab === 'settings' && <SettingsSection />}
      </main>
    </div>
  );
}
