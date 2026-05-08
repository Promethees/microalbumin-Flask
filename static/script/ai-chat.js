/**
 * OKAPI Assistant — floating AI chat widget
 * Connects to the local /ai/* routes which proxy to Ollama.
 */

(function () {
    'use strict';

    // ── Slash commands ────────────────────────────────────────────────────────

    const SLASH_COMMANDS = [
        { cmd: '/help', desc: 'List all available slash commands', action: 'help' },
        { cmd: '/guide', desc: 'Launch a full step-by-step app walkthrough', action: 'guide', guide_id: 'app_introduction' },
        { cmd: '/measurement', desc: 'Guide to Kinetics mode and the Reading Colorimeter Data console', action: 'guide', guide_id: 'measurement_guide' },
        { cmd: '/calibrate', desc: 'Create a calibration standard curve (full workflow)', action: 'guide', guide_id: 'create_calibration_curve_workflow' },
        { cmd: '/concentration', desc: 'Calculate sample concentration from calibration data', action: 'concentration' },
        { cmd: '/merge', desc: 'Combine multiple CSV files into a single multi-source file', action: 'guide', guide_id: 'merge_files' },
        { cmd: '/range', desc: 'Set the analysis time window (start, end, unit)', action: 'guide', guide_id: 'set_analysis_range' },
        { cmd: '/normalize', desc: 'Toggle baseline subtraction to remove background absorbance', action: 'guide', guide_id: 'normalize_data' },
        { cmd: '/split', desc: 'Display each measurement source as a separate chart', action: 'guide', guide_id: 'split_sources' },
        { cmd: '/window', desc: 'Configure sliding window size for max-rate regression', action: 'guide', guide_id: 'window_size' },
        { cmd: '/time-point', desc: 'Select the time point for point-mode calibration analysis', action: 'guide', guide_id: 'select_time_point' },
        { cmd: '/start', desc: 'Start a measurement with the connected device', action: 'guide', guide_id: 'start_device' },
        { cmd: '/stop', desc: 'Stop the current device measurement', action: 'guide', guide_id: 'stop_device' },
        { cmd: '/export', desc: 'Export current data to CSV', action: 'guide', guide_id: 'export_data' },
        { cmd: '/excel', desc: 'Export report items as a formatted Excel workbook', action: 'excel' },
        { cmd: '/live-view', desc: 'Browse to the live measurement output folder', action: 'live_view' },
        { cmd: '/report', desc: 'Create a quick or full HTML report', action: 'report' },
        { cmd: '/status', desc: 'Show current app state (mode, data, device)', action: 'status' },
        { cmd: '/redo', desc: 'Replay the last guide or retry the last question', action: 'redo' },
        { cmd: '/clear', desc: 'Clear the conversation history', action: 'clear' },
    ];

    // File-select prepend step (mirrors Python's _FILE_SELECT_STEP)
    const _FILE_SELECT_STEP = {
        target: '#file-selection',
        title: 'Select a File First',
        description: 'No data file is loaded yet. Click here to select a CSV data file before proceeding.',
        descriptions: {
            vi: 'Chưa có tệp dữ liệu nào được tải. Nhấp vào đây để chọn tệp CSV trước khi tiếp tục.',
            zh: '尚未加载数据文件。请点击此处选择 CSV 数据文件后再继续。',
            fr: 'Aucun fichier de données n\'est chargé. Cliquez ici pour sélectionner un fichier CSV avant de continuer.',
            ja: 'データファイルがまだ読み込まれていません。続行する前にここをクリックして CSV ファイルを選択してください。',
            ru: 'Файл данных ещё не загружен. Нажмите здесь, чтобы выбрать CSV-файл перед продолжением.',
        },
        position: 'left',
        skipInteraction: false,
    };

    // Get-started prepend step (mirrors Python's _GET_STARTED_STEP)
    const _GET_STARTED_STEP = {
        target: '#init-button',
        title: 'Click Get Started First',
        description: 'The app hasn\'t been initialised yet. Click "Get Started" to load the main interface before proceeding with this guide.',
        descriptions: {
            vi: 'Ứng dụng chưa được khởi tạo. Nhấp vào "Bắt đầu" để tải giao diện chính trước khi tiếp tục hướng dẫn này.',
            zh: '应用程序尚未初始化。请点击"开始"加载主界面后再继续本指南。',
            fr: 'L\'application n\'a pas encore été initialisée. Cliquez sur "Commencer" pour charger l\'interface principale avant de poursuivre ce guide.',
            ja: 'アプリはまだ初期化されていません。このガイドを続ける前に「はじめる」をクリックしてメインインターフェイスを読み込んでください。',
            ru: 'Приложение ещё не инициализировано. Нажмите «Начать», чтобы загрузить главный интерфейс перед продолжением руководства.',
        },
        position: 'right',
        skipInteraction: false,
    };

    // Confirmation messages (mirrors Python's _GUIDE_LAUNCHED)
    const _GUIDE_LAUNCHED = {
        en: 'Guide launched — follow the highlighted steps.',
        vi: 'Đã khởi động hướng dẫn — làm theo các bước được tô sáng.',
        zh: '指南已启动 — 请按照高亮步骤操作。',
        fr: 'Guide lancé — suivez les étapes mises en surbrillance.',
        ja: 'ガイドを起動しました — ハイライトされた手順に従ってください。',
        ru: 'Руководство запущено — следуйте выделенным шагам.',
    };

    const _EMPTY_REPLY = {
        en: "I couldn't generate a response. Please try rephrasing your question.",
        vi: 'Tôi không thể tạo phản hồi. Hãy thử diễn đạt lại câu hỏi của bạn.',
        zh: '我无法生成回复，请尝试换一种方式提问。',
        fr: "Je n'ai pas pu générer de réponse. Essayez de reformuler votre question.",
        ja: '回答を生成できませんでした。質問を言い換えてみてください。',
        ru: 'Не удалось сформировать ответ. Попробуйте перефразировать вопрос.',
    };

    const _NOTHING_TO_REDO = {
        en: 'Nothing to redo yet — send a message or run a command first.',
        vi: 'Chưa có gì để làm lại — hãy gửi tin nhắn hoặc chạy lệnh trước.',
        zh: '暂无可重做的操作 — 请先发送消息或运行命令。',
        fr: 'Rien à refaire pour l\'instant — envoyez d\'abord un message ou exécutez une commande.',
        ja: 'やり直せるものがまだありません — まずメッセージを送るかコマンドを実行してください。',
        ru: 'Нечего повторять — сначала отправьте сообщение или выполните команду.',
    };

    const _GUIDE_NOT_FOUND = {
        en: (id) => `Guide **${id}** not found. Try again after the app loads.`,
        vi: (id) => `Không tìm thấy hướng dẫn **${id}**. Vui lòng thử lại sau khi ứng dụng tải xong.`,
        zh: (id) => `未找到指南 **${id}**。请在应用加载完成后重试。`,
        fr: (id) => `Guide **${id}** introuvable. Réessayez après le chargement de l'application.`,
        ja: (id) => `ガイド **${id}** が見つかりません。アプリの読み込み後に再試行してください。`,
        ru: (id) => `Руководство **${id}** не найдено. Повторите попытку после загрузки приложения.`,
    };

    const _REPORT_CHOICE_PROMPT = {
        en: 'Which type of report would you like to create?',
        vi: 'Bạn muốn tạo loại báo cáo nào?',
        zh: '您想要创建哪种类型的报告？',
        fr: 'Quel type de rapport souhaitez-vous créer ?',
        ja: 'どのタイプのレポートを作成しますか？',
        ru: 'Какой тип отчёта вы хотите создать?',
    };

    const _REPORT_BTN_QUICK = {
        en: '⚡ Quick Report', vi: '⚡ Báo cáo nhanh', zh: '⚡ 快速报告',
        fr: '⚡ Rapport rapide', ja: '⚡ クイックレポート', ru: '⚡ Быстрый отчёт',
    };

    const _REPORT_BTN_FULL = {
        en: '📄 Full Report', vi: '📄 Báo cáo đầy đủ', zh: '📄 完整报告',
        fr: '📄 Rapport complet', ja: '📄 フルレポート', ru: '📄 Полный отчёт',
    };

    const _AI_DISABLED_MSG = {
        en: 'AI Assistant is disabled. Enable it in Settings.',
        vi: 'Trợ lý AI đã bị tắt. Hãy bật lại trong Cài đặt.',
        zh: 'AI 助手已禁用，请在设置中启用。',
        fr: 'L\'assistant IA est désactivé. Activez-le dans les Paramètres.',
        ja: 'AIアシスタントが無効です。設定で有効にしてください。',
        ru: 'Помощник ИИ отключён. Включите его в настройках.',
    };

    const _HELP_HEADER = {
        en: '**Available commands**', vi: '**Các lệnh có sẵn**', zh: '**可用命令**',
        fr: '**Commandes disponibles**', ja: '**使用可能なコマンド**', ru: '**Доступные команды**',
    };

    const _STATUS_HEADER = {
        en: '**App status**', vi: '**Trạng thái ứng dụng**', zh: '**应用状态**',
        fr: '**État de l\'application**', ja: '**アプリの状態**', ru: '**Состояние приложения**',
    };

    const _STATUS_LABELS = {
        en: { mode: 'mode', app_started: 'app started', data_loaded: 'data loaded', cal_mode: 'cal mode', model: 'model', ollama: 'ollama' },
        vi: { mode: 'chế độ', app_started: 'đã khởi động', data_loaded: 'dữ liệu đã tải', cal_mode: 'chế độ cal', model: 'mô hình', ollama: 'ollama' },
        zh: { mode: '模式', app_started: '已启动', data_loaded: '已加载数据', cal_mode: '校准模式', model: '模型', ollama: 'ollama' },
        fr: { mode: 'mode', app_started: 'démarré', data_loaded: 'données chargées', cal_mode: 'mode cal', model: 'modèle', ollama: 'ollama' },
        ja: { mode: 'モード', app_started: 'アプリ起動', data_loaded: 'データ読込', cal_mode: '校正モード', model: 'モデル', ollama: 'ollama' },
        ru: { mode: 'режим', app_started: 'запущено', data_loaded: 'данные загружены', cal_mode: 'режим кал', model: 'модель', ollama: 'ollama' },
    };

    const _STATUS_BAR_MSGS = {
        ollama_offline: {
            en: '⚠ Ollama offline — open Settings to install',
            vi: '⚠ Ollama ngoại tuyến — mở Cài đặt để cài đặt',
            zh: '⚠ Ollama 离线 — 打开设置安装',
            fr: '⚠ Ollama hors ligne — ouvrez les Paramètres pour installer',
            ja: '⚠ Ollama オフライン — 設定を開いてインストール',
            ru: '⚠ Ollama не работает — откройте Настройки для установки',
        },
        model_missing: {
            en: '⚠ Model not downloaded — open Settings to download',
            vi: '⚠ Mô hình chưa tải — mở Cài đặt để tải xuống',
            zh: '⚠ 模型未下载 — 打开设置下载',
            fr: '⚠ Modèle non téléchargé — ouvrez les Paramètres pour télécharger',
            ja: '⚠ モデル未ダウンロード — 設定を開いてダウンロード',
            ru: '⚠ Модель не загружена — откройте Настройки для загрузки',
        },
    };

    // Natural-language phrases that mean "redo the last thing"
    const _REDO_VOCAB = new Set([
        // English
        'redo', 'redo that', 'redo this', 'redo last', 'redo it',
        'do it again', 'do that again', 'do again',
        'show that again', 'show it again', 'show again', 'show me again',
        'show the steps again', 'show steps again',
        'repeat', 'repeat that', 'repeat this', 'repeat last', 'repeat it',
        'repeat the guide', 'repeat guide',
        'replay', 'replay that', 'replay guide', 'replay the guide',
        'run again', 'run it again', 'run that again',
        'go through that again', 'go over that again', 'go again',
        'once more', 'one more time', 'one more',
        'try again', 'try that again', 'retry', 'retry that',
        'restart guide', 'relaunch guide', 'start guide again', 'launch guide again',
        'rerun', 'rerun that',
        // Vietnamese
        'làm lại', 'làm lại đi', 'thử lại', 'lặp lại', 'chạy lại',
        'hiển thị lại', 'xem lại', 'hướng dẫn lại',
        // Chinese
        '再来一次', '重做', '再试一次', '重试', '再次运行', '再显示', '重新开始指南',
        // French
        'recommencer', 'refaire', 'répéter', 'réessayer', 'encore une fois', 'relancer',
        // Japanese
        'もう一度', 'やり直し', 'やり直す', 'もう一度やって', 'もう一回',
        // Russian
        'повтори', 'повторить', 'ещё раз', 'снова', 'заново', 'переделать',
    ]);

    const _picker = { visible: false, idx: 0, list: [] };

    // ── Tab title notification ────────────────────────────────────────────────

    let _origTitle = document.title;
    let _tabBlinkTimer = null;
    let _tabHasNotification = false;

    function _notifyTabTitle() {
        if (_tabHasNotification) return;
        _tabHasNotification = true;
        _origTitle = document.title;
        let alt = false;
        document.title = '• New reply — ' + _origTitle;
        _tabBlinkTimer = setInterval(() => {
            document.title = alt ? '• New reply — ' + _origTitle : _origTitle;
            alt = !alt;
        }, 1200);
    }

    function _clearTabNotification() {
        if (!_tabHasNotification) return;
        _tabHasNotification = false;
        clearInterval(_tabBlinkTimer);
        _tabBlinkTimer = null;
        document.title = _origTitle;
    }

    // ── State ────────────────────────────────────────────────────────────────

    const AI = {
        open: false,
        settingsOpen: false,
        messages: [],          // {role, content}[]  — conversation history
        settings: null,        // loaded from /ai/settings
        status: null,          // loaded from /ai/status
        guides: [],            // loaded from /ai/guides — keyed by id for O(1) lookup
        activeLang: null,      // currently active language (cycles through preferred_languages)
        pullTimer: null,
        currentAbort: null,    // AbortController for the active /ai/chat fetch
        lastAction: null,      // { type: 'custom_steps'|'workflow'|'llm', steps?, workflow?, query? }
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

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && AI.open) _clearTabNotification();
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
                if (e.key === 'ArrowUp') { e.preventDefault(); _pickerMove(-1); return; }
                if (e.key === 'ArrowDown') { e.preventDefault(); _pickerMove(1); return; }
                if (e.key === 'Escape') { e.preventDefault(); _pickerHide(); return; }
                if (e.key === 'Tab') { e.preventDefault(); _pickerConfirm(); return; }
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

        _loadGuides();
    }

    function _loadGuides() {
        const lang = AI.activeLang || 'en';
        fetch(`/ai/guides?lang=${encodeURIComponent(lang)}`)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    AI.guides = {};
                    (data.examples || []).forEach(e => { if (e.id) AI.guides[e.id] = e; });
                }
            })
            .catch(() => { });
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
        const lang = AI.activeLang || 'en';
        if (!AI.status.ollama_running) {
            const msg = _STATUS_BAR_MSGS.ollama_offline[lang] || _STATUS_BAR_MSGS.ollama_offline.en;
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-warn">${_esc(msg)}</span>`;
        } else if (!AI.status.model_available) {
            const msg = _STATUS_BAR_MSGS.model_missing[lang] || _STATUS_BAR_MSGS.model_missing.en;
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-warn">${_esc(msg)}</span>`;
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

    function _localizeSteps(steps) {
        const lang = AI.activeLang || 'en';
        if (lang === 'en') return steps;
        return steps.map(s => {
            const locDesc = s.descriptions && s.descriptions[lang];
            return locDesc ? { ...s, description: locDesc } : s;
        });
    }

    function _launchGuide(workflow) {
        AI.lastAction = { type: 'workflow', workflow };
        if (typeof window.userGuide === 'undefined') return;
        OkapiAI.close();
        setTimeout(() => window.userGuide.startWorkflow(workflow), 400);
    }

    function _launchCustomSteps(steps) {
        if (!_getUiContext().app_started) steps = [_GET_STARTED_STEP, ...steps];
        steps = _localizeSteps(steps);
        AI.lastAction = { type: 'custom_steps', steps };
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
            script_running: !!appState.scriptRunning,
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
        const active = el.querySelector('.okapi-ai-cmd-active');
        if (active) active.scrollIntoView({ block: 'nearest' });
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
        input.value = '';

        if (cmd.action === 'clear') {
            OkapiAI.clearHistory();
            return;
        }

        if (cmd.action === 'help') {
            const lang = AI.activeLang || 'en';
            const lines = SLASH_COMMANDS.map(c => `\`${c.cmd}\` — ${c.desc}`).join('\n');
            _addMsg('assistant', (_HELP_HEADER[lang] || _HELP_HEADER.en) + '\n\n' + lines);
            return;
        }

        if (cmd.action === 'status') {
            const lang = AI.activeLang || 'en';
            const ctx = _getUiContext();
            const lbl = _STATUS_LABELS[lang] || _STATUS_LABELS.en;
            const yesNo = (v) => v ? (lang === 'vi' ? 'có' : lang === 'zh' ? '是' : lang === 'fr' ? 'oui' : lang === 'ja' ? 'はい' : lang === 'ru' ? 'да' : 'yes') : (lang === 'vi' ? 'không' : lang === 'zh' ? '否' : lang === 'fr' ? 'non' : lang === 'ja' ? 'いいえ' : lang === 'ru' ? 'нет' : 'no');
            const onOff = (v) => v ? (lang === 'vi' ? 'đang chạy' : lang === 'zh' ? '运行中' : lang === 'fr' ? 'actif' : lang === 'ja' ? '実行中' : lang === 'ru' ? 'работает' : 'running') : (lang === 'vi' ? 'ngoại tuyến' : lang === 'zh' ? '离线' : lang === 'fr' ? 'hors ligne' : lang === 'ja' ? 'オフライン' : lang === 'ru' ? 'не работает' : 'offline');
            const lines = [
                `\`${lbl.mode}\` ${ctx.mode || '—'}`,
                `\`${lbl.app_started}\` ${yesNo(ctx.app_started)}`,
                `\`${lbl.data_loaded}\` ${yesNo(ctx.data_loaded)}`,
                `\`${lbl.cal_mode}\` ${ctx.cal_mode || '—'}`,
                `\`${lbl.model}\` ${(AI.settings && AI.settings.model) || '—'}`,
                `\`${lbl.ollama}\` ${onOff(AI.status && AI.status.ollama_running)}`,
            ].join('\n');
            _addMsg('assistant', (_STATUS_HEADER[lang] || _STATUS_HEADER.en) + '\n\n' + lines);
            return;
        }

        if (cmd.action === 'guide') {
            _addMsg('user', cmd.cmd);
            _runGuideById(cmd.guide_id);
            return;
        }

        if (cmd.action === 'concentration') {
            _addMsg('user', cmd.cmd);
            _runConcentrationGuide();
            return;
        }

        if (cmd.action === 'excel') {
            _addMsg('user', cmd.cmd);
            _runExcelGuide();
            return;
        }

        if (cmd.action === 'live_view') {
            _addMsg('user', cmd.cmd);
            _runLiveViewGuide();
            return;
        }

        if (cmd.action === 'report') {
            _addMsg('user', cmd.cmd);
            _runReportChoice();
            return;
        }

        if (cmd.action === 'redo') {
            _runRedoAction();
            return;
        }
    }

    // Resolve and launch a guide by training-example ID, applying UI context locally
    function _runGuideById(guide_id) {
        const example = AI.guides[guide_id];
        if (!example) {
            const lang = AI.activeLang || 'en';
            const fn = _GUIDE_NOT_FOUND[lang] || _GUIDE_NOT_FOUND.en;
            _addMsg('assistant', fn(_esc(guide_id)));
            return;
        }
        const ctx = _getUiContext();
        let steps = [...example.steps];
        if (example.requires_data_loaded && !ctx.data_loaded) {
            steps = [_FILE_SELECT_STEP, ...steps];
        }
        const lang = AI.activeLang || 'en';
        _addMsg('assistant', _GUIDE_LAUNCHED[lang] || _GUIDE_LAUNCHED.en);
        _launchCustomSteps(steps);
    }

    // Pick the correct concentration guide based on current mode
    function _runConcentrationGuide() {
        const mode = _getUiContext().mode;
        let guide_id;
        if (mode === 'kinetics') guide_id = 'concentration_calc_kinetics';
        else if (mode === 'point') guide_id = 'concentration_calc_point';
        else if (mode === 'calibrate' || mode === 'report') guide_id = 'concentration_calc_wrong_mode';
        else guide_id = 'concentration_calc_generic';
        _runGuideById(guide_id);
    }

    // Route Excel export guide based on current mode
    function _runExcelGuide() {
        const mode = _getUiContext().mode;
        _runGuideById(mode === 'report' ? 'export_excel_in_report' : 'export_excel_nav');
    }

    // Route live-view guide based on whether a measurement is currently running
    function _runLiveViewGuide() {
        const ctx = _getUiContext();
        _runGuideById(ctx.script_running ? 'live_view_active' : 'live_view_inactive');
    }

    function _runRedoAction() {
        const last = AI.lastAction;
        const lang = AI.activeLang || 'en';
        if (!last) {
            _addMsg('assistant', _NOTHING_TO_REDO[lang] || _NOTHING_TO_REDO.en);
            return;
        }
        if (last.type === 'custom_steps') {
            _addMsg('assistant', _GUIDE_LAUNCHED[lang] || _GUIDE_LAUNCHED.en);
            _launchCustomSteps(last.steps);
        } else if (last.type === 'workflow') {
            _addMsg('assistant', _GUIDE_LAUNCHED[lang] || _GUIDE_LAUNCHED.en);
            _launchGuide(last.workflow);
        } else if (last.type === 'llm') {
            // Remove last assistant reply from history so it isn't sent twice
            if (AI.messages.length && AI.messages[AI.messages.length - 1].role === 'assistant') {
                AI.messages.pop();
            }
            const input = document.getElementById('okapi-ai-input');
            if (input) { input.value = last.query; OkapiAI.send(); }
        }
    }

    // Show an inline quick/full choice — user clicks a button, guide launches immediately
    function _runReportChoice() {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return;
        const lang = AI.activeLang || 'en';
        const div = document.createElement('div');
        div.className = 'okapi-ai-msg okapi-ai-msg-assistant';
        div.innerHTML =
            _esc(_REPORT_CHOICE_PROMPT[lang] || _REPORT_CHOICE_PROMPT.en) +
            '<div class="okapi-ai-choice-btns">' +
            `<button class="okapi-ai-choice-btn" data-type="quick">${_esc(_REPORT_BTN_QUICK[lang] || _REPORT_BTN_QUICK.en)}</button>` +
            `<button class="okapi-ai-choice-btn" data-type="full">${_esc(_REPORT_BTN_FULL[lang] || _REPORT_BTN_FULL.en)}</button>` +
            '</div>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;

        div.querySelectorAll('.okapi-ai-choice-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                div.querySelectorAll('.okapi-ai-choice-btn').forEach(b => b.disabled = true);
                const mode = _getUiContext().mode;
                let guide_id;
                if (btn.dataset.type === 'quick') {
                    guide_id = (mode === 'report') ? 'report_quick_from_report' : 'report_quick';
                } else {
                    guide_id = (mode === 'report') ? 'report_full_in_report' : 'report_full_from_data';
                }
                _runGuideById(guide_id);
            });
        });
    }

    // ── Public API ────────────────────────────────────────────────────────────

    window.OkapiAI = {

        open_() {
            AI.open = true;
            _clearTabNotification();
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
            _loadGuides();
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

        stopGeneration() {
            if (AI.currentAbort) {
                AI.currentAbort.abort();
                AI.currentAbort = null;
            }
        },

        send() {
            const input = document.getElementById('okapi-ai-input');
            const text = (input.value || '').trim();
            if (!text) return;

            if (!AI.settings || !AI.settings.enabled) {
                const lang = AI.activeLang || 'en';
                _addSystemMsg(_AI_DISABLED_MSG[lang] || _AI_DISABLED_MSG.en);
                return;
            }

            // Redo intent — resolve locally, don't push to conversation history
            if (_REDO_VOCAB.has(text.toLowerCase().replace(/[!?.،。]+$/, '').trim())) {
                input.value = '';
                _addMsg('user', text);
                _runRedoAction();
                return;
            }

            AI.lastAction = { type: 'llm', query: text };

            input.value = '';
            _addMsg('user', text);
            AI.messages.push({ role: 'user', content: text });

            // Trim history to last 10 messages to keep prompts fast
            const historyToSend = AI.messages.length > 10
                ? AI.messages.slice(-10)
                : AI.messages.slice();

            const msgDiv = _addStreamingMsg();
            const sendBtn = document.getElementById('okapi-ai-send-btn');
            input.disabled = true;
            if (sendBtn) {
                sendBtn.innerHTML = '&#9632;';
                sendBtn.title = 'Stop generation';
                sendBtn.classList.add('okapi-ai-stop-mode');
                sendBtn.onclick = () => OkapiAI.stopGeneration();
            }

            const lang = AI.activeLang || 'en';
            const model = AI.settings.model || 'qwen2.5:7b';
            const controller = new AbortController();
            AI.currentAbort = controller;

            (async () => {
                let fullReply = '';
                try {
                    const resp = await fetch('/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ messages: historyToSend, language: lang, model, ui_context: _getUiContext() }),
                        signal: controller.signal,
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

                    if (fullReply) {
                        AI.messages.push({ role: 'assistant', content: fullReply });
                        _finalizeStreamingMsg(msgDiv, fullReply, null);
                        if (document.hidden || !AI.open) _notifyTabTitle();
                    } else {
                        const fallback = _EMPTY_REPLY[AI.activeLang] || _EMPTY_REPLY.en;
                        _finalizeStreamingMsg(msgDiv, null, fallback);
                    }

                } catch (err) {
                    if (err.name === 'AbortError') {
                        if (fullReply) {
                            _finalizeStreamingMsg(msgDiv, fullReply, null);
                        } else {
                            msgDiv?.remove();
                        }
                    } else {
                        _finalizeStreamingMsg(msgDiv, null, '⚠ Network error: ' + err.message);
                    }
                } finally {
                    AI.currentAbort = null;
                    if (sendBtn) {
                        sendBtn.innerHTML = '&#10148;';
                        sendBtn.title = 'Send message';
                        sendBtn.classList.remove('okapi-ai-stop-mode');
                        sendBtn.onclick = () => OkapiAI.send();
                        sendBtn.disabled = false;
                    }
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
