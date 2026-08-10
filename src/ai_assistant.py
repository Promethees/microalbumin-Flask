from __future__ import annotations

import json
import logging
import os
import time
import threading

# ── Guide training examples (few-shot injection) ──────────────────────────────

_GUIDE_TRAINING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guide_training.json")
_GUIDE_TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guide_translations")

VALID_LANGS = {'en', 'vi', 'zh', 'fr', 'ja', 'ru', 'ko'}


_GUIDE_CACHE: dict = {}
_GUIDE_CACHE_LOCK = threading.Lock()
_GUIDE_CACHE_TTL = 60  # seconds


def _apply_overlay(examples: list, lang: str) -> list:
    if lang not in VALID_LANGS:
        return examples
    overlay_path = os.path.join(_GUIDE_TRANSLATIONS_DIR, f"{lang}.json")
    try:
        with open(overlay_path, "r", encoding="utf-8") as f:
            overlay = json.load(f)
    except FileNotFoundError:
        return examples
    except Exception as exc:
        logging.warning("Guide translation overlay %s unreadable: %s", overlay_path, exc)
        return examples
    index = {item["id"]: item for item in overlay}
    result = []
    for ex in examples:
        item = index.get(ex["id"])
        if not item:
            result.append(ex)
            continue
        translated_steps = item.get("steps", [])
        new_steps = []
        for i, step in enumerate(ex["steps"]):
            desc = translated_steps[i] if i < len(translated_steps) and translated_steps[i] else step["description"]
            new_steps.append({**step, "description": desc})
        extra_queries = [q for q in item.get("queries", []) if q]
        new_queries = ex["queries"] + extra_queries
        result.append({**ex, "steps": new_steps, "queries": new_queries})
    return result


def _load_guide_examples(lang: str = "en") -> list:
    with _GUIDE_CACHE_LOCK:
        cached = _GUIDE_CACHE.get(lang)
        if cached and time.monotonic() - cached["ts"] < _GUIDE_CACHE_TTL:
            return cached["data"]
    try:
        with open(_GUIDE_TRAINING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        examples = [e for e in data.get("examples", []) if e.get("steps")]
    except Exception:
        return []
    if lang and lang != "en":
        examples = _apply_overlay(examples, lang)
    with _GUIDE_CACHE_LOCK:
        _GUIDE_CACHE[lang] = {"data": examples, "ts": time.monotonic()}
    return examples


def _translate_step(step: dict, lang: str) -> dict:
    if lang == "en" or "descriptions" not in step:
        return {k: v for k, v in step.items() if k != "descriptions"}
    desc = step["descriptions"].get(lang) or step["description"]
    return {**{k: v for k, v in step.items() if k != "descriptions"}, "description": desc}


def _translate_steps(steps: list, lang: str) -> list:
    if lang == "en":
        return [{k: v for k, v in s.items() if k != "descriptions"} for s in steps]
    return [_translate_step(s, lang) for s in steps]


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
    "của", "và", "là", "cho", "trong", "với", "để",
    "le", "la", "les", "des", "du", "de", "pour", "dans", "est", "un", "une",
    "的", "了", "和", "是", "就", "都", "而", "及",
    "и", "в", "на", "с", "что", "как", "это", "по", "для",
})


def _content_words(text: str) -> frozenset:
    return frozenset(w for w in text.lower().split() if len(w) >= 4 and w not in _STOPWORDS)


def _score_keyword(kw: str, q_lower: str, q_content: frozenset) -> float:
    if kw.lower() in q_lower:
        return 1.0
    kw_content = _content_words(kw)
    if not kw_content:
        return 0.0
    if len(kw_content) == 1:
        word = next(iter(kw_content))
        if len(word) < 5:
            return 0.0
        return 0.8 if any(word in qw or qw in word for qw in q_content) else 0.0
    if all(
        any(kw_word in qw or qw in kw_word for qw in q_content)
        for kw_word in kw_content
    ):
        return 0.8
    return 0.0


def _match_guide_example(query: str, ui_context: dict, lang: str = "en") -> tuple[dict, float] | tuple[None, float]:
    examples = _load_guide_examples(lang)
    if not examples:
        return None, 0

    q_lower = query.lower()
    q_content = _content_words(q_lower)
    mode = (ui_context or {}).get("mode", "")
    best_score: float = 0
    best = None

    for ex in examples:
        conditions = ex.get("conditions", {})
        if conditions.get("mode") and mode != conditions["mode"]:
            continue
        if conditions.get("mode_not") and mode == conditions["mode_not"]:
            continue
        if conditions.get("mode_in") is not None and mode not in conditions["mode_in"]:
            continue
        if conditions.get("mode_not_in") and mode in conditions["mode_not_in"]:
            continue

        keywords = ex.get("queries", [])
        score: float = sum(_score_keyword(kw, q_lower, q_content) for kw in keywords)
        if score < 0.1:
            continue

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
    "descriptions": {
        "vi": "Chưa có tệp dữ liệu nào được tải. Nhấp vào đây để chọn tệp CSV trước khi tiếp tục.",
        "zh": "尚未加载数据文件。请点击此处选择 CSV 数据文件后再继续。",
        "fr": "Aucun fichier de données n'est chargé. Cliquez ici pour sélectionner un fichier CSV avant de continuer.",
        "ja": "データファイルがまだ読み込まれていません。続行する前にここをクリックして CSV ファイルを選択してください。",
        "ru": "Файл данных ещё не загружен. Нажмите здесь, чтобы выбрать CSV-файл перед продолжением.",
        "ko": "데이터 파일이 아직 로드되지 않았습니다. 계속하기 전에 여기를 클릭하여 CSV 데이터 파일을 선택하세요.",
    },
    "position": "left",
    "skipInteraction": False,
}

# Keywords that identify the target mode inside a mode-switch step description.
_MODE_HINT_KEYWORDS: dict[str, list[str]] = {
    "kinetics":  ["kinetics", "time-series", "time series"],
    "point":     ["point mode", "endpoint", "single point"],
    "calibrate": ["calibrat"],
    "report":    ["report mode"],
}


def _is_redundant_mode_step(step: dict, current_mode: str) -> bool:
    """Return True when step is a #meas-mode-section switch to the mode the user is already in."""
    if step.get("target") != "#meas-mode-section" or not current_mode:
        return False
    desc = step.get("description", "").lower()
    keywords = _MODE_HINT_KEYWORDS.get(current_mode, [])
    return any(kw in desc for kw in keywords)


def _format_fewshot_hint(example: dict, ui_context: dict, language: str = "en", steps_only: bool = False):
    steps = list(example["steps"])
    current_mode = (ui_context or {}).get("mode", "")
    # Drop a leading mode-switch step when the user is already in that mode.
    if steps and _is_redundant_mode_step(steps[0], current_mode):
        steps = steps[1:]
    if example.get("requires_data_loaded") and not ui_context.get("data_loaded"):
        steps = [_translate_step(_FILE_SELECT_STEP, language)] + steps
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
        "data analysis, calibration, or app navigation. "
        "What would you like to do?"
    ),
    "vi": (
        "Xin chào! Tôi là OKAPI Assistant. Tôi có thể hỗ trợ bạn về Easy OKAPI — "
        "phân tích dữ liệu, hiệu chuẩn hoặc điều hướng ứng dụng. "
        "Bạn cần giúp gì?"
    ),
    "zh": (
        "你好！我是 OKAPI Assistant，可以帮助您使用 Easy OKAPI — "
        "数据分析、校准或应用导航。请问有什么可以帮您的？"
    ),
    "fr": (
        "Bonjour ! Je suis OKAPI Assistant. Je peux vous aider avec Easy OKAPI — "
        "analyse de données, calibration ou navigation dans l'application. "
        "Que puis-je faire pour vous ?"
    ),
    "ja": (
        "こんにちは！OKAPI Assistant です。Easy OKAPI に関することをお手伝いします — "
        "データ分析、キャリブレーション、アプリの操作など。"
        "何かご質問はありますか？"
    ),
    "ru": (
        "Привет! Я OKAPI Assistant. Могу помочь с Easy OKAPI — "
        "анализ данных, калибровка или навигация по приложению. "
        "Чем могу помочь?"
    ),
    "ko": (
        "안녕하세요! 저는 OKAPI Assistant입니다. Easy OKAPI에 대해 도와드릴 수 있습니다 — "
        "데이터 분석, 캘리브레이션, 앱 탐색 등. "
        "무엇을 도와드릴까요?"
    ),
}


def _is_greeting(query: str) -> bool:
    q = query.strip().lower().rstrip("!.,?")
    if q in _GREETING_TOKENS:
        return True
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
        "calibration, and app navigation. "
        "I can't assist with that topic. Is there something about Easy OKAPI I can help you with?"
    ),
    "vi": (
        "Tôi chỉ có thể hỗ trợ về Easy OKAPI — phân tích dữ liệu máy so màu, "
        "hiệu chuẩn và điều hướng ứng dụng. "
        "Tôi không thể hỗ trợ chủ đề này. Bạn có câu hỏi nào về Easy OKAPI không?"
    ),
    "zh": (
        "我只能协助解答 Easy OKAPI 相关问题——比色计数据分析、校准和应用导航。"
        "我无法帮助您解答该话题。请问您有关于 Easy OKAPI 的问题吗？"
    ),
    "fr": (
        "Je suis uniquement en mesure d'aider avec Easy OKAPI — analyse de données colorimètre, "
        "calibration et navigation dans l'application. "
        "Je ne peux pas vous aider sur ce sujet. Avez-vous une question sur Easy OKAPI ?"
    ),
    "ja": (
        "私が対応できるのは Easy OKAPI に関する内容のみです — 比色計データ分析、"
        "キャリブレーション、アプリナビゲーション。"
        "そのトピックについてはお手伝いできません。Easy OKAPI について何かご質問はありますか？"
    ),
    "ru": (
        "Я могу помочь только с Easy OKAPI — анализ данных колориметра, "
        "калибровка и навигация по приложению. "
        "Я не могу помочь по этой теме. Есть ли у вас вопросы об Easy OKAPI?"
    ),
    "ko": (
        "저는 Easy OKAPI에 대해서만 도움을 드릴 수 있습니다 — 비색계 데이터 분석, "
        "캘리브레이션, 앱 탐색. "
        "해당 주제는 도와드릴 수 없습니다. Easy OKAPI에 대해 궁금한 점이 있으신가요?"
    ),
}

_SYSTEM_PROMPTS = {
    "en": (
        "You are OKAPI Assistant, a helper inside Easy OKAPI — a cloud-hosted colorimeter data analysis app for biosensor experiments.\n\n"
        "You help users with: CSV data (absorbance, kinetics, calibration), app navigation, "
        "standard curves, R² values, Michaelis-Menten kinetics, reports, Google Drive sync.\n"
        "Use tools to fetch live data when needed.\n\n"
        "SCOPE RULE (highest priority):\n"
        "If the question is NOT about Easy OKAPI, colorimetry, biosensor data, or this application, "
        "reply ONLY with: \"I'm only able to help with Easy OKAPI — colorimeter data analysis, "
        "calibration, and app navigation. I can't assist with that topic. "
        "Is there something about Easy OKAPI I can help you with?\"\n"
        "Do NOT attempt to answer off-topic questions (coding help, general science, cooking, news, math, etc.).\n\n"
        "MANDATORY GUIDE RULE:\n"
        "When a user asks HOW to navigate or find a UI element, you MUST call trigger_custom_steps "
        "— do NOT answer with plain text only.\n"
        "Examples:\n"
        "• 'how to go to calibrate mode' → call trigger_custom_steps with target #meas-mode-section\n"
        "• 'how do I export?' → call trigger_custom_steps with target #export-analysis\n"
        "• 'how do I upload a file?' → call trigger_custom_steps with target #upload-file-btn\n"
        "• 'how do I connect Google Drive?' → call trigger_custom_steps with targets #drive-section, #drive-connect-btn\n"
        "• 'how do I sync to Drive?' → call trigger_custom_steps with targets #drive-section, #drive-sync-section, #auto-sync-checkbox\n"
        "• 'how do I disable popups?' → call trigger_custom_steps with target #no-swal-checkbox\n"
        "• 'how do I set the quantity?' → call trigger_custom_steps with target #regressed-quantity\n"
        "Only call trigger_guide when the user explicitly asks for a COMPLETE end-to-end workflow tour.\n"
        "Check [App state]: if mode already matches what the user wants, skip the mode-switch step.\n"
        "After calling a guide tool, confirm in one sentence that the guide launched.\n\n"
        "STANDARD CURVE DOMAIN KNOWLEDGE:\n"
        "Always check [App state] and tailor your coefficient explanation to the active mode.\n\n"
        "KINETICS MODE — standard curve maps X=max rate (ΔAbs/s, fastest linear slope from a sliding window) → Y=concentration:\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]: "
        "Vmax=enzymatic saturation rate (upper bound; must strictly exceed every measured rate), "
        "Km=affinity constant (scales how steeply concentration rises with rate).\n"
        "• Linear  y=a·x+b  [a,b]: a=concentration gained per unit rate, b=concentration extrapolated at zero rate.\n\n"
        "POINT MODE — standard curve maps X=known concentration → Y=absorbance at the selected time point:\n"
        "• Linear  y=a·x+b  [a,b]: a=sensitivity (absorbance per conc. unit), b=background absorbance at zero conc.\n"
        "• Polynomial  y=a·x²+b·x+c  [a,b,c]: a=curvature (positive=concave-up, negative=concave-down), "
        "b=linear sensitivity, c=y-intercept.\n"
        "• Logarithmic  y=a·ln(x+b)+c  [a,b,c]: a=dynamic range scaling, "
        "b=x-shift (keeps ln argument positive), c=vertical baseline.\n"
        "• Exponential  y=a·e^(b·x)+c  [a,b,c]: a=amplitude, "
        "b=growth rate (positive=rising curve, negative=falling), c=lower asymptote.\n\n"
        "R² (0–1): goodness of fit; ≥0.99 is expected for a reliable calibration curve.\n\n"
        "KINETICS QUANTITIES (select-quantity dropdown, kinetics mode only):\n"
        "• maxRate — highest absorbance-change rate (ΔAbs/s) found by sliding-window linear regression.\n"
        "• Slope — simple linear slope across the entire dataset.\n"
        "• Sat — plateau (saturation) absorbance value when the reaction levels off.\n"
        "• Time To Sat — time in minutes until the signal reaches the plateau.\n\n"
        "SOURCES: A 'source' is one measurement channel inside a CSV file — each distinct sample "
        "position recorded in the same run. A merged file can contain multiple sources.\n"
        "Always respond in English."
    ),
    "vi": (
        "Bạn là OKAPI Assistant, trợ lý AI tích hợp trong Easy OKAPI — ứng dụng phân tích "
        "dữ liệu máy so màu trực tuyến dành cho thí nghiệm cảm biến sinh học.\n\n"
        "Bạn hỗ trợ: dữ liệu CSV, điều hướng ứng dụng, đường chuẩn, R², động học, báo cáo, Google Drive.\n"
        "Sử dụng các công cụ để lấy dữ liệu thực tế khi cần.\n\n"
        "QUY TẮC PHẠM VI (ưu tiên cao nhất):\n"
        "Nếu câu hỏi KHÔNG liên quan đến Easy OKAPI, đo màu, dữ liệu cảm biến sinh học hoặc ứng dụng này, "
        "chỉ trả lời: \"Tôi chỉ có thể hỗ trợ về Easy OKAPI — phân tích dữ liệu máy so màu, "
        "hiệu chuẩn và điều hướng ứng dụng. "
        "Tôi không thể hỗ trợ chủ đề này. Bạn có câu hỏi nào về Easy OKAPI không?\"\n"
        "KHÔNG trả lời các câu hỏi ngoài phạm vi.\n\n"
        "QUY TẮC HƯỚNG DẪN BẮT BUỘC:\n"
        "Khi người dùng hỏi CÁCH điều hướng hoặc tìm thành phần giao diện, BẮT BUỘC gọi trigger_custom_steps.\n"
        "Chỉ gọi trigger_guide khi người dùng yêu cầu hướng dẫn TOÀN BỘ quy trình.\n"
        "Kiểm tra [App state]: nếu mode đã đúng, bỏ qua bước chuyển chế độ.\n"
        "Sau khi gọi công cụ hướng dẫn, xác nhận trong một câu.\n\n"
        "KIẾN THỨC MIỀN — HỆ SỐ ĐƯỜNG CHUẨN:\n"
        "CHẾ ĐỘ ĐỘNG HỌC (KINETICS) — đường chuẩn ánh xạ X=tốc độ cực đại (ΔAbs/s) → Y=nồng độ:\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km].\n"
        "• Tuyến tính  y=a·x+b  [a,b].\n\n"
        "CHẾ ĐỘ ĐIỂM (POINT) — đường chuẩn ánh xạ X=nồng độ đã biết → Y=độ hấp thụ:\n"
        "• Tuyến tính, Đa thức, Logarithm, Hàm mũ.\n\n"
        "R² (0–1): độ khớp; ≥0.99 là tiêu chuẩn cho đường chuẩn đáng tin cậy.\n"
        "Luôn trả lời bằng Tiếng Việt."
    ),
    "zh": (
        "您是 OKAPI Assistant，Easy OKAPI 内置的 AI 助手——云端比色计数据分析应用程序。\n\n"
        "您协助用户：CSV数据、应用导航、标准曲线、R²值、动力学、报告、Google Drive同步。\n"
        "需要时使用工具获取实时数据。\n\n"
        "范围规则（最高优先级）：\n"
        "如果问题与 Easy OKAPI、比色法或本应用无关，"
        "仅回复：\"我只能协助解答 Easy OKAPI 相关问题——比色计数据分析、校准和应用导航。"
        "我无法帮助您解答该话题。请问您有关于 Easy OKAPI 的问题吗？\"\n\n"
        "强制引导规则：\n"
        "当用户询问如何导航或找到UI元素时，必须调用 trigger_custom_steps。\n"
        "仅当用户明确要求完整流程演示时才调用 trigger_guide。\n"
        "调用引导工具后，用一句话确认引导已启动。\n\n"
        "标准曲线领域知识：\n"
        "动力学模式（KINETICS）— X=最大速率（ΔAbs/s）→ Y=浓度。\n"
        "点模式（POINT）— X=已知浓度 → Y=吸光度。\n"
        "R²（0–1）：≥0.99 为可靠校准曲线的标准。\n"
        "始终用中文（简体）回答。"
    ),
    "fr": (
        "Vous êtes OKAPI Assistant, un assistant IA intégré dans Easy OKAPI — application d'analyse colorimétrique en ligne.\n\n"
        "Vous aidez avec : données CSV, navigation, courbes étalon, R², cinétique, rapports, Google Drive.\n"
        "Utilisez les outils pour récupérer des données en direct si nécessaire.\n\n"
        "RÈGLE DE PORTÉE (priorité maximale) :\n"
        "Si la question n'est PAS liée à Easy OKAPI, répondez UNIQUEMENT : "
        "\"Je suis uniquement en mesure d'aider avec Easy OKAPI — analyse de données colorimètre, "
        "calibration et navigation dans l'application. "
        "Je ne peux pas vous aider sur ce sujet. Avez-vous une question sur Easy OKAPI ?\"\n\n"
        "RÈGLE DE GUIDE OBLIGATOIRE :\n"
        "Quand l'utilisateur demande COMMENT naviguer, vous DEVEZ appeler trigger_custom_steps.\n"
        "N'appelez trigger_guide que pour un parcours complet explicitement demandé.\n"
        "Après avoir appelé un outil guide, confirmez en une phrase.\n\n"
        "MODE CINÉTIQUE — X=taux maximal (ΔAbs/s) → Y=concentration.\n"
        "MODE POINT — X=concentration connue → Y=absorbance.\n"
        "R² (0–1) : ≥0.99 est attendu pour une calibration fiable.\n"
        "Répondez toujours en français."
    ),
    "ja": (
        "あなたは OKAPI Assistant — Easy OKAPI に内蔵された AI アシスタントです（クラウド比色計アプリ）。\n\n"
        "サポート内容：CSVデータ、アプリナビゲーション、標準曲線、R²、反応速度論、レポート、Google Drive。\n"
        "必要に応じてツールを使用してリアルタイムデータを取得してください。\n\n"
        "スコープルール（最優先）：\n"
        "質問が Easy OKAPI に関係しない場合、"
        "次のメッセージのみ返信してください：\"私が対応できるのは Easy OKAPI に関する内容のみです。"
        "そのトピックについてはお手伝いできません。Easy OKAPI について何かご質問はありますか？\"\n\n"
        "必須ガイドルール：\n"
        "ユーザーがUI要素への移動方法を尋ねた場合、必ず trigger_custom_steps を呼び出してください。\n"
        "明示的な完全ワークフローツアーのリクエストのみ trigger_guide を使用してください。\n"
        "ガイドツール呼び出し後、一文で確認してください。\n\n"
        "動力学モード — X=最大速度（ΔAbs/s）→ Y=濃度。\n"
        "点モード — X=既知濃度 → Y=吸光度。\n"
        "R²（0–1）：信頼できる校正には ≥0.99 が必要。\n"
        "常に日本語で回答してください。"
    ),
    "ru": (
        "Вы — OKAPI Assistant, встроенный ИИ-помощник в Easy OKAPI — облачное приложение колориметра.\n\n"
        "Помощь: данные CSV, навигация, стандартные кривые, R², кинетика, отчёты, Google Drive.\n"
        "При необходимости используйте инструменты для получения актуальных данных.\n\n"
        "ПРАВИЛО ОБЛАСТИ (наивысший приоритет):\n"
        "Если вопрос НЕ связан с Easy OKAPI, отвечайте ТОЛЬКО: "
        "\"Я могу помочь только с Easy OKAPI — анализ данных колориметра, "
        "калибровка и навигация по приложению. "
        "Я не могу помочь по этой теме. Есть ли у вас вопросы об Easy OKAPI?\"\n\n"
        "ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ГИДА:\n"
        "Когда пользователь спрашивает КАК перейти к элементу интерфейса, "
        "вы ОБЯЗАНЫ вызвать trigger_custom_steps.\n"
        "Вызывайте trigger_guide только для явного полного обзора рабочего процесса.\n"
        "После вызова инструмента подтвердите запуск одним предложением.\n\n"
        "Кинетический режим — X=максимальная скорость (ΔAbs/с) → Y=концентрация.\n"
        "Точечный режим — X=известная концентрация → Y=поглощение.\n"
        "R² (0–1): ≥0.99 требуется для надёжной калибровки.\n"
        "Всегда отвечайте на русском языке."
    ),
    "ko": (
        "당신은 OKAPI Assistant입니다 — 클라우드 기반 비색계 데이터 분석 앱 Easy OKAPI에 내장된 AI 어시스턴트입니다.\n\n"
        "지원 범위: CSV 데이터, 앱 탐색, 표준 곡선, R², 반응 속도론, 리포트, Google Drive.\n"
        "필요할 때 도구를 사용해 실시간 데이터를 가져오세요.\n\n"
        "범위 규칙(최우선):\n"
        "질문이 Easy OKAPI와 관련이 없으면 다음만 답하세요: "
        "\"저는 Easy OKAPI에 대해서만 도움을 드릴 수 있습니다 — 비색계 데이터 분석, "
        "캘리브레이션, 앱 탐색. "
        "해당 주제는 도와드릴 수 없습니다. Easy OKAPI에 대해 궁금한 점이 있으신가요?\"\n\n"
        "필수 가이드 규칙:\n"
        "사용자가 UI 요소로 이동하는 방법을 물으면 반드시 trigger_custom_steps를 호출하세요.\n"
        "명시적으로 전체 워크플로 투어를 요청한 경우에만 trigger_guide를 호출하세요.\n"
        "가이드 도구를 호출한 뒤에는 한 문장으로 확인하세요.\n\n"
        "Kinetics 모드 — X=최대 속도(ΔAbs/s) → Y=농도.\n"
        "Point 모드 — X=알려진 농도 → Y=흡광도.\n"
        "R²(0–1): 신뢰할 수 있는 캘리브레이션에는 ≥0.99가 필요합니다.\n"
        "항상 한국어로 답변하세요."
    ),
}

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_app_context",
            "description": (
                "Get the current state of the Easy OKAPI application: "
                "uploaded CSV files and calibration JSON files."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_csv_file",
            "description": "Read an uploaded CSV data file. Returns metadata headers and the first rows of data.",
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
            "description": "Read a JSON calibration / standard-curve file.",
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
            "name": "get_help_topic",
            "description": "Return built-in documentation for a specific Easy OKAPI feature or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": [
                            "measurement_modes", "kinetics_analysis", "standard_curve",
                            "calibration", "csv_format", "regression",
                            "reports", "file_operations", "google_drive", "upload_files",
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
                "Valid IDs: "
                "#meas-mode-section #file-selection #cal-json-sel-section #merge-file-btn "
                "#data-display-section #chart-container #range-display #window-size-section "
                "#split-source-section #normalize-mode-section #open-all-analysis "
                "#export-analysis #report-section #cal-mode-select "
                "#select-quantity-section #regressed-quantity #select-regress-algo "
                "#export-coef #threshold-value #select-time-point "
                "#report-console-section #report-items-container "
                "#drive-section #drive-connect-btn #drive-sync-section #auto-sync-checkbox "
                "#upload-file-btn #upload-json-btn #no-swal-checkbox #filter-source "
                "#deselect-file-btn #copy-file-btn #report-subject-name"
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
                                        "Default: true."
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
        "Reports are standalone HTML files.\n"
        "• 'Generate quick Report' — snapshot current chart\n"
        "• 'Export Data to Report' — push data into a named subject folder\n"
        "Subjects can be renamed, copied, or deleted from the Report panel."
    ),
    "file_operations": (
        "File operations:\n"
        "• Upload CSV/JSON — drag & drop or browse\n"
        "• Edit — modify CSV/JSON values in a modal editor\n"
        "• Delete — remove files from your session\n"
        "• Copy — duplicate files\n"
        "• Merge CSV — combine multiple CSV files\n"
        "• Export — save calibration results to new CSV/JSON\n"
        "• Google Drive — sync files with your Drive account"
    ),
    "google_drive": (
        "Google Drive Integration (sidebar Drive section):\n"
        "• Connect — click 'Connect to Google Drive' to sign in and authorise access\n"
        "• Select folder — pick an existing Drive folder or create a new one for syncing\n"
        "• Push — upload local data files from your session to the selected Drive folder\n"
        "• Pull — download files from the Drive folder into your local session\n"
        "• Auto-sync — when enabled, new data files are automatically pushed to Drive after each measurement\n"
        "Access via the Google Drive section in the left sidebar."
    ),
    "upload_files": (
        "Uploading files:\n"
        "• Upload CSV — click 'Upload CSV' in the File Selection section to import a measurement CSV from your device\n"
        "• Upload JSON — click 'Upload JSON' in the Calibration section to import a standard-curve coefficient file\n"
        "• Files are added to the respective lists and available for immediate selection\n"
        "• Alternatively, use Google Drive sync to pull files from the cloud"
    ),
}

# ── Guide-launched confirmation messages ──────────────────────────────────────

_GUIDE_LAUNCHED = {
    "en": "Guide launched — follow the highlighted steps.",
    "vi": "Đã khởi động hướng dẫn — làm theo các bước được tô sáng.",
    "zh": "指南已启动 — 请按照高亮步骤操作。",
    "fr": "Guide lancé — suivez les étapes mises en surbrillance.",
    "ja": "ガイドを起動しました — ハイライトされた手順に従ってください。",
    "ru": "Руководство запущено — следуйте выделенным шагам.",
    "ko": "가이드를 시작했습니다 — 강조 표시된 단계를 따르세요.",
}

_GUIDE_TOOLS = {"trigger_guide", "trigger_custom_steps"}

# ── Tool execution ────────────────────────────────────────────────────────────

def _run_tool(name: str, args: dict, user_data: dict = None, help_docs: dict = None) -> str:
    user_data = user_data or {}
    try:
        if name == "get_app_context":
            csv_files = list(user_data.get('csv', {}).keys())
            json_k = list(user_data.get('json', {}).get('kinetics', {}).keys())
            json_p = list(user_data.get('json', {}).get('point', {}).keys())
            return json.dumps({
                "csv_files": csv_files,
                "json_calibration_kinetics": json_k,
                "json_calibration_point": json_p,
            }, ensure_ascii=False)

        elif name == "read_csv_file":
            filename = args.get("filename", "")
            max_rows = min(int(args.get("max_rows", 30)), 100)
            content = user_data.get('csv', {}).get(filename)
            if content is None:
                return json.dumps({"error": f"'{filename}' not found in your uploaded files."})
            lines = content.split('\n')
            output_lines = []
            data_rows = 0
            for line in lines:
                output_lines.append(line)
                if not line.startswith('#'):
                    data_rows += 1
                if data_rows >= max_rows + 1:
                    break
            return json.dumps({"filename": filename, "content": "\n".join(output_lines)}, ensure_ascii=False)

        elif name == "read_calibration_file":
            filename = args.get("filename", "")
            mode = args.get("mode", "kinetics")
            data = user_data.get('json', {}).get(mode, {}).get(filename)
            if data is None:
                return json.dumps({"error": f"'{filename}' not found in json/{mode}/."})
            return json.dumps(data, ensure_ascii=False)

        elif name == "get_help_topic":
            topic = args.get("topic", "")
            # A client-grounded (desktop) request supplies its own help docs so
            # the answer describes the local app, not this website.
            docs = help_docs if isinstance(help_docs, dict) and help_docs else _HELP_DOCS
            doc = docs.get(topic, "Topic not found.")
            return json.dumps({"topic": topic, "content": doc})

        elif name == "get_hardware_status":
            # Desktop-only tool (the local app talks to a USB colorimeter). The
            # server has no hardware, so report that rather than erroring.
            return json.dumps({
                "running": False,
                "note": "Hardware status is only available in the local desktop app, not via the server.",
            })

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
    "ko": (
        "**빠른 보고서**(현재 차트와 분석의 즉시 스냅샷)를 원하시나요, "
        "아니면 **전체 보고서**(데이터를 주제로 내보내고 종합 멀티 스냅샷 보고서를 컴파일)를 원하시나요?"
    ),
}

_QUICK_REPORT_STEPS = [
    {
        "target": "#report-section",
        "title": "Generate Quick Report",
        "description": (
            "Click 'Generate quick Report' here to instantly snapshot the current chart "
            "and analysis as a standalone HTML report."
        ),
        "descriptions": {
            "vi": "Nhấp 'Generate quick Report' tại đây để chụp nhanh biểu đồ và phân tích hiện tại.",
            "zh": "点击此处的「Generate quick Report」即时将当前图表和分析快照为独立的 HTML 报告。",
            "fr": "Cliquez sur 'Generate quick Report' ici pour capturer instantanément le graphique et l'analyse.",
            "ja": "ここで「Generate quick Report」をクリックして、現在のチャートと分析を即時スナップショットします。",
            "ru": "Нажмите «Generate quick Report», чтобы мгновенно сохранить текущий график и анализ.",
            "ko": "여기서 'Generate quick Report'를 클릭하면 현재 차트와 분석이 즉시 스냅샷됩니다.",
        },
        "position": "top",
        "skipInteraction": False,
    },
]

_QUICK_REPORT_STEPS_NO_DATA = [
    {
        "target": "#file-selection",
        "title": "Load Data First",
        "description": "Select a CSV data file to load your analysis before generating a report.",
        "descriptions": {
            "vi": "Chọn tệp dữ liệu CSV để tải phân tích trước khi tạo báo cáo.",
            "zh": "选择一个 CSV 数据文件以在生成报告之前加载您的分析。",
            "fr": "Sélectionnez un fichier de données CSV pour charger votre analyse avant de générer un rapport.",
            "ja": "レポートを生成する前に分析を読み込むため CSV データファイルを選択してください。",
            "ru": "Выберите CSV-файл данных для загрузки анализа перед созданием отчёта.",
            "ko": "보고서를 생성하기 전에 분석을 불러오려면 CSV 데이터 파일을 선택하세요.",
        },
        "position": "left",
        "skipInteraction": False,
    },
    {
        "target": "#report-section",
        "title": "Generate Quick Report",
        "description": "Once data is loaded, click 'Generate quick Report' here to snapshot the current chart.",
        "descriptions": {
            "vi": "Khi dữ liệu đã tải, nhấp 'Generate quick Report' tại đây.",
            "zh": "数据加载后，点击此处的「Generate quick Report」。",
            "fr": "Une fois les données chargées, cliquez sur 'Generate quick Report' ici.",
            "ja": "データが読み込まれたら、ここで「Generate quick Report」をクリックします。",
            "ru": "После загрузки данных нажмите «Generate quick Report».",
            "ko": "데이터가 로드되면 여기서 'Generate quick Report'를 클릭하세요.",
        },
        "position": "top",
        "skipInteraction": True,
    },
]

_FULL_REPORT_STEPS_FROM_DATA = [
    {
        "target": "#report-section",
        "title": "Export Data to Report",
        "description": "Click 'Export Data to Report' to save this analysis snapshot into a named report subject.",
        "descriptions": {
            "vi": "Nhấp 'Export Data to Report' để lưu ảnh chụp phân tích này vào chủ đề báo cáo.",
            "zh": "点击「Export Data to Report」将此分析快照保存到命名报告主题中。",
            "fr": "Cliquez sur 'Export Data to Report' pour enregistrer ce snapshot d'analyse.",
            "ja": "「Export Data to Report」をクリックして、分析スナップショットを保存します。",
            "ru": "Нажмите «Export Data to Report», чтобы сохранить снимок анализа.",
            "ko": "'Export Data to Report'를 클릭하여 분석 스냅샷을 저장하세요.",
        },
        "position": "top",
        "skipInteraction": False,
    },
    {
        "target": "#meas-mode-section",
        "title": "Switch to Report Mode",
        "description": "After exporting, switch to Report mode here to open the full report management interface.",
        "descriptions": {
            "vi": "Sau khi xuất, chuyển sang chế độ Report ở đây.",
            "zh": "导出后，在此切换到 Report 模式。",
            "fr": "Après l'exportation, passez en mode Report ici.",
            "ja": "エクスポート後、ここで Report モードに切り替えます。",
            "ru": "После экспорта переключитесь в режим Report.",
            "ko": "내보낸 뒤 여기서 Report 모드로 전환하세요.",
        },
        "position": "right",
        "skipInteraction": False,
    },
    {
        "target": "#report-console-section",
        "title": "Report Console",
        "description": "Manage your saved analysis snapshots here. Configure layout and set a report title.",
        "descriptions": {
            "vi": "Quản lý các ảnh chụp phân tích đã lưu tại đây.",
            "zh": "在此管理已保存的分析快照。",
            "fr": "Gérez vos snapshots d'analyse sauvegardés ici.",
            "ja": "ここで保存された分析スナップショットを管理します。",
            "ru": "Управляйте сохранёнными снимками анализа здесь.",
            "ko": "여기서 저장된 분석 스냅샷을 관리합니다.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "#report-items-container",
        "title": "Report Items",
        "description": "All saved snapshots are listed here. Remove any before generating the final report.",
        "descriptions": {
            "vi": "Tất cả ảnh chụp đã lưu được liệt kê ở đây.",
            "zh": "所有已保存的快照都列在这里。",
            "fr": "Tous les snapshots sauvegardés sont listés ici.",
            "ja": "保存されたすべてのスナップショットがここに一覧表示されます。",
            "ru": "Все сохранённые снимки перечислены здесь.",
            "ko": "저장된 모든 스냅샷이 여기에 나열됩니다.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReport()\"]",
        "title": "Generate PDF Report",
        "description": "Compile all items into a printable HTML report. Open in your browser, then Print → Save as PDF.",
        "descriptions": {
            "vi": "Tổng hợp tất cả mục thành báo cáo HTML. Mở trong trình duyệt, sau đó In → Lưu thành PDF.",
            "zh": "将所有项目编译为可打印的 HTML 报告。在浏览器中打印 → 另存为 PDF。",
            "fr": "Compilez tous les éléments en rapport HTML imprimable. Imprimer → Enregistrer en PDF.",
            "ja": "すべての項目を印刷可能な HTML レポートにまとめます。印刷 → PDF として保存。",
            "ru": "Скомпилируйте все элементы в HTML-отчёт. Печать → Сохранить как PDF.",
            "ko": "모든 항목을 인쇄 가능한 HTML 보고서로 컴파일합니다. 인쇄 → PDF로 저장.",
        },
        "position": "top",
        "skipInteraction": True,
    },
]

_FULL_REPORT_STEPS_IN_REPORT = [
    {
        "target": "#report-console-section",
        "title": "Report Console",
        "description": "Manage your saved analysis snapshots here. Configure layout and set a report title.",
        "descriptions": {
            "vi": "Quản lý các ảnh chụp phân tích đã lưu tại đây.",
            "zh": "在此管理已保存的分析快照。",
            "fr": "Gérez vos snapshots d'analyse sauvegardés ici.",
            "ja": "ここで保存された分析スナップショットを管理します。",
            "ru": "Управляйте сохранёнными снимками анализа здесь.",
            "ko": "여기서 저장된 분석 스냅샷을 관리합니다.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "#report-items-container",
        "title": "Report Items",
        "description": "All saved snapshots are listed here. Remove any before generating.",
        "descriptions": {
            "vi": "Tất cả ảnh chụp đã lưu được liệt kê ở đây.",
            "zh": "所有已保存的快照都列在这里。",
            "fr": "Tous les snapshots sauvegardés sont listés ici.",
            "ja": "保存されたすべてのスナップショットがここに一覧表示されます。",
            "ru": "Все сохранённые снимки перечислены здесь.",
            "ko": "저장된 모든 스냅샷이 여기에 나열됩니다.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReportExcel()\"]",
        "title": "Export as Excel",
        "description": "Download all items as a formatted Excel workbook with embedded charts.",
        "descriptions": {
            "vi": "Tải xuống tất cả mục dưới dạng bảng tính Excel.",
            "zh": "将所有项目下载为格式化的 Excel 工作簿。",
            "fr": "Téléchargez tous les éléments sous forme de classeur Excel formaté.",
            "ja": "すべての項目をフォーマットされた Excel ワークブックとしてダウンロードします。",
            "ru": "Загрузите все элементы как форматированную Excel-книгу.",
            "ko": "모든 항목을 서식이 적용된 Excel 통합 문서로 다운로드합니다.",
        },
        "position": "top",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReport()\"]",
        "title": "Generate PDF Report",
        "description": "Or compile all items into a printable HTML report.",
        "descriptions": {
            "vi": "Hoặc tổng hợp tất cả mục thành báo cáo HTML có thể in.",
            "zh": "或者将所有项目编译为可打印的 HTML 报告。",
            "fr": "Ou compilez tous les éléments en rapport HTML imprimable.",
            "ja": "またはすべての項目を印刷可能な HTML レポートにまとめます。",
            "ru": "Или скомпилируйте все элементы в печатаемый HTML-отчёт.",
            "ko": "또는 모든 항목을 인쇄 가능한 HTML 보고서로 컴파일합니다.",
        },
        "position": "top",
        "skipInteraction": True,
    },
]

_REPORT_SPECIFIC_KEYWORDS = {
    "quick", "fast", "snapshot", "nhanh", "rapide", "schnell", "быстро",
    "full", "final", "compile", "comprehensive", "excel", "pdf", "complete",
    "đầy đủ", "toàn", "complet", "полный",
    "export to report", "save to report", "export data to report",
    "快速", "快", "すぐ", "クイック", "速い",
}


def _needs_report_clarification(query: str, messages: list) -> bool:
    q = query.lower()
    if "report" not in q:
        return False
    if any(kw in q for kw in _REPORT_SPECIFIC_KEYWORDS):
        return False
    for msg in reversed(messages[:-1]):
        if msg.get("role") == "assistant":
            c = msg.get("content", "").lower()
            if "quick report" in c and "full report" in c:
                return False
            break
    return True


def _get_pending_report_type(messages: list) -> str | None:
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


_IN_SCOPE_KEYWORDS = {
    "okapi", "colorimeter", "absorbance", "kinetics", "calibrat", "csv",
    "measurement", "regression", "standard curve", "r squared",
    "michaelis", "menten", "export", "report", "biosensor",
    "mode", "chart", "graph", "file", "upload", "drive",
    "concentration", "slope", "saturation", "maxrate", "threshold", "workflow",
    "tutorial", "walkthrough", "overview", "getting started", "how to use",
    "how does this", "introduction", "guide me", "show me how",
    "hiệu chuẩn", "động học", "báo cáo", "nồng độ", "kết quả",
    "校准", "动力学", "测量", "报告", "浓度",
    "calibration", "cinétique", "mesure", "rapport", "concentration",
    "キャリブレーション", "キネティクス", "測定", "レポート", "濃度",
    "калибровка", "кинетика", "измерение", "отчёт", "концентрация",
}

_OUT_OF_SCOPE_KEYWORDS = {
    "recipe", "cooking", "weather", "stock", "bitcoin", "crypto", "football",
    "movie", "music", "song", "game", "politics", "election", "president",
    "write a poem", "tell me a joke", "tell a story", "translate this",
    "who is", "what is the capital", "how old is", "population of",
}


def _is_out_of_scope(query: str) -> bool:
    q = query.lower()
    if any(kw in q for kw in _IN_SCOPE_KEYWORDS):
        return False
    if any(kw in q for kw in _OUT_OF_SCOPE_KEYWORDS):
        return True
    return False


# ── Groq chat ─────────────────────────────────────────────────────────────────

def _groq_chat(api_key: str, model: str, messages: list, tools: list) -> dict:
    """Call Groq API and return the response message dict."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 500,
        }
        # GPT-OSS are reasoning models: reasoning tokens count against the
        # completion budget, so keep effort low and give the answer headroom
        # (otherwise max_tokens is spent reasoning and content comes back empty).
        if model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = "low"
            kwargs["max_tokens"] = 1500
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        result = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return result
    except ImportError:
        return {"role": "assistant", "content": "", "error": "groq_not_installed"}
    except Exception as e:
        err = str(e)
        if "401" in err or "api_key" in err.lower() or "authentication" in err.lower():
            return {"role": "assistant", "content": "", "error": "api_key_invalid"}
        if "429" in err or "rate_limit" in err.lower():
            return {"role": "assistant", "content": "", "error": "rate_limit"}
        return {"role": "assistant", "content": "", "error": err}


def chat_stream(messages: list, language: str, api_key: str, model: str,
                ui_context: dict = None, user_data: dict = None,
                system_prompt_override: str = None, help_docs_override: dict = None,
                tools_override: list = None):
    """Generator yielding SSE event dicts.

    The desktop (downloaded) app proxies through /ai/proxy/chat and supplies its
    OWN grounding — system prompt, help-topic docs, and tool schema — via the
    *_override params, so the model answers as the local desktop assistant
    instead of describing this cloud website's features (Drive sync, uploads,
    accounts). When an override is present ("client-grounded"), the server-side
    guide matcher is skipped too: the desktop resolves navigation guides locally
    against its own UI (/ai/match), so matching here against this app's guide
    examples would spotlight element IDs that don't exist in the desktop UI.
    The website's own /ai/chat passes no overrides and keeps its full behaviour.
    """
    client_grounded = bool(system_prompt_override)
    # Validate the client-supplied tool schema before trusting it upstream; a
    # malformed value must not break the Groq call, so fall back to this app's.
    if isinstance(tools_override, list) and tools_override and all(
        isinstance(t, dict) for t in tools_override
    ):
        active_tools = tools_override
    else:
        active_tools = TOOLS
    last_user_query = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    mode = (ui_context or {}).get("mode", "")
    data_loaded = (ui_context or {}).get("data_loaded", False)

    if _is_greeting(last_user_query):
        yield {"type": "chunk", "content": _GREETING_RESPONSE.get(language, _GREETING_RESPONSE["en"])}
        return

    if _is_out_of_scope(last_user_query):
        yield {"type": "chunk", "content": _OUT_OF_SCOPE.get(language, _OUT_OF_SCOPE["en"])}
        return

    pending_report = _get_pending_report_type(messages)
    if pending_report == "quick":
        raw = _QUICK_REPORT_STEPS_NO_DATA if not data_loaded else _QUICK_REPORT_STEPS
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": _translate_steps(raw, language)}}
        return
    if pending_report == "full":
        raw = _FULL_REPORT_STEPS_IN_REPORT if mode == "report" else _FULL_REPORT_STEPS_FROM_DATA
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": _translate_steps(raw, language)}}
        return

    if _needs_report_clarification(last_user_query, messages):
        yield {"type": "chunk", "content": _REPORT_CLARIFY_PROMPTS.get(language, _REPORT_CLARIFY_PROMPTS["en"])}
        return

    system_prompt = system_prompt_override or _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["en"])
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

    # Skip server-side guide matching for a client-grounded (desktop) request —
    # it resolves guides locally against its own UI, so matching here would
    # spotlight this website's element IDs.
    if not client_grounded:
        matched, match_score = _match_guide_example(last_user_query, ui_context or {}, language)
        if matched and match_score >= 0.7:
            steps = _format_fewshot_hint(matched, ui_context or {}, language, steps_only=True)
            yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
            yield {"type": "guide", "guide_action": {"custom_steps": steps}}
            return

    full_messages = [{"role": "system", "content": system_prompt}] + messages
    guide_action = None
    ud = user_data or {}

    for _ in range(6):
        result = _groq_chat(api_key, model, full_messages, active_tools)
        if "error" in result:
            error_map = {
                "groq_not_installed": "groq_not_installed",
                "api_key_invalid": "api_key_invalid",
                "rate_limit": "rate_limit",
            }
            yield {"type": "error", "error": error_map.get(result["error"], result["error"])}
            return

        tool_calls = result.get("tool_calls") or []

        if not tool_calls:
            content = result.get("content", "")
            if content:
                yield {"type": "chunk", "content": content}
            if guide_action:
                yield {"type": "guide", "guide_action": guide_action}
            return

        full_messages.append(result)
        only_guide_tools = True
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            try:
                tool_args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                tool_args = {}
            tool_result = _run_tool(tool_name, tool_args, ud, help_docs_override)
            if tool_name in _GUIDE_TOOLS:
                try:
                    guide_action = json.loads(tool_result)
                except Exception:
                    pass
            else:
                only_guide_tools = False
            full_messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": tool_result,
            })

        if only_guide_tools and guide_action:
            # Prefer any text the LLM included alongside the tool call; fall back to canned message.
            llm_text = (result.get("content") or "").strip()
            yield {
                "type": "chunk",
                "content": llm_text or _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"]),
            }
            yield {"type": "guide", "guide_action": guide_action}
            return

    yield {"type": "error", "error": "max_iterations"}


def get_guide_examples(lang: str = "en") -> list:
    return _load_guide_examples(lang)
