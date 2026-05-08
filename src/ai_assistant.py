from __future__ import annotations

import json
import os
import threading
import requests
from file_path import get_directory
from file import get_file_list
import state

# ── Guide training examples (few-shot injection) ──────────────────────────────

_GUIDE_TRAINING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guide_training.json")


def _load_guide_examples() -> list:
    try:
        with open(_GUIDE_TRAINING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [e for e in data.get("examples", []) if e.get("steps")]
    except Exception:
        return []


_STOPWORDS = frozenset({
    "how", "to", "the", "a", "an", "i", "me", "my", "do", "what",
    "where", "when", "why", "is", "it", "in", "for", "of", "and",
    "or", "with", "by", "from", "at", "can", "show", "help",
    "want", "need", "let", "make", "get", "go", "set", "use",
    "this", "that", "these", "those", "am", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "will", "would",
    "could", "should", "may", "might", "shall", "also", "just",
    "please", "tell", "give", "find", "see", "look", "about",
    "up", "out", "on", "into", "than", "then", "so", "but", "if",
    "now", "here", "there", "some", "any", "all", "more", "very",
    "no", "not", "we", "you", "your", "its", "our",
})


def _content_words(text: str) -> frozenset:
    """Return lowercase content words (length >= 4, not stopwords)."""
    return frozenset(w for w in text.lower().split() if len(w) >= 4 and w not in _STOPWORDS)


def _score_keyword(kw: str, q_lower: str, q_content: frozenset) -> float:
    """Score a single keyword phrase against a query.

    Returns:
      1.0  exact phrase found in query
      0.8  stem-overlap match:
             - single content word that is >= 5 chars (e.g. 'measure' ↔ 'measurement')
             - OR all content words of a multi-word phrase match in the query
      0.0  otherwise
    """
    if kw.lower() in q_lower:
        return 1.0
    kw_content = _content_words(kw)
    if not kw_content:
        return 0.0
    if len(kw_content) == 1:
        word = next(iter(kw_content))
        # Short single-content-word phrases (e.g. "go to data" → "data") are too
        # generic for stem-overlap; require the word to be at least 5 chars.
        if len(word) < 5:
            return 0.0
        return 0.8 if any(word in qw or qw in word for qw in q_content) else 0.0
    # Multi-word: all content words must stem-match something in the query
    if all(
        any(kw_word in qw or qw in kw_word for qw in q_content)
        for kw_word in kw_content
    ):
        return 0.8
    return 0.0


def _match_guide_example(query: str, ui_context: dict) -> tuple[dict, float] | tuple[None, float]:
    """Return (best_example, score) for the given query and UI context, or (None, 0).

    Scoring:
      1.0  exact keyword phrase found in query
      0.8  all content words of a keyword phrase stem-match words in the query
             (e.g. 'measure' is a prefix of 'measurement')
      +2   bonus when the example's mode condition matches the current mode
      +1   bonus for mode_not condition (lower specificity)

    Fast-path threshold is 0.7, so a single stem-match (0.8) is enough to
    bypass Ollama, while preventing spurious matches from very short fragments.
    """
    examples = _load_guide_examples()
    if not examples:
        return None, 0

    q_lower = query.lower()
    q_content = _content_words(q_lower)
    mode = (ui_context or {}).get("mode", "")
    best_score: float = 0
    best = None

    for ex in examples:
        conditions = ex.get("conditions", {})

        # Hard mode filters
        if conditions.get("mode") and mode != conditions["mode"]:
            continue
        if conditions.get("mode_not") and mode == conditions["mode_not"]:
            continue
        if conditions.get("mode_in") is not None and mode not in conditions["mode_in"]:
            continue

        keywords = ex.get("queries", [])
        score: float = sum(_score_keyword(kw, q_lower, q_content) for kw in keywords)
        if score < 0.1:
            continue

        # Specificity bonus so mode-matched examples win ties
        if conditions.get("mode") and mode == conditions["mode"]:
            score += 2
        elif conditions.get("mode_in") and mode in conditions["mode_in"]:
            score += 2
        elif conditions.get("mode_not"):
            score += 1

        if score > best_score:
            best_score = score
            best = ex

    return (best, best_score) if best_score >= 0.1 else (None, 0)


_FILE_SELECT_STEP = {
    "target": "#file-selection",
    "title": "Select a File First",
    "description": "No data file is loaded yet. Click here to select a CSV data file before proceeding.",
    "position": "left",
    "skipInteraction": False,
}


def _format_fewshot_hint(example: dict, ui_context: dict, steps_only: bool = False):
    """Format a matched example as a few-shot hint or return raw steps list.

    If steps_only=True, return the steps list directly (for fast-path bypass).
    Otherwise return a string hint appended to the system prompt.
    If the example requires data to be loaded but data_loaded is False,
    prepend a file-selection step.
    """
    steps = list(example["steps"])
    if example.get("requires_data_loaded") and not ui_context.get("data_loaded"):
        steps = [_FILE_SELECT_STEP] + steps
    if steps_only:
        return steps
    steps_json = json.dumps(steps, ensure_ascii=False)
    sample_query = example["queries"][0] if example["queries"] else ""
    return (
        f'\n\nFEW-SHOT EXAMPLE — for queries like "{sample_query}", '
        f"call trigger_custom_steps with exactly these steps:\n{steps_json}"
    )

# ── Greetings fast-path ───────────────────────────────────────────────────────

_GREETING_TOKENS = frozenset({
    "hi", "hey", "hello", "hiya", "howdy", "sup", "yo",
    "good morning", "good afternoon", "good evening", "good night",
    "greetings", "what's up", "whats up", "how are you", "how r u",
    "xin chào", "chào", "bonjour", "salut", "こんにちは", "おはよう",
    "привет", "здравствуйте", "你好", "早上好",
})

_GREETING_RESPONSE = {
    "en": (
        "Hi! I'm OKAPI Assistant. I can help with Easy OKAPI — "
        "data analysis, calibration, hardware setup, or app navigation. "
        "What would you like to do?"
    ),
    "vi": (
        "Xin chào! Tôi là OKAPI Assistant. Tôi có thể hỗ trợ bạn về Easy OKAPI — "
        "phân tích dữ liệu, hiệu chuẩn, cài đặt phần cứng hoặc điều hướng ứng dụng. "
        "Bạn cần giúp gì?"
    ),
    "zh": (
        "你好！我是 OKAPI Assistant，可以帮助您使用 Easy OKAPI — "
        "数据分析、校准、硬件设置或应用导航。请问有什么可以帮您的？"
    ),
    "fr": (
        "Bonjour ! Je suis OKAPI Assistant. Je peux vous aider avec Easy OKAPI — "
        "analyse de données, calibration, configuration matérielle ou navigation dans l'application. "
        "Que puis-je faire pour vous ?"
    ),
    "ja": (
        "こんにちは！OKAPI Assistant です。Easy OKAPI に関することをお手伝いします — "
        "データ分析、キャリブレーション、ハードウェア設定、アプリの操作など。"
        "何かご質問はありますか？"
    ),
    "ru": (
        "Привет! Я OKAPI Assistant. Могу помочь с Easy OKAPI — "
        "анализ данных, калибровка, настройка оборудования или навигация по приложению. "
        "Чем могу помочь?"
    ),
}


def _is_greeting(query: str) -> bool:
    """True if the query is a standalone greeting with no app-related content."""
    q = query.strip().lower().rstrip("!.,?")
    if q in _GREETING_TOKENS:
        return True
    # Short query (≤ 5 words) whose every token is a greeting or filler word
    tokens = q.split()
    if len(tokens) <= 5 and all(
        t in _GREETING_TOKENS or t in {
            "there", "you", "ya", "r", "u", "it", "its", "ok", "okay",
            "how", "are", "doing", "going", "been", "today",
        }
        for t in tokens
    ):
        return True
    return False


# ── Multilingual system prompts ───────────────────────────────────────────────

_OUT_OF_SCOPE = {
    "en": (
        "I'm only able to help with Easy OKAPI — colorimeter data analysis, "
        "calibration, hardware setup, and app navigation. "
        "I can't assist with that topic. Is there something about Easy OKAPI I can help you with?"
    ),
    "vi": (
        "Tôi chỉ có thể hỗ trợ về Easy OKAPI — phân tích dữ liệu máy so màu, "
        "hiệu chuẩn, cài đặt phần cứng và điều hướng ứng dụng. "
        "Tôi không thể hỗ trợ chủ đề này. Bạn có câu hỏi nào về Easy OKAPI không?"
    ),
    "zh": (
        "我只能协助解答 Easy OKAPI 相关问题——比色计数据分析、校准、硬件设置和应用导航。"
        "我无法帮助您解答该话题。请问您有关于 Easy OKAPI 的问题吗？"
    ),
    "fr": (
        "Je suis uniquement en mesure d'aider avec Easy OKAPI — analyse de données colorimètre, "
        "calibration, configuration matérielle et navigation dans l'application. "
        "Je ne peux pas vous aider sur ce sujet. Avez-vous une question sur Easy OKAPI ?"
    ),
    "ja": (
        "私が対応できるのは Easy OKAPI に関する内容のみです — 比色計データ分析、"
        "キャリブレーション、ハードウェア設定、アプリナビゲーション。"
        "そのトピックについてはお手伝いできません。Easy OKAPI について何かご質問はありますか？"
    ),
    "ru": (
        "Я могу помочь только с Easy OKAPI — анализ данных колориметра, "
        "калибровка, настройка оборудования и навигация по приложению. "
        "Я не могу помочь по этой теме. Есть ли у вас вопросы об Easy OKAPI?"
    ),
}

_SYSTEM_PROMPTS = {
    "en": (
        "You are OKAPI Assistant, a helper inside Easy OKAPI — a local colorimeter app for biosensor experiments.\n\n"
        "You help users with: CSV data (absorbance, kinetics, calibration), app navigation, "
        "standard curves, R² values, Michaelis-Menten kinetics, reports, hardware troubleshooting.\n"
        "Use tools to fetch live data when needed.\n\n"
        "SCOPE RULE (highest priority):\n"
        "If the question is NOT about Easy OKAPI, colorimetry, biosensor data, or this application, "
        "reply ONLY with: \"I'm only able to help with Easy OKAPI — colorimeter data analysis, "
        "calibration, hardware setup, and app navigation. I can't assist with that topic. "
        "Is there something about Easy OKAPI I can help you with?\"\n"
        "Do NOT attempt to answer off-topic questions (coding help, general science, cooking, news, math, etc.).\n\n"
        "MANDATORY GUIDE RULE:\n"
        "When a user asks HOW to navigate or find a UI element, you MUST call trigger_custom_steps "
        "— do NOT answer with plain text only.\n"
        "Examples:\n"
        "• 'how to go to calibrate mode' → call trigger_custom_steps with target #meas-mode-section\n"
        "• 'where is the timeout setting?' → call trigger_custom_steps with target #timeout-control\n"
        "• 'how do I export?' → call trigger_custom_steps with target #export-analysis\n"
        "• 'how do I start the device?' → call trigger_custom_steps with target #run-script-btn\n"
        "Only call trigger_guide when the user explicitly asks for a COMPLETE end-to-end workflow tour.\n"
        "Check [App state]: if mode already matches what the user wants, skip the mode-switch step.\n"
        "After calling a guide tool, confirm in one sentence that the guide launched.\n"
        "Always respond in English."
    ),
    "vi": (
        "Bạn là OKAPI Assistant, trợ lý AI tích hợp trong Easy OKAPI — ứng dụng phân tích "
        "dữ liệu máy so màu cục bộ dành cho thí nghiệm cảm biến sinh học.\n\n"
        "Bạn hỗ trợ: dữ liệu CSV, điều hướng ứng dụng, đường chuẩn, R², động học, báo cáo, phần cứng.\n"
        "Sử dụng các công cụ để lấy dữ liệu thực tế khi cần.\n\n"
        "QUY TẮC PHẠM VI (ưu tiên cao nhất):\n"
        "Nếu câu hỏi KHÔNG liên quan đến Easy OKAPI, đo màu, dữ liệu cảm biến sinh học hoặc ứng dụng này, "
        "chỉ trả lời: \"Tôi chỉ có thể hỗ trợ về Easy OKAPI — phân tích dữ liệu máy so màu, "
        "hiệu chuẩn, cài đặt phần cứng và điều hướng ứng dụng. "
        "Tôi không thể hỗ trợ chủ đề này. Bạn có câu hỏi nào về Easy OKAPI không?\"\n"
        "KHÔNG trả lời các câu hỏi ngoài phạm vi (lập trình, khoa học chung, nấu ăn, tin tức, toán học, v.v.).\n\n"
        "QUY TẮC HƯỚNG DẪN BẮT BUỘC:\n"
        "Khi người dùng hỏi CÁCH điều hướng hoặc tìm thành phần giao diện, BẮT BUỘC gọi trigger_custom_steps "
        "— không trả lời chỉ bằng văn bản.\n"
        "Ví dụ:\n"
        "• 'cách chuyển sang chế độ calibrate' → gọi trigger_custom_steps với target #meas-mode-section\n"
        "• 'timeout ở đâu?' → gọi trigger_custom_steps với target #timeout-control\n"
        "• 'cách xuất dữ liệu?' → gọi trigger_custom_steps với target #export-analysis\n"
        "Chỉ gọi trigger_guide khi người dùng yêu cầu hướng dẫn TOÀN BỘ quy trình từ đầu đến cuối.\n"
        "Kiểm tra [App state]: nếu mode đã đúng, bỏ qua bước chuyển chế độ.\n"
        "Sau khi gọi công cụ hướng dẫn, xác nhận trong một câu.\n"
        "Luôn trả lời bằng Tiếng Việt."
    ),
    "zh": (
        "您是 OKAPI Assistant，Easy OKAPI 内置的 AI 助手——本地比色计数据分析应用程序。\n\n"
        "您协助用户：CSV数据、应用导航、标准曲线、R²值、动力学、报告、硬件故障排除。\n"
        "需要时使用工具获取实时数据。\n\n"
        "范围规则（最高优先级）：\n"
        "如果问题与 Easy OKAPI、比色法、生物传感器数据或本应用无关，"
        "仅回复：\"我只能协助解答 Easy OKAPI 相关问题——比色计数据分析、校准、硬件设置和应用导航。"
        "我无法帮助您解答该话题。请问您有关于 Easy OKAPI 的问题吗？\"\n"
        "不要回答题外问题（编程帮助、通用科学、烹饪、新闻、数学等）。\n\n"
        "强制引导规则：\n"
        "当用户询问如何导航或找到UI元素时，必须调用 trigger_custom_steps——不得仅用文字回答。\n"
        "示例：\n"
        "• '如何切换到校准模式' → 调用 trigger_custom_steps，目标 #meas-mode-section\n"
        "• '超时设置在哪里？' → 调用 trigger_custom_steps，目标 #timeout-control\n"
        "• '如何导出？' → 调用 trigger_custom_steps，目标 #export-analysis\n"
        "仅当用户明确要求完整端到端流程演示时才调用 trigger_guide。\n"
        "检查[App state]：如果模式已匹配，跳过模式切换步骤。\n"
        "调用引导工具后，用一句话确认引导已启动。\n"
        "始终用中文（简体）回答。"
    ),
    "fr": (
        "Vous êtes OKAPI Assistant, un assistant IA intégré dans Easy OKAPI — application locale d'analyse colorimétrique.\n\n"
        "Vous aidez avec : données CSV, navigation, courbes étalon, R², cinétique, rapports, matériel.\n"
        "Utilisez les outils pour récupérer des données en direct si nécessaire.\n\n"
        "RÈGLE DE PORTÉE (priorité maximale) :\n"
        "Si la question n'est PAS liée à Easy OKAPI, à la colorimétrie, aux données de biocapteurs ou à cette application, "
        "répondez UNIQUEMENT : \"Je suis uniquement en mesure d'aider avec Easy OKAPI — analyse de données colorimètre, "
        "calibration, configuration matérielle et navigation dans l'application. "
        "Je ne peux pas vous aider sur ce sujet. Avez-vous une question sur Easy OKAPI ?\"\n"
        "Ne répondez PAS aux questions hors sujet (aide en programmation, sciences générales, cuisine, actualités, mathématiques, etc.).\n\n"
        "RÈGLE DE GUIDE OBLIGATOIRE :\n"
        "Quand l'utilisateur demande COMMENT naviguer ou trouver un élément d'interface, "
        "vous DEVEZ appeler trigger_custom_steps — ne répondez pas uniquement par du texte.\n"
        "Exemples :\n"
        "• 'comment aller en mode calibration' → appeler trigger_custom_steps, cible #meas-mode-section\n"
        "• 'où est le délai d'attente ?' → appeler trigger_custom_steps, cible #timeout-control\n"
        "• 'comment exporter ?' → appeler trigger_custom_steps, cible #export-analysis\n"
        "N'appelez trigger_guide que pour un parcours complet de bout en bout explicitement demandé.\n"
        "Vérifiez [App state] : si le mode correspond déjà, ignorez l'étape de changement de mode.\n"
        "Après avoir appelé un outil guide, confirmez en une phrase.\n"
        "Répondez toujours en français."
    ),
    "ja": (
        "あなたは OKAPI Assistant — Easy OKAPI に内蔵された AI アシスタントです（ローカル比色計アプリ）。\n\n"
        "サポート内容：CSVデータ、アプリナビゲーション、標準曲線、R²、反応速度論、レポート、ハードウェア。\n"
        "必要に応じてツールを使用してリアルタイムデータを取得してください。\n\n"
        "スコープルール（最優先）：\n"
        "質問が Easy OKAPI、比色法、バイオセンサーデータ、またはこのアプリに関係しない場合、"
        "次のメッセージのみ返信してください：\"私が対応できるのは Easy OKAPI に関する内容のみです — "
        "比色計データ分析、キャリブレーション、ハードウェア設定、アプリナビゲーション。"
        "そのトピックについてはお手伝いできません。Easy OKAPI について何かご質問はありますか？\"\n"
        "スコープ外の質問（コーディング支援、一般科学、料理、ニュース、数学など）には回答しないこと。\n\n"
        "必須ガイドルール：\n"
        "ユーザーがUI要素への移動方法を尋ねた場合、必ず trigger_custom_steps を呼び出してください "
        "— テキストのみで回答しないこと。\n"
        "例：\n"
        "• 'キャリブレーションモードへの行き方' → target #meas-mode-section で trigger_custom_steps を呼び出す\n"
        "• 'タイムアウト設定はどこ？' → target #timeout-control で trigger_custom_steps を呼び出す\n"
        "• 'エクスポートの方法' → target #export-analysis で trigger_custom_steps を呼び出す\n"
        "明示的な完全ワークフローツアーのリクエストのみ trigger_guide を使用してください。\n"
        "[App state]を確認し、モードが既に一致している場合はモード切替ステップをスキップ。\n"
        "ガイドツール呼び出し後、一文で確認してください。\n"
        "常に日本語で回答してください。"
    ),
    "ru": (
        "Вы — OKAPI Assistant, встроенный ИИ-помощник в Easy OKAPI — локальное приложение колориметра.\n\n"
        "Помощь: данные CSV, навигация, стандартные кривые, R², кинетика, отчёты, оборудование.\n"
        "При необходимости используйте инструменты для получения актуальных данных.\n\n"
        "ПРАВИЛО ОБЛАСТИ (наивысший приоритет):\n"
        "Если вопрос НЕ связан с Easy OKAPI, колориметрией, данными биосенсоров или этим приложением, "
        "отвечайте ТОЛЬКО: \"Я могу помочь только с Easy OKAPI — анализ данных колориметра, "
        "калибровка, настройка оборудования и навигация по приложению. "
        "Я не могу помочь по этой теме. Есть ли у вас вопросы об Easy OKAPI?\"\n"
        "НЕ отвечайте на вопросы не по теме (помощь в программировании, общая наука, кулинария, новости, математика и т.д.).\n\n"
        "ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ГИДА:\n"
        "Когда пользователь спрашивает КАК перейти к элементу интерфейса, "
        "вы ОБЯЗАНЫ вызвать trigger_custom_steps — не отвечайте только текстом.\n"
        "Примеры:\n"
        "• 'как перейти в режим калибровки' → вызвать trigger_custom_steps с target #meas-mode-section\n"
        "• 'где настройка таймаута?' → вызвать trigger_custom_steps с target #timeout-control\n"
        "• 'как экспортировать?' → вызвать trigger_custom_steps с target #export-analysis\n"
        "Вызывайте trigger_guide только для явного полного обзора рабочего процесса.\n"
        "Проверьте [App state]: если режим уже совпадает, пропустите шаг переключения.\n"
        "После вызова инструмента подтвердите запуск одним предложением.\n"
        "Всегда отвечайте на русском языке."
    ),
}

# ── Tool definitions (MCP-style, sent to Ollama) ──────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_app_context",
            "description": (
                "Get the current state of the Easy OKAPI application: "
                "current directory, CSV files, calibration JSON files, and hardware subprocess status."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_csv_file",
            "description": "Read a CSV data file. Returns metadata headers and the first rows of data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "CSV filename (basename only, e.g. 'data.csv').",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Maximum data rows to return (default 30, max 100).",
                        "default": 30,
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_calibration_file",
            "description": "Read a JSON calibration / standard-curve file from the json/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "JSON filename (basename only)."},
                    "mode": {
                        "type": "string",
                        "description": "Subfolder: 'kinetics' or 'point'.",
                        "enum": ["kinetics", "point"],
                    },
                },
                "required": ["filename", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hardware_status",
            "description": "Check whether the PyBadge colorimeter HID subprocess is running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_help_topic",
            "description": "Return built-in documentation for a specific Easy OKAPI feature or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": [
                            "measurement_modes", "kinetics_analysis", "standard_curve",
                            "calibration", "csv_format", "hardware_setup", "regression",
                            "reports", "file_operations",
                        ],
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_guide",
            "description": (
                "Launch a full preset workflow guide (highlights many UI elements in sequence). "
                "Use for broad 'walk me through X' requests. "
                "For focused questions about specific steps, use trigger_custom_steps instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "enum": [
                            "general",
                            "kinetics",
                            "point",
                            "calibrate_kinetics",
                            "calibrate_point",
                            "report",
                        ],
                        "description": (
                            "general: full app tour. "
                            "kinetics: time-series measurement workflow. "
                            "point: endpoint measurement workflow. "
                            "calibrate_kinetics: standard curve from kinetics data. "
                            "calibrate_point: standard curve from point data. "
                            "report: report management workflow."
                        ),
                    },
                },
                "required": ["workflow"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_custom_steps",
            "description": (
                "Focused spotlight guide for 2-5 specific UI elements. "
                "Use for targeted how-to questions. "
                "Valid IDs: #log-hid-data #run-script-btn #terminate-script-btn #base-dir #base-name "
                "#timeout-control #interval-control #log-display #go-to-btn #directory "
                "#meas-mode-section #file-selection #cal-json-sel-section #merge-file-btn "
                "#data-display-section #chart-container #range-display #window-size-section "
                "#split-source-section #export-analysis #report-section #cal-mode-select "
                "#select-quantity-section #select-regress-algo #export-coef #threshold-value "
                "#select-time-point #report-console-section #report-items-container"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": (
                            "Steps to highlight. Each step: "
                            "{\"target\": \"#element-id\", \"title\": \"short title\", "
                            "\"description\": \"what to do / why this matters\", "
                            "\"position\": \"right|left|top|bottom\"}"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "target":          {"type": "string"},
                                "title":           {"type": "string"},
                                "description":     {"type": "string"},
                                "position":        {"type": "string",
                                                   "enum": ["right", "left", "top", "bottom"]},
                                "skipInteraction": {
                                    "type": "boolean",
                                    "description": (
                                        "true = informational step, user clicks Next manually. "
                                        "false = interactive step, guide waits for user to click the element. "
                                        "Use false for action steps (clicking a button, selecting a dropdown). "
                                        "Use true for observation steps. Default: true."
                                    ),
                                },
                            },
                            "required": ["target", "title", "description"],
                        },
                    },
                },
                "required": ["steps"],
            },
        },
    },
]

_HELP_DOCS = {
    "measurement_modes": (
        "Easy OKAPI has 3 measurement modes:\n"
        "• kinetics — measures absorbance over time; computes max rate, slope, saturation.\n"
        "• point — single time-point absorbance; used for endpoint assays.\n"
        "• calibrate — applies a saved standard-curve JSON to convert absorbance to concentration."
    ),
    "kinetics_analysis": (
        "Kinetics analysis computes from a sliding-window algorithm:\n"
        "• Max Rate: maximum rate of absorbance change\n"
        "• Slope: overall linear slope\n"
        "• Sat: plateau absorbance value\n"
        "• Time To Sat: time when the reaction plateaus"
    ),
    "standard_curve": (
        "Standard curves relate known concentrations to measured absorbance values.\n"
        "Supported algorithms: linear, polynomial (degree 2-6), logarithmic, exponential, Michaelis-Menten.\n"
        "R² threshold filters out poor fits. Saved as JSON files in json/<mode>/."
    ),
    "calibration": (
        "Calibration converts absorbance to concentrations using a saved standard-curve JSON.\n"
        "Load the JSON via the dropdown, then run calibrate-mode measurements.\n"
        "The app applies stored regression coefficients automatically."
    ),
    "csv_format": (
        "CSV structure:\n"
        "• Metadata lines start with #: Measurement, MeasUnit, TimeUnit, MeasMode\n"
        "• Data header: Timestamp, Value:1, Value:2, …\n"
        "• Calibration CSVs: Concentration, maxRate/Value, Slope, Sat, Time To Sat"
    ),
    "hardware_setup": (
        "PyBadge colorimeter setup:\n"
        "• Mac: hidapi library, run app with sudo for HID access\n"
        "• Windows: install libusbK driver via Zadig, then pyusb\n"
        "• VID/PID: 0x239A / 0x800B (HID) or 0x8034 (serial)\n"
        "• Serial commands via pyserial before spawning the HID logger subprocess"
    ),
    "regression": (
        "Supported regression types:\n"
        "• linear: y = mx + b\n"
        "• polynomial: y = a₀ + a₁x + a₂x² + …\n"
        "• logarithmic: y = a·ln(x) + b\n"
        "• exponential: y = a·e^(bx)\n"
        "• Michaelis-Menten: y = Vmax·x / (Km + x)\n"
        "All computed server-side via scipy.optimize.curve_fit."
    ),
    "reports": (
        "Reports are standalone HTML files saved under report/<subject>/.\n"
        "• 'Generate quick Report' — snapshot current chart\n"
        "• 'Export Data to Report' — push data into a named subject folder\n"
        "Subjects can be renamed, copied, or deleted from the Report panel."
    ),
    "file_operations": (
        "File operations:\n"
        "• Edit — modify CSV/JSON values in a modal editor\n"
        "• Delete — permanently remove files\n"
        "• Copy — duplicate files\n"
        "• Merge CSV — combine multiple CSV files\n"
        "• Remove columns — delete Value columns from CSV\n"
        "• Export — save calibration results to new CSV/JSON"
    ),
}

# ── Guide-launched confirmation messages (one per language) ──────────────────

_GUIDE_LAUNCHED = {
    "en": "Guide launched — follow the highlighted steps.",
    "vi": "Đã khởi động hướng dẫn — làm theo các bước được tô sáng.",
    "zh": "指南已启动 — 请按照高亮步骤操作。",
    "fr": "Guide lancé — suivez les étapes mises en surbrillance.",
    "ja": "ガイドを起動しました — ハイライトされた手順に従ってください。",
    "ru": "Руководство запущено — следуйте выделенным шагам.",
}

# ── Model pull state (module-level, single-user app) ─────────────────────────

_pull_state = {
    "active": False,
    "model": "",
    "status": "",
    "total": 0,
    "completed": 0,
    "error": "",
    "done": False,
}
_pull_lock = threading.Lock()


def get_pull_state() -> dict:
    with _pull_lock:
        return dict(_pull_state)


def start_model_pull(ollama_url: str, model: str) -> None:
    """Start an Ollama model pull in a background thread."""
    with _pull_lock:
        if _pull_state["active"]:
            return
        _pull_state.update({"active": True, "model": model, "status": "starting",
                             "total": 0, "completed": 0, "error": "", "done": False})

    def _pull():
        try:
            resp = requests.post(
                f"{ollama_url}/api/pull",
                json={"name": model, "stream": True},
                stream=True,
                timeout=600,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                with _pull_lock:
                    _pull_state["status"] = data.get("status", _pull_state["status"])
                    if "total" in data:
                        _pull_state["total"] = data["total"]
                    if "completed" in data:
                        _pull_state["completed"] = data["completed"]
                    if data.get("status") == "success":
                        _pull_state["done"] = True
        except Exception as e:
            with _pull_lock:
                _pull_state["error"] = str(e)
                _pull_state["done"] = True
        finally:
            with _pull_lock:
                _pull_state["active"] = False

    threading.Thread(target=_pull, daemon=True).start()


# ── Tool execution ────────────────────────────────────────────────────────────

def _run_tool(name: str, args: dict) -> str:
    try:
        if name == "get_app_context":
            directory = get_directory()
            csv_files = get_file_list(directory)
            json_k = get_file_list(os.path.join(state.json_root_path, "kinetics"), "*.json")
            json_p = get_file_list(os.path.join(state.json_root_path, "point"), "*.json")
            running = state.process is not None and state.process.poll() is None
            return json.dumps({
                "current_directory": os.path.abspath(directory),
                "csv_files": csv_files,
                "json_calibration_kinetics": json_k,
                "json_calibration_point": json_p,
                "hardware_subprocess_running": running,
            }, ensure_ascii=False)

        elif name == "read_csv_file":
            filename = args.get("filename", "")
            max_rows = min(int(args.get("max_rows", 30)), 100)
            filepath = os.path.join(get_directory(), filename)
            if not os.path.exists(filepath):
                return json.dumps({"error": f"'{filename}' not found in current directory."})
            lines = []
            data_rows = 0
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.rstrip()
                    lines.append(stripped)
                    if not stripped.startswith('#'):
                        data_rows += 1
                    if data_rows >= max_rows + 1:
                        break
            return json.dumps({"filename": filename, "content": "\n".join(lines)}, ensure_ascii=False)

        elif name == "read_calibration_file":
            filename = args.get("filename", "")
            mode = args.get("mode", "kinetics")
            filepath = os.path.join(state.json_root_path, mode, filename)
            if not os.path.exists(filepath):
                return json.dumps({"error": f"'{filename}' not found in json/{mode}/."})
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False)

        elif name == "get_hardware_status":
            running = state.process is not None and state.process.poll() is None
            return json.dumps({
                "subprocess_running": running,
                "pid": state.process.pid if running else None,
            })

        elif name == "get_help_topic":
            topic = args.get("topic", "")
            doc = _HELP_DOCS.get(topic, "Topic not found.")
            return json.dumps({"topic": topic, "content": doc})

        elif name == "trigger_guide":
            valid = {"general", "kinetics", "point", "calibrate_kinetics", "calibrate_point", "report"}
            workflow = args.get("workflow", "general")
            if workflow not in valid:
                workflow = "general"
            return json.dumps({"guide_workflow": workflow})

        elif name == "trigger_custom_steps":
            raw_steps = args.get("steps", [])
            steps = []
            for s in raw_steps:
                if not (isinstance(s, dict) and s.get("target", "").startswith("#")):
                    continue
                step = {
                    "target":      s.get("target", ""),
                    "title":       s.get("title", "Step"),
                    "description": s.get("description", ""),
                    "position":    s.get("position", "bottom"),
                }
                if "skipInteraction" in s:
                    step["skipInteraction"] = bool(s["skipInteraction"])
                steps.append(step)
            if not steps:
                return json.dumps({"error": "No valid steps provided (targets must start with #)"})
            return json.dumps({"custom_steps": steps})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(messages: list, language: str, ollama_url: str, model: str) -> dict:
    """Send a chat request to Ollama, executing any tool calls, and return the final reply."""
    system_prompt = _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["en"])
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    guide_action = None

    for _ in range(6):  # guard against infinite tool loops
        try:
            resp = requests.post(
                f"{ollama_url}/api/chat",
                json={"model": model, "messages": full_messages, "tools": TOOLS, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return {"error": "ollama_offline"}
        except requests.exceptions.Timeout:
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)}

        result = resp.json()
        assistant_msg = result.get("message", {})
        tool_calls = assistant_msg.get("tool_calls") or []

        if not tool_calls:
            out = {"reply": assistant_msg.get("content", "")}
            if guide_action:
                out["guide_action"] = guide_action
            return out

        # Execute tool calls and feed results back
        full_messages.append(assistant_msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_result = _run_tool(tool_name, fn.get("arguments") or {})
            if tool_name in ("trigger_guide", "trigger_custom_steps"):
                try:
                    guide_action = json.loads(tool_result)
                except Exception:
                    pass
            full_messages.append({"role": "tool", "content": tool_result})

    return {"error": "max_iterations"}


_GUIDE_TOOLS = {"trigger_guide", "trigger_custom_steps"}

# ── Report clarification flow ─────────────────────────────────────────────────

_REPORT_CLARIFY_PROMPTS = {
    "en": (
        "Would you like a **quick report** (instant snapshot of the current chart and analysis) "
        "or a **full report** (export data to a subject and compile a comprehensive multi-snapshot report)?"
    ),
    "vi": (
        "Bạn muốn tạo **báo cáo nhanh** (chụp nhanh biểu đồ và phân tích hiện tại) "
        "hay **báo cáo đầy đủ** (xuất dữ liệu vào chủ đề và tổng hợp báo cáo toàn diện)?"
    ),
    "zh": (
        "您想要**快速报告**（即时快照当前图表和分析）"
        "还是**完整报告**（将数据导出到主题并编译综合多快照报告）？"
    ),
    "fr": (
        "Souhaitez-vous un **rapport rapide** (instantané du graphique et de l'analyse en cours) "
        "ou un **rapport complet** (exporter les données vers un sujet et compiler un rapport multi-snapshot) ?"
    ),
    "ja": (
        "**クイックレポート**（現在のチャートと分析の即時スナップショット）と"
        "**フルレポート**（データをエクスポートして包括的なマルチスナップショットレポートを作成）、"
        "どちらをご希望ですか？"
    ),
    "ru": (
        "Вам нужен **быстрый отчёт** (мгновенный снимок текущего графика и анализа) "
        "или **полный отчёт** (экспорт данных в тему и компиляция комплексного отчёта)?"
    ),
}

# Quick report: snapshot current chart — only shown when data is loaded
_QUICK_REPORT_STEPS = [
    {
        "target": "#report-section",
        "title": "Generate Quick Report",
        "description": (
            "Click 'Generate quick Report' here to instantly snapshot the current chart "
            "and analysis as a standalone HTML report."
        ),
        "position": "top",
        "skipInteraction": False,
    },
]

# Quick report when no data is loaded yet — prepend file selection
_QUICK_REPORT_STEPS_NO_DATA = [
    {
        "target": "#file-selection",
        "title": "Load Data First",
        "description": "Select a CSV data file to load your analysis before generating a report.",
        "position": "left",
        "skipInteraction": False,
    },
    {
        "target": "#report-section",
        "title": "Generate Quick Report",
        "description": (
            "Once data is loaded, click 'Generate quick Report' here to snapshot the "
            "current chart and analysis."
        ),
        "position": "top",
        "skipInteraction": True,
    },
]

# Full report starting from a data mode (kinetics / point / calibrate)
_FULL_REPORT_STEPS_FROM_DATA = [
    {
        "target": "#report-section",
        "title": "Export Data to Report",
        "description": (
            "Click 'Export Data to Report' to save this analysis snapshot into a named "
            "report subject for later compilation."
        ),
        "position": "top",
        "skipInteraction": False,
    },
    {
        "target": "#meas-mode-section",
        "title": "Switch to Report Mode",
        "description": (
            "After exporting, switch to Report mode here to open the full "
            "report management interface."
        ),
        "position": "right",
        "skipInteraction": False,
    },
    {
        "target": "#report-console-section",
        "title": "Report Console",
        "description": (
            "Manage your saved analysis snapshots here. Configure layout options "
            "and set a report title."
        ),
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "#report-items-container",
        "title": "Report Items",
        "description": (
            "All saved snapshots are listed here. Remove any you don't want "
            "before generating the final report."
        ),
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReport()\"]",
        "title": "Generate PDF Report",
        "description": (
            "Compile all items into a printable HTML report. "
            "Open in your browser, then use Print → Save as PDF."
        ),
        "position": "top",
        "skipInteraction": True,
    },
]

# Full report when already in report mode
_FULL_REPORT_STEPS_IN_REPORT = [
    {
        "target": "#report-console-section",
        "title": "Report Console",
        "description": (
            "Manage your saved analysis snapshots here. Configure layout and set a report title."
        ),
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "#report-items-container",
        "title": "Report Items",
        "description": "All saved snapshots are listed here. Remove any before generating.",
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReportExcel()\"]",
        "title": "Export as Excel",
        "description": "Download all items as a formatted Excel workbook with embedded charts.",
        "position": "top",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReport()\"]",
        "title": "Generate PDF Report",
        "description": "Or compile all items into a printable HTML report.",
        "position": "top",
        "skipInteraction": True,
    },
]

_REPORT_SPECIFIC_KEYWORDS = {
    "quick", "fast", "snapshot", "nhanh", "rapide", "schnell", "быстро",
    "full", "final", "compile", "comprehensive", "excel", "pdf", "complete",
    "đầy đủ", "toàn", "complet", "полный",
    "export to report", "save to report", "export data to report",
}


def _needs_report_clarification(query: str, messages: list) -> bool:
    """True when the query is about reports but doesn't specify quick vs full."""
    q = query.lower()
    if "report" not in q:
        return False
    if any(kw in q for kw in _REPORT_SPECIFIC_KEYWORDS):
        return False
    # Don't re-ask if the last assistant turn already asked the clarification
    for msg in reversed(messages[:-1]):
        if msg.get("role") == "assistant":
            c = msg.get("content", "").lower()
            if "quick report" in c and "full report" in c:
                return False
            break
    return True


def _get_pending_report_type(messages: list) -> str | None:
    """If the previous assistant turn was the quick/full clarification question,
    return 'quick' or 'full' based on the latest user answer, or None."""
    if len(messages) < 2:
        return None
    prev_assistant = None
    for msg in reversed(messages[:-1]):
        if msg.get("role") == "assistant":
            prev_assistant = msg
            break
    if not prev_assistant:
        return None
    c = prev_assistant.get("content", "").lower()
    if "quick report" not in c or "full report" not in c:
        return None
    user_answer = messages[-1].get("content", "").lower()
    quick_kws = {"quick", "fast", "snapshot", "nhanh", "rapide", "schnell", "быстро", "instant"}
    full_kws = {
        "full", "final", "compile", "comprehensive", "excel", "pdf", "complete",
        "đầy đủ", "toàn", "complet", "полный",
    }
    if any(kw in user_answer for kw in quick_kws):
        return "quick"
    if any(kw in user_answer for kw in full_kws):
        return "full"
    return None


# Keywords that strongly indicate the question is about Easy OKAPI
_IN_SCOPE_KEYWORDS = {
    "okapi", "colorimeter", "absorbance", "kinetics", "calibrat", "csv",
    "measurement", "pybadge", "hid", "regression", "standard curve", "r squared",
    "michaelis", "menten", "export", "report", "timeout", "interval", "biosensor",
    "mode", "chart", "graph", "file", "directory", "hardware", "device", "sensor",
    "concentration", "slope", "saturation", "maxrate", "threshold", "workflow",
    "tutorial", "walkthrough", "overview", "getting started", "how to use",
    "how does this", "introduction", "guide me", "show me how",
}

# Keywords that strongly indicate off-topic content
_OUT_OF_SCOPE_KEYWORDS = {
    "recipe", "cooking", "weather", "stock", "bitcoin", "crypto", "football",
    "movie", "music", "song", "game", "politics", "election", "president",
    "write a poem", "tell me a joke", "tell a story", "translate this",
    "who is", "what is the capital", "how old is", "population of",
}


def _is_out_of_scope(query: str) -> bool:
    """Fast keyword pre-filter. Returns True only for clearly off-topic queries."""
    q = query.lower()
    if any(kw in q for kw in _IN_SCOPE_KEYWORDS):
        return False
    if any(kw in q for kw in _OUT_OF_SCOPE_KEYWORDS):
        return True
    return False


def chat_stream(messages: list, language: str, ollama_url: str, model: str, ui_context: dict = None):
    """Generator yielding SSE event dicts.

    Uses stream=False for all Ollama calls so that tool calling works reliably
    on small models (qwen2.5:3b ignores tool definitions when stream=True).
    """
    last_user_query = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    mode = (ui_context or {}).get("mode", "")
    data_loaded = (ui_context or {}).get("data_loaded", False)

    # Greeting fast-path — respond instantly without touching Ollama
    if _is_greeting(last_user_query):
        yield {"type": "chunk", "content": _GREETING_RESPONSE.get(language, _GREETING_RESPONSE["en"])}
        return

    # Fast pre-filter: bail out immediately for clearly off-topic queries
    if _is_out_of_scope(last_user_query):
        yield {"type": "chunk", "content": _OUT_OF_SCOPE.get(language, _OUT_OF_SCOPE["en"])}
        return

    # Report clarification: turn 2 — user answered quick/full, dispatch guide directly
    pending_report = _get_pending_report_type(messages)
    if pending_report == "quick":
        steps = _QUICK_REPORT_STEPS_NO_DATA if not data_loaded else _QUICK_REPORT_STEPS
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": steps}}
        return
    if pending_report == "full":
        steps = _FULL_REPORT_STEPS_IN_REPORT if mode == "report" else _FULL_REPORT_STEPS_FROM_DATA
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": steps}}
        return

    # Report clarification: turn 1 — ask user to specify quick vs full
    if _needs_report_clarification(last_user_query, messages):
        yield {"type": "chunk", "content": _REPORT_CLARIFY_PROMPTS.get(language, _REPORT_CLARIFY_PROMPTS["en"])}
        return

    system_prompt = _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["en"])
    if ui_context:
        parts = []
        if mode and mode != "unknown":
            parts.append(f"mode={mode}")
        parts.append("app_started=" + ("yes" if ui_context.get("app_started") else "no"))
        parts.append("data_loaded=" + ("yes" if data_loaded else "no"))
        cal_mode = ui_context.get("cal_mode", "")
        if cal_mode:
            parts.append(f"cal_mode={cal_mode}")
        if parts:
            system_prompt += f"\n\n[App state: {', '.join(parts)}]"
    matched, match_score = _match_guide_example(last_user_query, ui_context or {})

    # Guide match (exact phrase = 1.0, stem-word overlap = 0.8) — skip Ollama
    if matched and match_score >= 0.7:
        steps = _format_fewshot_hint(matched, ui_context or {}, steps_only=True)
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": steps}}
        return

    # General Q&A — full LLM response with tools
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    guide_action = None

    for _ in range(6):
        try:
            resp = requests.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": full_messages,
                    "tools": TOOLS,
                    "stream": False,
                    "keep_alive": -1,
                    "options": {"num_predict": 400, "num_ctx": 2048, "temperature": 0.1},
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            yield {"type": "error", "error": "ollama_offline"}
            return
        except requests.exceptions.Timeout:
            yield {"type": "error", "error": "timeout"}
            return
        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        result = resp.json()
        assistant_msg = result.get("message", {})
        tool_calls = assistant_msg.get("tool_calls") or []

        if not tool_calls:
            content = assistant_msg.get("content", "")
            if content:
                yield {"type": "chunk", "content": content}
            if guide_action:
                yield {"type": "guide", "guide_action": guide_action}
            return

        full_messages.append(assistant_msg)
        only_guide_tools = True
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_result = _run_tool(tool_name, fn.get("arguments") or {})
            if tool_name in _GUIDE_TOOLS:
                try:
                    guide_action = json.loads(tool_result)
                except Exception:
                    pass
            else:
                only_guide_tools = False
            full_messages.append({"role": "tool", "content": tool_result})

        # All tool calls were guide triggers — skip the second Ollama round-trip
        # and return a brief confirmation immediately
        if only_guide_tools and guide_action:
            msg = _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])
            yield {"type": "chunk", "content": msg}
            yield {"type": "guide", "guide_action": guide_action}
            return

    yield {"type": "error", "error": "max_iterations"}


def get_guide_examples() -> list:
    return _load_guide_examples()



def prewarm_model(ollama_url: str, model: str) -> None:
    """Fire-and-forget POST to keep the model loaded in Ollama memory."""
    try:
        requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": -1},
            timeout=30,
        )
    except Exception:
        pass


def check_ollama(ollama_url: str) -> dict:
    """Return {'running': bool, 'models': [...]} for the given Ollama URL."""
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}
