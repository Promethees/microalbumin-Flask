/**
 * OKAPI Assistant — floating AI chat widget (online / cloud version)
 * Connects to /ai/* routes which proxy to Groq API.
 */

(function () {
    'use strict';

    // ── Slash commands ────────────────────────────────────────────────────────

    const SLASH_COMMANDS = [
        { cmd: '/help', desc: 'List all available slash commands', action: 'help' },
        { cmd: '/guide', desc: 'Launch a full step-by-step app walkthrough', action: 'guide', guide_id: 'app_introduction' },
        { cmd: '/measurement', desc: 'Guide to Kinetics mode analysis', action: 'guide', guide_id: 'measurement_guide' },
        { cmd: '/kinetics', desc: 'Navigate to Kinetics (time-series) measurement mode', action: 'guide', guide_id: 'nav_kinetics_mode' },
        { cmd: '/point', desc: 'Navigate to Point (endpoint) measurement mode', action: 'guide', guide_id: 'nav_point_mode' },
        { cmd: '/calibrate', desc: 'Create a calibration standard curve (full workflow)', action: 'guide', guide_id: 'create_calibration_curve_workflow' },
        { cmd: '/concentration', desc: 'Calculate sample concentration from calibration data', action: 'concentration' },
        { cmd: '/merge', desc: 'Combine multiple CSV files into a single multi-source file', action: 'guide', guide_id: 'merge_files' },
        { cmd: '/upload', desc: 'Upload a CSV data file from your device', action: 'guide', guide_id: 'upload_file' },
        { cmd: '/range', desc: 'Set the analysis time window (start, end, unit)', action: 'guide', guide_id: 'set_analysis_range' },
        { cmd: '/normalize', desc: 'Toggle baseline subtraction to remove background absorbance', action: 'guide', guide_id: 'normalize_data' },
        { cmd: '/split', desc: 'Display each measurement source as a separate chart', action: 'guide', guide_id: 'split_sources' },
        { cmd: '/window', desc: 'Configure sliding window size for max-rate regression', action: 'guide', guide_id: 'window_size' },
        { cmd: '/quantity', desc: 'Select the kinetics quantity for calibration (maxRate, Slope, Sat)', action: 'guide', guide_id: 'select_quantity' },
        { cmd: '/threshold', desc: 'Set the R² threshold for calibration curve fitting', action: 'guide', guide_id: 'rsquared_threshold' },
        { cmd: '/time-point', desc: 'Select the time point for point-mode calibration analysis', action: 'guide', guide_id: 'select_time_point' },
        { cmd: '/export', desc: 'Export current data to CSV', action: 'guide', guide_id: 'export_data' },
        { cmd: '/excel', desc: 'Export report items as a formatted Excel workbook', action: 'excel' },
        { cmd: '/report', desc: 'Create a quick or full HTML report', action: 'report' },
        { cmd: '/layout', desc: 'Configure report layout (title, watermark, logo, split sheets)', action: 'guide', guide_id: 'report_layout_options' },
        { cmd: '/drive', desc: 'Connect and sync data with Google Drive', action: 'guide', guide_id: 'google_drive_connect' },
        { cmd: '/popups', desc: 'Disable or enable confirmation popups', action: 'guide', guide_id: 'disable_popups' },
        { cmd: '/filter', desc: 'Filter the file list by number of measurement sources', action: 'guide', guide_id: 'filter_sources' },
        { cmd: '/status', desc: 'Show current app state (mode, data)', action: 'status' },
        { cmd: '/redo', desc: 'Replay the last guide or retry the last question', action: 'redo' },
        { cmd: '/clear', desc: 'Clear the conversation history', action: 'clear' },
    ];

    // File-select prepend step
    const _FILE_SELECT_STEP = {
        target: '#file-selection',
        title: window.t('dlg.select_file_first', 'Select a File First'),
        description: 'No data file is loaded yet. Click here to select a CSV data file before proceeding.',
        descriptions: {
            vi: 'Chưa có tệp dữ liệu nào được tải. Nhấp vào đây để chọn tệp CSV trước khi tiếp tục.',
            zh: '尚未加载数据文件。请点击此处选择 CSV 数据文件后再继续。',
            fr: 'Aucun fichier de données n\'est chargé. Cliquez ici pour sélectionner un fichier CSV avant de continuer.',
            ja: 'データファイルがまだ読み込まれていません。続行する前にここをクリックして CSV ファイルを選択してください。',
            ru: 'Файл данных ещё не загружен. Нажмите здесь, чтобы выбрать CSV-файл перед продолжением.',
            ko: '데이터 파일이 아직 로드되지 않았습니다. 계속하기 전에 여기를 클릭하여 CSV 데이터 파일을 선택하세요.',
        },
        position: 'left',
        skipInteraction: false,
    };

    const _GUIDE_LAUNCHED = {
        en: 'Guide launched — follow the highlighted steps.',
        vi: 'Đã khởi động hướng dẫn — làm theo các bước được tô sáng.',
        zh: '指南已启动 — 请按照高亮步骤操作。',
        fr: 'Guide lancé — suivez les étapes mises en surbrillance.',
        ja: 'ガイドを起動しました — ハイライトされた手順に従ってください。',
        ru: 'Руководство запущено — следуйте выделенным шагам.',
        ko: '가이드를 시작했습니다 — 강조 표시된 단계를 따르세요.',
    };

    const _EMPTY_REPLY = {
        en: "I couldn't generate a response. Please try rephrasing your question.",
        vi: 'Tôi không thể tạo phản hồi. Hãy thử diễn đạt lại câu hỏi của bạn.',
        zh: '我无法生成回复，请尝试换一种方式提问。',
        fr: "Je n'ai pas pu générer de réponse. Essayez de reformuler votre question.",
        ja: '回答を生成できませんでした。質問を言い換えてみてください。',
        ru: 'Не удалось сформировать ответ. Попробуйте перефразировать вопрос.',
        ko: '응답을 생성하지 못했습니다. 질문을 다시 표현해 보세요.',
    };

    const _NOTHING_TO_REDO = {
        en: 'Nothing to redo yet — send a message or run a command first.',
        vi: 'Chưa có gì để làm lại — hãy gửi tin nhắn hoặc chạy lệnh trước.',
        zh: '暂无可重做的操作 — 请先发送消息或运行命令。',
        fr: 'Rien à refaire pour l\'instant — envoyez d\'abord un message ou exécutez une commande.',
        ja: 'やり直せるものがまだありません — まずメッセージを送るかコマンドを実行してください。',
        ru: 'Нечего повторять — сначала отправьте сообщение или выполните команду.',
        ko: '아직 다시 실행할 항목이 없습니다 — 먼저 메시지를 보내거나 명령을 실행하세요.',
    };

    const _REDO_NOTE = {
        en: '↺ Retrying last question…',
        vi: '↺ Thử lại câu hỏi trước…',
        zh: '↺ 重新发送上一条问题…',
        fr: '↺ Nouvel essai pour la dernière question…',
        ja: '↺ 最後の質問を再試行中…',
        ru: '↺ Повтор последнего вопроса…',
        ko: '↺ 마지막 질문을 다시 시도하는 중…',
    };

    const _GUIDE_NOT_FOUND = {
        en: (id) => `Guide **${id}** not found. Try again after the app loads.`,
        vi: (id) => `Không tìm thấy hướng dẫn **${id}**. Vui lòng thử lại sau khi ứng dụng tải xong.`,
        zh: (id) => `未找到指南 **${id}**。请在应用加载完成后重试。`,
        fr: (id) => `Guide **${id}** introuvable. Réessayez après le chargement de l'application.`,
        ja: (id) => `ガイド **${id}** が見つかりません。アプリの読み込み後に再試行してください。`,
        ru: (id) => `Руководство **${id}** не найдено. Повторите попытку после загрузки приложения.`,
        ko: (id) => `가이드 **${id}** 을(를) 찾을 수 없습니다. 앱이 로드된 후 다시 시도하세요.`,
    };

    const _REPORT_CHOICE_PROMPT = {
        en: 'Which type of report would you like to create?',
        vi: 'Bạn muốn tạo loại báo cáo nào?',
        zh: '您想要创建哪种类型的报告？',
        fr: 'Quel type de rapport souhaitez-vous créer ?',
        ja: 'どのタイプのレポートを作成しますか？',
        ru: 'Какой тип отчёта вы хотите создать?',
        ko: '어떤 유형의 보고서를 만드시겠습니까?',
    };

    const _REPORT_BTN_QUICK = {
        en: '⚡ Quick Report', vi: '⚡ Báo cáo nhanh', zh: '⚡ 快速报告',
        fr: '⚡ Rapport rapide', ja: '⚡ クイックレポート', ru: '⚡ Быстрый отчёт',
        ko: '⚡ 빠른 보고서',
    };

    const _REPORT_BTN_FULL = {
        en: '📄 Full Report', vi: '📄 Báo cáo đầy đủ', zh: '📄 完整报告',
        fr: '📄 Rapport complet', ja: '📄 フルレポート', ru: '📄 Полный отчёт',
        ko: '📄 전체 보고서',
    };

    const _AI_UNAVAILABLE_MSG = {
        en: '⚠ AI Assistant is not configured on this server.',
        vi: '⚠ Trợ lý AI chưa được cấu hình trên máy chủ này.',
        zh: '⚠ AI 助手未在此服务器上配置。',
        fr: '⚠ L\'assistant IA n\'est pas configuré sur ce serveur.',
        ja: '⚠ AIアシスタントはこのサーバーで設定されていません。',
        ru: '⚠ Помощник ИИ не настроен на этом сервере.',
        ko: '⚠ 이 서버에는 AI 어시스턴트가 구성되어 있지 않습니다.',
    };

    const _HELP_HEADER = {
        en: '**Available commands**', vi: '**Các lệnh có sẵn**', zh: '**可用命令**',
        fr: '**Commandes disponibles**', ja: '**使用可能なコマンド**', ru: '**Доступные команды**',
        ko: '**사용 가능한 명령**',
    };

    const _STATUS_HEADER = {
        en: '**App status**', vi: '**Trạng thái ứng dụng**', zh: '**应用状态**',
        fr: '**État de l\'application**', ja: '**アプリの状態**', ru: '**Состояние приложения**',
        ko: '**앱 상태**',
    };

    const _STATUS_LABELS = {
        en: { mode: 'mode', app_started: 'app started', data_loaded: 'data loaded', cal_mode: 'cal mode' },
        vi: { mode: 'chế độ', app_started: 'đã khởi động', data_loaded: 'dữ liệu đã tải', cal_mode: 'chế độ cal' },
        zh: { mode: '模式', app_started: '已启动', data_loaded: '已加载数据', cal_mode: '校准模式' },
        fr: { mode: 'mode', app_started: 'démarré', data_loaded: 'données chargées', cal_mode: 'mode cal' },
        ja: { mode: 'モード', app_started: 'アプリ起動', data_loaded: 'データ読込', cal_mode: '校正モード' },
        ru: { mode: 'режим', app_started: 'запущено', data_loaded: 'данные загружены', cal_mode: 'режим кал' },
        ko: { mode: '모드', app_started: '앱 시작됨', data_loaded: '데이터 로드됨', cal_mode: 'cal 모드' },
    };

    // Natural-language phrases that mean "redo the last thing"
    const _REDO_VOCAB = new Set([
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
        'làm lại', 'làm lại đi', 'thử lại', 'lặp lại', 'chạy lại',
        'hiển thị lại', 'xem lại', 'hướng dẫn lại',
        '再来一次', '重做', '再试一次', '重试', '再次运行', '再显示', '重新开始指南',
        'recommencer', 'refaire', 'répéter', 'réessayer', 'encore une fois', 'relancer',
        'もう一度', 'やり直し', 'やり直す', 'もう一度やって', 'もう一回',
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
        messages: [],
        settings: null,
        status: null,
        guides: [],
        activeLang: null,
        currentAbort: null,
        lastAction: null,
        // Machine-readable conversation state echoed back to /ai/chat on the NEXT
        // turn (currently only 'report_type', set by the quick/full report
        // clarification — work-list A8, same contract as main's ai-chat.js).
        // Armed only by the `pending` SSE event; consumed at the head of every
        // user turn by _consumePending(); re-armed by _rearmPending() only when
        // the turn never reached the server, so a retry still resolves.
        pending: '',
        LANG_LABELS: {
            en: 'EN', vi: 'VI', zh: '中', fr: 'FR', ja: '日', ru: 'RU', ko: '한'
        },
        LANG_NAMES: {
            en: 'English', vi: 'Tiếng Việt', zh: '中文',
            fr: 'Français', ja: '日本語', ru: 'Русский', ko: '한국어'
        },
        LANG_DISPLAY: {
            en: 'English', vi: 'Tiếng Việt', zh: '中文 (简体)',
            fr: 'Français', ja: '日本語', ru: 'Русский', ko: '한국어'
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
        fab.setAttribute('data-hint', 'OKAPI Assistant');
        fab.innerHTML = `<span class="okapi-ai-label">AI Assistant</span><span class="okapi-ai-icon">&#129302;</span>`;
        fab.addEventListener('click', _togglePanel);
        document.body.appendChild(fab);

        const panel = document.createElement('div');
        panel.id = 'okapi-ai-panel';
        panel.innerHTML = `
<div id="okapi-ai-header">
  <span id="okapi-ai-title">&#129302; OKAPI Assistant</span>
  <div id="okapi-ai-header-btns">
    <div id="okapi-ai-lang-select">
      <button id="okapi-ai-lang-btn" data-hint="Change language" onclick="OkapiAI.toggleLangMenu()"></button>
      <div id="okapi-ai-lang-menu" class="okapi-hidden">
        <button class="okapi-ai-lang-opt" data-lang="en">English</button>
        <button class="okapi-ai-lang-opt" data-lang="vi">Ti&#7871;ng Vi&#7879;t</button>
        <button class="okapi-ai-lang-opt" data-lang="zh">&#20013;&#25991; (&#31616;&#20307;)</button>
        <button class="okapi-ai-lang-opt" data-lang="fr">Fran&#231;ais</button>
        <button class="okapi-ai-lang-opt" data-lang="ja">&#26085;&#26412;&#35486;</button>
        <button class="okapi-ai-lang-opt" data-lang="ru">&#1056;&#1091;&#1089;&#1089;&#1082;&#1080;&#1081;</button>
        <button class="okapi-ai-lang-opt" data-lang="ko">&#54620;&#44397;&#50612;</button>
      </div>
    </div>
    <button id="okapi-ai-close-btn" data-hint="Close" onclick="OkapiAI.close()">&#10005;</button>
  </div>
</div>

<!-- Chat view -->
<div id="okapi-ai-body">
  <div id="okapi-ai-messages"></div>
  <div id="okapi-ai-status-bar"></div>
  <div id="okapi-ai-cmd-picker" class="okapi-hidden"></div>
  <div id="okapi-ai-input-row">
    <textarea id="okapi-ai-input" rows="2" placeholder="Ask anything… (type / for commands)"></textarea>
    <button id="okapi-ai-send-btn" onclick="OkapiAI.send()">&#10148;</button>
  </div>
</div>`;
        document.body.appendChild(panel);

        // Move lang menu to <body> so position:fixed escapes the panel's transform
        // (any non-none transform creates a new containing block for fixed descendants)
        const langMenu = panel.querySelector('#okapi-ai-lang-menu');
        if (langMenu) document.body.appendChild(langMenu);

        document.querySelectorAll('.okapi-ai-lang-opt').forEach(btn => {
            btn.addEventListener('click', () => OkapiAI.setLang(btn.dataset.lang));
        });

        document.addEventListener('click', (e) => {
            const langBtn = document.getElementById('okapi-ai-lang-btn');
            const menu = document.getElementById('okapi-ai-lang-menu');
            if (menu && langBtn && !langBtn.contains(e.target) && !menu.contains(e.target)) {
                _langMenuHide();
            }
        });

        const inputEl = document.getElementById('okapi-ai-input');

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

        inputEl.addEventListener('input', () => {
            const val = inputEl.value;
            if (val.startsWith('/')) _pickerShow(val.slice(1));
            else _pickerHide();
        });

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
                const pl = AI.settings.preferred_languages
                    || (AI.settings.preferred_language ? [AI.settings.preferred_language] : null)
                    || ['en'];
                AI.activeLang = pl[0] || 'en';
                _updateLangBtn();
                _showWelcomeIfNeeded();
            })
            .catch(() => { });

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
            en: '👋 Hi! I\'m your OKAPI Assistant. Ask me about your data, calibration, or app workflow.',
            vi: '👋 Xin chào! Tôi là OKAPI Assistant. Hãy hỏi tôi về dữ liệu, hiệu chuẩn hoặc quy trình làm việc.',
            zh: '👋 您好！我是 OKAPI Assistant。请向我询问有关数据、校准或工作流程的问题。',
            fr: '👋 Bonjour ! Je suis votre assistant OKAPI. Posez-moi des questions sur vos données, la calibration ou votre flux de travail.',
            ja: '👋 こんにちは！OKAPIアシスタントです。データ、キャリブレーション、ワークフローについてお気軽にご質問ください。',
            ru: '👋 Привет! Я OKAPI Assistant. Задавайте вопросы о данных, калибровке или рабочем процессе.',
            ko: '👋 안녕하세요! 저는 OKAPI Assistant입니다. 데이터, 캘리브레이션, 앱 워크플로에 대해 물어보세요.',
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
        btn.setAttribute('data-hint', AI.LANG_NAMES[lang] || lang);
    }

    // ── Status bar ────────────────────────────────────────────────────────────

    function _updateStatusBar() {
        const bar = document.getElementById('okapi-ai-status-bar');
        if (!bar || !AI.status) return;
        if (!AI.status.api_ready) {
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-warn">&#9888; AI not configured</span>`;
        } else {
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-ok">&#10003; AI ready</span>`;
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
        div.innerHTML = _renderMarkdown(content);
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
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
        let t = _esc(text);
        t = t.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
        t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        t = t.replace(/^[•·]\s+(.+)$/gm, '<li>$1</li>');
        t = t.replace(/(<li>[\s\S]*?<\/li>(\s*<li>[\s\S]*?<\/li>)*)/g, '<ul>$1</ul>');
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

    // ── Language menu ─────────────────────────────────────────────────────────

    function _langMenuHide() {
        const menu = document.getElementById('okapi-ai-lang-menu');
        if (menu) menu.classList.add('okapi-hidden');
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
        steps = _localizeSteps(steps);
        AI.lastAction = { type: 'custom_steps', steps };
        if (typeof window.userGuide === 'undefined') return;
        OkapiAI.close();
        setTimeout(() => window.userGuide.startCustomSteps(steps), 400);
    }

    // Text written into the conversation follows the chat's own language picker
    // (AI.activeLang), from the ai.msg.* / ai.err.* slice of every catalog that
    // index.html injects as window.AI_CHAT_STRINGS. Falls back to English.
    function _trChat(key, fallback) {
        const all = window.AI_CHAT_STRINGS || null;
        const cat = all ? all[AI.activeLang || 'en'] : null;
        return (cat && cat[key]) || fallback;
    }

    // Take the pending marker for this turn and disarm it (the only consumer).
    function _consumePending() {
        const pending = AI.pending || '';
        AI.pending = '';
        return pending;
    }

    // Put the marker back when the turn never reached the server.
    function _rearmPending(pending) {
        if (pending && !AI.pending) AI.pending = pending;
    }

    function _getUiContext(pending) {
        const appState = window.AppState || {};
        const mainContent = document.getElementById('main-content');
        const dataDisplay = document.getElementById('data-display-section');
        const calMode = document.getElementById('cal-mode-select');
        return {
            mode: appState.currentMeasurementMode || 'unknown',
            app_started: !!(mainContent && !mainContent.classList.contains('hidden')),
            data_loaded: !!(dataDisplay && !dataDisplay.classList.contains('hidden')),
            cal_mode: calMode ? (calMode.getAttribute('data-value') || '') : '',
            // ALWAYS present (empty when unarmed): the server reads its absence
            // as "client older than the marker" and only then falls back to
            // matching the clarification prose.
            pending: pending || '',
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
        // A slash command ends any outstanding clarification.
        _consumePending();

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
            const yesNo = (v) => v
                ? (lang === 'vi' ? 'có' : lang === 'zh' ? '是' : lang === 'fr' ? 'oui' : lang === 'ja' ? 'はい' : lang === 'ru' ? 'да' : lang === 'ko' ? '예' : 'yes')
                : (lang === 'vi' ? 'không' : lang === 'zh' ? '否' : lang === 'fr' ? 'non' : lang === 'ja' ? 'いいえ' : lang === 'ru' ? 'нет' : lang === 'ko' ? '아니오' : 'no');
            const lines = [
                `\`${lbl.mode}\` ${ctx.mode || '—'}`,
                `\`${lbl.app_started}\` ${yesNo(ctx.app_started)}`,
                `\`${lbl.data_loaded}\` ${yesNo(ctx.data_loaded)}`,
                `\`${lbl.cal_mode}\` ${ctx.cal_mode || '—'}`,
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

        if (cmd.action === 'report') {
            _addMsg('user', cmd.cmd);
            AI.lastAction = { type: 'report_choice' };
            _runReportChoice();
            return;
        }

        if (cmd.action === 'redo') {
            _runRedoAction();
            return;
        }
    }

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

    function _runConcentrationGuide() {
        const mode = _getUiContext().mode;
        let guide_id;
        if (mode === 'kinetics') guide_id = 'concentration_calc_kinetics';
        else if (mode === 'point') guide_id = 'concentration_calc_point';
        else if (mode === 'calibrate' || mode === 'report') guide_id = 'concentration_calc_wrong_mode';
        else guide_id = 'concentration_calc_generic';
        _runGuideById(guide_id);
    }

    function _runExcelGuide() {
        const mode = _getUiContext().mode;
        _runGuideById(mode === 'report' ? 'export_excel_in_report' : 'export_excel_nav');
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
        } else if (last.type === 'report_choice') {
            _runReportChoice();
        } else if (last.type === 'llm') {
            if (AI.messages.length && AI.messages[AI.messages.length - 1].role === 'assistant') {
                AI.messages.pop();
            }
            // Also remove the original user turn so OkapiAI.send() can re-add it cleanly,
            // preventing the same user message appearing twice in history.
            if (AI.messages.length &&
                AI.messages[AI.messages.length - 1].role === 'user' &&
                AI.messages[AI.messages.length - 1].content === last.query) {
                AI.messages.pop();
            }
            _addSystemMsg(_REDO_NOTE[lang] || _REDO_NOTE.en);
            const input = document.getElementById('okapi-ai-input');
            if (input) { input.value = last.query; OkapiAI.send(); }
        }
    }

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

        toggleLangMenu() {
            const menu = document.getElementById('okapi-ai-lang-menu');
            if (!menu) return;
            if (menu.classList.contains('okapi-hidden')) {
                const btn = document.getElementById('okapi-ai-lang-btn');
                if (btn) {
                    const r = btn.getBoundingClientRect();
                    menu.style.top = (r.bottom + 6) + 'px';
                    menu.style.right = (window.innerWidth - r.right) + 'px';
                }
                const lang = AI.activeLang || 'en';
                menu.querySelectorAll('.okapi-ai-lang-opt').forEach(opt => {
                    opt.classList.toggle('okapi-ai-lang-active', opt.dataset.lang === lang);
                });
                menu.classList.remove('okapi-hidden');
            } else {
                _langMenuHide();
            }
        },

        setLang(lang) {
            AI.activeLang = lang;
            _updateLangBtn();
            _langMenuHide();
            _loadGuides();
            if (AI.settings) {
                AI.settings.preferred_languages = [lang];
                fetch('/ai/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ preferred_languages: [lang] }),
                }).then(r => r.json()).then(d => {
                    if (d.status === 'success') AI.settings = d.settings;
                }).catch(() => {});
            }
        },

        refreshStatus() {
            fetch('/ai/status')
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'success') return;
                    AI.status = data;
                    AI.settings = data.settings;
                    const pl = AI.settings.preferred_languages || ['en'];
                    if (!AI.activeLang || !pl.includes(AI.activeLang)) {
                        AI.activeLang = pl[0] || 'en';
                    }
                    _updateLangBtn();
                    _updateStatusBar();
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

            // A user turn: take the pending marker before any branch, so no early
            // return can leak it into a later, unrelated turn.
            const pending = _consumePending();

            if (AI.status && !AI.status.api_ready) {
                const lang = AI.activeLang || 'en';
                _addSystemMsg(_AI_UNAVAILABLE_MSG[lang] || _AI_UNAVAILABLE_MSG.en);
                return;
            }

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

            const historyToSend = AI.messages.length > 10
                ? AI.messages.slice(-10)
                : AI.messages.slice();

            const msgDiv = _addStreamingMsg();
            const sendBtn = document.getElementById('okapi-ai-send-btn');
            input.disabled = true;
            if (sendBtn) {
                sendBtn.innerHTML = '&#9632;';
                sendBtn.setAttribute('data-hint', 'Stop generation');
                sendBtn.classList.add('okapi-ai-stop-mode');
                sendBtn.onclick = () => OkapiAI.stopGeneration();
            }

            const lang = AI.activeLang || 'en';
            const controller = new AbortController();
            AI.currentAbort = controller;

            (async () => {
                let fullReply = '';
                try {
                    const resp = await fetch('/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            messages: historyToSend,
                            language: lang,
                            ui_context: _getUiContext(pending),
                        }),
                        signal: controller.signal,
                    });

                    if (!resp.ok || !resp.body) {
                        const err = await resp.json().catch(() => ({}));
                        _finalizeStreamingMsg(msgDiv, null, '⚠ ' + (err.message || _trChat('ai.msg.request_failed', 'Request failed')));
                        _rearmPending(pending);
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
                            } else if (event.type === 'pending') {
                                AI.pending = event.pending || '';
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
                                const errMap = {
                                    api_key_invalid: '⚠ AI API key is invalid. Please contact the administrator.',
                                    rate_limit: '⚠ AI rate limit reached. Please wait a moment and try again.',
                                    groq_not_installed: '⚠ AI service is not configured on this server.',
                                    max_iterations: '⚠ Could not complete the request. Please try again.',
                                };
                                const errMsg = errMap[event.error] || ('⚠ ' + event.error);
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
                        _finalizeStreamingMsg(msgDiv, null, '⚠ ' + _trChat('ai.msg.network_error', 'Network error') + ': ' + err.message);
                        _rearmPending(pending);
                    }
                } finally {
                    AI.currentAbort = null;
                    if (sendBtn) {
                        sendBtn.innerHTML = '&#10148;';
                        sendBtn.setAttribute('data-hint', 'Send message');
                        sendBtn.classList.remove('okapi-ai-stop-mode');
                        sendBtn.onclick = () => OkapiAI.send();
                        sendBtn.disabled = false;
                    }
                    input.disabled = false;
                    input.focus();
                }
            })();
        },

        clearHistory() {
            AI.messages = [];
            AI.pending = '';
            const container = document.getElementById('okapi-ai-messages');
            if (container) container.innerHTML = '';
        },
    };
})();
