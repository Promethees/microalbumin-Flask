/**
 * OKAPI Assistant — floating AI chat widget
 * Connects to the local /ai/* routes which proxy to Ollama.
 */

(function () {
    'use strict';

    // ── Slash commands ────────────────────────────────────────────────────────

    const SLASH_COMMANDS = [
        { cmd: '/help',          desc: 'List all available slash commands',                       action: 'help' },
        { cmd: '/guide',         desc: 'Launch a full step-by-step app walkthrough',              action: 'send', query: 'how does this app work' },
        { cmd: '/calibrate',     desc: 'Create a calibration standard curve (full workflow)',     action: 'send', query: 'how to create a calibration curve' },
        { cmd: '/concentration', desc: 'Calculate sample concentration from calibration data',    action: 'send', query: 'how to calculate concentration' },
        { cmd: '/start',         desc: 'Start a measurement with the connected device',           action: 'send', query: 'how to start the device' },
        { cmd: '/stop',          desc: 'Stop the current device measurement',                     action: 'send', query: 'how to stop the device' },
        { cmd: '/export',        desc: 'Export current data to CSV',                              action: 'send', query: 'how to export data' },
        { cmd: '/report',        desc: 'Create a quick or full HTML report',                      action: 'send', query: 'how to create a report' },
        { cmd: '/status',        desc: 'Show current app state (mode, data, device)',             action: 'status' },
        { cmd: '/clear',         desc: 'Clear the conversation history',                          action: 'clear' },
    ];

    const _picker = { visible: false, idx: 0, list: [] };

    // ── State ────────────────────────────────────────────────────────────────

    const AI = {
        open: false,
        settingsOpen: false,
        messages: [],          // {role, content}[]  — conversation history
        settings: null,        // loaded from /ai/settings
        status: null,          // loaded from /ai/status
        activeLang: null,      // currently active language (cycles through preferred_languages)
        pullTimer: null,
        LANG_LABELS: {
            en: 'EN', vi: 'VI', zh: '中', fr: 'FR', ja: '日', ru: 'RU'
        },
        LANG_NAMES: {
            en: 'English', vi: 'Tiếng Việt', zh: '中文',
            fr: 'Français', ja: '日本語', ru: 'Русский'
        },
        LANG_DISPLAY: {
            en: 'English', vi: 'Tiếng Việt', zh: '中文 (简体)',
            fr: 'Français', ja: '日本語', ru: 'Русский'
        },
    };

    // ── Bootstrap ─────────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', () => {
        _injectWidget();
        _loadStatus();
    });

    // ── DOM injection ────────────────────────────────────────────────────────

    function _injectWidget() {
        const fab = document.createElement('button');
        fab.id = 'okapi-ai-fab';
        fab.title = 'OKAPI Assistant';
        fab.innerHTML = `<span class="okapi-ai-label">AI Assistant</span><span class="okapi-ai-icon">&#129302;</span>`;
        fab.addEventListener('click', _togglePanel);
        document.body.appendChild(fab);

        const panel = document.createElement('div');
        panel.id = 'okapi-ai-panel';
        panel.innerHTML = `
<div id="okapi-ai-header">
  <span id="okapi-ai-title">&#129302; OKAPI Assistant</span>
  <div id="okapi-ai-header-btns">
    <button id="okapi-ai-lang-btn" title="Cycle language" onclick="OkapiAI.cycleLang()"></button>
    <button id="okapi-ai-settings-btn" title="Settings" onclick="OkapiAI.toggleSettings()">&#9881;</button>
    <button id="okapi-ai-close-btn" title="Close" onclick="OkapiAI.close()">&#10005;</button>
  </div>
</div>

<!-- Main chat view -->
<div id="okapi-ai-body">
  <div id="okapi-ai-messages"></div>
  <div id="okapi-ai-status-bar"></div>
  <div id="okapi-ai-cmd-picker" class="okapi-hidden"></div>
  <div id="okapi-ai-input-row">
    <textarea id="okapi-ai-input" rows="2" placeholder="Ask anything… (type / for commands)"></textarea>
    <button id="okapi-ai-send-btn" onclick="OkapiAI.send()">&#10148;</button>
  </div>
</div>

<!-- Settings view (hidden by default) -->
<div id="okapi-ai-settings" class="okapi-hidden">
  <h4>&#129302; AI Assistant Manager</h4>
  <div id="okapi-ai-lang-section">
    <div class="okapi-ai-set-label">Languages <span class="okapi-ai-set-hint">(select one or more; cycle with button)</span></div>
    <div id="okapi-ai-lang-checks">
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="en"> English</label>
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="vi"> Ti&#7871;ng Vi&#7879;t</label>
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="zh"> &#20013;&#25991; (&#31616;&#20307;)</label>
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="fr"> Fran&#231;ais</label>
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="ja"> &#26085;&#26412;&#35486;</label>
      <label><input type="checkbox" class="okapi-ai-lang-cb" value="ru"> &#1056;&#1091;&#1089;&#1089;&#1082;&#1080;&#1081;</label>
    </div>
  </div>
  <label>Model
    <select id="okapi-ai-set-model"></select>
  </label>
  <label>Ollama URL
    <input type="text" id="okapi-ai-set-url">
  </label>
  <label class="okapi-ai-toggle-row">
    <span>Enable AI Assistant</span>
    <input type="checkbox" id="okapi-ai-set-enabled">
  </label>
  <div id="okapi-ai-ollama-status"></div>
  <div id="okapi-ai-pull-section" class="okapi-hidden">
    <div id="okapi-ai-pull-info"></div>
    <div id="okapi-ai-pull-bar-wrap"><div id="okapi-ai-pull-bar"></div></div>
    <button id="okapi-ai-pull-btn" onclick="OkapiAI.pullModel()">&#11015; Download Model</button>
  </div>
  <details id="okapi-ai-uninstall-details">
    <summary>Uninstall / Remove</summary>
    <div class="okapi-ai-uninstall-box">
      <strong>Disable feature:</strong> uncheck "Enable AI Assistant" above and save.<br>
      <strong>Remove downloaded model:</strong>
      <code>ollama rm MODEL_NAME</code> in Terminal.<br>
      <strong>Uninstall Ollama:</strong>
      <a href="https://ollama.com" target="_blank">ollama.com</a>
      &#8594; Docs &#8594; Uninstall.<br>
      <strong>Reset AI settings:</strong>
      <button onclick="OkapiAI.resetSettings()">&#8635; Reset to defaults</button>
    </div>
  </details>
  <div id="okapi-ai-settings-actions">
    <button onclick="OkapiAI.saveSettings()">Save</button>
    <button onclick="OkapiAI.toggleSettings()">Back</button>
  </div>
</div>`;
        document.body.appendChild(panel);

        const inputEl = document.getElementById('okapi-ai-input');

        // send on Enter (Shift+Enter = newline); navigate picker with arrow keys
        inputEl.addEventListener('keydown', (e) => {
            if (_picker.visible) {
                if (e.key === 'ArrowUp')   { e.preventDefault(); _pickerMove(-1); return; }
                if (e.key === 'ArrowDown') { e.preventDefault(); _pickerMove(1);  return; }
                if (e.key === 'Escape')    { e.preventDefault(); _pickerHide();   return; }
                if (e.key === 'Tab')       { e.preventDefault(); _pickerConfirm(); return; }
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _pickerConfirm(); return; }
            }
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); OkapiAI.send(); }
        });

        // show picker when text starts with /
        inputEl.addEventListener('input', () => {
            const val = inputEl.value;
            if (val.startsWith('/')) _pickerShow(val.slice(1));
            else _pickerHide();
        });

        // delay hide so clicks register before blur fires
        inputEl.addEventListener('blur', () => { setTimeout(_pickerHide, 150); });
    }

    // ── Load status & settings ────────────────────────────────────────────────

    function _loadStatus() {
        fetch('/ai/status')
            .then(r => r.json())
            .then(data => {
                if (data.status !== 'success') return;
                AI.status = data;
                AI.settings = data.settings;
                // Initialize activeLang from preferred_languages (or legacy field)
                const pl = AI.settings.preferred_languages
                    || (AI.settings.preferred_language ? [AI.settings.preferred_language] : null)
                    || ['en'];
                AI.activeLang = pl[0] || 'en';
                _updateLangBtn();
                _showWelcomeIfNeeded();
            })
            .catch(() => {/* AI routes may not be registered yet */ });
    }

    function _showWelcomeIfNeeded() {
        if (!AI.status || !AI.settings) return;
        if (!AI.settings.first_run_shown) {
            _addSystemMsg(_welcomeMsg());
            fetch('/ai/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ first_run_shown: true }),
            });
            AI.settings.first_run_shown = true;
        }
        _updateStatusBar();
    }

    function _welcomeMsg() {
        const msgs = {
            en: '👋 Hi! I\'m your OKAPI Assistant. Ask me about your data, calibration, hardware, or workflow.',
            vi: '👋 Xin chào! Tôi là OKAPI Assistant. Hãy hỏi tôi về dữ liệu, hiệu chuẩn, phần cứng hoặc quy trình làm việc.',
            zh: '👋 您好！我是 OKAPI Assistant。请向我询问有关数据、校准、硬件或工作流程的问题。',
            fr: '👋 Bonjour ! Je suis votre assistant OKAPI. Posez-moi des questions sur vos données, la calibration, le matériel ou votre flux de travail.',
            ja: '👋 こんにちは！OKAPIアシスタントです。データ、キャリブレーション、ハードウェア、ワークフローについてお気軽にご質問ください。',
            ru: '👋 Привет! Я OKAPI Assistant. Задавайте вопросы о данных, калибровке, оборудовании или рабочем процессе.',
        };
        return msgs[AI.activeLang] || msgs.en;
    }

    // ── Panel toggle ──────────────────────────────────────────────────────────

    function _togglePanel() {
        AI.open ? OkapiAI.close() : OkapiAI.open_();
    }

    // ── Language ──────────────────────────────────────────────────────────────

    function _updateLangBtn() {
        const btn = document.getElementById('okapi-ai-lang-btn');
        if (!btn) return;
        const lang = AI.activeLang || 'en';
        btn.textContent = AI.LANG_LABELS[lang] || lang.toUpperCase();
        btn.title = AI.LANG_NAMES[lang] || lang;
    }

    // ── Status bar ────────────────────────────────────────────────────────────

    function _updateStatusBar() {
        const bar = document.getElementById('okapi-ai-status-bar');
        if (!bar || !AI.status) return;
        if (!AI.status.ollama_running) {
            bar.innerHTML = '<span class="okapi-ai-badge okapi-ai-badge-warn">&#9888; Ollama offline &mdash; open Settings to install</span>';
        } else if (!AI.status.model_available) {
            bar.innerHTML = '<span class="okapi-ai-badge okapi-ai-badge-warn">&#9888; Model not downloaded &mdash; open Settings to download</span>';
        } else {
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-ok">&#10003; ${_esc(AI.settings.model)}</span>`;
        }
    }

    // ── Messages ──────────────────────────────────────────────────────────────

    function _addSystemMsg(text) {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'okapi-ai-msg okapi-ai-msg-system';
        div.textContent = text;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function _addMsg(role, content) {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return;
        const div = document.createElement('div');
        div.className = `okapi-ai-msg okapi-ai-msg-${role}`;

        // simple markdown: **bold**, newlines, code blocks
        div.innerHTML = _renderMarkdown(content);
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function _addThinkingBubble() {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return null;
        const div = document.createElement('div');
        div.className = 'okapi-ai-msg okapi-ai-msg-assistant okapi-ai-thinking';
        div.innerHTML = '<span></span><span></span><span></span>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return div;
    }

    function _addStreamingMsg() {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return null;
        const div = document.createElement('div');
        div.className = 'okapi-ai-msg okapi-ai-msg-assistant okapi-ai-thinking';
        div.innerHTML = '<span></span><span></span><span></span>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return div;
    }

    function _updateStreamingMsg(div, content) {
        if (!div) return;
        div.className = 'okapi-ai-msg okapi-ai-msg-assistant';
        div.innerHTML = _renderMarkdown(content) + '<span class="okapi-ai-cursor">&#9611;</span>';
        const container = document.getElementById('okapi-ai-messages');
        if (container) container.scrollTop = container.scrollHeight;
    }

    function _finalizeStreamingMsg(div, content, errorText) {
        if (!div) return;
        const container = document.getElementById('okapi-ai-messages');
        if (errorText) {
            div.className = 'okapi-ai-msg okapi-ai-msg-system';
            div.textContent = errorText;
        } else {
            div.className = 'okapi-ai-msg okapi-ai-msg-assistant';
            div.innerHTML = _renderMarkdown(content || '');
        }
        if (container) container.scrollTop = container.scrollHeight;
    }

    function _renderMarkdown(text) {
        if (!text) return '';
        // escape HTML first
        let t = _esc(text);
        // code blocks
        t = t.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        // inline code
        t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
        // bold
        t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // bullet points
        t = t.replace(/^[•·]\s+(.+)$/gm, '<li>$1</li>');
        t = t.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        // newlines
        t = t.replace(/\n/g, '<br>');
        return t;
    }

    function _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Settings panel ────────────────────────────────────────────────────────

    function _populateSettings() {
        if (!AI.status || !AI.settings) return;

        // language checkboxes
        const preferredLangs = AI.settings.preferred_languages || ['en'];
        document.querySelectorAll('.okapi-ai-lang-cb').forEach(cb => {
            cb.checked = preferredLangs.includes(cb.value);
        });

        // model select
        const modelSel = document.getElementById('okapi-ai-set-model');
        modelSel.innerHTML = '';
        const catalog = AI.status.available_models_catalog || [];
        catalog.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = `${m.name} (${m.size}) — ${m.note}`;
            if (m.name === AI.settings.model) opt.selected = true;
            modelSel.appendChild(opt);
        });
        // also add any already-installed models not in catalog
        (AI.status.available_models || []).forEach(name => {
            if (!catalog.find(m => m.name === name)) {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name + ' (installed)';
                if (name === AI.settings.model) opt.selected = true;
                modelSel.appendChild(opt);
            }
        });

        // URL & enabled
        document.getElementById('okapi-ai-set-url').value = AI.settings.ollama_url || 'http://localhost:11434';
        document.getElementById('okapi-ai-set-enabled').checked = !!AI.settings.enabled;

        // Ollama status
        _renderOllamaStatus();
    }

    function _renderOllamaStatus() {
        const el = document.getElementById('okapi-ai-ollama-status');
        if (!el || !AI.status) return;
        const pullSection = document.getElementById('okapi-ai-pull-section');

        if (!AI.status.ollama_running) {
            el.innerHTML = `
<div class="okapi-ai-setup-box">
  <strong>&#9888; Ollama is not running or not installed.</strong><br>
  1. <a href="https://ollama.com/download" target="_blank">Download Ollama</a> and install it.<br>
  2. Start Ollama, then click <strong>Refresh</strong> below.<br>
  <button onclick="OkapiAI.refreshStatus()">&#8635; Refresh</button>
</div>`;
            pullSection.classList.add('okapi-hidden');
        } else if (!AI.status.model_available) {
            el.innerHTML = '<span class="okapi-ai-badge okapi-ai-badge-ok">&#10003; Ollama running</span>';
            pullSection.classList.remove('okapi-hidden');
            document.getElementById('okapi-ai-pull-info').textContent =
                `Model "${AI.settings.model}" is not downloaded yet.`;
        } else {
            el.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-ok">&#10003; Ollama running &bull; ${_esc(AI.settings.model)} ready</span>`;
            pullSection.classList.add('okapi-hidden');
        }
    }

    // ── Pull progress ─────────────────────────────────────────────────────────

    function _startPullPolling() {
        if (AI.pullTimer) return;
        AI.pullTimer = setInterval(() => {
            fetch('/ai/pull_status')
                .then(r => r.json())
                .then(d => {
                    if (d.status !== 'success') return;
                    const info = document.getElementById('okapi-ai-pull-info');
                    const bar = document.getElementById('okapi-ai-pull-bar');
                    const btn = document.getElementById('okapi-ai-pull-btn');
                    if (info) info.textContent = d.pull_status + (d.percent ? ` — ${d.percent}%` : '');
                    if (bar) bar.style.width = (d.percent || 0) + '%';
                    if (d.done || !d.active) {
                        clearInterval(AI.pullTimer);
                        AI.pullTimer = null;
                        if (btn) btn.disabled = false;
                        if (d.error) {
                            if (info) info.textContent = 'Error: ' + d.error;
                        } else {
                            if (info) info.textContent = 'Download complete! ✓';
                            // refresh status
                            OkapiAI.refreshStatus();
                        }
                    }
                })
                .catch(() => {
                    clearInterval(AI.pullTimer);
                    AI.pullTimer = null;
                });
        }, 2000);
    }

    // ── Guide launcher ────────────────────────────────────────────────────────

    function _launchGuide(workflow) {
        if (typeof window.userGuide === 'undefined') return;
        OkapiAI.close();
        setTimeout(() => window.userGuide.startWorkflow(workflow), 400);
    }

    function _launchCustomSteps(steps) {
        if (typeof window.userGuide === 'undefined') return;
        OkapiAI.close();
        setTimeout(() => window.userGuide.startCustomSteps(steps), 400);
    }

    function _getUiContext() {
        const appState = window.AppState || {};
        const mainContent = document.getElementById('main-content');
        const dataDisplay = document.getElementById('data-display-section');
        const calMode = document.getElementById('cal-mode-select');
        return {
            mode: appState.currentMeasurementMode || 'unknown',
            app_started: !!(mainContent && !mainContent.classList.contains('hidden')),
            data_loaded: !!(dataDisplay && !dataDisplay.classList.contains('hidden')),
            cal_mode: calMode ? (calMode.getAttribute('data-value') || '') : '',
        };
    }

    // ── Slash command picker ──────────────────────────────────────────────────

    function _pickerShow(query) {
        const q = query.toLowerCase();
        _picker.list = SLASH_COMMANDS.filter(c =>
            q === '' || c.cmd.slice(1).startsWith(q) || c.desc.toLowerCase().includes(q)
        );
        if (_picker.list.length === 0) { _pickerHide(); return; }
        _picker.idx = Math.min(_picker.idx, _picker.list.length - 1);
        _picker.visible = true;
        _pickerRender();
        document.getElementById('okapi-ai-cmd-picker').classList.remove('okapi-hidden');
    }

    function _pickerHide() {
        _picker.visible = false;
        _picker.idx = 0;
        const el = document.getElementById('okapi-ai-cmd-picker');
        if (el) el.classList.add('okapi-hidden');
    }

    function _pickerRender() {
        const el = document.getElementById('okapi-ai-cmd-picker');
        if (!el) return;
        el.innerHTML = _picker.list.map((c, i) =>
            `<div class="okapi-ai-cmd-item${i === _picker.idx ? ' okapi-ai-cmd-active' : ''}" data-i="${i}">` +
            `<span class="okapi-ai-cmd-name">${_esc(c.cmd)}</span>` +
            `<span class="okapi-ai-cmd-desc">${_esc(c.desc)}</span>` +
            `</div>`
        ).join('');
        el.querySelectorAll('.okapi-ai-cmd-item').forEach(item => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                _picker.idx = parseInt(item.dataset.i, 10);
                _pickerConfirm();
            });
        });
    }

    function _pickerMove(dir) {
        _picker.idx = (_picker.idx + dir + _picker.list.length) % _picker.list.length;
        _pickerRender();
    }

    function _pickerConfirm() {
        const cmd = _picker.list[_picker.idx];
        _pickerHide();
        if (cmd) _cmdExecute(cmd);
    }

    function _cmdExecute(cmd) {
        const input = document.getElementById('okapi-ai-input');

        if (cmd.action === 'clear') {
            input.value = '';
            OkapiAI.clearHistory();
            return;
        }

        if (cmd.action === 'help') {
            input.value = '';
            const lines = SLASH_COMMANDS.map(c => `\`${c.cmd}\` — ${c.desc}`).join('\n');
            _addMsg('assistant', '**Available commands**\n\n' + lines);
            return;
        }

        if (cmd.action === 'status') {
            input.value = '';
            const ctx = _getUiContext();
            const lines = [
                `\`mode\` ${ctx.mode || '—'}`,
                `\`app started\` ${ctx.app_started ? 'yes' : 'no'}`,
                `\`data loaded\` ${ctx.data_loaded ? 'yes' : 'no'}`,
                `\`cal mode\` ${ctx.cal_mode || '—'}`,
                `\`model\` ${(AI.settings && AI.settings.model) || '—'}`,
                `\`ollama\` ${(AI.status && AI.status.ollama_running) ? 'running' : 'offline'}`,
            ].join('\n');
            _addMsg('assistant', '**App status**\n\n' + lines);
            return;
        }

        if (cmd.action === 'send' && cmd.query) {
            input.value = cmd.query;
            setTimeout(() => OkapiAI.send(), 20);
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────

    window.OkapiAI = {

        open_() {
            AI.open = true;
            const panel = document.getElementById('okapi-ai-panel');
            if (panel) panel.classList.add('okapi-ai-panel-open');
            if (!AI.settings) _loadStatus();
        },

        close() {
            AI.open = false;
            const panel = document.getElementById('okapi-ai-panel');
            if (panel) panel.classList.remove('okapi-ai-panel-open');
        },

        toggleSettings() {
            AI.settingsOpen = !AI.settingsOpen;
            const body = document.getElementById('okapi-ai-body');
            const sett = document.getElementById('okapi-ai-settings');
            const btn = document.getElementById('okapi-ai-settings-btn');

            if (AI.settingsOpen) {
                body.classList.add('okapi-hidden');
                sett.classList.remove('okapi-hidden');
                if (btn) {
                    btn.innerHTML = '&#128172;';
                    btn.title = 'Back to Chat';
                }
                _populateSettings();
            } else {
                body.classList.remove('okapi-hidden');
                sett.classList.add('okapi-hidden');
                if (btn) {
                    btn.innerHTML = '&#9881;';
                    btn.title = 'Settings';
                }
                _updateStatusBar();
            }
        },

        cycleLang() {
            if (!AI.settings) return;
            const pl = AI.settings.preferred_languages || ['en'];
            if (pl.length <= 1) return;
            const idx = pl.indexOf(AI.activeLang);
            AI.activeLang = pl[(idx + 1) % pl.length];
            _updateLangBtn();
        },

        saveSettings() {
            const langBoxes = document.querySelectorAll('.okapi-ai-lang-cb:checked');
            let langs = Array.from(langBoxes).map(cb => cb.value);
            if (langs.length === 0) langs = ['en'];

            const model = document.getElementById('okapi-ai-set-model').value;
            const url = document.getElementById('okapi-ai-set-url').value.trim();
            const enabled = document.getElementById('okapi-ai-set-enabled').checked;

            fetch('/ai/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    preferred_languages: langs,
                    model,
                    ollama_url: url,
                    enabled,
                }),
            })
                .then(r => r.json())
                .then(d => {
                    if (d.status === 'success') {
                        AI.settings = d.settings;
                        // Keep activeLang if still preferred, else reset to first
                        const pl = AI.settings.preferred_languages || ['en'];
                        if (!pl.includes(AI.activeLang)) AI.activeLang = pl[0];
                        _updateLangBtn();
                        OkapiAI.refreshStatus();
                        OkapiAI.toggleSettings();
                    }
                });
        },

        refreshStatus() {
            fetch('/ai/status')
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'success') return;
                    AI.status = data;
                    AI.settings = data.settings;
                    // Maintain activeLang if still in preferred list, else reset
                    const pl = AI.settings.preferred_languages || ['en'];
                    if (!AI.activeLang || !pl.includes(AI.activeLang)) {
                        AI.activeLang = pl[0] || 'en';
                    }
                    _updateLangBtn();
                    _updateStatusBar();
                    if (AI.settingsOpen) _renderOllamaStatus();
                });
        },

        pullModel() {
            const model = document.getElementById('okapi-ai-set-model').value;
            const btn = document.getElementById('okapi-ai-pull-btn');
            if (btn) btn.disabled = true;

            // update settings model first
            AI.settings.model = model;
            fetch('/ai/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model }),
            });

            fetch('/ai/pull_model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model }),
            })
                .then(r => r.json())
                .then(d => {
                    const info = document.getElementById('okapi-ai-pull-info');
                    if (d.status !== 'success') {
                        if (info) info.textContent = 'Error: ' + d.message;
                        if (btn) btn.disabled = false;
                        return;
                    }
                    if (info) info.textContent = 'Downloading…';
                    _startPullPolling();
                });
        },

        send() {
            const input = document.getElementById('okapi-ai-input');
            const text = (input.value || '').trim();
            if (!text) return;

            if (!AI.settings || !AI.settings.enabled) {
                _addSystemMsg('AI Assistant is disabled. Enable it in Settings.');
                return;
            }

            input.value = '';
            _addMsg('user', text);
            AI.messages.push({ role: 'user', content: text });

            // Trim history to last 10 messages to keep prompts fast
            const historyToSend = AI.messages.length > 10
                ? AI.messages.slice(-10)
                : AI.messages.slice();

            const msgDiv = _addStreamingMsg();
            const sendBtn = document.getElementById('okapi-ai-send-btn');
            if (sendBtn) sendBtn.disabled = true;
            input.disabled = true;

            const lang = AI.activeLang || 'en';
            const model = AI.settings.model || 'qwen2.5:7b';

            (async () => {
                let fullReply = '';
                try {
                    const resp = await fetch('/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ messages: historyToSend, language: lang, model, ui_context: _getUiContext() }),
                    });

                    if (!resp.ok || !resp.body) {
                        const err = await resp.json().catch(() => ({}));
                        _finalizeStreamingMsg(msgDiv, null, '⚠ ' + (err.message || 'Request failed'));
                        return;
                    }

                    const reader = resp.body.getReader();
                    const decoder = new TextDecoder();
                    let sseBuffer = '';

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        sseBuffer += decoder.decode(value, { stream: true });
                        const lines = sseBuffer.split('\n');
                        sseBuffer = lines.pop();

                        for (const line of lines) {
                            if (!line.startsWith('data: ')) continue;
                            const payload = line.slice(6).trim();
                            if (payload === '[DONE]') break;
                            let event;
                            try { event = JSON.parse(payload); } catch { continue; }

                            if (event.type === 'chunk') {
                                fullReply += event.content;
                                _updateStreamingMsg(msgDiv, fullReply);
                            } else if (event.type === 'clear') {
                                fullReply = '';
                                _updateStreamingMsg(msgDiv, '');
                            } else if (event.type === 'guide') {
                                const ga = event.guide_action;
                                if (ga && ga.guide_workflow) {
                                    _launchGuide(ga.guide_workflow);
                                } else if (ga && ga.custom_steps && ga.custom_steps.length) {
                                    _launchCustomSteps(ga.custom_steps);
                                }
                            } else if (event.type === 'error') {
                                const errMsg = event.error === 'ollama_offline'
                                    ? '⚠ Ollama is not running. Please start Ollama first.'
                                    : event.error === 'timeout'
                                    ? '⚠ Request timed out. The model may be loading — try again.'
                                    : '⚠ ' + event.error;
                                _finalizeStreamingMsg(msgDiv, null, errMsg);
                                return;
                            }
                        }
                    }

                    AI.messages.push({ role: 'assistant', content: fullReply });
                    _finalizeStreamingMsg(msgDiv, fullReply, null);

                } catch (err) {
                    _finalizeStreamingMsg(msgDiv, null, '⚠ Network error: ' + err.message);
                } finally {
                    if (sendBtn) sendBtn.disabled = false;
                    input.disabled = false;
                    input.focus();
                }
            })();
        },

        resetSettings() {
            if (!confirm('Reset all AI Assistant settings to defaults?')) return;
            fetch('/ai/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: true,
                    preferred_languages: ['en'],
                    model: 'qwen2.5:7b',
                    ollama_url: 'http://localhost:11434',
                    first_run_shown: false,
                }),
            })
                .then(r => r.json())
                .then(d => {
                    if (d.status === 'success') {
                        AI.settings = d.settings;
                        AI.activeLang = 'en';
                        _updateLangBtn();
                        OkapiAI.refreshStatus();
                        _populateSettings();
                    }
                });
        },


        clearHistory() {
            AI.messages = [];
            const container = document.getElementById('okapi-ai-messages');
            if (container) container.innerHTML = '';
        },
    };
})();
