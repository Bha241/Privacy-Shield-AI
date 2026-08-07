// PrivacyShieldAI — Obsidian Precision Enterprise Logic

let currentFileName = "";
let currentRawText = "";
let candidateEntities = [];
let maskedResultData = null;
let currentMapping = {};
let isGlobalDemaskActive = false;
let isMaskPromptActive = true;
let isViewingMaskedText = true;
let sessionFileList = [];
let conversationHistory = [];

try {
    const savedHistory = sessionStorage.getItem('privacyshield_chat_history');
    if (savedHistory) {
        conversationHistory = JSON.parse(savedHistory);
    }
} catch (e) {}

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('privacyshield_theme') || 'dark';
    applyTheme(savedTheme);
});

// --- QUICK PROMPTS ---
function quickPrompt(text) {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.value = text;
        sendChatQuery();
    }
}

// --- THEME SWITCHER ---
function toggleTheme() {
    const isDark = document.documentElement.classList.contains('dark');
    if (isDark) {
        document.documentElement.classList.remove('dark');
        applyTheme('light');
    } else {
        document.documentElement.classList.add('dark');
        applyTheme('dark');
    }
}

function applyTheme(theme) {
    const icon = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');

    if (theme === 'light') {
        document.documentElement.classList.remove('dark');
        if (icon) icon.innerText = '🌙';
        if (label) label.innerText = 'Light';
        localStorage.setItem('privacyshield_theme', 'light');
    } else {
        document.documentElement.classList.add('dark');
        if (icon) icon.innerText = '☀️';
        if (label) label.innerText = 'Dark';
        localStorage.setItem('privacyshield_theme', 'dark');
    }
}

// --- PANEL TOGGLES ---
function toggleHitlPanel() {
    const hitlPanel = document.getElementById('hitl-panel');
    const demaskPanel = document.getElementById('demask-panel');
    if (demaskPanel) demaskPanel.style.display = 'none';

    if (hitlPanel) {
        if (hitlPanel.style.display === 'none') {
            if (!currentFileName) {
                alert("Please upload a document first.");
                return;
            }
            hitlPanel.style.display = 'block';
            hitlPanel.scrollIntoView({ behavior: 'smooth' });
        } else {
            hitlPanel.style.display = 'none';
        }
    }
}

function toggleDemaskDocView() {
    const demaskPanel = document.getElementById('demask-panel');
    const hitlPanel = document.getElementById('hitl-panel');
    if (hitlPanel) hitlPanel.style.display = 'none';

    if (demaskPanel) {
        if (demaskPanel.style.display === 'none') {
            if (!maskedResultData && !currentRawText) {
                alert("Please upload a document first.");
                return;
            }
            demaskPanel.style.display = 'block';
            demaskPanel.scrollIntoView({ behavior: 'smooth' });
            updateDocViewerContent();
        } else {
            demaskPanel.style.display = 'none';
        }
    }
}

function toggleViewText() {
    isViewingMaskedText = !isViewingMaskedText;
    updateDocViewerContent();
}

function updateDocViewerContent() {
    const viewer = document.getElementById('doc-viewer-text');
    if (!viewer) return;

    if (maskedResultData && isViewingMaskedText) {
        viewer.innerText = `[ENCRYPTED MASKED TOKEN OUTPUT]\n\n${maskedResultData.masked_text}`;
    } else {
        viewer.innerText = `[UNMASKED ORIGINAL TEXT]\n\n${currentRawText}`;
    }
}

// --- FILE SELECTION & PII DETECTION ---
async function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    if (!files || files.length === 0) return;

    if (files.length === 1) {
        uploadAndDetectFile(files[0]);
    } else {
        uploadAndDetectMultipleFiles(files);
    }
}

async function uploadAndDetectFile(file) {
    const bannerText = document.getElementById('file-status-text');
    const domainSelect = document.getElementById('domain-select');
    const selectedDomain = domainSelect ? domainSelect.value : 'general';

    if (bannerText) bannerText.innerHTML = `Scanning <strong>${escapeHtml(file.name)}</strong> (${selectedDomain.toUpperCase()})...`;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('domain', selectedDomain);

    try {
        const response = await fetch('/api/detect', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            alert(`Detection Error: ${data.detail || 'Failed to analyze document'}`);
            if (bannerText) bannerText.innerHTML = `No document uploaded yet. Click <strong>"Analyze Document"</strong>.`;
            return;
        }

        currentFileName = data.file_name;
        currentRawText = data.raw_text;
        candidateEntities = data.candidate_entities;

        addFilesToSessionList([file]);

        if (bannerText) bannerText.innerHTML = `Active: <strong>${escapeHtml(currentFileName)}</strong> (${data.total_detected} PII detected)`;

        renderUploadedFilesList(sessionFileList, selectedDomain, candidateEntities);
        renderHitlTable(candidateEntities);
        
        const hitlPanel = document.getElementById('hitl-panel');
        if (hitlPanel) {
            hitlPanel.style.display = 'block';
            hitlPanel.scrollIntoView({ behavior: 'smooth' });
        }

    } catch (err) {
        alert(`Network Error: ${err.message}`);
    }
}

async function uploadAndDetectMultipleFiles(files) {
    const bannerText = document.getElementById('file-status-text');
    const domainSelect = document.getElementById('domain-select');
    const selectedDomain = domainSelect ? domainSelect.value : 'general';

    if (bannerText) bannerText.innerHTML = `Scanning <strong>${files.length} documents</strong> (${selectedDomain.toUpperCase()})...`;

    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('domain', selectedDomain);

    try {
        const response = await fetch('/api/detect_batch', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            alert(`Detection Error: ${data.detail || 'Failed to analyze documents'}`);
            if (bannerText) bannerText.innerHTML = `No document uploaded yet. Click <strong>"Analyze Document"</strong>.`;
            return;
        }

        currentFileName = data.file_name;
        currentRawText = data.raw_text;
        candidateEntities = data.candidate_entities;

        addFilesToSessionList(files);

        if (bannerText) bannerText.innerHTML = `Workspace: <strong>${sessionFileList.length} file(s)</strong> (${data.total_detected} total PII detected)`;

        renderUploadedFilesList(sessionFileList, selectedDomain, candidateEntities);
        renderHitlTable(candidateEntities);
        
        const hitlPanel = document.getElementById('hitl-panel');
        if (hitlPanel) {
            hitlPanel.style.display = 'block';
            hitlPanel.scrollIntoView({ behavior: 'smooth' });
        }

    } catch (err) {
        alert(`Network Error: ${err.message}`);
    }
}

function addFilesToSessionList(newFiles) {
    newFiles.forEach(f => {
        const fname = typeof f === 'string' ? f : f.name;
        if (!sessionFileList.includes(fname)) {
            sessionFileList.push(fname);
        }
    });
}

async function clearUploadedFiles() {
    try {
        await fetch('/api/clear_session', { method: 'POST' });
    } catch (e) {}

    currentFileName = "";
    currentRawText = "";
    candidateEntities = [];
    maskedResultData = null;
    currentMapping = {};
    sessionFileList = [];
    conversationHistory = [];
    try {
        sessionStorage.removeItem('privacyshield_chat_history');
    } catch (e) {}

    const chipGrid = document.getElementById('files-chip-grid');
    if (chipGrid) chipGrid.innerHTML = '';

    const hitlPanel = document.getElementById('hitl-panel');
    if (hitlPanel) hitlPanel.style.display = 'none';

    const demaskPanel = document.getElementById('demask-panel');
    if (demaskPanel) demaskPanel.style.display = 'none';

    const bannerText = document.getElementById('file-status-text');
    if (bannerText) bannerText.innerHTML = `No document uploaded yet. Click <strong>"Analyze Document"</strong>.`;
}

function renderUploadedFilesList(filesArray, domain, candidateEntitiesList) {
    const domainBadge = document.getElementById('uploaded-domain-badge');
    const chipGrid = document.getElementById('files-chip-grid');

    if (!chipGrid) return;
    if (domainBadge) domainBadge.innerText = (domain || 'general').toUpperCase();

    const countByFile = {};
    (candidateEntitiesList || []).forEach(e => {
        const fname = e.file_name || 'Document';
        countByFile[fname] = (countByFile[fname] || 0) + 1;
    });

    chipGrid.innerHTML = filesArray.map(f => {
        const fileName = typeof f === 'string' ? f : (f.name || 'Document');
        const piiCount = countByFile[fileName] || 0;
        return `
            <div class="flex items-center justify-between p-sm glass-panel rounded-lg group cursor-pointer hover:border-white/20 transition-all">
                <div class="flex items-center gap-sm overflow-hidden">
                    <span class="material-symbols-outlined text-[16px] text-on-surface-variant">description</span>
                    <span class="text-[12px] font-body-sm truncate text-on-surface" title="${escapeHtml(fileName)}">${escapeHtml(fileName)}</span>
                </div>
                <span class="text-[10px] font-code bg-primary/20 text-primary px-xs rounded font-bold">${piiCount} PII</span>
            </div>
        `;
    }).join('');
}

// --- HITL REDACTION STUDIO ---
function renderHitlTable(entities) {
    const tbody = document.getElementById('hitl-table-body');
    if (!tbody) return;

    if (!entities || entities.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-on-surface-variant py-md">No PII candidates detected. Click "+ Add Custom PII" or "Go Without Masking".</td></tr>`;
        return;
    }

    tbody.innerHTML = entities.map((ent, idx) => `
        <tr>
            <td>
                <label class="switch">
                    <input type="checkbox" ${ent.approved ? 'checked' : ''} onchange="updateEntityApproval(${idx}, this.checked)">
                    <span class="slider"></span>
                </label>
            </td>
            <td>
                <input type="text" value="${escapeHtml(ent.text)}" class="bg-surface-container-highest border border-white/10 text-on-surface text-xs font-code rounded px-xs py-0.5 w-full focus:ring-primary focus:border-primary" onchange="updateEntityText(${idx}, this.value)">
            </td>
            <td>
                <select class="bg-surface-container-highest border border-white/10 text-on-surface text-xs font-code rounded px-xs py-0.5" onchange="updateEntityLabel(${idx}, this.value)">
                    <option value="NAME" ${ent.label === 'NAME' ? 'selected' : ''}>NAME</option>
                    <option value="PHONE" ${ent.label === 'PHONE' ? 'selected' : ''}>PHONE</option>
                    <option value="EMAIL" ${ent.label === 'EMAIL' ? 'selected' : ''}>EMAIL</option>
                    <option value="PAN" ${ent.label === 'PAN' ? 'selected' : ''}>PAN</option>
                    <option value="AADHAAR" ${ent.label === 'AADHAAR' ? 'selected' : ''}>AADHAAR</option>
                    <option value="ADDRESS" ${ent.label === 'ADDRESS' ? 'selected' : ''}>ADDRESS</option>
                    <option value="MONEY" ${ent.label === 'MONEY' ? 'selected' : ''}>MONEY</option>
                    <option value="DATE" ${ent.label === 'DATE' ? 'selected' : ''}>DATE</option>
                    <option value="CUSTOM" ${!['NAME','PHONE','EMAIL','PAN','AADHAAR','ADDRESS','MONEY','DATE'].includes(ent.label) ? 'selected' : ''}>CUSTOM</option>
                </select>
            </td>
            <td><span class="badge badge-cyan">${Math.round((ent.confidence || 1.0) * 100)}%</span></td>
            <td><span class="badge badge-amber" title="${escapeHtml(ent.file_name || 'Document')}">${escapeHtml(ent.file_name ? ent.file_name : (ent.source || 'regex_spacy'))}</span></td>
        </tr>
    `).join('');
}

function updateEntityApproval(index, checked) {
    if (candidateEntities[index]) candidateEntities[index].approved = checked;
}

function updateEntityText(index, val) {
    if (candidateEntities[index]) candidateEntities[index].text = val;
}

function updateEntityLabel(index, val) {
    if (candidateEntities[index]) candidateEntities[index].label = val;
}

function addCustomEntityRow() {
    candidateEntities.push({
        id: candidateEntities.length + 1,
        text: "Custom PII",
        label: "CUSTOM",
        start: 0,
        end: 0,
        confidence: 1.0,
        source: "human_added",
        approved: true
    });
    renderHitlTable(candidateEntities);
}

async function submitHitlVerification() {
    const bannerText = document.getElementById('file-status-text');
    if (bannerText) bannerText.innerHTML = `Applying Redaction Tokens & DPDP Verification...`;

    try {
        const response = await fetch('/api/verify_and_mask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: currentFileName,
                raw_text: currentRawText,
                entities: candidateEntities
            })
        });

        const data = await response.json();

        if (!response.ok) {
            alert(`Masking Error: ${data.detail || 'Failed to process redaction.'}`);
            return;
        }

        maskedResultData = data;
        currentMapping = data.mapping || {};

        const hitlPanel = document.getElementById('hitl-panel');
        if (hitlPanel) hitlPanel.style.display = 'none';

        if (bannerText) bannerText.innerHTML = `Masked: <strong>${escapeHtml(currentFileName)}</strong> (${Object.keys(currentMapping).length} PII tokens redacted)`;

    } catch (err) {
        alert(`Network Error: ${err.message}`);
    }
}

async function proceedWithoutMasking() {
    if (!confirm("⚠️ Are you sure you want to proceed WITHOUT masking sensitive PII? Raw document text will be ingested directly.")) return;

    const bannerText = document.getElementById('file-status-text');
    if (bannerText) bannerText.innerHTML = `Ingesting Raw Document Without Masking...`;

    try {
        const response = await fetch('/api/bypass_masking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: currentFileName,
                raw_text: currentRawText
            })
        });

        const data = await response.json();

        if (!response.ok) {
            alert(`Error: ${data.detail || 'Failed to process unmasked ingestion.'}`);
            return;
        }

        maskedResultData = null;
        currentMapping = {};

        const hitlPanel = document.getElementById('hitl-panel');
        if (hitlPanel) hitlPanel.style.display = 'none';

        if (bannerText) bannerText.innerHTML = `⚠️ <strong>Unmasked Mode Active</strong>: Ingested <strong>${escapeHtml(currentFileName)}</strong> without masking.`;

    } catch (err) {
        alert(`Network Error: ${err.message}`);
    }
}

// --- CHAT & DE-MASKING ---
function handleChatKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChatQuery();
    }
}

function toggleGlobalDemask(active) {
    isGlobalDemaskActive = active;
}

function toggleMaskPrompt(active) {
    isMaskPromptActive = active;
}

async function sendChatQuery() {
    const input = document.getElementById('chat-input');
    const query = input.value.trim();
    if (!query) return;

    input.value = '';
    const userMsgId = `user-msg-${Date.now()}`;
    appendChatMessage('user', query, userMsgId);

    const tempEl = document.getElementById('param-temp');
    const toppEl = document.getElementById('param-topp');
    const maxTokEl = document.getElementById('param-maxtokens');
    const modelEl = document.getElementById('param-model');
    const apiKeyEl = document.getElementById('param-apikey');

    let currentMaskedQuery = query;

    const formData = new FormData();
    formData.append('query', query);
    formData.append('auto_demask', isGlobalDemaskActive);
    formData.append('mask_prompt', isMaskPromptActive);
    formData.append('temperature', tempEl ? tempEl.value : '0.2');
    formData.append('top_p', toppEl ? toppEl.value : '0.95');
    formData.append('max_tokens', maxTokEl ? maxTokEl.value : '512');
    formData.append('model_name', modelEl ? modelEl.value : 'llama-3.1-8b-instant');
    formData.append('history', JSON.stringify(conversationHistory));
    if (apiKeyEl && apiKeyEl.value.trim()) {
        formData.append('groq_api_key', apiKeyEl.value.trim());
    }

    const msgId = `msg-${Date.now()}`;
    const streamContainer = document.getElementById('chat-stream');
    const botMsgDiv = document.createElement('div');
    botMsgDiv.className = 'flex gap-4 chat-msg-container';
    botMsgDiv.innerHTML = `
        <div class="w-10 h-10 rounded-lg overflow-hidden border border-border-accent shrink-0 shadow-sm">
            <img src="/static/logo.jpg" alt="PrivacyShield Logo" class="w-full h-full object-cover">
        </div>
        <div class="space-y-1 flex-1">
            <div class="flex items-center justify-between mb-1">
                <span class="text-xs font-semibold text-text-muted" id="${msgId}-model">PRIVACYSHIELD ASSISTANT</span>
                <span class="badge badge-success">🛡️ Zero Cloud Leakage</span>
            </div>
            <div class="glass-card p-4 text-text-main text-sm leading-relaxed min-h-[48px]" id="${msgId}-text">
                <span class="inline-block animate-pulse text-text-muted font-mono text-xs">⏳ Retrieving context & streaming response...</span>
            </div>
            <div class="flex justify-between items-center pt-2 text-xs font-mono text-text-muted" id="${msgId}-footer" style="display:none;">
                <span id="${msgId}-status">Streaming Response...</span>
                <button class="hover:text-primary transition-colors text-xs flex items-center gap-1" id="${msgId}-toggle-btn">
                    <span class="material-symbols-outlined text-sm">sync</span> Toggle De-Mask / Mask
                </button>
            </div>
        </div>
    `;

    streamContainer.appendChild(botMsgDiv);
    const scrollContainer = document.getElementById('chat-history-container');
    
    let scrollScheduled = false;
    function requestSmoothScroll() {
        if (!scrollScheduled && scrollContainer) {
            scrollScheduled = true;
            requestAnimationFrame(() => {
                scrollContainer.scrollTop = scrollContainer.scrollHeight;
                scrollScheduled = false;
            });
        }
    }

    requestSmoothScroll();

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            let errorText = 'Failed to process query.';
            try {
                const errorData = await response.json();
                errorText = errorData.detail || errorText;
            } catch (_) {}

            document.getElementById(`${msgId}-text`).innerHTML = `
                <div class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-300 text-xs space-y-2">
                    <div class="font-bold flex items-center gap-2">
                        <span class="material-symbols-outlined text-base">warning</span> Query Error (${response.status})
                    </div>
                    <div>${escapeHtml(errorText)}</div>
                    ${response.status === 403 ? `
                        <div class="pt-1 border-t border-red-500/20 text-[11px] text-text-muted">
                            💡 <strong>Tip:</strong> If Groq Cloud is blocked on your network or proxy, open <strong>LLM Controls</strong> sidebar and paste your custom Groq API Key into the <strong>Custom Groq API Key</strong> field.
                        </div>
                    ` : ''}
                </div>
            `;
            if (response.status === 403 && typeof toggleRightPanel === 'function') {
                const panel = document.getElementById('right-panel');
                if (panel && panel.classList.contains('hidden')) {
                    toggleRightPanel();
                }
            }
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalMasked = "";
        let finalUnmasked = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const dataStr = line.replace("data: ", "").trim();
                    if (!dataStr) continue;

                    try {
                        const eventData = JSON.parse(dataStr);

                        if (eventData.event === 'start') {
                            currentMapping = eventData.mapping || currentMapping;
                            if (eventData.masked_query) {
                                currentMaskedQuery = eventData.masked_query;
                            }
                            updateUserMessageMaskingInfo(userMsgId, eventData);
                            const modelLabel = document.getElementById(`${msgId}-model`);
                            if (modelLabel) modelLabel.innerText = `PRIVACYSHIELD ASSISTANT (${eventData.model || 'Groq'})`;
                            document.getElementById(`${msgId}-text`).innerText = '';
                            document.getElementById(`${msgId}-footer`).style.display = 'flex';
                        } else if (eventData.event === 'chunk') {
                            finalMasked = eventData.accumulated_masked;
                            finalUnmasked = eventData.accumulated_unmasked;
                            const textEl = document.getElementById(`${msgId}-text`);
                            if (textEl) {
                                const displayText = isGlobalDemaskActive ? finalUnmasked : finalMasked;
                                textEl.innerHTML = renderMarkdown(displayText);
                                textEl.setAttribute('data-state', isGlobalDemaskActive ? 'unmasked' : 'masked');
                            }
                            requestSmoothScroll();
                        } else if (eventData.event === 'end') {
                            finalMasked = eventData.masked_response;
                            finalUnmasked = eventData.unmasked_response;
                            const textEl = document.getElementById(`${msgId}-text`);
                            const statusEl = document.getElementById(`${msgId}-status`);
                            const toggleBtn = document.getElementById(`${msgId}-toggle-btn`);

                            if (textEl) {
                                const displayText = isGlobalDemaskActive ? finalUnmasked : finalMasked;
                                textEl.innerHTML = renderMarkdown(displayText);
                                textEl.setAttribute('data-state', isGlobalDemaskActive ? 'unmasked' : 'masked');
                            }
                            if (statusEl) statusEl.innerText = isGlobalDemaskActive ? 'Unmasked (Human Approved)' : 'Masked Token Output';

                            if (toggleBtn) {
                                toggleBtn.onclick = () => toggleMessageDemask(msgId, finalMasked, finalUnmasked);
                            }

                            // Store masked turn in conversation history for multi-turn context
                            if (currentMaskedQuery && finalMasked) {
                                conversationHistory.push({ role: 'user', content: currentMaskedQuery });
                                conversationHistory.push({ role: 'assistant', content: finalMasked });
                                try {
                                    sessionStorage.setItem('privacyshield_chat_history', JSON.stringify(conversationHistory));
                                } catch (e) {}
                            }

                            requestSmoothScroll();
                        }
                    } catch (e) {}
                }
            }
        }

    } catch (err) {
        document.getElementById(`${msgId}-text`).innerText = `⚠️ Network Error: ${err.message}`;
    }
}

function appendChatMessage(role, text, msgId = null) {
    const stream = document.getElementById('chat-stream');
    if (!stream) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'flex gap-4 chat-msg-container';
    if (msgId) msgDiv.id = msgId;

    if (role === 'user') {
        msgDiv.innerHTML = `
            <div class="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center shrink-0 ml-auto order-2">
                <span class="material-symbols-outlined text-text-main text-xl">person</span>
            </div>
            <div class="space-y-1 flex-1 text-right order-1">
                <div class="flex items-center justify-end gap-2 mb-1">
                    <span id="${msgId ? msgId + '-badge' : ''}"></span>
                    <span class="text-xs font-semibold text-text-muted">YOU</span>
                </div>
                <div class="glass-card p-4 text-text-main text-sm leading-relaxed inline-block text-left bg-primary/10 border-primary/20" id="${msgId ? msgId + '-text' : ''}">${escapeHtml(text)}</div>
                <div id="${msgId ? msgId + '-sub' : ''}"></div>
            </div>
        `;
    } else {
        msgDiv.innerHTML = `
            <div class="w-10 h-10 rounded-lg overflow-hidden border border-border-accent shrink-0 shadow-sm">
                <img src="/static/logo.jpg" alt="PrivacyShield Logo" class="w-full h-full object-cover">
            </div>
            <div class="space-y-1 flex-1">
                <div class="flex items-center justify-between mb-1">
                    <span class="text-xs font-semibold text-text-muted">PRIVACYSHIELD ASSISTANT</span>
                    <span class="badge badge-success">🛡️ Zero Cloud Leakage</span>
                </div>
                <div class="glass-card p-4 text-text-main text-sm leading-relaxed" id="${msgId ? msgId + '-text' : ''}">${escapeHtml(text)}</div>
                <div id="${msgId ? msgId + '-sub' : ''}"></div>
            </div>
        `;
    }

    stream.appendChild(msgDiv);
    const container = document.getElementById('chat-history-container');
    if (container) container.scrollTop = container.scrollHeight;
}

function updateUserMessageMaskingInfo(userMsgId, data) {
    const badgeEl = document.getElementById(`${userMsgId}-badge`);
    const subEl = document.getElementById(`${userMsgId}-sub`);
    if (!badgeEl) return;

    if (data.mask_prompt_enabled) {
        if (data.prompt_pii_detected > 0) {
            badgeEl.className = "badge badge-cyan";
            badgeEl.innerHTML = `🛡️ Input Masked (${data.prompt_pii_detected} PII)`;

            if (subEl) {
                subEl.className = "pt-xs text-[11px] font-label-caps text-on-surface-variant flex justify-end gap-sm items-center";
                subEl.innerHTML = `
                    <span id="${userMsgId}-status">Masked Prompt Sent</span>
                    <button class="hover:text-primary transition-colors text-[10px]" onclick="toggleUserPromptDisplay('${userMsgId}', \`${escapeJs(data.query)}\`, \`${escapeJs(data.masked_query)}\`)">
                        🔄 Toggle Masked/Raw
                    </button>
                `;
            }
        } else {
            badgeEl.className = "badge badge-success";
            badgeEl.innerHTML = `🛡️ Input Clean`;
        }
    } else {
        badgeEl.className = "badge badge-amber";
        badgeEl.innerHTML = `⚠️ Raw Input (Unmasked)`;
    }
}

function toggleUserPromptDisplay(msgId, rawQuery, maskedQuery) {
    const textEl = document.getElementById(`${msgId}-text`);
    const statusEl = document.getElementById(`${msgId}-status`);
    if (!textEl) return;

    if (textEl.innerText === rawQuery) {
        textEl.innerText = maskedQuery;
        if (statusEl) statusEl.innerText = "Masked Prompt Sent";
    } else {
        textEl.innerText = rawQuery;
        if (statusEl) statusEl.innerText = "Unmasked Original Input";
    }
}

function appendBotMessageWithDemaskOption(data) {
    const stream = document.getElementById('chat-stream');
    if (!stream) return;

    const msgId = `msg-${Date.now()}`;
    const initialText = isGlobalDemaskActive ? data.unmasked_response : data.masked_response;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'flex gap-lg';

    msgDiv.innerHTML = `
        <div class="w-10 h-10 rounded bg-primary/20 border border-primary/30 flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-primary">smart_toy</span>
        </div>
        <div class="space-y-xs flex-1">
            <div class="flex items-center justify-between">
                <span class="font-label-caps text-[10px] text-on-surface-variant">PRIVACYSHIELD ASSISTANT (${data.model || 'Groq'})</span>
                <span class="badge badge-success">🛡️ Zero Cloud Leakage</span>
            </div>
            <div class="glass-panel p-md rounded-xl text-on-surface leading-relaxed font-body-sm text-body-sm" id="${msgId}-text">${escapeHtml(initialText)}</div>
            
            <div class="flex justify-between items-center pt-xs text-[11px] font-label-caps text-on-surface-variant">
                <span id="${msgId}-status">${isGlobalDemaskActive ? 'Unmasked (Human Approved)' : 'Masked Token Output'}</span>
                <button class="hover:text-primary transition-colors text-[10px] flex items-center gap-xs" onclick="toggleMessageDemask('${msgId}', \`${escapeJs(data.masked_response)}\`, \`${escapeJs(data.unmasked_response)}\`)">
                    <span class="material-symbols-outlined text-[14px]">sync</span> Toggle De-Mask / Mask
                </button>
            </div>
        </div>
    `;

    stream.appendChild(msgDiv);
    const container = document.getElementById('chat-history-container');
    if (container) container.scrollTop = container.scrollHeight;
}

function toggleMessageDemask(msgId, maskedText, unmaskedText) {
    const textEl = document.getElementById(`${msgId}-text`);
    const statusEl = document.getElementById(`${msgId}-status`);
    if (!textEl) return;

    const currentState = textEl.getAttribute('data-state') || (isGlobalDemaskActive ? 'unmasked' : 'masked');

    if (currentState === 'masked') {
        textEl.innerHTML = renderMarkdown(unmaskedText);
        textEl.setAttribute('data-state', 'unmasked');
        if (statusEl) statusEl.innerText = "Unmasked (Human Approved)";
    } else {
        textEl.innerHTML = renderMarkdown(maskedText);
        textEl.setAttribute('data-state', 'masked');
        if (statusEl) statusEl.innerText = "Masked Token Output";
    }
}

// DOWNLOADS
function downloadMaskedDoc() {
    if (!maskedResultData) return alert("Please upload and verify a document first.");
    window.location.href = `/api/download/masked/${maskedResultData.masked_file_name}`;
}

function downloadMappingJson() {
    if (!maskedResultData) return alert("Please upload and verify a document first.");
    window.location.href = `/api/download/mapping/${maskedResultData.mapping_file_name}`;
}

// MARKDOWN & HTML HELPERS
function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    
    // Bold: **text** or __text__
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-on-surface">$1</strong>');
    html = html.replace(/__(.*?)__/g, '<strong class="font-bold text-on-surface">$1</strong>');

    // Bullet lists: * item or - item
    html = html.replace(/^\s*[\*\-]\s+(.*)$/gm, '• $1');

    // Italic: *text* (single asterisk)
    html = html.replace(/(^|[^\*])\*(?!\*)(.*?)\*/g, '$1<em class="italic">$2</em>');

    // Code: `code`
    html = html.replace(/`(.*?)`/g, '<code class="font-code text-primary bg-white/5 px-1 py-0.5 rounded text-xs">$1</code>');

    // Newlines
    html = html.replace(/\n/g, '<br>');

    return html;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeJs(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\${/g, '\\${');
}
