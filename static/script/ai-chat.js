/**
 * OKAPI Assistant — floating AI chat widget
 * Connects to /ai/* routes which proxy to Groq API.
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
        { cmd: '/merge', desc: 'Combine multiple CSV files into a single multi-source file (dialog flow)', action: 'guide', guide_id: 'merge_files' },
        { cmd: '/edit', desc: 'Edit a data or calibration file — rename or change its contents (dialog flow)', action: 'guide', guide_id: 'edit_file' },
        { cmd: '/settings', desc: 'Open App Settings — language, default mode, units, data folder (dialog flow)', action: 'guide', guide_id: 'app_settings' },
        { cmd: '/range', desc: 'Set the analysis time window (start, end, unit)', action: 'guide', guide_id: 'set_analysis_range' },
        { cmd: '/save-range', desc: 'Save the current display-range rows to a new CSV (dialog flow)', action: 'save_range' },
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
            ko: '데이터 파일이 아직 로드되지 않았습니다. 계속하기 전에 여기를 클릭하여 CSV 데이터 파일을 선택하세요.',
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
            ko: '앱이 아직 초기화되지 않았습니다. 이 가이드를 계속하기 전에 "시작하기"를 클릭하여 기본 화면을 불러오세요.',
        },
        position: 'right',
        skipInteraction: false,
    };

    // Switch-mode prepend (mirrors Python's _MODE_SWITCH_STEP). Used when a guide
    // carries a soft `requires_mode` and the app is in a different mode — the mode
    // name (technical term) is interpolated as-is.
    // `mode` may be a single mode or an array of acceptable modes (joined ' / ',
    // a language-neutral separator since mode names stay in English).
    function _modeSwitchStep(mode) {
        const m = Array.isArray(mode) ? mode.join(' / ') : mode;
        return {
            target: '#meas-mode-section',
            title: 'Switch Measurement Mode',
            description: `This feature is only available in ${m} mode. Click here to switch to ${m} mode first, then reopen this guide.`,
            descriptions: {
                vi: `Tính năng này chỉ có trong chế độ ${m}. Nhấp vào đây để chuyển sang chế độ ${m} trước, rồi mở lại hướng dẫn này.`,
                zh: `此功能仅在 ${m} 模式下可用。请先点击此处切换到 ${m} 模式，然后重新打开本指南。`,
                fr: `Cette fonction n'est disponible qu'en mode ${m}. Cliquez ici pour passer d'abord en mode ${m}, puis rouvrez ce guide.`,
                ja: `この機能は ${m} モードでのみ利用できます。まずここをクリックして ${m} モードに切り替え、このガイドを開き直してください。`,
                ru: `Эта функция доступна только в режиме ${m}. Нажмите здесь, чтобы сначала переключиться в режим ${m}, затем снова откройте руководство.`,
                ko: `이 기능은 ${m} 모드에서만 사용할 수 있습니다. 먼저 여기를 클릭해 ${m} 모드로 전환한 뒤 이 가이드를 다시 여세요.`,
            },
            position: 'right',
            skipInteraction: false,
        };
    }

    // Confirmation messages (mirrors Python's _GUIDE_LAUNCHED)
    const _GUIDE_LAUNCHED = {
        en: 'Guide launched — follow the highlighted steps.',
        vi: 'Đã khởi động hướng dẫn — làm theo các bước được tô sáng.',
        zh: '指南已启动 — 请按照高亮步骤操作。',
        fr: 'Guide lancé — suivez les étapes mises en surbrillance.',
        ja: 'ガイドを起動しました — ハイライトされた手順に従ってください。',
        ru: 'Руководство запущено — следуйте выделенным шагам.',
        ko: '가이드를 시작했습니다 — 강조 표시된 단계를 따르세요.',
    };

    // ── Save-range demo flow (button → SweetAlert2 dialog) ────────────────────
    // Demonstrates a guide that walks INTO a Swal dialog: step 1 opens it, step 2
    // targets the dialog's own input (a `.swal2-*` selector), which the guide
    // engine lifts above Swal's z-index and auto-advances when the dialog closes.

    const _SAVE_RANGE_BTN_STEP = {
        target: '#save-range-btn',
        title: 'Save Display Range',
        description: "Set your From/To display range above, then click 'Save Display Range' here. A dialog opens to name the CSV file.",
        descriptions: {
            vi: "Đặt khoảng hiển thị Từ/Đến ở trên, rồi nhấp 'Save Display Range' tại đây. Một hộp thoại sẽ mở ra để đặt tên tệp CSV.",
            zh: "先在上方设置 From/To 显示范围，然后点击此处的「Save Display Range」。将弹出对话框为 CSV 文件命名。",
            fr: "Définissez votre plage d'affichage De/À ci-dessus, puis cliquez sur 'Save Display Range' ici. Une boîte de dialogue s'ouvre pour nommer le fichier CSV.",
            ja: "上で From/To の表示範囲を設定し、ここで「Save Display Range」をクリックします。CSV ファイルに名前を付けるダイアログが開きます。",
            ru: "Задайте диапазон отображения От/До выше, затем нажмите «Save Display Range» здесь. Откроется диалог для имени CSV-файла.",
            ko: "위에서 From/To 표시 범위를 설정한 뒤 여기서 'Save Display Range'를 클릭하세요. CSV 파일 이름을 정하는 대화 상자가 열립니다.",
        },
        position: 'bottom',
        skipInteraction: false,
    };

    const _SAVE_RANGE_DIALOG_STEP = {
        target: '.swal2-input',
        title: 'Name the CSV File',
        description: 'Type a filename for the range subset, then click Save (or Cancel). The guide continues automatically once the dialog closes.',
        descriptions: {
            vi: 'Nhập tên tệp cho phần dữ liệu trong khoảng, rồi nhấp Save (hoặc Cancel). Hướng dẫn sẽ tự tiếp tục khi hộp thoại đóng.',
            zh: '为该范围子集输入文件名，然后点击 Save（或 Cancel）。对话框关闭后指南会自动继续。',
            fr: 'Saisissez un nom de fichier pour le sous-ensemble, puis cliquez sur Save (ou Cancel). Le guide continue automatiquement à la fermeture de la boîte de dialogue.',
            ja: '範囲の部分データにファイル名を入力し、Save（または Cancel）をクリックします。ダイアログが閉じるとガイドは自動的に続行します。',
            ru: 'Введите имя файла для подмножества диапазона, затем нажмите Save (или Cancel). Руководство продолжится автоматически после закрытия диалога.',
            ko: '범위로 잘라낸 데이터의 파일 이름을 입력한 뒤 Save(또는 Cancel)를 클릭하세요. 대화 상자가 닫히면 가이드가 자동으로 이어집니다.',
        },
        position: 'top',
        skipInteraction: true,
    };

    const _SAVE_RANGE_WRONG_MODE = {
        en: 'Saving a display range works in kinetics or point mode with a data file loaded. Switch to one of those modes and select a file first.',
        vi: 'Lưu khoảng hiển thị hoạt động ở chế độ kinetics hoặc point khi đã tải tệp dữ liệu. Hãy chuyển sang một trong các chế độ đó và chọn tệp trước.',
        zh: '保存显示范围需在 kinetics 或 point 模式下并已加载数据文件。请先切换到其中一种模式并选择文件。',
        fr: "L'enregistrement d'une plage d'affichage fonctionne en mode kinetics ou point avec un fichier de données chargé. Passez d'abord dans l'un de ces modes et sélectionnez un fichier.",
        ja: '表示範囲の保存は、データファイルを読み込んだ kinetics または point モードで動作します。まずいずれかのモードに切り替えてファイルを選択してください。',
        ru: 'Сохранение диапазона отображения работает в режиме kinetics или point с загруженным файлом данных. Сначала переключитесь в один из этих режимов и выберите файл.',
        ko: '표시 범위 저장은 데이터 파일이 로드된 kinetics 또는 point 모드에서 동작합니다. 먼저 두 모드 중 하나로 전환하고 파일을 선택하세요.',
    };

    // ── Swal-dialog demo flows: Edit file, Merge files, App Settings ──────────
    // Each walks a trigger button that opens a SweetAlert2 dialog, then one or
    // more dialog steps (.swal2-* / #swal-* targets) the engine lifts above Swal
    // and auto-advances when the dialog closes. App Settings uses TWO dialog steps
    // in one modal (change language → Save), exercising the multi-step-dialog run.

    const _EMPTY_REPLY = {
        en: "I couldn't generate a response. Please try rephrasing your question.",
        vi: 'Tôi không thể tạo phản hồi. Hãy thử diễn đạt lại câu hỏi của bạn.',
        zh: '我无法生成回复，请尝试换一种方式提问。',
        fr: "Je n'ai pas pu générer de réponse. Essayez de reformuler votre question.",
        ja: '回答を生成できませんでした。質問を言い換えてみてください。',
        ru: 'Не удалось сформировать ответ. Попробуйте перефразировать вопрос.',
        ko: '응답을 생성하지 못했습니다. 질문을 다시 표현해 보세요.',
    };

    // Friendly stand-in for a raw Groq "tool_use_failed" / schema-mismatch error
    // (the model produced an invalid function call). The backend auto-retries
    // without tools on the dev path; this covers the proxy path, where the raw
    // upstream message would otherwise reach the user.
    const _TOOL_FALLBACK = {
        en: '⚠ I had trouble answering that. Please try rephrasing your question.',
        vi: '⚠ Tôi gặp trục trặc khi trả lời. Vui lòng thử diễn đạt lại câu hỏi.',
        zh: '⚠ 回答时遇到问题。请尝试换一种方式提问。',
        fr: "⚠ J'ai eu du mal à répondre. Veuillez reformuler votre question.",
        ja: '⚠ うまく回答できませんでした。質問を言い換えてみてください。',
        ru: '⚠ Не удалось ответить. Попробуйте перефразировать вопрос.',
        ko: '⚠ 답변하는 데 문제가 있었습니다. 질문을 다시 표현해 보세요.',
    };

    // True for a raw upstream error string that means "the model emitted an
    // invalid tool call" — matched loosely so any Groq phrasing is caught.
    function _isToolFailure(raw) {
        return /tool_use_failed|tool call validation failed|did not match schema|failed to call a function/i
            .test(String(raw || ''));
    }

    const _NOTHING_TO_REDO = {
        en: 'Nothing to redo yet — send a message or run a command first.',
        vi: 'Chưa có gì để làm lại — hãy gửi tin nhắn hoặc chạy lệnh trước.',
        zh: '暂无可重做的操作 — 请先发送消息或运行命令。',
        fr: 'Rien à refaire pour l\'instant — envoyez d\'abord un message ou exécutez une commande.',
        ja: 'やり直せるものがまだありません — まずメッセージを送るかコマンドを実行してください。',
        ru: 'Нечего повторять — сначала отправьте сообщение или выполните команду.',
        ko: '아직 다시 실행할 항목이 없습니다 — 먼저 메시지를 보내거나 명령을 실행하세요.',
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
        en: '⚠ AI not activated. Enter your Easy OKAPI token in the panel below.',
        vi: '⚠ AI chưa được kích hoạt. Nhập mã Easy OKAPI của bạn vào ô bên dưới.',
        zh: '⚠ AI 未激活。请在下方输入您的 Easy OKAPI 令牌。',
        fr: '⚠ IA non activée. Entrez votre jeton Easy OKAPI ci-dessous.',
        ja: '⚠ AI が有効化されていません。下の欄に Easy OKAPI トークンを入力してください。',
        ru: '⚠ ИИ не активирован. Введите ваш токен Easy OKAPI в поле ниже.',
        ko: '⚠ AI가 활성화되지 않았습니다. 아래 칸에 Easy OKAPI 토큰을 입력하세요.',
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

    // Edit-and-resend controls on user messages
    const _EDIT_HINT = {
        en: 'Edit and resend', vi: 'Sửa và gửi lại', zh: '编辑并重新发送',
        fr: 'Modifier et renvoyer', ja: '編集して再送信', ru: 'Изменить и отправить снова',
        ko: '수정 후 다시 보내기',
    };

    const _EDIT_SAVE = {
        en: 'Save & resend', vi: 'Lưu & gửi lại', zh: '保存并重新发送',
        fr: 'Enregistrer et renvoyer', ja: '保存して再送信', ru: 'Сохранить и отправить',
        ko: '저장 후 다시 보내기',
    };

    const _EDIT_CANCEL = {
        en: 'Cancel', vi: 'Hủy', zh: '取消',
        fr: 'Annuler', ja: 'キャンセル', ru: 'Отмена',
        ko: '취소',
    };

    // New-conversation confirmation
    const _NEW_CHAT_CONFIRM_TITLE = {
        en: 'Start a new conversation?', vi: 'Bắt đầu cuộc trò chuyện mới?', zh: '开始新对话？',
        fr: 'Démarrer une nouvelle conversation ?', ja: '新しい会話を始めますか？', ru: 'Начать новый разговор?',
        ko: '새 대화를 시작할까요?',
    };

    const _NEW_CHAT_CONFIRM_TEXT = {
        en: 'This clears the current chat and can\'t be undone.',
        vi: 'Thao tác này sẽ xóa cuộc trò chuyện hiện tại và không thể hoàn tác.',
        zh: '这将清除当前对话且无法撤销。',
        fr: 'Cela efface la conversation actuelle et est irréversible.',
        ja: '現在のチャットが消去され、元に戻せません。',
        ru: 'Это очистит текущий чат без возможности отмены.',
        ko: '현재 대화가 지워지며 되돌릴 수 없습니다.',
    };

    const _NEW_CHAT_CONFIRM_OK = {
        en: 'Start new', vi: 'Bắt đầu mới', zh: '开始新对话',
        fr: 'Nouvelle conversation', ja: '新規開始', ru: 'Начать',
        ko: '새로 시작',
    };

    // Answer-rating (feedback) controls
    const _FB_UP_HINT = {
        en: 'Helpful', vi: 'Hữu ích', zh: '有帮助',
        fr: 'Utile', ja: '役に立った', ru: 'Полезно',
        ko: '도움이 됨',
    };

    const _FB_DOWN_HINT = {
        en: 'Not helpful', vi: 'Không hữu ích', zh: '没帮助',
        fr: 'Pas utile', ja: '役に立たない', ru: 'Бесполезно',
        ko: '도움이 안 됨',
    };

    const _FB_THANKS = {
        en: 'Thanks for your feedback!', vi: 'Cảm ơn phản hồi của bạn!', zh: '感谢您的反馈！',
        fr: 'Merci pour votre retour !', ja: 'フィードバックありがとうございます！', ru: 'Спасибо за отзыв!',
        ko: '피드백 감사합니다!',
    };

    const _FB_COMMENT_PH = {
        en: 'What went wrong? (optional)',
        vi: 'Điều gì chưa đúng? (không bắt buộc)',
        zh: '哪里有问题？（可选）',
        fr: 'Qu\'est-ce qui n\'allait pas ? (facultatif)',
        ja: '何が問題でしたか？（任意）',
        ru: 'Что было не так? (необязательно)',
        ko: '무엇이 잘못되었나요? (선택 사항)',
    };

    const _FB_SEND = {
        en: 'Send', vi: 'Gửi', zh: '发送',
        fr: 'Envoyer', ja: '送信', ru: 'Отправить',
        ko: '보내기',
    };

    const _FB_SKIP = {
        en: 'Skip', vi: 'Bỏ qua', zh: '跳过',
        fr: 'Ignorer', ja: 'スキップ', ru: 'Пропустить',
        ko: '건너뛰기',
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

    // ── Rate limiter ──────────────────────────────────────────────────────────
    // Sliding-window: max 15 LLM requests per 60 s. Slash-command guide actions
    // (which never hit /ai/chat) are exempt — only actual LLM sends are counted.

    const _RATE_LIMIT_MAX = 15;
    const _RATE_LIMIT_WINDOW_MS = 60 * 1000;
    const _rateLimitTimestamps = [];

    const _RATE_LIMITED_MSG = {
        en: (s) => `⏳ Sending too fast — please wait ${s}s before the next message.`,
        vi: (s) => `⏳ Gửi quá nhanh — vui lòng chờ ${s}s trước khi gửi tiếp.`,
        zh: (s) => `⏳ 发送过快 — 请等待 ${s} 秒后再发送。`,
        fr: (s) => `⏳ Trop rapide — attendez ${s}s avant le prochain message.`,
        ja: (s) => `⏳ 送信が速すぎます — ${s} 秒待ってから送信してください。`,
        ru: (s) => `⏳ Слишком быстро — подождите ${s} сек. перед следующим сообщением.`,
        ko: (s) => `⏳ 너무 빠르게 보내고 있습니다 — 다음 메시지까지 ${s}초 기다려 주세요.`,
    };

    function _checkRateLimit() {
        const now = Date.now();
        while (_rateLimitTimestamps.length && now - _rateLimitTimestamps[0] > _RATE_LIMIT_WINDOW_MS) {
            _rateLimitTimestamps.shift();
        }
        if (_rateLimitTimestamps.length >= _RATE_LIMIT_MAX) {
            return Math.ceil((_RATE_LIMIT_WINDOW_MS - (now - _rateLimitTimestamps[0])) / 1000);
        }
        _rateLimitTimestamps.push(now);
        return 0;
    }

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
        messages: [],
        settings: null,
        status: null,
        guides: [],
        activeLang: null,
        currentAbort: null,
        lastAction: null,
        // Machine-readable conversation state echoed back to /ai/chat on the NEXT
        // turn (currently only 'report_type', set by the quick/full clarification).
        //
        // LIFECYCLE — one armer, one consumer, one turn:
        //   armed    by the `pending` SSE event (_sendToLLM's reader), nowhere else;
        //   consumed by _consumePending(), called at the HEAD of every path that
        //            handles a user turn (send / _cmdExecute / _saveEdit), which
        //            takes the value as a local and leaves AI.pending empty;
        //   re-armed by _rearmPending() only when the turn never reached the
        //            server (rate-limited, request failed), so a retry still works.
        // Because the consume is unconditional and happens before any branch, no
        // early return can leak the marker into a later, unrelated turn — the
        // bound is structural rather than a clear-call on each exit path.
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

    // UI-catalog string (Rule.md §2.22) for the widget's accessible names.
    function _tr(key, fallback) {
        return (typeof t === 'function') ? t(key, fallback) : fallback;
    }

    function _injectWidget() {
        const fab = document.createElement('button');
        fab.id = 'okapi-ai-fab';
        fab.setAttribute('data-hint', 'OKAPI Assistant');
        fab.innerHTML = `<span class="okapi-ai-label">AI Assistant</span><span class="okapi-ai-icon">&#129302;</span>`;
        fab.addEventListener('click', _togglePanel);
        fab.setAttribute('aria-controls', 'okapi-ai-panel');
        fab.setAttribute('aria-expanded', 'false');
        document.body.appendChild(fab);

        const panel = document.createElement('div');
        panel.id = 'okapi-ai-panel';
        panel.innerHTML = `
<div id="okapi-ai-header">
  <span id="okapi-ai-title">&#129302; OKAPI Assistant</span>
  <div id="okapi-ai-header-btns">
    <button id="okapi-ai-new-btn" type="button" data-hint="${_esc(_tr('ai.new_chat', 'New conversation'))}" aria-label="${_esc(_tr('ai.new_chat', 'New conversation'))}" onclick="OkapiAI.newChat()">&#43;</button>
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
    <button id="okapi-ai-close-btn" type="button" data-hint="${_esc(_tr('ai.close', 'Close'))}" aria-label="${_esc(_tr('ai.close', 'Close'))}" onclick="OkapiAI.close()">&#10005;</button>
  </div>
</div>

<!-- Chat view -->
<div id="okapi-ai-body">
  <div id="okapi-ai-messages"></div>
  <div id="okapi-ai-status-bar"></div>
  <div id="okapi-ai-cmd-picker" class="okapi-hidden"></div>
  <div id="okapi-ai-input-row">
    <textarea id="okapi-ai-input" rows="2" placeholder="Ask anything… (type / for commands)" aria-label="${_esc(_tr('ai.input_label', 'Message the AI assistant'))}"></textarea>
    <button id="okapi-ai-send-btn" type="button" data-hint="${_esc(_tr('ai.send', 'Send message'))}" aria-label="${_esc(_tr('ai.send', 'Send message'))}" onclick="OkapiAI.send()">&#10148;</button>
  </div>
</div>`;
        document.body.appendChild(panel);
        _setPanelOpen(false);
        // Escape closes the panel — unless something inside it (the slash-
        // command picker) already used the key.
        panel.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !e.defaultPrevented && AI.open) {
                e.preventDefault();
                OkapiAI.close();
            }
        });

        // Move lang menu to <body> so position:fixed escapes the panel's transform
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
                AI.activeLang = localStorage.getItem('okapi_ai_lang') || 'en';
                _updateLangBtn();
                _loadGuides();
                _showWelcomeIfNeeded();
            })
            .catch(() => {});
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
        if (!AI.status) return;
        if (!localStorage.getItem('okapi_ai_first_run')) {
            _addSystemMsg(_welcomeMsg());
            localStorage.setItem('okapi_ai_first_run', '1');
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
            ko: '👋 안녕하세요! 저는 OKAPI Assistant입니다. 데이터, 캘리브레이션, 하드웨어, 워크플로에 대해 물어보세요.',
        };
        return msgs[AI.activeLang] || msgs.en;
    }

    // ── Panel toggle ──────────────────────────────────────────────────────────

    function _togglePanel() {
        AI.open ? OkapiAI.close() : OkapiAI.open_();
    }

    // The closed panel is only faded out (opacity + pointer-events), which left
    // its controls in the Tab order and the accessibility tree: Tab landed on
    // invisible buttons and Enter on the invisible "+" opened a dialog. `inert`
    // takes the whole closed panel out of both; aria-expanded tells the FAB's
    // user whether it is open (Rule.md §2.36).
    function _setPanelOpen(open) {
        const panel = document.getElementById('okapi-ai-panel');
        if (panel) {
            panel.classList.toggle('okapi-ai-panel-open', open);
            panel.inert = !open;
            if (open) panel.removeAttribute('aria-hidden');
            else panel.setAttribute('aria-hidden', 'true');
        }
        const fab = document.getElementById('okapi-ai-fab');
        if (fab) fab.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    // ── Language ──────────────────────────────────────────────────────────────

    function _updateLangBtn() {
        const btn = document.getElementById('okapi-ai-lang-btn');
        if (!btn) return;
        const lang = AI.activeLang || 'en';
        btn.textContent = AI.LANG_LABELS[lang] || lang.toUpperCase();
        btn.setAttribute('data-hint', AI.LANG_NAMES[lang] || lang);
        // The face is a code ("EN"); name the control and its current value.
        btn.setAttribute('aria-label', `${_tr('ai.change_language', 'Change language')}: ${AI.LANG_NAMES[lang] || lang}`);
    }

    // ── Status bar ────────────────────────────────────────────────────────────

    function _updateStatusBar() {
        const bar = document.getElementById('okapi-ai-status-bar');
        if (!bar || !AI.status) return;
        if (AI.status.api_ready) {
            bar.innerHTML = `<span class="okapi-ai-badge okapi-ai-badge-ok">&#10003; AI ready</span>`;
        } else {
            bar.innerHTML =
                `<div class="okapi-ai-activate-box">` +
                `<span class="okapi-ai-badge okapi-ai-badge-warn">&#9888; Not activated</span>` +
                `<div class="okapi-ai-activate-row">` +
                `<input id="okapi-ai-token-input" type="text" class="okapi-ai-token-input" placeholder="Paste Easy OKAPI token…" aria-label="${_esc(_tr('ai.token_label', 'Easy OKAPI token'))}" />` +
                `<button class="okapi-ai-activate-btn" onclick="OkapiAI.activate()">Activate</button>` +
                `</div>` +
                `<a class="okapi-ai-activate-link" href="https://www.easyokapi.cbbiotec.vn" target="_blank">Get token at easyokapi.cbbiotec.vn &#8599;</a>` +
                `</div>`;
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
        return div;
    }

    // ── Answer rating (feedback) ──────────────────────────────────────────────

    // Append a 👍/👎 rating row directly under an assistant bubble. `meta` carries
    // the context posted to /ai/feedback: { source: 'guide'|'llm', guide_id,
    // query, answer }. For matched-guide answers this rating tunes the local guide
    // matcher; for LLM answers it is logged for review.
    function _attachFeedback(afterDiv, meta) {
        const container = document.getElementById('okapi-ai-messages');
        if (!container || !afterDiv) return;
        // Respect the opt-out toggle (App Settings → AI Assistant). Read live so a
        // mid-session change takes effect on the next answer without a reload.
        // USER_SETTINGS is a top-level `const` in index.html's classic script:
        // a global binding, but not a window property — window.USER_SETTINGS
        // was always undefined, so the opt-out never took effect.
        if (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS && USER_SETTINGS.ai_feedback_enabled === false) return;
        const lang = AI.activeLang || 'en';
        const up = _esc(_FB_UP_HINT[lang] || _FB_UP_HINT.en);
        const down = _esc(_FB_DOWN_HINT[lang] || _FB_DOWN_HINT.en);
        const row = document.createElement('div');
        row.className = 'okapi-ai-feedback';
        row.innerHTML =
            `<button class="okapi-ai-fb-btn" type="button" data-fb="up" data-hint="${up}" aria-label="${up}">&#128077;</button>` +
            `<button class="okapi-ai-fb-btn" type="button" data-fb="down" data-hint="${down}" aria-label="${down}">&#128078;</button>`;
        afterDiv.insertAdjacentElement('afterend', row);
        container.scrollTop = container.scrollHeight;
        row.querySelectorAll('.okapi-ai-fb-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.dataset.fb === 'down') _fbCommentBox(row, meta);
                else _fbSubmit(row, meta, 'up', '');
            });
        });
    }

    // 👎 reveals an optional comment box. Both Send and Skip record the down-vote
    // (the rating always counts) — Send attaches the note, Skip leaves it empty.
    function _fbCommentBox(row, meta) {
        const lang = AI.activeLang || 'en';
        row.innerHTML =
            `<textarea class="okapi-ai-fb-comment" rows="2" placeholder="${_esc(_FB_COMMENT_PH[lang] || _FB_COMMENT_PH.en)}"></textarea>` +
            `<div class="okapi-ai-fb-actions">` +
            `<button class="okapi-ai-fb-send" type="button">${_esc(_FB_SEND[lang] || _FB_SEND.en)}</button>` +
            `<button class="okapi-ai-fb-cancel" type="button">${_esc(_FB_SKIP[lang] || _FB_SKIP.en)}</button>` +
            `</div>`;
        const ta = row.querySelector('.okapi-ai-fb-comment');
        ta.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _fbSubmit(row, meta, 'down', ta.value); }
            else if (e.key === 'Escape') { e.preventDefault(); _fbSubmit(row, meta, 'down', ''); }
        });
        row.querySelector('.okapi-ai-fb-send').addEventListener('click', () => _fbSubmit(row, meta, 'down', ta.value));
        row.querySelector('.okapi-ai-fb-cancel').addEventListener('click', () => _fbSubmit(row, meta, 'down', ''));
        ta.focus();
        const container = document.getElementById('okapi-ai-messages');
        if (container) container.scrollTop = container.scrollHeight;
    }

    function _fbSubmit(row, meta, rating, comment) {
        fetch('/ai/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rating,
                source: meta.source || '',
                guide_id: meta.guide_id || '',
                query: meta.query || '',
                answer: meta.answer || '',
                language: AI.activeLang || 'en',
                comment: (comment || '').trim(),
            }),
        }).catch(() => { });   // fire-and-forget; the UI confirms regardless
        const lang = AI.activeLang || 'en';
        row.classList.add('okapi-ai-feedback-done');
        row.innerHTML = `<span class="okapi-ai-fb-thanks">${_esc(_FB_THANKS[lang] || _FB_THANKS.en)}</span>`;
        const container = document.getElementById('okapi-ai-messages');
        if (container) container.scrollTop = container.scrollHeight;
    }

    // A user message that can be edited and resent. `msgIndex` is its position in
    // AI.messages (the LLM history); editing truncates the history at that index and
    // re-sends, so subsequent assistant replies are discarded. Only LLM queries get
    // this treatment — slash-command/guide echoes stay plain via _addMsg.
    function _addEditableUserMsg(content, msgIndex) {
        const container = document.getElementById('okapi-ai-messages');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'okapi-ai-msg okapi-ai-msg-user okapi-ai-msg-editable';
        div.dataset.msgIndex = String(msgIndex);
        div.dataset.raw = content;
        _renderUserMsgView(div, content);
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    // Render the read-only view of an editable user bubble (content + pencil button).
    function _renderUserMsgView(div, content) {
        const lang = AI.activeLang || 'en';
        const hint = _esc(_EDIT_HINT[lang] || _EDIT_HINT.en);
        div.dataset.raw = content;
        div.classList.remove('okapi-ai-editing');
        div.innerHTML =
            `<div class="okapi-ai-msg-content">${_renderMarkdown(content)}</div>` +
            `<button class="okapi-ai-edit-btn" type="button" data-hint="${hint}" aria-label="${hint}">&#9998;</button>`;
        const btn = div.querySelector('.okapi-ai-edit-btn');
        if (btn) btn.addEventListener('click', () => _enterEditMode(div));
    }

    // Swap an editable bubble into an inline textarea + Save/Cancel controls.
    function _enterEditMode(div) {
        if (AI.currentAbort) return;   // a reply is still streaming — don't edit mid-flight
        const lang = AI.activeLang || 'en';
        const raw = div.dataset.raw || '';
        div.classList.add('okapi-ai-editing');
        div.innerHTML =
            `<textarea class="okapi-ai-edit-area" rows="2"></textarea>` +
            `<div class="okapi-ai-edit-btns">` +
            `<button class="okapi-ai-edit-save" type="button">${_esc(_EDIT_SAVE[lang] || _EDIT_SAVE.en)}</button>` +
            `<button class="okapi-ai-edit-cancel" type="button">${_esc(_EDIT_CANCEL[lang] || _EDIT_CANCEL.en)}</button>` +
            `</div>`;
        const ta = div.querySelector('.okapi-ai-edit-area');
        ta.value = raw;
        const grow = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
        ta.addEventListener('input', grow);
        ta.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _saveEdit(div); }
            else if (e.key === 'Escape') { e.preventDefault(); _renderUserMsgView(div, raw); }
        });
        div.querySelector('.okapi-ai-edit-save').addEventListener('click', () => _saveEdit(div));
        div.querySelector('.okapi-ai-edit-cancel').addEventListener('click', () => _renderUserMsgView(div, raw));
        ta.focus();
        ta.setSelectionRange(raw.length, raw.length);
        grow();
        const container = document.getElementById('okapi-ai-messages');
        if (container) container.scrollTop = container.scrollHeight;
    }

    // Commit an edit: truncate history at this message, clear the bubbles after it,
    // and resend the new text through the normal LLM path.
    function _saveEdit(div) {
        const ta = div.querySelector('.okapi-ai-edit-area');
        if (!ta) return;
        const newText = (ta.value || '').trim();
        const raw = div.dataset.raw || '';
        if (!newText || newText === raw) { _renderUserMsgView(div, raw); return; }
        const msgIndex = parseInt(div.dataset.msgIndex, 10);
        if (isNaN(msgIndex)) { _renderUserMsgView(div, raw); return; }

        // Drop this user turn and everything after it from the LLM history;
        // _sendToLLM re-adds the edited query and streams a fresh reply.
        AI.messages = AI.messages.slice(0, msgIndex);
        // …and drop any outstanding clarification with it. An edit REPLACES the
        // turn the marker was an answer to, so the marker is void: keeping it
        // shipped ui_context.pending='report_type' alongside the new text, and
        // rewriting "how do I make a report?" to "how do I export to Excel?"
        // launched the full-report walkthrough ('excel' is a _FULL_KWS word)
        // instead of answering the edited question.
        _consumePending();

        // Remove this bubble and every node after it from the DOM.
        const container = document.getElementById('okapi-ai-messages');
        if (container) {
            while (container.lastChild && container.lastChild !== div) {
                container.removeChild(container.lastChild);
            }
            if (container.lastChild === div) container.removeChild(div);
        }

        OkapiAI._sendToLLM(newText);
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
        // bullet points — wrap each contiguous run of <li> items in <ul>.
        // Separator \n inside the run is removed here so the later \n→<br>
        // pass does not inject a <br> between adjacent list items.
        t = t.replace(/^[•·]\s+(.+)$/gm, '<li>$1</li>');
        t = t.replace(/<li>[^\n]*<\/li>(?:\n<li>[^\n]*<\/li>)*/g, m => '<ul>' + m.replace(/\n/g, '') + '</ul>');
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
        if (!_getUiContext().app_started) steps = [_GET_STARTED_STEP, ...steps];
        steps = _localizeSteps(steps);
        AI.lastAction = { type: 'custom_steps', steps };
        if (typeof window.userGuide === 'undefined') return;
        OkapiAI.close();
        setTimeout(() => window.userGuide.startCustomSteps(steps), 400);
    }

    // Resolve a UI-navigation guide LOCALLY (typo/phrasing tolerant) via /ai/match,
    // so the guide uses THIS app's own UI rather than the cloud proxy's. Returns a
    // Promise<bool>: true when a local guide was launched (caller should stop),
    // false to fall through to the LLM. Any error falls through.
    function _tryLocalGuide(text, pending) {
        const lang = AI.activeLang || 'en';
        // An outstanding clarification outranks any local guide match: this turn
        // is an ANSWER, and only /ai/chat knows the question. Without this, a
        // French/Russian "rapport complet" / «полный отчёт» matches
        // report_full_from_data locally and opens the wrong variant, and on a
        // machine whose learned 👍 weights push a report guide over the launch
        // gate the clarification would never be reachable at all.
        if (pending) return Promise.resolve(false);
        return fetch('/ai/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: text, language: lang, ui_context: _getUiContext() }),
        })
            .then(r => r.json())
            .then(data => {
                if (!data || data.status !== 'success' || !data.fires || !(data.steps || []).length) {
                    return false;
                }
                _addMsg('user', text);
                const aDiv = _addMsg('assistant', _GUIDE_LAUNCHED[lang] || _GUIDE_LAUNCHED.en);
                // Let the user rate whether this was the right guide — a 👍/👎 here
                // tunes the local matcher's coefficient for this guide_id.
                _attachFeedback(aDiv, { source: 'guide', guide_id: data.guide_id || '', query: text, answer: '' });
                _launchCustomSteps(data.steps);   // sets AI.lastAction for /redo
                return true;
            })
            .catch(() => false);
    }

    // Take the pending marker for this turn and disarm it. THE ONLY consumer:
    // every user-turn entry point calls this first, so the marker can never
    // outlive the single turn that follows the one which armed it.
    function _consumePending() {
        const pending = AI.pending || '';
        AI.pending = '';
        return pending;
    }

    // Put a consumed marker back when its turn never reached /ai/chat (client
    // rate limit, network failure). Never overwrites a marker armed since — the
    // server's answer always wins over a retry of a turn that was not processed.
    function _rearmPending(pending) {
        if (pending && !AI.pending) AI.pending = pending;
    }

    function _getUiContext(pending) {
        // AppState is a bare top-level `const` (index.js) — a classic-script const
        // is a global *lexical* binding, NOT a property of window, so `window.AppState`
        // is undefined. Reading it that way made mode/subfolder/script_running always
        // wrong (mode='unknown'), which broke mode-aware guide routing (e.g. the
        // /save-range mode gate) and the read_csv subfolder. Reference the global
        // directly, like user-guide.js does.
        const appState = (typeof AppState !== 'undefined' && AppState) ? AppState : (window.AppState || {});
        const mainContent = document.getElementById('main-content');
        const dataDisplay = document.getElementById('data-display-section');
        const calMode = document.getElementById('cal-mode-select');
        const dir = appState.currentDirectory || '';
        const dataRoot = typeof DATA_ROOT !== 'undefined' ? DATA_ROOT : '';
        // The subfolder is sent to read_csv_file, which joins it under DATA_ROOT.
        // Pass the FULL path relative to the data root (not just the last
        // segment) so a nested folder like "a/b" still resolves; the backend
        // re-validates containment. Fall back to the basename if dir isn't under
        // the known data root.
        let subfolder = '';
        if (dir && dataRoot && dir !== dataRoot) {
            subfolder = dir.startsWith(dataRoot)
                ? dir.slice(dataRoot.length).replace(/^[/\\]+/, '')
                : dir.split(/[/\\]/).pop();
        }
        return {
            mode: appState.currentMeasurementMode || 'unknown',
            app_started: !!(mainContent && !mainContent.classList.contains('hidden')),
            data_loaded: !!(dataDisplay && !dataDisplay.classList.contains('hidden')),
            cal_mode: calMode ? (calMode.getAttribute('data-value') || '') : '',
            script_running: !!appState.scriptRunning,
            subfolder,
            // Explicit pending-clarification state (see AI.pending). Carried in
            // ui_context — NOT on a message — because /ai/chat forwards the message
            // dicts verbatim to Groq, which rejects unknown message fields.
            //
            // Passed in by the caller rather than read from AI.pending: the marker
            // is consumed at the head of the turn, so by the time the request is
            // built AI.pending is already empty. The key is ALWAYS present (empty
            // when unarmed) — the backend reads its absence as "client older than
            // the marker" and only then falls back to prose matching
            // (`_prose_fallback_applies` in ai_assistant.py).
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
        // A slash command ends any outstanding clarification: the user answered
        // with an action instead of quick/full. Consumed HERE and not only in
        // send() because the command picker (Tab/Enter -> _pickerConfirm) reaches
        // this function without going through send() at all.
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
            const yesNo = (v) => v ? (lang === 'vi' ? 'có' : lang === 'zh' ? '是' : lang === 'fr' ? 'oui' : lang === 'ja' ? 'はい' : lang === 'ru' ? 'да' : lang === 'ko' ? '예' : 'yes') : (lang === 'vi' ? 'không' : lang === 'zh' ? '否' : lang === 'fr' ? 'non' : lang === 'ja' ? 'いいえ' : lang === 'ru' ? 'нет' : lang === 'ko' ? '아니오' : 'no');
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

        if (cmd.action === 'save_range') {
            _addMsg('user', cmd.cmd);
            _runSaveRangeGuide();
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
        // Soft mode gate: prepend a switch-mode step (ahead of file-select) when
        // the guide's feature needs a mode the app isn't currently in. requires_mode
        // may be a single mode or a list of acceptable modes.
        if (example.requires_mode) {
            const rm = example.requires_mode;
            const ok = Array.isArray(rm) ? rm.includes(ctx.mode) : ctx.mode === rm;
            if (!ok) steps = [_modeSwitchStep(rm), ...steps];
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

    // Demo of a guide that walks into a SweetAlert2 dialog. Step 1 opens the
    // "Save Range to CSV" dialog; step 2 targets the dialog's own text input,
    // which the guide engine lifts above Swal and auto-advances on close.
    function _runSaveRangeGuide() {
        const ctx = _getUiContext();
        const lang = AI.activeLang || 'en';
        // The Save Display Range button only exists in the kinetics/point data views.
        if (ctx.mode !== 'kinetics' && ctx.mode !== 'point') {
            _addMsg('assistant', _SAVE_RANGE_WRONG_MODE[lang] || _SAVE_RANGE_WRONG_MODE.en);
            return;
        }
        let steps = [_SAVE_RANGE_BTN_STEP, _SAVE_RANGE_DIALOG_STEP];
        if (!ctx.data_loaded) steps = [_FILE_SELECT_STEP, ...steps];
        _addMsg('assistant', _GUIDE_LAUNCHED[lang] || _GUIDE_LAUNCHED.en);
        _launchCustomSteps(steps);
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
                    // Quick report fires the "Report Details" Swal dialog — and
                    // while that modal is open the chat widget is unreachable, so
                    // the guide must be launched here (before the dialog opens)
                    // and walk INTO it. generate_report_dialog opens the dialog
                    // and steps through its fields; its requires_mode / requires_
                    // data_loaded prefixes handle report-mode (switch to a data
                    // mode) and the file-select first.
                    guide_id = 'generate_report_dialog';
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
            _setPanelOpen(true);
            if (!AI.settings) _loadStatus();
        },

        close() {
            AI.open = false;
            const panel = document.getElementById('okapi-ai-panel');
            // Focus inside a panel that is about to go inert would fall to
            // <body>; hand it back to the button that opens the panel.
            const hadFocus = !!(panel && panel.contains(document.activeElement));
            _setPanelOpen(false);
            if (hadFocus) document.getElementById('okapi-ai-fab')?.focus();
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
            localStorage.setItem('okapi_ai_lang', lang);
        },

        refreshStatus() {
            fetch('/ai/status')
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'success') return;
                    AI.status = data;
                    if (!AI.activeLang) {
                        AI.activeLang = localStorage.getItem('okapi_ai_lang') || 'en';
                    }
                    _updateLangBtn();
                    _updateStatusBar();
                })
                .catch(() => { });   // best-effort refresh; server may be briefly down
        },

        stopGeneration() {
            if (AI.currentAbort) {
                AI.currentAbort.abort();
                AI.currentAbort = null;
            }
        },

        activate() {
            const input = document.getElementById('okapi-ai-token-input');
            const token = (input ? input.value : '').trim();
            if (!token) return;
            const btn = document.querySelector('.okapi-ai-activate-btn');
            if (btn) { btn.disabled = true; btn.textContent = 'Activating…'; }
            fetch('/ai/activate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token }),
            })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success') {
                        fetch('/ai/status')
                            .then(r => r.json())
                            .then(d => {
                                if (d.status === 'success') {
                                    AI.status = d;
                                    _updateStatusBar();
                                }
                            });
                    } else {
                        const bar = document.getElementById('okapi-ai-status-bar');
                        const errEl = bar && bar.querySelector('.okapi-ai-activate-err');
                        if (errEl) errEl.textContent = data.message || 'Activation failed.';
                        else if (bar) bar.insertAdjacentHTML('beforeend',
                            `<span class="okapi-ai-activate-err">${data.message || 'Activation failed.'}</span>`);
                        if (btn) { btn.disabled = false; btn.textContent = 'Activate'; }
                    }
                })
                .catch(() => {
                    if (btn) { btn.disabled = false; btn.textContent = 'Activate'; }
                });
        },

        send() {
            const input = document.getElementById('okapi-ai-input');
            const text = (input.value || '').trim();
            if (!text) return;

            // This is a user turn: take the pending marker now, before any branch.
            // Every exit below therefore leaves AI.pending empty by construction.
            const pending = _consumePending();

            // Route exact slash commands before the activation gate — guide commands
            // work without AI being activated.
            const _matchedCmd = SLASH_COMMANDS.find(c => c.cmd === text.toLowerCase());
            if (_matchedCmd) { input.value = ''; _cmdExecute(_matchedCmd); return; }

            input.value = '';
            // Resolve UI-navigation guides LOCALLY first (typo/phrasing tolerant) so
            // they use THIS app's UI rather than the cloud proxy's. Works without AI
            // activation. Falls through to the LLM when no guide fires. Skipped
            // outright while a clarification is outstanding (see _tryLocalGuide).
            _tryLocalGuide(text, pending).then(handled => {
                if (handled) return;
                OkapiAI._sendToLLM(text, pending);
            });
        },

        // `pending` is the marker already consumed by the caller for THIS turn
        // (send passes it through; _saveEdit deliberately passes nothing). A
        // direct call with no argument is a fresh turn with no marker.
        _sendToLLM(text, pending) {
            pending = pending || '';
            const input = document.getElementById('okapi-ai-input');
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

            const _waitSecs = _checkRateLimit();
            if (_waitSecs > 0) {
                const lang = AI.activeLang || 'en';
                const fn = _RATE_LIMITED_MSG[lang] || _RATE_LIMITED_MSG.en;
                _addSystemMsg(fn(_waitSecs));
                // The turn was never sent, so the clarification is still
                // outstanding — put the marker back so the retry resolves.
                _rearmPending(pending);
                return;
            }

            AI.lastAction = { type: 'llm', query: text };

            AI.messages.push({ role: 'user', content: text });
            _addEditableUserMsg(text, AI.messages.length - 1);

            const historyToSend = AI.messages.length > 10
                ? AI.messages.slice(-10)
                : AI.messages.slice();

            const msgDiv = _addStreamingMsg();
            const sendBtn = document.getElementById('okapi-ai-send-btn');
            input.disabled = true;
            if (sendBtn) {
                sendBtn.innerHTML = '&#9632;';
                sendBtn.setAttribute('data-hint', _tr('ai.stop', 'Stop generation'));
                sendBtn.setAttribute('aria-label', _tr('ai.stop', 'Stop generation'));
                sendBtn.classList.add('okapi-ai-stop-mode');
                sendBtn.onclick = () => OkapiAI.stopGeneration();
            }

            const lang = AI.activeLang || 'en';
            const controller = new AbortController();
            AI.currentAbort = controller;

            (async () => {
                let fullReply = '';
                try {
                    // The marker was consumed at the head of the turn; hand it to
                    // the context builder explicitly (it applies to this one send).
                    const uiContext = _getUiContext(pending);
                    const resp = await fetch('/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ messages: historyToSend, language: lang, ui_context: uiContext }),
                        signal: controller.signal,
                    });

                    if (!resp.ok || !resp.body) {
                        const err = await resp.json().catch(() => ({}));
                        _finalizeStreamingMsg(msgDiv, null, '⚠ ' + (err.message || 'Request failed'));
                        // Nothing was processed — the clarification still stands.
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
                                // The assistant is waiting on an answer (quick vs
                                // full report). Store the marker; the next send
                                // echoes it back in ui_context so the backend
                                // recovers the state from data, not from prose.
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
                                // An invalid-tool-call error (code, or a raw Groq
                                // message from the proxy) becomes a friendly line
                                // instead of leaking 'failed_generation' details.
                                if (event.error === 'tool_call_failed' || _isToolFailure(event.error)) {
                                    const l = AI.activeLang || 'en';
                                    _finalizeStreamingMsg(msgDiv, null, _TOOL_FALLBACK[l] || _TOOL_FALLBACK.en);
                                    return;
                                }
                                const errMsg = {
                                    groq_not_installed: '⚠ AI service is not configured on this server.',
                                    service_unavailable: '⚠ AI service is temporarily unavailable. Please try again later.',
                                    proxy_unreachable: '⚠ Cannot connect to AI service. Check your internet connection.',
                                    proxy_timeout: '⚠ AI service timed out. Please try again.',
                                    api_key_invalid: '⚠ AI API key is invalid. Contact the server administrator.',
                                    rate_limit: '⚠ Rate limit reached. Please wait a moment and try again.',
                                    license_invalid: '⚠ AI license is invalid or expired. Re-activate at easyokapi.cbbiotec.vn.',
                                    max_iterations: '⚠ The assistant could not complete its response. Please try again.',
                                }[event.error] || ('⚠ ' + event.error);
                                _finalizeStreamingMsg(msgDiv, null, errMsg);
                                return;
                            }
                        }
                    }

                    if (fullReply) {
                        AI.messages.push({ role: 'assistant', content: fullReply });
                        _finalizeStreamingMsg(msgDiv, fullReply, null);
                        _attachFeedback(msgDiv, { source: 'llm', guide_id: '', query: text, answer: fullReply });
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
                        // The send failed before the server saw it — keep the
                        // clarification outstanding so retrying "quick" works.
                        // Without this the marker was burned by a flaky send and
                        // only the transitional prose match rescued the retry.
                        _rearmPending(pending);
                    }
                } finally {
                    AI.currentAbort = null;
                    if (sendBtn) {
                        sendBtn.innerHTML = '&#10148;';
                        sendBtn.setAttribute('data-hint', _tr('ai.send', 'Send message'));
                        sendBtn.setAttribute('aria-label', _tr('ai.send', 'Send message'));
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

        // Start a fresh conversation: drop history + on-screen messages and show the
        // welcome again. Confirms first when there is a visible conversation to lose.
        newChat() {
            const container = document.getElementById('okapi-ai-messages');
            const hasContent = !!(container && container.children.length);

            const doReset = () => {
                if (AI.currentAbort) OkapiAI.stopGeneration();
                AI.messages = [];
                AI.lastAction = null;
                AI.pending = '';
                if (container) container.innerHTML = '';
                const input = document.getElementById('okapi-ai-input');
                if (input) input.value = '';
                _pickerHide();
                _clearTabNotification();
                _addSystemMsg(_welcomeMsg());
                if (input) input.focus();
            };

            const lang = AI.activeLang || 'en';
            if (hasContent && typeof Swal !== 'undefined') {
                Swal.fire({
                    title: _NEW_CHAT_CONFIRM_TITLE[lang] || _NEW_CHAT_CONFIRM_TITLE.en,
                    text: _NEW_CHAT_CONFIRM_TEXT[lang] || _NEW_CHAT_CONFIRM_TEXT.en,
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: _NEW_CHAT_CONFIRM_OK[lang] || _NEW_CHAT_CONFIRM_OK.en,
                    cancelButtonText: _EDIT_CANCEL[lang] || _EDIT_CANCEL.en,
                }).then(res => { if (res.isConfirmed) doReset(); });
            } else {
                doReset();
            }
        },
    };
})();
