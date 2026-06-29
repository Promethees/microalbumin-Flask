from __future__ import annotations

import difflib
import json
import os
from file_path import DATA_ROOT, validate_in_data_root
from file import get_file_list
import state
import ai_feedback

# ── Guide training examples (few-shot injection) ──────────────────────────────

# Read-only bundled assets: resolve from the bundle root (== project root in dev,
# sys._MEIPASS in a frozen build).
_GUIDE_TRAINING_PATH = os.path.join(state.bundle_dir, "guide_training.json")
_GUIDE_TRANSLATIONS_DIR = os.path.join(state.bundle_dir, "guide_translations")

VALID_LANGS = {'en', 'vi', 'zh', 'fr', 'ja', 'ru'}


def _apply_overlay(examples: list, lang: str) -> list:
    if lang not in VALID_LANGS:
        return examples
    overlay_path = os.path.join(_GUIDE_TRANSLATIONS_DIR, f"{lang}.json")
    try:
        with open(overlay_path, "r", encoding="utf-8") as f:
            overlay = json.load(f)
    except Exception:
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
    try:
        with open(_GUIDE_TRAINING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        examples = [e for e in data.get("examples", []) if e.get("steps")]
    except Exception:
        return []
    if lang and lang != "en":
        examples = _apply_overlay(examples, lang)
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
    # Basic multilingual stopwords
    "của", "và", "là", "cho", "trong", "với", "để", # vi
    "le", "la", "les", "des", "du", "de", "pour", "dans", "est", "un", "une", # fr
    "的", "了", "和", "是", "就", "都", "而", "及", # zh
    "и", "в", "на", "с", "что", "как", "это", "по", "для", # ru
})


def _is_cjk(s: str) -> bool:
    """True when s contains CJK / kana characters (Chinese, Japanese, Korean)."""
    return any(
        0x2E80 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF or 0xAC00 <= ord(c) <= 0xD7AF
        for c in s
    )


# Edge punctuation stripped from query/keyword tokens before matching, so
# "measurement?" or "(kinetics)" normalise to their bare word forms.
_EDGE_PUNCT = ".,!?;:()[]{}\"'`…“”’"


def _content_words(text: str) -> frozenset:
    result = set()
    for w in text.lower().split():
        w = w.strip(_EDGE_PUNCT)
        min_len = 2 if _is_cjk(w) else 4
        if len(w) >= min_len and w not in _STOPWORDS:
            result.add(w)
    return frozenset(result)


def _token_match(a: str, b: str) -> bool:
    """Prefix-aware token equality.

    Two words match when they are equal or one is a *prefix* of the other, so
    stem variants line up ('file'/'files', 'record'/'recorded'). Plain substring
    containment is deliberately avoided: a negation/derivation prefix such as
    'de-' or 'un-' embeds the base word as a *suffix* ('select' ⊂ 'deselect'),
    which would otherwise produce a confidently wrong, antonymous match.
    """
    return a == b or a.startswith(b) or b.startswith(a)


# ── Typo tolerance: spell-correct query words to the guide vocabulary ─────────
# Misspellings are normalised to the nearest known keyword word BEFORE scoring,
# so the prefix matcher above and the keyword lists keep working unchanged.
# Guards (shared 2-char prefix, length within 2, high similarity) keep this to
# genuine typos ('measurment'→'measurement') and never map a real out-of-domain
# word onto a near neighbour ('internal'≁'interval', 'select'≁'deselect').

def _guide_vocabulary(examples: list) -> frozenset:
    vocab = set()
    for ex in examples:
        for kw in ex.get("queries", []):
            vocab |= _content_words(kw)
    return frozenset(vocab)


def _nearest_keyword_word(word: str, vocab: frozenset) -> str:
    if _is_cjk(word) or len(word) < 5 or word in vocab:
        return word
    best, best_ratio = word, 0.88
    for v in vocab:
        if len(v) < 5 or v[:2] != word[:2] or abs(len(v) - len(word)) > 2:
            continue
        ratio = difflib.SequenceMatcher(None, word, v).ratio()
        if ratio > best_ratio:
            best, best_ratio = v, ratio
    return best


def _canonicalize_content(content: frozenset, vocab: frozenset) -> frozenset:
    return frozenset(_nearest_keyword_word(w, vocab) for w in content)


def _score_keyword(kw: str, q_lower: str, q_content: frozenset) -> float:
    kw_lower = kw.lower()
    min_len = 2 if _is_cjk(kw_lower) else 4
    kw_content = _content_words(kw_lower)
    # Exact contiguous phrase match — weighted by specificity (content-word
    # count) so one long, specific phrase ('export data to report') outranks a
    # pile of short generic keywords summed from a less-relevant example.
    if kw_lower in q_lower and len(kw_lower) >= min_len and kw_lower not in _STOPWORDS:
        return 1.0 + 0.8 * max(0, len(kw_content) - 1)
    if not kw_content:
        return 0.0
    if len(kw_content) == 1:
        word = next(iter(kw_content))
        if len(word) < 5:
            return 0.0
        return 0.8 if any(_token_match(word, qw) for qw in q_content) else 0.0
    if all(
        any(_token_match(kw_word, qw) for qw in q_content)
        for kw_word in kw_content
    ):
        return 0.8
    return 0.0


def _match_guide_example(query: str, ui_context: dict, lang: str = "en") -> tuple[dict, float] | tuple[None, float]:
    examples = _load_guide_examples(lang)
    if not examples:
        return None, 0

    q_lower = query.lower()
    q_content = _canonicalize_content(_content_words(q_lower), _guide_vocabulary(examples))
    mode = (ui_context or {}).get("mode", "")
    best_score: float = 0
    best = None
    # Learned feedback weights apply only while the opt-out toggle is on. Read it
    # once here, never inside the per-guide loop below.
    fb_on = ai_feedback.is_enabled()

    for ex in examples:
        conditions = ex.get("conditions", {})
        if conditions.get("mode") and mode != conditions["mode"]:
            continue
        if conditions.get("mode_not") and mode == conditions["mode_not"]:
            continue
        if conditions.get("mode_in") is not None and mode not in conditions["mode_in"]:
            continue

        ex_id = ex.get("id", "")
        keywords = ex.get("queries", [])
        score: float = sum(_score_keyword(kw, q_lower, q_content) for kw in keywords)
        # Reinforced vocabulary from user 👍 feedback adds to the baseline signal,
        # so phrasings the user confirmed for this guide score higher next time.
        if fb_on:
            learned = ai_feedback.learned_terms(ex_id)
            if learned:
                score += sum(_score_keyword(kw, q_lower, q_content) for kw in learned)
        if score < 0.1:
            continue
        if conditions.get("mode") and mode == conditions["mode"]:
            score += 2
        elif conditions.get("mode_in") and mode in conditions["mode_in"]:
            score += 2
        elif conditions.get("mode_not"):
            score += 1

        # Learned coefficient: 👍 lifts this guide, 👎 suppresses it. Applied AFTER
        # the baseline-relevance gate so a positive weight can never make an
        # unrelated guide (zero keyword signal) fire; a negative weight can push a
        # genuine match below the launch threshold (effectively un-firing it).
        if fb_on:
            score += ai_feedback.learned_bonus(ex_id)

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
    },
    "position": "left",
    "skipInteraction": False,
}

_GET_STARTED_STEP = {
    "target": "#init-button",
    "title": "Click Get Started First",
    "description": 'The app hasn\'t been initialised yet. Click "Get Started" to load the main interface before proceeding with this guide.',
    "descriptions": {
        "vi": 'Ứng dụng chưa được khởi tạo. Nhấp vào "Bắt đầu" để tải giao diện chính trước khi tiếp tục hướng dẫn này.',
        "zh": '应用程序尚未初始化。请点击"开始"加载主界面后再继续本指南。',
        "fr": "L'application n'a pas encore été initialisée. Cliquez sur \"Commencer\" pour charger l'interface principale avant de poursuivre ce guide.",
        "ja": 'アプリはまだ初期化されていません。このガイドを続ける前に「はじめる」をクリックしてメインインターフェイスを読み込んでください。',
        "ru": "Приложение ещё не инициализировано. Нажмите «Начать», чтобы загрузить главный интерфейс перед продолжением руководства.",
    },
    "position": "right",
    "skipInteraction": False,
}


def _format_fewshot_hint(example: dict, ui_context: dict, language: str = "en", steps_only: bool = False):
    steps = list(example["steps"])
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

# ── Greeting fast-path ───────────────────────────────────────────────────────

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
        "• 'how do I change the app language / open settings?' → call trigger_custom_steps with target #settingsBtn\n"
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
        "• maxRate — highest absorbance-change rate (ΔAbs/s) found by sliding-window linear regression "
        "over the steepest phase of the curve; the most common choice for enzyme-kinetics assays.\n"
        "• Slope — simple linear slope across the entire dataset; less precise than maxRate for sigmoid curves.\n"
        "• Sat — plateau (saturation) absorbance value when the reaction levels off.\n"
        "• Time To Sat — time in minutes until the signal reaches the plateau; useful for reaction-speed comparisons.\n\n"
        "SOURCES: A 'source' is one measurement channel inside a CSV file — each distinct sample or sensor "
        "position recorded in the same run. A merged file can contain multiple sources.\n\n"
        "APP SETTINGS — the gear button (#settingsBtn) opens App Settings: interface Language (6 languages), "
        "default mode & window size, concentration unit, table sort order, and (installed builds) the data-folder location.\n"
        "CONCENTRATION UNITS: a concentration is labelled ng/µL, nM, or % — a label only (switching the unit never "
        "converts the numbers). A measurement CSV pairs with a calibration JSON only when both share the same "
        "Measurement, Unit, and concentration unit.\n"
        "ASSISTANT CONTROLS: users can type / for slash commands, click + to start a new conversation, "
        "edit a sent message to resend it, and rate answers with 👍/👎.\n"
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
        "• 'đổi ngôn ngữ ứng dụng / mở cài đặt' → gọi trigger_custom_steps với target #settingsBtn\n"
        "Chỉ gọi trigger_guide khi người dùng yêu cầu hướng dẫn TOÀN BỘ quy trình từ đầu đến cuối.\n"
        "Kiểm tra [App state]: nếu mode đã đúng, bỏ qua bước chuyển chế độ.\n"
        "Sau khi gọi công cụ hướng dẫn, xác nhận trong một câu.\n\n"
        "KIẾN THỨC MIỀN — HỆ SỐ ĐƯỜNG CHUẨN:\n"
        "Luôn kiểm tra [App state] và điều chỉnh giải thích hệ số theo chế độ đang hoạt động.\n\n"
        "CHẾ ĐỘ ĐỘNG HỌC (KINETICS) — đường chuẩn ánh xạ X=tốc độ cực đại (ΔAbs/s) → Y=nồng độ:\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]: "
        "Vmax=tốc độ bão hòa enzyme (cận trên; phải lớn hơn mọi tốc độ đo được), "
        "Km=hằng số ái lực (thể hiện mức độ nồng độ tăng theo tốc độ).\n"
        "• Tuyến tính  y=a·x+b  [a,b]: a=nồng độ tăng trên mỗi đơn vị tốc độ, "
        "b=nồng độ ngoại suy tại tốc độ bằng 0.\n\n"
        "CHẾ ĐỘ ĐIỂM (POINT) — đường chuẩn ánh xạ X=nồng độ đã biết → Y=độ hấp thụ tại thời điểm chọn:\n"
        "• Tuyến tính  y=a·x+b  [a,b]: a=độ nhạy (độ hấp thụ/đơn vị nồng độ), "
        "b=độ hấp thụ nền tại nồng độ bằng 0.\n"
        "• Đa thức  y=a·x²+b·x+c  [a,b,c]: a=độ cong (dương=lõm lên, âm=lõm xuống), "
        "b=độ nhạy tuyến tính, c=giá trị chặn Y.\n"
        "• Logarithm  y=a·ln(x+b)+c  [a,b,c]: a=hệ số tỉ lệ, "
        "b=dịch chuyển trục X (giữ ln dương), c=đường cơ sở.\n"
        "• Hàm mũ  y=a·e^(b·x)+c  [a,b,c]: a=biên độ, "
        "b=tốc độ tăng/giảm (dương=tăng, âm=giảm), c=đường tiệm cận dưới.\n\n"
        "R² (0–1): độ khớp; ≥0.99 là tiêu chuẩn cho đường chuẩn đáng tin cậy.\n\n"
        "CÀI ĐẶT ỨNG DỤNG — nút bánh răng (#settingsBtn) mở App Settings: Ngôn ngữ giao diện (6 ngôn ngữ), "
        "chế độ & kích thước cửa sổ mặc định, đơn vị nồng độ, thứ tự sắp xếp bảng, và (bản cài đặt) vị trí thư mục dữ liệu.\n"
        "ĐƠN VỊ NỒNG ĐỘ: nồng độ được gắn nhãn ng/µL, nM hoặc % — chỉ là nhãn (đổi đơn vị không chuyển đổi số liệu). "
        "Một tệp CSV đo lường chỉ ghép với JSON hiệu chuẩn khi cả hai có cùng Measurement, Unit và đơn vị nồng độ.\n"
        "ĐIỀU KHIỂN TRỢ LÝ: người dùng gõ / để xem lệnh, nhấn + để bắt đầu cuộc trò chuyện mới, "
        "sửa tin nhắn đã gửi để gửi lại, và đánh giá câu trả lời bằng 👍/👎.\n"
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
        "• '如何更改应用语言 / 打开设置' → 调用 trigger_custom_steps，目标 #settingsBtn\n"
        "仅当用户明确要求完整端到端流程演示时才调用 trigger_guide。\n"
        "检查[App state]：如果模式已匹配，跳过模式切换步骤。\n"
        "调用引导工具后，用一句话确认引导已启动。\n\n"
        "标准曲线领域知识：\n"
        "始终检查 [App state] 并根据当前模式调整系数说明。\n\n"
        "动力学模式（KINETICS）— 标准曲线映射 X=最大速率（ΔAbs/s）→ Y=浓度：\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]："
        "Vmax=酶饱和速率（上限，必须严格大于所有测量速率），Km=亲和力常数（反映浓度随速率的增长幅度）。\n"
        "• 线性  y=a·x+b  [a,b]：a=每单位速率对应的浓度增量，b=零速率时的外推浓度。\n\n"
        "点模式（POINT）— 标准曲线映射 X=已知浓度 → Y=所选时间点的吸光度：\n"
        "• 线性  y=a·x+b  [a,b]：a=灵敏度（每单位浓度的吸光度变化），b=零浓度时的本底吸光度。\n"
        "• 多项式  y=a·x²+b·x+c  [a,b,c]：a=曲率（正=开口向上，负=开口向下），b=线性灵敏度，c=Y轴截距。\n"
        "• 对数  y=a·ln(x+b)+c  [a,b,c]：a=动态范围缩放，b=X轴平移（保持ln参数为正），c=基线。\n"
        "• 指数  y=a·e^(b·x)+c  [a,b,c]：a=振幅，b=增长率（正=上升，负=下降），c=下渐近线。\n\n"
        "R²（0–1）：拟合优度；≥0.99 为可靠校准曲线的标准。\n\n"
        "应用设置——齿轮按钮（#settingsBtn）打开 App Settings：界面语言（6 种）、默认模式与窗口大小、浓度单位、表格排序，"
        "以及（安装版）数据文件夹位置。\n"
        "浓度单位：浓度标注为 ng/µL、nM 或 %——仅为标签（切换单位不会换算数值）。"
        "测量 CSV 仅在与校准 JSON 的 Measurement、Unit 和浓度单位都相同时才能配对。\n"
        "助手控制：用户可输入 / 查看命令、点击 + 开始新对话、编辑已发送的消息以重新发送、用 👍/👎 评价回答。\n"
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
        "• 'comment changer la langue / ouvrir les paramètres ?' → appeler trigger_custom_steps, cible #settingsBtn\n"
        "N'appelez trigger_guide que pour un parcours complet de bout en bout explicitement demandé.\n"
        "Vérifiez [App state] : si le mode correspond déjà, ignorez l'étape de changement de mode.\n"
        "Après avoir appelé un outil guide, confirmez en une phrase.\n\n"
        "CONNAISSANCES DOMAINE — COURBE ÉTALON :\n"
        "Vérifiez toujours [App state] et adaptez l'explication des coefficients au mode actif.\n\n"
        "MODE CINÉTIQUE (KINETICS) — courbe étalon : X=taux maximal (ΔAbs/s) → Y=concentration :\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km] : "
        "Vmax=taux de saturation enzymatique (borne supérieure ; doit strictement dépasser tous les taux mesurés), "
        "Km=constante d'affinité (indique la rapidité de montée en concentration).\n"
        "• Linéaire  y=a·x+b  [a,b] : a=concentration gagnée par unité de taux, "
        "b=concentration extrapolée à taux nul.\n\n"
        "MODE POINT — courbe étalon : X=concentration connue → Y=absorbance au point de temps choisi :\n"
        "• Linéaire  y=a·x+b  [a,b] : a=sensibilité (absorbance par unité de conc.), "
        "b=absorbance de fond à concentration nulle.\n"
        "• Polynomiale  y=a·x²+b·x+c  [a,b,c] : a=courbure (pos=concave vers le haut, nég=vers le bas), "
        "b=sensibilité linéaire, c=ordonnée à l'origine.\n"
        "• Logarithmique  y=a·ln(x+b)+c  [a,b,c] : a=facteur d'échelle dynamique, "
        "b=décalage en x (garde ln positif), c=ligne de base.\n"
        "• Exponentielle  y=a·e^(b·x)+c  [a,b,c] : a=amplitude, "
        "b=taux de croissance (pos=courbe croissante, nég=décroissante), c=asymptote inférieure.\n\n"
        "R² (0–1) : qualité d'ajustement ; ≥0.99 est attendu pour une calibration fiable.\n\n"
        "PARAMÈTRES — le bouton engrenage (#settingsBtn) ouvre App Settings : langue de l'interface (6 langues), "
        "mode et taille de fenêtre par défaut, unité de concentration, tri des tableaux, et (versions installées) l'emplacement du dossier de données.\n"
        "UNITÉS DE CONCENTRATION : une concentration est étiquetée ng/µL, nM ou % — une étiquette seulement "
        "(changer d'unité ne convertit jamais les valeurs). Un CSV de mesure ne s'associe à un JSON d'étalonnage "
        "que si les deux partagent les mêmes Measurement, Unit et unité de concentration.\n"
        "CONTRÔLES DE L'ASSISTANT : tapez / pour les commandes, cliquez + pour une nouvelle conversation, "
        "modifiez un message envoyé pour le renvoyer, et évaluez les réponses avec 👍/👎.\n"
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
        "• 'アプリの言語を変える / 設定を開く' → target #settingsBtn で trigger_custom_steps を呼び出す\n"
        "明示的な完全ワークフローツアーのリクエストのみ trigger_guide を使用してください。\n"
        "[App state]を確認し、モードが既に一致している場合はモード切替ステップをスキップ。\n"
        "ガイドツール呼び出し後、一文で確認してください。\n\n"
        "標準曲線ドメイン知識：\n"
        "常に [App state] を確認し、アクティブなモードに合わせて係数の説明を調整してください。\n\n"
        "動力学モード（KINETICS）— 標準曲線は X=最大速度（ΔAbs/s）→ Y=濃度 を対応付けます：\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]："
        "Vmax=酵素飽和速度（上限；測定速度すべてを厳密に超える必要あり）、"
        "Km=親和性定数（速度に対する濃度の上昇幅を示す）。\n"
        "• 線形  y=a·x+b  [a,b]：a=速度単位あたりの濃度増加量、b=速度ゼロ時の外挿濃度。\n\n"
        "点モード（POINT）— 標準曲線は X=既知濃度 → Y=選択時間点での吸光度 を対応付けます：\n"
        "• 線形  y=a·x+b  [a,b]：a=感度（濃度単位あたりの吸光度変化）、b=ゼロ濃度でのバックグラウンド吸光度。\n"
        "• 多項式  y=a·x²+b·x+c  [a,b,c]：a=曲率（正=上に凸、負=下に凸）、b=線形感度、c=y切片。\n"
        "• 対数  y=a·ln(x+b)+c  [a,b,c]：a=ダイナミックレンジスケール、"
        "b=x軸シフト（lnの引数を正に保つ）、c=ベースライン。\n"
        "• 指数  y=a·e^(b·x)+c  [a,b,c]：a=振幅、"
        "b=増加率（正=上昇曲線、負=下降曲線）、c=下限漸近線。\n\n"
        "R²（0–1）：適合度；信頼できる校正には ≥0.99 が必要。\n\n"
        "アプリ設定 — 歯車ボタン（#settingsBtn）で App Settings を開きます：インターフェース言語（6 言語）、"
        "既定モードとウィンドウサイズ、濃度単位、テーブルの並び順、（インストール版では）データフォルダの場所。\n"
        "濃度単位：濃度は ng/µL、nM、% のいずれかのラベル（ラベルのみで、切り替えても数値は変換されません）。"
        "測定 CSV は、Measurement・Unit・濃度単位がすべて一致する校正 JSON とのみ対応付けられます。\n"
        "アシスタント操作：/ でコマンド一覧、+ で新しい会話、送信済みメッセージを編集して再送信、👍/👎 で回答を評価できます。\n"
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
        "• 'как изменить язык приложения / открыть настройки' → вызвать trigger_custom_steps с target #settingsBtn\n"
        "Вызывайте trigger_guide только для явного полного обзора рабочего процесса.\n"
        "Проверьте [App state]: если режим уже совпадает, пропустите шаг переключения.\n"
        "После вызова инструмента подтвердите запуск одним предложением.\n\n"
        "ЗНАНИЯ ПРЕДМЕТНОЙ ОБЛАСТИ — СТАНДАРТНАЯ КРИВАЯ:\n"
        "Всегда проверяйте [App state] и адаптируйте объяснение коэффициентов к активному режиму.\n\n"
        "КИНЕТИЧЕСКИЙ РЕЖИМ (KINETICS) — стандартная кривая: X=максимальная скорость (ΔAbs/с) → Y=концентрация:\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]: "
        "Vmax=скорость насыщения фермента (верхняя граница; строго больше всех измеренных скоростей), "
        "Km=константа сродства (показывает, как быстро концентрация растёт со скоростью).\n"
        "• Линейная  y=a·x+b  [a,b]: a=прирост концентрации на единицу скорости, "
        "b=экстраполированная концентрация при нулевой скорости.\n\n"
        "ТОЧЕЧНЫЙ РЕЖИМ (POINT) — стандартная кривая: X=известная концентрация → Y=поглощение в выбранной точке времени:\n"
        "• Линейная  y=a·x+b  [a,b]: a=чувствительность (поглощение на единицу конц.), "
        "b=фоновое поглощение при нулевой концентрации.\n"
        "• Полиномиальная  y=a·x²+b·x+c  [a,b,c]: a=кривизна (положит.=вогнутость вверх, отрицат.=вниз), "
        "b=линейная чувствительность, c=точка пересечения Y.\n"
        "• Логарифмическая  y=a·ln(x+b)+c  [a,b,c]: a=масштабирование динамического диапазона, "
        "b=сдвиг по X (сохраняет ln положительным), c=базовая линия.\n"
        "• Экспоненциальная  y=a·e^(b·x)+c  [a,b,c]: a=амплитуда, "
        "b=скорость роста (положит.=возрастающая, отрицат.=убывающая), c=нижняя асимптота.\n\n"
        "R² (0–1): качество подгонки; ≥0.99 требуется для надёжной калибровки.\n\n"
        "НАСТРОЙКИ — кнопка-шестерёнка (#settingsBtn) открывает App Settings: язык интерфейса (6 языков), "
        "режим и размер окна по умолчанию, единица концентрации, порядок сортировки таблиц и (в установленных сборках) расположение папки данных.\n"
        "ЕДИНИЦЫ КОНЦЕНТРАЦИИ: концентрация обозначается ng/µL, nM или % — только метка (переключение единицы "
        "не пересчитывает значения). Измерительный CSV сопоставляется с калибровочным JSON только если у обоих "
        "совпадают Measurement, Unit и единица концентрации.\n"
        "УПРАВЛЕНИЕ АССИСТЕНТОМ: введите / для команд, нажмите + для нового разговора, "
        "отредактируйте отправленное сообщение для повторной отправки и оцените ответы с помощью 👍/👎.\n"
        "Всегда отвечайте на русском языке."
    ),
}

# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_app_context",
            "description": (
                "Get the current state of the Easy OKAPI application: "
                "the data root folder, the CSV files in it, calibration JSON files, and hardware subprocess status."
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
            "description": "Check whether the PyBadge colorimeter data-logger subprocess is running.",
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
                "Collapsed sections are expanded automatically before spotlighting. "
                "Valid IDs: #log-cdc-data #cdc-save-section #run-script-btn #terminate-script-btn "
                "#base-name #timeout-control #interval-control #log-display #go-to-btn "
                "#meas-mode-section #file-selection #cal-json-sel-section #merge-file-btn "
                "#data-display-section #chart-container #range-display #window-size-section "
                "#split-source-section #normalize-mode-section #open-all-analysis-section "
                "#export-analysis #report-section #cal-mode-select "
                "#select-quantity-section #select-regress-algo #export-coef #threshold-value "
                "#select-time-point #report-console-section #report-items-container "
                "#settingsBtn (opens App Settings: language, default mode, concentration unit, data folder) "
                "#user-guide-btn (opens the interactive user guide)"
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
        "The app applies stored regression coefficients automatically.\n"
        "Pairing rule: a measurement CSV and a calibration JSON can be paired only when both share the same "
        "Measurement, Unit, and concentration unit (ConcenUnit); for a mismatched pair the Select button is disabled."
    ),
    "csv_format": (
        "CSV structure:\n"
        "• Metadata lines start with #: Measurement, MeasUnit, TimeUnit, MeasMode, Concentration, ConcenUnit\n"
        "• ConcenUnit is the concentration label — one of ng/µL, nM, or % (absent ⇒ ng/µL for legacy files)\n"
        "• Data header: Timestamp, Value:1, Value:2, …\n"
        "• Calibration CSVs: Concentration, maxRate/Value, Slope, Sat, Time To Sat"
    ),
    "hardware_setup": (
        "PyBadge colorimeter setup:\n"
        "• Connects over USB CDC serial (pyserial) — no admin/sudo, no driver needed\n"
        "• Mac & Windows use the same cross-platform logger (log_cdc_data.py)\n"
        "• VID/PID: 0x239A / 0x8034 (serial)\n"
        "• Fallback: press the device's Left button to 'type' data via keyboard input into any text field"
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
        "• 'Generate quick Report' — snapshot the current chart\n"
        "• 'Export Data to Report' — push data into a named subject folder\n"
        "• Full reports compile multiple report items; items can be exported to a formatted Excel workbook\n"
        "Subjects can be renamed, copied, or deleted from the Report panel."
    ),
    "file_operations": (
        "File operations:\n"
        "• Edit — modify CSV/JSON values in a modal editor\n"
        "• Delete — permanently remove files\n"
        "• Copy — duplicate files\n"
        "• Move — move a CSV between data subfolders\n"
        "• Merge CSV — combine multiple CSV files\n"
        "• Remove columns — delete Value columns from CSV\n"
        "• Export — save calibration results to new CSV/JSON\n"
        "Data files live in subfolders of the data root; subfolders can be created, renamed, and deleted from the file panel."
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

# ── Tool execution ────────────────────────────────────────────────────────────

def _run_tool(name: str, args: dict, ui_context: dict = None) -> str:
    try:
        if name == "get_app_context":
            csv_files = get_file_list(DATA_ROOT)
            json_k = get_file_list(os.path.join(state.json_root_path, "kinetics"), "*.json")
            json_p = get_file_list(os.path.join(state.json_root_path, "point"), "*.json")
            running = state.process is not None and state.process.poll() is None
            return json.dumps({
                "data_directory": DATA_ROOT,
                "csv_files": csv_files,
                "json_calibration_kinetics": json_k,
                "json_calibration_point": json_p,
                "hardware_subprocess_running": running,
            }, ensure_ascii=False)

        elif name == "read_csv_file":
            filename = args.get("filename", "")
            max_rows = min(int(args.get("max_rows", 30)), 100)
            subfolder = (ui_context or {}).get("subfolder", "")
            candidate = os.path.join(DATA_ROOT, subfolder, filename) if subfolder else os.path.join(DATA_ROOT, filename)
            filepath = validate_in_data_root(candidate)
            if not filepath or not os.path.exists(filepath):
                return json.dumps({"error": f"'{filename}' not found in the selected data folder."})
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


# ── Groq chat ─────────────────────────────────────────────────────────────────

def _groq_chat(api_key: str, model: str, messages: list, tools: list) -> dict:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 500,
        }
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
        "descriptions": {
            "vi": "Nhấp 'Generate quick Report' tại đây để chụp nhanh biểu đồ và phân tích hiện tại thành báo cáo HTML độc lập.",
            "zh": "点击此处的「Generate quick Report」即时将当前图表和分析快照为独立的 HTML 报告。",
            "fr": "Cliquez sur 'Generate quick Report' ici pour capturer instantanément le graphique et l'analyse en cours sous forme de rapport HTML autonome.",
            "ja": "ここで「Generate quick Report」をクリックして、現在のチャートと分析を独立した HTML レポートとして即時スナップショットします。",
            "ru": "Нажмите «Generate quick Report», чтобы мгновенно сохранить текущий график и анализ как автономный HTML-отчёт.",
        },
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
        "descriptions": {
            "vi": "Chọn tệp dữ liệu CSV để tải phân tích trước khi tạo báo cáo.",
            "zh": "选择一个 CSV 数据文件以在生成报告之前加载您的分析。",
            "fr": "Sélectionnez un fichier de données CSV pour charger votre analyse avant de générer un rapport.",
            "ja": "レポートを生成する前に分析を読み込むため CSV データファイルを選択してください。",
            "ru": "Выберите CSV-файл данных для загрузки анализа перед созданием отчёта.",
        },
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
        "descriptions": {
            "vi": "Khi dữ liệu đã tải, nhấp 'Generate quick Report' tại đây để chụp nhanh biểu đồ và phân tích hiện tại.",
            "zh": "数据加载后，点击此处的「Generate quick Report」以快照当前图表和分析。",
            "fr": "Une fois les données chargées, cliquez sur 'Generate quick Report' ici pour capturer le graphique et l'analyse.",
            "ja": "データが読み込まれたら、ここで「Generate quick Report」をクリックして現在のチャートと分析をスナップショットします。",
            "ru": "После загрузки данных нажмите «Generate quick Report» для снимка текущего графика и анализа.",
        },
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
        "descriptions": {
            "vi": "Nhấp 'Export Data to Report' để lưu ảnh chụp phân tích này vào chủ đề báo cáo đặt tên để tổng hợp sau.",
            "zh": "点击「Export Data to Report」将此分析快照保存到命名报告主题中，供后续汇编。",
            "fr": "Cliquez sur 'Export Data to Report' pour enregistrer ce snapshot d'analyse dans un sujet de rapport nommé pour une compilation ultérieure.",
            "ja": "「Export Data to Report」をクリックして、後で使うためこの分析スナップショットを名前付きレポートテーマに保存します。",
            "ru": "Нажмите «Export Data to Report», чтобы сохранить снимок анализа в именованную тему отчёта для последующей компиляции.",
        },
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
        "descriptions": {
            "vi": "Sau khi xuất, chuyển sang chế độ Report ở đây để mở giao diện quản lý báo cáo đầy đủ.",
            "zh": "导出后，在此切换到 Report 模式以打开完整的报告管理界面。",
            "fr": "Après l'exportation, passez en mode Report ici pour ouvrir l'interface complète de gestion des rapports.",
            "ja": "エクスポート後、ここで Report モードに切り替えてレポート管理インターフェイスを開きます。",
            "ru": "После экспорта переключитесь в режим Report, чтобы открыть полный интерфейс управления отчётами.",
        },
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
        "descriptions": {
            "vi": "Quản lý các ảnh chụp phân tích đã lưu tại đây. Cấu hình tùy chọn bố cục và đặt tiêu đề báo cáo.",
            "zh": "在此管理已保存的分析快照。配置布局选项并设置报告标题。",
            "fr": "Gérez vos snapshots d'analyse sauvegardés ici. Configurez les options de mise en page et définissez un titre de rapport.",
            "ja": "ここで保存された分析スナップショットを管理します。レイアウトオプションを設定してレポートのタイトルを設定してください。",
            "ru": "Управляйте сохранёнными снимками анализа здесь. Настройте параметры макета и задайте название отчёта.",
        },
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
        "descriptions": {
            "vi": "Tất cả ảnh chụp đã lưu được liệt kê ở đây. Xóa bất kỳ ảnh nào bạn không muốn trước khi tạo báo cáo cuối.",
            "zh": "所有已保存的快照都列在这里。在生成最终报告之前删除不需要的快照。",
            "fr": "Tous les snapshots sauvegardés sont listés ici. Supprimez ceux que vous ne souhaitez pas avant de générer le rapport final.",
            "ja": "保存されたすべてのスナップショットがここに一覧表示されます。最終レポートを生成する前に不要なものを削除してください。",
            "ru": "Все сохранённые снимки перечислены здесь. Удалите ненужные перед созданием финального отчёта.",
        },
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
        "descriptions": {
            "vi": "Tổng hợp tất cả mục thành báo cáo HTML có thể in. Mở trong trình duyệt, sau đó dùng In → Lưu thành PDF.",
            "zh": "将所有项目编译为可打印的 HTML 报告。在浏览器中打开，然后使用打印 → 另存为 PDF。",
            "fr": "Compilez tous les éléments en rapport HTML imprimable. Ouvrez dans votre navigateur, puis Imprimer → Enregistrer en PDF.",
            "ja": "すべての項目を印刷可能な HTML レポートにまとめます。ブラウザで開き、印刷 → PDF として保存を使用してください。",
            "ru": "Скомпилируйте все элементы в печатаемый HTML-отчёт. Откройте в браузере, затем Печать → Сохранить как PDF.",
        },
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
        "descriptions": {
            "vi": "Quản lý các ảnh chụp phân tích đã lưu tại đây. Cấu hình bố cục và đặt tiêu đề báo cáo.",
            "zh": "在此管理已保存的分析快照。配置布局并设置报告标题。",
            "fr": "Gérez vos snapshots d'analyse sauvegardés ici. Configurez la mise en page et définissez un titre de rapport.",
            "ja": "ここで保存された分析スナップショットを管理します。レイアウトを設定してレポートのタイトルを設定してください。",
            "ru": "Управляйте сохранёнными снимками анализа здесь. Настройте макет и задайте название отчёта.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "#report-items-container",
        "title": "Report Items",
        "description": "All saved snapshots are listed here. Remove any before generating.",
        "descriptions": {
            "vi": "Tất cả ảnh chụp đã lưu được liệt kê ở đây. Xóa bất kỳ ảnh nào trước khi tạo.",
            "zh": "所有已保存的快照都列在这里。在生成之前删除不需要的快照。",
            "fr": "Tous les snapshots sauvegardés sont listés ici. Supprimez-en avant de générer.",
            "ja": "保存されたすべてのスナップショットがここに一覧表示されます。生成前に不要なものを削除してください。",
            "ru": "Все сохранённые снимки перечислены здесь. Удалите ненужные перед созданием.",
        },
        "position": "right",
        "skipInteraction": True,
    },
    {
        "target": "button[onclick=\"finalizeReportExcel()\"]",
        "title": "Export as Excel",
        "description": "Download all items as a formatted Excel workbook with embedded charts.",
        "descriptions": {
            "vi": "Tải xuống tất cả mục dưới dạng bảng tính Excel được định dạng với biểu đồ nhúng.",
            "zh": "将所有项目下载为带有嵌入图表的格式化 Excel 工作簿。",
            "fr": "Téléchargez tous les éléments sous forme de classeur Excel formaté avec graphiques intégrés.",
            "ja": "すべての項目を埋め込みグラフ付きのフォーマットされた Excel ワークブックとしてダウンロードします。",
            "ru": "Загрузите все элементы как форматированную Excel-книгу со встроенными графиками.",
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
    "measurement", "pybadge", "cdc", "regression", "standard curve", "r squared",
    "michaelis", "menten", "export", "report", "timeout", "interval", "biosensor",
    "mode", "chart", "graph", "file", "directory", "hardware", "device", "sensor",
    "concentration", "slope", "saturation", "maxrate", "threshold", "workflow",
    "tutorial", "walkthrough", "overview", "getting started", "how to use",
    "how does this", "introduction", "guide me", "show me how",
    "setting", "language", "concenunit", "data folder", "data root", "subfolder",
    "rename", "feedback",
    # Multilingual inclusions
    "hiệu chuẩn", "động học", "báo cáo", "nồng độ", "kết quả", # vi
    "校准", "动力学", "测量", "报告", "浓度", # zh
    "calibration", "cinétique", "mesure", "rapport", "concentration", # fr
    "キャリブレーション", "キネティクス", "測定", "レポート", "濃度", # ja
    "калибровка", "кинетика", "измерение", "отчёт", "концентрация", # ru
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


# Phrases that indicate the user wants a conceptual explanation, not UI navigation.
# Queries containing these should go to Groq rather than be short-circuited to a guide.
_CONCEPTUAL_MARKERS = frozenset({
    # English — explanatory starters ("how to" is intentionally absent; it signals navigation)
    "what is", "what are", "what does", "what do", "what's",
    "why", "why is", "why does", "why do",
    "explain", "describe", "tell me about", "what does it mean",
    "meaning of", "definition of", "difference between",
    "how does", "how do", "how is",
    # Vietnamese
    "là gì", "nghĩa là", "tại sao", "giải thích", "khác nhau",
    # Chinese
    "什么是", "为什么", "解释", "区别", "意思",
    # French
    "qu'est-ce", "pourquoi", "expliquer", "signifie", "différence",
    # Japanese
    "とは", "なぜ", "説明", "違い", "意味",
    # Russian
    "что такое", "почему", "объясни", "разница", "значит",
})

# Phrases that carry an explicit navigation / how-to-do-it signal.
# A query must contain at least one of these to be short-circuited to a guide.
# Checked BEFORE _CONCEPTUAL_MARKERS so that more-specific phrases like
# "how do i" take priority over the broader "how do" conceptual marker.
_NAV_MARKERS = frozenset({
    # English
    "how to", "how do i", "how can i", "where is", "where do i", "where can i",
    "show me", "take me to", "navigate to", "go to", "find the", "open the",
    "step by step", "walk me through", "guide me", "walk me",
    # Vietnamese
    "cách", "làm thế nào", "ở đâu", "hướng dẫn tôi", "chỉ tôi", "chỉ cho tôi",
    # Chinese
    "怎么", "如何", "在哪", "带我", "找到",
    # French
    "comment faire", "comment", "où est", "montre-moi", "guidez-moi",
    # Japanese
    "どうやって", "どこ", "やり方", "使い方",
    # Russian
    "как мне", "как", "где", "покажи", "найти",
})


def _has_nav_intent(query: str) -> bool:
    """True only when the query carries an explicit navigation/how-to signal.

    NAV markers are checked before conceptual markers so that precise phrases
    like 'how do i' take priority over the broader 'how do' conceptual marker.
    Bare topic phrases with neither marker (e.g. 'kinetics settings') return
    False and fall through to the LLM rather than being short-circuited to a
    guide.
    """
    q = query.lower()
    if any(marker in q for marker in _NAV_MARKERS):
        return True
    if any(marker in q for marker in _CONCEPTUAL_MARKERS):
        return False
    return False


def _is_conceptual(query: str) -> bool:
    """True when the query is asking for an explanation rather than how to do something.

    Conceptual questions ("what is R²", "why does Vmax matter") are routed to the LLM
    so it can explain, rather than short-circuited to a UI guide.
    """
    q = query.lower()
    return any(marker in q for marker in _CONCEPTUAL_MARKERS)


# A keyword score this high (≈ two strong keyword hits) is treated as a confident
# match, enough to launch a guide for imperative commands that carry no explicit
# nav marker (e.g. "switch to point mode", "change the interval", "merge two files").
_STRONG_MATCH_SCORE = 1.6

# A single solid keyword hit. The nav/how-to path requires at least this much so
# that an incidental fuzzy match (0.8) on one out-of-context word — e.g. "select"
# in "select a regression algorithm" matching the file-selection guide — cannot
# hijack the query into an unrelated guide.
_NAV_LAUNCH_SCORE = 1.0

# Explicit "give me the whole tour" phrasings. The intent here is unambiguous, so
# a matched guide may launch on a weak keyword score (e.g. "walkthrough" fuzzily
# matching "walk me through the whole app").
_TOUR_MARKERS = frozenset({
    "walk me through", "walkthrough", "walk through", "step by step",
    "step-by-step", "guide me through", "full tour", "whole app", "entire app",
    "tour of the app", "show me everything", "from scratch",
    # Multilingual
    "toàn bộ", "từng bước", "hướng dẫn toàn bộ",            # vi
    "完整流程", "逐步", "整个应用",                              # zh
    "tout le processus", "pas à pas", "visite complète",   # fr
    "アプリ全体", "ステップバイステップ", "全体の流れ",                  # ja
    "пошагово", "весь процесс", "всё приложение",          # ru
})


def _is_tour_request(query: str) -> bool:
    """True when the query explicitly asks for a full, end-to-end walkthrough."""
    q = query.lower()
    return any(marker in q for marker in _TOUR_MARKERS)


def _should_launch_guide(query: str, score: float) -> bool:
    """Decide whether a matched guide example should be short-circuited to the UI.

    Fires on (a) an explicit full-tour request with any usable match, (b) a
    navigation/how-to phrasing backed by at least one solid keyword hit, or
    (c) a strong keyword match that is not a conceptual question. Conceptual
    questions always fall through to the LLM.

    Tour and nav intent are checked before the conceptual gate so that precise
    phrasings like "how do i" take priority over the broader "how do" conceptual
    marker.
    """
    if _is_tour_request(query) and score >= 0.7:
        return True
    if _has_nav_intent(query) and score >= _NAV_LAUNCH_SCORE:
        return True
    if _is_conceptual(query):
        return False
    return score >= _STRONG_MATCH_SCORE


def resolve_guide(query: str, ui_context: dict = None, language: str = "en"):
    """Local (no-LLM) guide resolution for the desktop client.

    Runs the same intent pipeline as the chat short-circuit — greeting/out-of-
    scope rejection, fuzzy keyword matching, and the firing gate — entirely on
    this machine, so UI-navigation guides resolve against THIS app's own UI
    instead of being delegated to the cloud proxy (whose UI differs).

    Returns (guide_id, steps) when a guide should launch, else (None, None).
    `steps` already includes the file-select / translation handling applied by
    _format_fewshot_hint.
    """
    ui_context = ui_context or {}
    if not query or _is_greeting(query) or _is_out_of_scope(query):
        return None, None
    matched, score = _match_guide_example(query, ui_context, language)
    if not matched or not _should_launch_guide(query, score):
        return None, None
    steps = _format_fewshot_hint(matched, ui_context, language, steps_only=True)
    return matched["id"], steps


def chat_stream(messages: list, language: str, api_key: str, model: str, ui_context: dict = None):
    """Generator yielding SSE event dicts."""
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

    matched, match_score = _match_guide_example(last_user_query, ui_context or {}, language)
    if matched and _should_launch_guide(last_user_query, match_score):
        steps = _format_fewshot_hint(matched, ui_context or {}, language, steps_only=True)
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": steps}}
        return

    full_messages = [{"role": "system", "content": system_prompt}] + messages
    guide_action = None

    for _ in range(6):
        result = _groq_chat(api_key, model, full_messages, TOOLS)
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
            tool_result = _run_tool(tool_name, tool_args, ui_context)
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
            yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
            yield {"type": "guide", "guide_action": guide_action}
            return

    yield {"type": "error", "error": "max_iterations"}


def get_guide_examples(lang: str = "en") -> list:
    return _load_guide_examples(lang)


def proxy_chat_stream(messages, language, license_token, proxy_url, model, ui_context=None):
    """Generator yielding SSE event dicts via the online proxy server."""
    import requests as http_req

    # Send this machine's fingerprint so the proxy can confirm the license token
    # is being presented from the machine it was hardware-locked to.
    try:
        import hwid as _hwid_mod
        machine_id = _hwid_mod.get_hwid()
    except Exception:
        machine_id = ''

    payload = {
        'messages': messages,
        'language': language,
        'license_token': license_token,
        'hwid': machine_id,
        'model': model,
        'ui_context': ui_context or {},
    }

    try:
        resp = http_req.post(
            f"{proxy_url}/ai/proxy/chat",
            json=payload,
            stream=True,
            timeout=(10, 120),
        )
        if resp.status_code == 401:
            yield {'type': 'error', 'error': 'license_invalid'}
            return
        if resp.status_code == 503:
            yield {'type': 'error', 'error': 'service_unavailable'}
            return
        # Any other non-2xx (e.g. a 400 the proxy raises for an unsupported
        # request) should surface as a friendly message, not a raw HTTPError
        # string from raise_for_status().
        if resp.status_code >= 400:
            yield {'type': 'error', 'error': 'service_unavailable'}
            return

        for line in resp.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode('utf-8')
            if not line.startswith('data: '):
                continue
            raw = line[6:]
            if raw == '[DONE]':
                return
            try:
                event = json.loads(raw)
                yield event
            except (ValueError, KeyError):
                pass

    except http_req.exceptions.ConnectionError:
        yield {'type': 'error', 'error': 'proxy_unreachable'}
    except http_req.exceptions.Timeout:
        yield {'type': 'error', 'error': 'proxy_timeout'}
    except Exception as e:
        yield {'type': 'error', 'error': str(e)}
