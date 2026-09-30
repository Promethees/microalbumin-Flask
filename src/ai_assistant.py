from __future__ import annotations

import difflib
import json
import os
import re
from file_path import DATA_ROOT, validate_in_data_root, validate_in_json_root
from file import get_file_list
import state
import ai_feedback

# ── Guide training examples (few-shot injection) ──────────────────────────────

# Read-only bundled assets: resolve from the bundle root (== project root in dev,
# sys._MEIPASS in a frozen build).
_GUIDE_TRAINING_PATH = os.path.join(state.bundle_dir, "guide_training.json")
_GUIDE_TRANSLATIONS_DIR = os.path.join(state.bundle_dir, "guide_translations")

# One language list (Rule.md §2.22): the supported-language registry.
import user_settings as _user_settings  # noqa: E402

VALID_LANGS = frozenset(_user_settings.SUPPORTED_LANGUAGES)


def _overlay_step_translations(ex_steps: list, translated: list) -> list:
    """Per-step {description, title} translations for one guide (B8 / A15).

    Overlay steps come in two shapes, and one guide may use either:
      * ``{"target": …, "description": …, "title": …}`` — matched by TARGET, so
        inserting or reordering a step in guide_training.json can never shift a
        translation onto the wrong element. A target used more than once in a
        guide is matched in order of appearance.
      * a plain string — the legacy positional form (description only).
    Returns one dict per EN step (empty when there is no translation).
    """
    keyed: dict = {}
    for t in translated:
        if isinstance(t, dict) and isinstance(t.get("target"), str):
            keyed.setdefault(t["target"], []).append(t)
    used: dict = {}
    out = []
    for i, step in enumerate(ex_steps):
        target = step.get("target")
        entry = {}
        if keyed:
            candidates = keyed.get(target, [])
            k = used.get(target, 0)
            if k < len(candidates):
                entry = candidates[k]
                used[target] = k + 1
        elif i < len(translated) and isinstance(translated[i], str):
            entry = {"description": translated[i]}
        out.append(entry)
    return out


def _apply_overlay(examples: list, lang: str) -> list:
    if lang not in VALID_LANGS:
        return examples
    overlay_path = os.path.join(_GUIDE_TRANSLATIONS_DIR, f"{lang}.json")
    try:
        with open(overlay_path, "r", encoding="utf-8") as f:
            overlay = json.load(f)
    except Exception:
        return examples
    index = {item["id"]: item for item in overlay if isinstance(item, dict) and "id" in item}
    result = []
    for ex in examples:
        item = index.get(ex["id"])
        if not item:
            result.append(ex)
            continue
        new_steps = []
        for step, tr in zip(ex["steps"], _overlay_step_translations(ex["steps"], item.get("steps", []))):
            new_step = {**step, "description": tr.get("description") or step["description"]}
            if tr.get("title"):
                new_step["title"] = tr["title"]
            new_steps.append(new_step)
        extra_queries = [q for q in item.get("queries", []) if isinstance(q, str) and q]
        result.append({**ex, "steps": new_steps, "queries": ex["queries"] + extra_queries})
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
            if isinstance(kw, str):
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


# ── Keyword scoring (shared verbatim by main and online — keep in lockstep) ───
# Work-list items A6/A7 (online) and B3 (main). Three rules stop the score
# inflation that let an unrelated statement launch a guide at 6.0:
#
#   1. A direct phrase hit must sit on word boundaries and be a real word
#      (>= 4 chars, >= 2 for CJK, not a stop-word). Plain substring matching let
#      overlay keywords such as "le"/"de" hit inside "coefficient"/"mode", and
#      "merge" hit inside "unmerge". The leading boundary also refuses a
#      hyphenated negation/derivation prefix ("un-merge", "re-export", "de-select");
#      short keywords (< 6 chars) must end on a boundary too, longer ones may
#      continue as a stem ("calibrat" → "calibration").
#   2. Each distinct set of content words counts ONCE per guide
#      (_score_guide_keywords), so ten paraphrases of "concentration" no
#      longer sum to 8.
#   3. The mode bonus is added only on top of a solid baseline (see the matcher).

def _phrase_hit(kw_lower: str, q_lower: str) -> bool:
    """True when kw_lower occurs in q_lower as a phrase on word boundaries."""
    if _is_cjk(kw_lower):
        return kw_lower in q_lower
    pattern = r"(?<![\w-])" + re.escape(kw_lower)
    if len(kw_lower) < 6:
        pattern += r"(?!\w)"
    return re.search(pattern, q_lower) is not None


def _phrase_tokens(text: str) -> frozenset:
    """Non-stop-word tokens of >= 2 chars (a CJK run counts as one token).

    Unlike _content_words (a 4-char floor, for fuzzy matching), short real
    words such as 'app', 'log' or 'csv' count here: they make a phrase more
    specific ('app settings' vs 'settings', 'log data' vs 'data').
    """
    out = set()
    for w in text.lower().split():
        w = w.strip(_EDGE_PUNCT)
        if len(w) >= 2 and w not in _STOPWORDS:
            out.add(w)
    return frozenset(out)


def _same_word(a: str, b: str) -> bool:
    """Equal, or equal up to an English plural 's' ('file' / 'files')."""
    return a == b or a == b + "s" or b == a + "s"


def _same_token_set(a: frozenset, b: frozenset) -> bool:
    return all(any(_same_word(x, y) for y in b) for x in a) and all(
        any(_same_word(x, y) for x in a) for y in b
    )


def _keyword_hit(kw: str, q_lower: str, q_content: frozenset, q_tokens: frozenset):
    """(score, dedup_key, strong) for one keyword against the query."""
    kw_lower = kw.lower().strip()
    min_len = 2 if _is_cjk(kw_lower) else 4
    kw_content = _content_words(kw_lower)
    kw_tokens = _phrase_tokens(kw_lower)
    specificity = 1.0 + 0.8 * max(0, len(kw_tokens) - 1)
    # 1. Exact phrase on word boundaries — weighted by specificity so one long,
    #    specific phrase ('export data to report') outranks a pile of short
    #    generic keywords.
    if len(kw_lower) >= min_len and kw_lower not in _STOPWORDS and _phrase_hit(kw_lower, q_lower):
        key = kw_tokens or frozenset([kw_lower])
        return specificity, key, len(kw_tokens) >= 2 or _is_cjk(kw_lower)
    # 2. Full coverage: the query says exactly what the keyword says, stop-words
    #    and plurals aside ('how to calibrate' vs the keyword 'how calibrate').
    #    A query that says MORE ('change the concentration unit' vs 'get
    #    concentration') falls through to the partial scores below.
    if kw_tokens and q_tokens and _same_token_set(kw_tokens, q_tokens):
        return specificity, kw_tokens, len(kw_tokens) >= 2
    if not kw_content:
        return 0.0, None, False
    # 3. Partial (fuzzy, prefix-aware) content-word matches.
    if len(kw_content) == 1:
        word = next(iter(kw_content))
        if len(word) < 5:
            return 0.0, None, False
        if any(_token_match(word, qw) for qw in q_content):
            return 0.8, kw_content, False
        return 0.0, None, False
    if all(any(_token_match(kw_word, qw) for qw in q_content) for kw_word in kw_content):
        return 0.8, kw_content, True
    return 0.0, None, False


def _score_keyword(kw: str, q_lower: str, q_content: frozenset, q_tokens: frozenset = None) -> float:
    if q_tokens is None:
        q_tokens = _phrase_tokens(q_lower)
    return _keyword_hit(kw, q_lower, q_content, q_tokens)[0]


def _score_guide_keywords(keywords, q_lower: str, q_content: frozenset,
                          q_tokens: frozenset = None) -> tuple[float, bool, int]:
    """Sum a guide's keyword scores, counting each distinct word set once.

    Returns (score, strong_hit, hits). ``strong_hit`` is True when at least one
    hit came from a multi-word keyword (exact phrase, full coverage, or all its
    content words present) or a CJK phrase — the evidence a no-"how do I"
    launch needs (see _should_launch_guide); a single generic word
    ("concentration", "chart") never counts as strong on its own. ``hits`` (the
    raw number of matching keywords) only breaks ties between guides.
    """
    if q_tokens is None:
        q_tokens = _phrase_tokens(q_lower)
    best: dict = {}
    strong = False
    hits = 0
    for kw in keywords or ():
        if not isinstance(kw, str) or not kw.strip():
            continue
        sc, key, is_strong = _keyword_hit(kw, q_lower, q_content, q_tokens)
        if sc <= 0:
            continue
        hits += 1
        strong = strong or is_strong
        if sc > best.get(key, 0.0):
            best[key] = sc
    return sum(best.values()), strong, hits


def _condition_excludes(conditions: dict, mode: str) -> bool:
    """True when a guide's hard ``conditions`` rule it out in ``mode``."""
    if conditions.get("mode") and mode != conditions["mode"]:
        return True
    if conditions.get("mode_not") and mode == conditions["mode_not"]:
        return True
    if conditions.get("mode_in") is not None and mode not in conditions["mode_in"]:
        return True
    if conditions.get("mode_not_in") and mode in conditions["mode_not_in"]:
        return True
    return False


def _mode_bonus(conditions: dict, mode: str) -> float:
    if conditions.get("mode") and mode == conditions["mode"]:
        return 2.0
    if conditions.get("mode_in") and mode in conditions["mode_in"]:
        return 2.0
    if conditions.get("mode_not"):
        return 1.0
    return 0.0

def _match_guide_detail(query: str, ui_context: dict, lang: str = "en"):
    """Best guide for ``query`` as (example, score, strong_hit), or (None, 0, False).

    The relevance gate (baseline >= 0.1) and the mode bonus look at the
    BASELINE keyword score only (B3/B4): neither a guide's mode condition nor
    its learned 👍 vocabulary/weight can lift a guide the query never
    mentions. Learned terms and the (clamped) learned weight are added only
    after the gate.
    """
    examples = _load_guide_examples(lang)
    if not examples:
        return None, 0, False

    q_lower = (query or "").lower()
    vocab = _guide_vocabulary(examples)
    q_content = _canonicalize_content(_content_words(q_lower), vocab)
    q_tokens = _canonicalize_content(_phrase_tokens(q_lower), vocab)
    mode = (ui_context or {}).get("mode", "")
    best_score: float = 0
    best_hits = 0
    best = None
    best_strong = False
    # Learned feedback weights apply only while the opt-out toggle is on. Read it
    # once here, never inside the per-guide loop below.
    fb_on = ai_feedback.is_enabled()

    for ex in examples:
        conditions = ex.get("conditions") or {}
        if _condition_excludes(conditions, mode):
            continue
        ex_id = ex.get("id", "")
        baseline, strong, hits = _score_guide_keywords(ex.get("queries", []), q_lower, q_content, q_tokens)
        if baseline < 0.1:
            continue
        score = baseline
        if baseline >= _NAV_LAUNCH_SCORE:
            score += _mode_bonus(conditions, mode)
        if fb_on:
            learned = ai_feedback.learned_terms(ex_id)
            if learned:
                learned_score, _, _ = _score_guide_keywords(learned, q_lower, q_content, q_tokens)
                score += learned_score
            # 👍 lifts this guide, 👎 suppresses it (clamped in ai_feedback); a
            # negative weight can push a genuine match below the launch gate.
            score += ai_feedback.learned_bonus(ex_id)

        # Ties go to the guide with more matching keywords (breadth of
        # evidence) — dedup no longer lets that breadth inflate the score.
        if (score, hits) > (best_score, best_hits):
            best_score, best_hits, best, best_strong = score, hits, ex, strong

    return (best, best_score, best_strong) if best_score >= 0.1 else (None, 0, False)


def _match_guide_example(query: str, ui_context: dict, lang: str = "en") -> tuple[dict, float] | tuple[None, float]:
    best, score, _strong = _match_guide_detail(query, ui_context, lang)
    return best, score


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
        "ko": '앱이 아직 초기화되지 않았습니다. 이 가이드를 계속하기 전에 "시작하기"를 클릭하여 기본 화면을 불러오세요.',
    },
    "position": "right",
    "skipInteraction": False,
}

# Prepended (via a guide's soft ``requires_mode``) when the feature the guide
# targets only exists in a particular measurement mode and the app is currently
# in a different one — the mode name (a technical term) is interpolated as-is.
# Unlike a guide's hard ``conditions.mode`` (which EXCLUDES the guide from
# matching outside that mode), ``requires_mode`` keeps the guide matchable
# everywhere and instead corrects the user with this switch-mode step, so a
# strong query ("save linearity range") never falls through to the LLM and lands
# on an unrelated screen.
_MODE_SWITCH_STEP = {
    "target": "#meas-mode-section",
    "title": "Switch Measurement Mode",
    "description": "This feature is only available in {mode} mode. Click here to switch to {mode} mode first, then reopen this guide.",
    "descriptions": {
        "vi": "Tính năng này chỉ có trong chế độ {mode}. Nhấp vào đây để chuyển sang chế độ {mode} trước, rồi mở lại hướng dẫn này.",
        "zh": "此功能仅在 {mode} 模式下可用。请先点击此处切换到 {mode} 模式，然后重新打开本指南。",
        "fr": "Cette fonction n'est disponible qu'en mode {mode}. Cliquez ici pour passer d'abord en mode {mode}, puis rouvrez ce guide.",
        "ja": "この機能は {mode} モードでのみ利用できます。まずここをクリックして {mode} モードに切り替え、このガイドを開き直してください。",
        "ru": "Эта функция доступна только в режиме {mode}. Нажмите здесь, чтобы сначала переключиться в режим {mode}, затем снова откройте руководство.",
        "ko": "이 기능은 {mode} 모드에서만 사용할 수 있습니다. 먼저 여기를 클릭해 {mode} 모드로 전환한 뒤 이 가이드를 다시 여세요.",
    },
    "position": "right",
    "skipInteraction": False,
}


def _mode_switch_step(mode, language: str) -> dict:
    """A localized 'switch to <mode> mode' step (mode name kept as-is).

    ``mode`` may be a single mode string or a list of acceptable modes; a list is
    joined with ' / ' (a language-neutral separator, since mode names stay in
    English) — e.g. 'kinetics / point'.
    """
    label = " / ".join(mode) if isinstance(mode, (list, tuple)) else mode
    step = _translate_step(_MODE_SWITCH_STEP, language)
    return {**step, "description": step["description"].format(mode=label)}


def _requires_mode_satisfied(req_mode, mode: str) -> bool:
    """True when the current ``mode`` meets a guide's soft ``requires_mode``
    (a single mode string or a list of acceptable modes)."""
    if isinstance(req_mode, (list, tuple)):
        return mode in req_mode
    return mode == req_mode


def _guide_example_by_id(guide_id: str, language: str = "en"):
    """Load a single guide example (localized) by id, or None if absent."""
    return next(
        (e for e in _load_guide_examples(language) if e.get("id") == guide_id), None
    )


def _format_fewshot_hint(example: dict, ui_context: dict, language: str = "en", steps_only: bool = False):
    steps = list(example["steps"])
    if example.get("requires_data_loaded") and not ui_context.get("data_loaded"):
        steps = [_translate_step(_FILE_SELECT_STEP, language)] + steps
    # Soft mode gate: correct the user into the right mode FIRST (prepended last so
    # it lands ahead of the file-select step). requires_mode may be a single mode
    # or a list of acceptable modes (e.g. editing a calibration JSON needs the
    # Select-Coefficients panel, shown only in kinetics/point).
    req_mode = example.get("requires_mode")
    if req_mode and not _requires_mode_satisfied(req_mode, (ui_context or {}).get("mode")):
        steps = [_mode_switch_step(req_mode, language)] + steps
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
    "ko": (
        "안녕하세요! 저는 OKAPI Assistant입니다. Easy OKAPI에 대해 도와드릴 수 있습니다 — "
        "데이터 분석, 캘리브레이션, 하드웨어 설정, 앱 탐색 등. "
        "무엇을 도와드릴까요?"
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
    "ko": (
        "저는 Easy OKAPI에 대해서만 도움을 드릴 수 있습니다 — 비색계 데이터 분석, "
        "캘리브레이션, 하드웨어 설정, 앱 탐색. "
        "해당 주제는 도와드릴 수 없습니다. Easy OKAPI에 대해 궁금한 점이 있으신가요?"
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
        "ANSWER-DIRECTLY RULE:\n"
        "If you can answer from your own knowledge — what Easy OKAPI is or does, what a term, mode, or "
        "coefficient means, how something works — reply in plain text and do NOT call any tool. "
        "Call a tool ONLY to fetch live data (files, calibration, hardware) or to launch a navigation "
        "guide the user asked for.\n\n"
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
        "POINT MODE — standard curve maps X=known concentration → Y=absorbance. "
        "For a time-series file the Y value is read at the selected time point; for a Turn file "
        "(each recorded Turn is one standard, no time axis) the Turn's own value is used directly, "
        "the user assigns a concentration per Turn, and replicate Turns at the same concentration "
        "are averaged. A Turn data file pairs only with a Turn calibration curve, a time-series file "
        "only with a time-based one:\n"
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
        "APP SETTINGS — the gear button (#settingsBtn) opens App Settings: interface Language (7 languages), "
        "default mode & window size, concentration unit, table sort order, and (installed builds) the data-folder location.\n"
        "CONCENTRATION UNITS: a concentration is labelled ng/µL, nM, %, or CFU — a label only (switching the unit never "
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
        "QUY TẮC TRẢ LỜI TRỰC TIẾP:\n"
        "Nếu bạn có thể trả lời từ kiến thức của mình — Easy OKAPI là gì hoặc làm gì, ý nghĩa của một thuật ngữ, "
        "chế độ hay hệ số, cách hoạt động — hãy trả lời bằng văn bản và KHÔNG gọi bất kỳ công cụ nào. "
        "Chỉ gọi công cụ để lấy dữ liệu thực tế (tệp, hiệu chuẩn, phần cứng) hoặc để khởi động hướng dẫn "
        "điều hướng khi người dùng yêu cầu.\n\n"
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
        "CÀI ĐẶT ỨNG DỤNG — nút bánh răng (#settingsBtn) mở App Settings: Ngôn ngữ giao diện (7 ngôn ngữ), "
        "chế độ & kích thước cửa sổ mặc định, đơn vị nồng độ, thứ tự sắp xếp bảng, và (bản cài đặt) vị trí thư mục dữ liệu.\n"
        "ĐƠN VỊ NỒNG ĐỘ: nồng độ được gắn nhãn ng/µL, nM, % hoặc CFU — chỉ là nhãn (đổi đơn vị không chuyển đổi số liệu). "
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
        "直接回答规则：\n"
        "如果可以凭借自身知识回答——Easy OKAPI 是什么或能做什么、某个术语、模式或系数的含义、工作原理——"
        "请直接用文字回答，不要调用任何工具。"
        "仅在需要获取实时数据（文件、校准、硬件）或用户要求启动导航引导时才调用工具。\n\n"
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
        "应用设置——齿轮按钮（#settingsBtn）打开 App Settings：界面语言（7 种）、默认模式与窗口大小、浓度单位、表格排序，"
        "以及（安装版）数据文件夹位置。\n"
        "浓度单位：浓度标注为 ng/µL、nM、% 或 CFU——仅为标签（切换单位不会换算数值）。"
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
        "RÈGLE DE RÉPONSE DIRECTE :\n"
        "Si vous pouvez répondre à partir de vos connaissances — ce qu'est ou fait Easy OKAPI, la signification "
        "d'un terme, d'un mode ou d'un coefficient, le fonctionnement — répondez en texte et n'appelez AUCUN outil. "
        "N'appelez un outil que pour récupérer des données en direct (fichiers, calibration, matériel) ou pour "
        "lancer un guide de navigation demandé par l'utilisateur.\n\n"
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
        "PARAMÈTRES — le bouton engrenage (#settingsBtn) ouvre App Settings : langue de l'interface (7 langues), "
        "mode et taille de fenêtre par défaut, unité de concentration, tri des tableaux, et (versions installées) l'emplacement du dossier de données.\n"
        "UNITÉS DE CONCENTRATION : une concentration est étiquetée ng/µL, nM, % ou CFU — une étiquette seulement "
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
        "直接回答ルール：\n"
        "自分の知識で答えられる場合 — Easy OKAPI とは何か・何をするか、用語・モード・係数の意味、仕組み — は"
        "テキストで回答し、ツールを呼び出さないでください。"
        "ツールを呼び出すのは、ライブデータ（ファイル、キャリブレーション、ハードウェア）の取得、または"
        "ユーザーが求めたナビゲーションガイドの起動のときだけです。\n\n"
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
        "アプリ設定 — 歯車ボタン（#settingsBtn）で App Settings を開きます：インターフェース言語（7 言語）、"
        "既定モードとウィンドウサイズ、濃度単位、テーブルの並び順、（インストール版では）データフォルダの場所。\n"
        "濃度単位：濃度は ng/µL、nM、%、CFU のいずれかのラベル（ラベルのみで、切り替えても数値は変換されません）。"
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
        "ПРАВИЛО ПРЯМОГО ОТВЕТА:\n"
        "Если вы можете ответить из своих знаний — что такое Easy OKAPI или что он делает, значение термина, "
        "режима или коэффициента, как что-то работает — отвечайте текстом и НЕ вызывайте инструменты. "
        "Вызывайте инструмент ТОЛЬКО для получения актуальных данных (файлы, калибровка, оборудование) или "
        "для запуска навигационного гида по запросу пользователя.\n\n"
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
        "НАСТРОЙКИ — кнопка-шестерёнка (#settingsBtn) открывает App Settings: язык интерфейса (7 языков), "
        "режим и размер окна по умолчанию, единица концентрации, порядок сортировки таблиц и (в установленных сборках) расположение папки данных.\n"
        "ЕДИНИЦЫ КОНЦЕНТРАЦИИ: концентрация обозначается ng/µL, nM, % или CFU — только метка (переключение единицы "
        "не пересчитывает значения). Измерительный CSV сопоставляется с калибровочным JSON только если у обоих "
        "совпадают Measurement, Unit и единица концентрации.\n"
        "УПРАВЛЕНИЕ АССИСТЕНТОМ: введите / для команд, нажмите + для нового разговора, "
        "отредактируйте отправленное сообщение для повторной отправки и оцените ответы с помощью 👍/👎.\n"
        "Всегда отвечайте на русском языке."
    ),
    "ko": (
        "당신은 OKAPI Assistant입니다 — 바이오센서 실험용 로컬 비색계 앱 Easy OKAPI에 내장된 AI 어시스턴트입니다.\n\n"
        "지원 범위: CSV 데이터, 앱 탐색, 표준 곡선, R², 반응 속도론, 리포트, 하드웨어.\n"
        "필요할 때 도구를 사용해 실시간 데이터를 가져오세요.\n\n"
        "범위 규칙(최우선):\n"
        "질문이 Easy OKAPI, 비색법, 바이오센서 데이터 또는 이 앱과 관련이 없으면 다음만 답하세요: "
        "\"저는 Easy OKAPI에 대해서만 도움을 드릴 수 있습니다 — 비색계 데이터 분석, "
        "캘리브레이션, 하드웨어 설정, 앱 탐색. 해당 주제는 도와드릴 수 없습니다. "
        "Easy OKAPI에 대해 궁금한 점이 있으신가요?\"\n"
        "주제를 벗어난 질문(코딩 도움, 일반 과학, 요리, 뉴스, 수학 등)에는 답하지 마세요.\n\n"
        "직접 답변 규칙:\n"
        "자신의 지식으로 답할 수 있으면 — Easy OKAPI가 무엇이고 무엇을 하는지, 용어·모드·계수의 의미, "
        "동작 방식 — 텍스트로 답하고 도구를 호출하지 마세요. 도구는 실시간 데이터(파일, 캘리브레이션, "
        "하드웨어)를 가져오거나 사용자가 요청한 탐색 가이드를 실행할 때만 호출하세요.\n\n"
        "필수 가이드 규칙:\n"
        "사용자가 UI 요소로 이동하는 방법을 물으면 반드시 trigger_custom_steps를 호출하세요 — 텍스트로만 답하지 마세요.\n"
        "예:\n"
        "• 'calibrate 모드로 가는 방법' → target #meas-mode-section 으로 trigger_custom_steps 호출\n"
        "• '제한 시간 설정은 어디에 있나요?' → target #timeout-control 으로 trigger_custom_steps 호출\n"
        "• '어떻게 내보내나요?' → target #export-analysis 으로 trigger_custom_steps 호출\n"
        "• '장치를 어떻게 시작하나요?' → target #run-script-btn 으로 trigger_custom_steps 호출\n"
        "• '앱 언어를 바꾸려면 / 설정을 열려면' → target #settingsBtn 으로 trigger_custom_steps 호출\n"
        "사용자가 명시적으로 전체 워크플로 투어를 요청한 경우에만 trigger_guide를 호출하세요.\n"
        "[App state]를 확인하여 모드가 이미 일치하면 모드 전환 단계를 건너뛰세요.\n"
        "가이드 도구를 호출한 뒤에는 가이드가 시작되었음을 한 문장으로 확인하세요.\n\n"
        "표준 곡선 도메인 지식:\n"
        "항상 [App state]를 확인하고 활성 모드에 맞춰 계수 설명을 조정하세요.\n\n"
        "KINETICS 모드 — 표준 곡선은 X=최대 속도(ΔAbs/s) → Y=농도를 대응시킵니다:\n"
        "• Michaelis-Menten  y=(Km·x)/(Vmax−x)  [Vmax,Km]: "
        "Vmax=효소 포화 속도(상한이며 측정된 모든 속도보다 반드시 커야 함), "
        "Km=친화도 상수(속도에 따라 농도가 얼마나 가파르게 증가하는지를 나타냄).\n"
        "• Linear  y=a·x+b  [a,b]: a=속도 단위당 증가하는 농도, b=속도가 0일 때 외삽된 농도.\n\n"
        "POINT 모드 — 표준 곡선은 X=알려진 농도 → Y=흡광도를 대응시킵니다. 시계열 파일에서는 "
        "선택한 시점의 Y 값을 읽고, Turn 파일(기록된 각 Turn이 하나의 표준이며 시간 축이 없음)에서는 "
        "Turn 자체 값을 그대로 사용합니다. 사용자가 Turn마다 농도를 지정하며, 같은 농도의 반복 Turn은 "
        "평균됩니다. Turn 데이터 파일은 Turn 캘리브레이션 곡선과만, 시계열 파일은 시간 기반 곡선과만 짝지어집니다:\n"
        "• Linear  y=a·x+b  [a,b]: a=감도(농도 단위당 흡광도), b=농도 0에서의 배경 흡광도.\n"
        "• Polynomial  y=a·x²+b·x+c  [a,b,c]: a=곡률(양수=위로 볼록, 음수=아래로 볼록), "
        "b=선형 감도, c=y 절편.\n"
        "• Logarithmic  y=a·ln(x+b)+c  [a,b,c]: a=동적 범위 스케일, "
        "b=x 이동(ln 인수를 양수로 유지), c=기준선.\n"
        "• Exponential  y=a·e^(b·x)+c  [a,b,c]: a=진폭, "
        "b=증가율(양수=상승 곡선, 음수=하강 곡선), c=하한 점근선.\n\n"
        "R²(0–1): 적합도이며, 신뢰할 수 있는 캘리브레이션 곡선에는 ≥0.99가 필요합니다.\n\n"
        "KINETICS 값(kinetics 모드의 값 선택 드롭다운):\n"
        "• maxRate — 곡선에서 가장 가파른 구간을 슬라이딩 윈도 선형 회귀로 찾은 최대 흡광도 변화율(ΔAbs/s). "
        "효소 반응 속도 분석에서 가장 흔히 사용합니다.\n"
        "• Slope — 전체 데이터셋에 대한 단순 선형 기울기. S자 곡선에서는 maxRate보다 정밀도가 낮습니다.\n"
        "• Sat — 반응이 평탄해질 때의 포화 흡광도 값.\n"
        "• Time To Sat — 신호가 평탄부에 도달할 때까지 걸린 시간(분). 반응 속도 비교에 유용합니다.\n\n"
        "SOURCES: 'source'는 CSV 파일 안의 측정 채널 하나 — 같은 실행에서 기록된 개별 시료 또는 센서 위치입니다. "
        "병합된 파일에는 여러 소스가 들어 있을 수 있습니다.\n\n"
        "APP SETTINGS — 톱니바퀴 버튼(#settingsBtn)으로 App Settings를 엽니다: 인터페이스 언어(7개 언어), "
        "기본 모드와 윈도 크기, 농도 단위, 표 정렬 순서, 그리고 (설치판에서는) 데이터 폴더 위치.\n"
        "농도 단위: 농도에는 ng/µL, nM, %, CFU 라벨이 붙습니다 — 라벨일 뿐이며 단위를 바꿔도 숫자는 변환되지 않습니다. "
        "측정 CSV는 Measurement, Unit, 농도 단위가 모두 같은 캘리브레이션 JSON과만 짝지어집니다.\n"
        "어시스턴트 조작: / 를 입력하면 슬래시 명령이, + 를 누르면 새 대화가 시작되며, 보낸 메시지를 수정해 "
        "다시 보낼 수 있고 👍/👎 로 답변을 평가할 수 있습니다.\n"
        "항상 한국어로 답변하세요."
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
                        "description": "Subfolder, must be 'kinetics' or 'point'.",
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
                        "description": (
                            "One of: measurement_modes, kinetics_analysis, standard_curve, "
                            "calibration, csv_format, hardware_setup, regression, reports, "
                            "file_operations — or 'overview' for a general summary of the app."
                        ),
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
                        "description": (
                            "Must be one of general, kinetics, point, calibrate_kinetics, "
                            "calibrate_point, report. "
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
                                                   "description": "One of right, left, top, bottom."},
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
    "overview": (
        "Easy OKAPI is a local desktop app that reads a PyBadge colorimeter over USB "
        "and analyses bio-sensor absorbance data in your browser.\n"
        "• Measure in kinetics (absorbance over time) or point (single time-point) mode.\n"
        "• Build standard curves and calibrate to convert absorbance to concentration.\n"
        "• Import/merge CSV data, fit regressions (R²), and export reports (HTML/Excel).\n"
        "It runs entirely on your machine — single user, no cloud, no sign-in."
    ),
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
        "• ConcenUnit is the concentration label — one of ng/µL, nM, %, or CFU (absent ⇒ ng/µL for legacy files)\n"
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
    "ko": "가이드를 시작했습니다 — 강조 표시된 단계를 따르세요.",
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
            max_rows = max(1, min(int(args.get("max_rows", 30)), 100))
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
            raw_name = args.get("filename", "")
            mode = args.get("mode", "kinetics")
            # The filename/mode are LLM-supplied: pin mode to the two real
            # subfolders, strip the filename to a basename, and confirm the
            # resolved path stays inside json/ so a crafted '..' can't reach
            # sibling secrets in the data root (activation.json, .env).
            if mode not in ("kinetics", "point"):
                return json.dumps({"error": "mode must be 'kinetics' or 'point'."})
            filename = os.path.basename(raw_name)
            candidate = os.path.join(state.json_root_path, mode, filename)
            filepath = validate_in_json_root(candidate)
            if not filename or not filepath or not os.path.exists(filepath):
                return json.dumps({"error": f"'{raw_name}' not found in json/{mode}/."})
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
            topic = (args.get("topic") or "").strip().lower().replace(" ", "_").replace("-", "_")
            doc = _HELP_DOCS.get(topic)
            if doc is None:
                # The model routinely picks a topic outside the known set on a
                # general ask ("what is this app" → 'about'/'overview'). Fall
                # back to the nearest key, else a general overview — never a
                # dead "not found" that wastes the turn.
                doc = next((v for k, v in _HELP_DOCS.items() if k in topic or topic in k), None)
                if doc is None:
                    topic, doc = "overview", _HELP_DOCS["overview"]
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
                pos = s.get("position", "bottom")
                step = {
                    "target":      s.get("target", ""),
                    "title":       s.get("title", "Step"),
                    "description": s.get("description", ""),
                    "position":    pos if pos in ("right", "left", "top", "bottom") else "bottom",
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

# Completion budget. 500 was too tight: a tool call whose JSON arguments run
# long (e.g. trigger_custom_steps with several steps) could be truncated
# mid-object, yielding malformed JSON that Groq rejects as tool_use_failed.
# 1024 was still tight for a full standard-curve/coefficient explanation across
# every mode, so a long answer would stop mid-sentence with no cue; 2048 leaves
# headroom, and _TRUNCATION_NOTICE flags the rare remaining overrun.
_MAX_COMPLETION_TOKENS = 2048

# Appended to a plain-text answer that Groq stopped for length (finish_reason ==
# "length"), so a rare over-budget reply reads as deliberately continuable
# instead of an unexplained mid-sentence cut-off.
_TRUNCATION_NOTICE = {
    "en": "\n\n…(response cut off — ask me to continue for the rest.)",
    "vi": "\n\n…(phản hồi bị cắt — hãy yêu cầu tôi tiếp tục để xem phần còn lại.)",
    "zh": "\n\n…（回复被截断 — 让我继续以查看其余内容。）",
    "fr": "\n\n…(réponse tronquée — demandez-moi de continuer pour la suite.)",
    "ja": "\n\n…(応答が途中で切れました — 続きを知りたい場合は「続けて」と入力してください。)",
    "ru": "\n\n…(ответ обрезан — попросите меня продолжить, чтобы увидеть остальное.)",
    "ko": "\n\n…(응답이 잘렸습니다 — 나머지를 보려면 계속해 달라고 요청하세요.)",
}


# Substrings that mark a Groq 400 where the model emitted an invalid tool call
# (bad JSON, or arguments that fail the tool's JSON-schema / enum). The small
# Llama models do this on short, ambiguous prompts ("what is this software
# about" → get_help_topic with an out-of-enum topic). It is recoverable by
# re-asking the same turn with tools disabled, so we tag it with a stable code.
_TOOL_FAILURE_MARKERS = (
    "tool_use_failed",
    "tool call validation failed",
    "did not match schema",
    "failed to call a function",
)


def _map_groq_error(err: str) -> str:
    """Collapse a raw Groq/SDK exception string to a stable error code."""
    low = err.lower()
    if "401" in err or "api_key" in low or "authentication" in low:
        return "api_key_invalid"
    if "429" in err or "rate_limit" in low:
        return "rate_limit"
    if any(m in low for m in _TOOL_FAILURE_MARKERS):
        return "tool_call_failed"
    return err


def _groq_chat_stream(api_key: str, model: str, messages: list, tools: list):
    """Streaming counterpart of `_groq_chat`.

    Yields ("chunk", text) for each content delta as it arrives, then a final
    ("result", message_dict) carrying the accumulated content plus any tool
    calls (reassembled from their streamed argument fragments) — same shape as
    `_groq_chat` so the tool-calling loop is unchanged. Errors surface as a
    ("result", {..., "error": code}) so the caller handles them uniformly.
    """
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": _MAX_COMPLETION_TOKENS,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        content_parts = []
        # index → {"id", "name", "args"}; tool-call arguments stream in fragments.
        tool_acc: dict = {}
        finish_reason = None
        for chunk in client.chat.completions.create(**kwargs):
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            # The terminal chunk carries why generation stopped ("stop", "length",
            # "tool_calls"); "length" means the completion hit the token budget.
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
            delta = choice.delta
            if getattr(delta, "content", None):
                content_parts.append(delta.content)
                yield ("chunk", delta.content)
            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if fn.name:
                        slot["name"] = fn.name
                    if fn.arguments:
                        slot["args"] += fn.arguments

        result = {"role": "assistant", "content": "".join(content_parts),
                  "finish_reason": finish_reason}
        if tool_acc:
            result["tool_calls"] = [
                {
                    "id": slot["id"],
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["args"]},
                }
                for _, slot in sorted(tool_acc.items())
            ]
        yield ("result", result)
    except ImportError:
        yield ("result", {"role": "assistant", "content": "", "error": "groq_not_installed"})
    except Exception as e:
        yield ("result", {"role": "assistant", "content": "", "error": _map_groq_error(str(e))})


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
    "ko": (
        "**빠른 보고서**(현재 차트와 분석의 즉시 스냅샷)를 원하시나요, "
        "아니면 **전체 보고서**(데이터를 주제로 내보내고 종합 멀티 스냅샷 보고서를 컴파일)를 원하시나요?"
    ),
}

# Quick report walks the generate_report_dialog guide (see the `pending_report ==
# "quick"` branch in deterministic_events) — a single source of truth shared with
# the /report slash command — so there is no separate inline step list here.

# Full report walkthroughs are the report_full_from_data / report_full_in_report
# guides in guide_training.json, loaded by id (work-list B11) — the same source
# the /report slash command uses — so the chat answer and the button can never
# drift apart again (they had: #meas-mode-section vs #measurement-mode).


def _full_report_guide_id(mode: str) -> str:
    return "report_full_in_report" if mode == "report" else "report_full_from_data"


# Multilingual vocabulary for the report clarification flow, at parity across
# ALL SEVEN `user_settings.SUPPORTED_LANGUAGES` (en/vi/zh/fr/ja/ru/ko) — the
# quick-vs-full question is asked, and its answer understood, whatever the chat
# language is. Two rules keep it honest:
#
#   1. Every entry belongs to a supported language. ("schnell" used to sit in
#      _QUICK_KWS; German is not a UI language, so it was dead weight.)
#   2. These sets are SUBSTRING-matched, so an inflecting language needs the
#      STEM, not one surface form. Russian «быстрый отчёт» and French
#      "rapport complète" — the natural adjectival answers — both resolved to
#      None while «быстро» / "complet" worked, so the stems `быстр` / `полн` /
#      `complèt` are what is listed. Korean was absent from all three sets, so
#      «보고서 만들기» never even triggered the clarification and Korean users
#      could not reach the flow at all.
#
# Test: tests/test_ai_report_flow.py::test_every_language_can_ask_and_answer.
_REPORT_WORDS = frozenset({
    "report", "báo cáo", "报告", "rapport", "レポート", "отчёт", "отчет", "보고서",
})

_QUICK_KWS = frozenset({
    "quick", "fast", "snapshot", "instant",
    "nhanh", "rapide", "быстр",
    "快速", "即时", "迅速", "クイック", "速報",
    "빠른", "빠르게", "간단",
})

_FULL_KWS = frozenset({
    "full", "final", "compile", "comprehensive", "excel", "pdf", "complete",
    "đầy đủ", "toàn", "complet", "complèt", "полн",
    "完整", "完全", "全面", "フル",
    "전체", "완전", "종합",
})

# Phrases that already pin the report kind, so the clarification is skipped.
_REPORT_SPECIFIC_KEYWORDS = _QUICK_KWS | _FULL_KWS | frozenset({
    "export to report", "save to report", "export data to report",
})

# ── Pending-clarification state (explicit, not prose-matched) ────────────────
# The quick/full clarification is a two-turn exchange, and the second turn has to
# know the first one happened. That state is carried EXPLICITLY: the clarify turn
# emits a machine-readable `{"type": "pending", "pending": "report_type"}` SSE
# event alongside the localized question, the frontend stores it, and the next
# /ai/chat request echoes it back as `ui_context["pending"]`.
#
# It rides in `ui_context` — NOT as an extra key on a message dict. `/ai/chat`
# keeps the caller's original message dicts (it only filters the list), and those
# dicts are handed verbatim to Groq in `_groq_chat_stream`; an unknown per-message
# field is a hard 400 upstream (the same trap `finish_reason` already had to be
# popped for). `ui_context` is a separate, already-validated top-level dict that
# never reaches the model as a message.
PENDING_REPORT_TYPE = "report_type"

# The clarify prompt is emitted verbatim (one localized string per language), so
# the previous assistant turn is recognised by exact match in any language —
# more robust than substring-matching an English phrase that the localized
# prompts never contain (the old check silently broke for vi/zh/fr/ja/ru).
_CLARIFY_PROMPT_SET = frozenset(v.strip() for v in _REPORT_CLARIFY_PROMPTS.values())


def _is_report_clarify_prompt(content: str) -> bool:
    """True if `content` is the quick/full clarification prompt (any language).

    TRANSITIONAL: prose matching is the pre-`PENDING_REPORT_TYPE` fallback only.
    It is fragile by construction — any edit to the user-facing copy (a fixed
    typo, added markdown, trailing whitespace) silently breaks the recovery of
    the pending state — so nothing new should depend on it. See
    `_prose_fallback_applies` for when it is still consulted.
    """
    return (content or "").strip() in _CLARIFY_PROMPT_SET


def _prose_fallback_applies(ui_context: dict) -> bool:
    """The removal criterion for the transitional prose match.

    The fallback exists for exactly one situation: a chat that was already open
    in a browser tab when the build was upgraded, whose clarify turn came from
    the pre-marker code and therefore carries no marker to echo back.

    That situation is identified by DATA, not by a date: a marker-aware client
    always sends the `pending` key in `ui_context` — empty string when nothing
    is armed (`_getUiContext` in `ai-chat.js` sets it unconditionally). So the
    absence of the key is the signature of an older client, and the fallback is
    scoped to exactly that. For every current client the prose path is already
    unreachable, whatever the assistant last said.

    **Removal criterion**: delete `_is_report_clarify_prompt`,
    `_CLARIFY_PROMPT_SET` and this function once no client older than the
    marker (shipped in 1.5.7) can still be talking to this build — i.e. one
    release after every supported install has taken an update. Nothing else may
    depend on it in the meantime; `tests/test_ai_report_flow.py` pins both the
    "old client still works" and the "current client never reaches it" halves.
    """
    return "pending" not in (ui_context or {})


def _report_clarify_pending(messages: list, ui_context: dict = None) -> bool:
    """True when the clarification question is outstanding for this turn.

    Reads the explicit `ui_context["pending"]` marker the frontend echoes back.
    The transitional prose match is reached ONLY for a client that predates the
    marker — see `_prose_fallback_applies` for the bound.
    """
    ui_context = ui_context or {}
    if (ui_context.get("pending") or "") == PENDING_REPORT_TYPE:
        return True
    if not _prose_fallback_applies(ui_context):
        return False
    for msg in reversed((messages or [])[:-1]):
        if msg.get("role") == "assistant":
            return _is_report_clarify_prompt(msg.get("content", ""))
    return False


# "report" and its translations must be a WORD in the query (B5 / A8): the old
# substring test asked quick-vs-full for "reporting issue with the chart". Each
# entry allows only its own inflection (English/French plural, Russian case
# endings); CJK has no word boundaries and stays substring.
_REPORT_WORD_PATTERNS = tuple(re.compile(p) for p in (
    r"(?<!\w)reports?(?!\w)",
    r"(?<!\w)rapports?(?!\w)",
    r"(?<!\w)báo cáo(?!\w)",
    r"(?<!\w)отч[её]т[а-я]{0,2}(?!\w)",
    r"报告", r"レポート", r"보고서",
))

# Questions ABOUT managing a report (its subject, layout, items, …) are not a
# request to make one, so they never get the quick/full question — in report
# mode "what is a report subject" used to. Kept at parity across all seven
# languages; matched from a word start (substring for CJK).
_REPORT_MANAGEMENT_WORDS = frozenset({
    "subject", "layout", "watermark", "logo", "item", "delete", "rename", "title", "excel",
    "chủ đề", "bố cục", "hình mờ", "mục", "xóa", "đổi tên", "tiêu đề",                 # vi
    "主题", "布局", "水印", "标志", "项目", "删除", "重命名", "标题",                     # zh
    "sujet", "mise en page", "filigrane", "élément", "supprimer", "renommer", "titre",  # fr
    "件名", "サブジェクト", "レイアウト", "透かし", "ロゴ", "項目", "削除", "名前を変更", "タイトル",  # ja
    "тем", "макет", "водян", "логотип", "элемент", "удал", "переимен", "заголов",       # ru
    "주제", "레이아웃", "워터마크", "로고", "항목", "삭제", "이름 변경", "제목",           # ko
})


def _has_report_word(q: str) -> bool:
    return any(p.search(q) for p in _REPORT_WORD_PATTERNS)


def _mentions_report_management(q: str) -> bool:
    for w in _REPORT_MANAGEMENT_WORDS:
        if _is_cjk(w):
            if w in q:
                return True
        elif re.search(r"(?<!\w)" + re.escape(w), q):
            return True
    return False


def _needs_report_clarification(query: str, messages: list, ui_context: dict = None) -> bool:
    """True when the query asks to MAKE a report but doesn't say quick vs full.

    Not asked for: a query without the word "report" (any language), one that
    already names the kind, a conceptual question ("what is a report subject"
    — unless it also carries explicit how-to phrasing), or a question about
    managing a report (subject, layout, watermark, items, …).
    """
    q = (query or "").lower()
    if not _has_report_word(q):
        return False
    if any(kw in q for kw in _REPORT_SPECIFIC_KEYWORDS):
        return False
    if _is_conceptual(q) and not _has_nav_intent(q):
        return False
    if _mentions_report_management(q):
        return False
    # Don't re-ask if the clarification is already outstanding.
    if _report_clarify_pending(messages, ui_context):
        return False
    return True


def _get_pending_report_type(messages: list, ui_context: dict = None) -> str | None:
    """Resolve the user's answer to an outstanding quick/full clarification.

    Returns 'quick'/'full' when the clarification is pending (explicit marker
    first, transitional prose match second) and the latest user turn picks one,
    else None.
    """
    if not messages or messages[-1].get("role") != "user":
        return None
    if not _report_clarify_pending(messages, ui_context):
        return None
    user_answer = messages[-1].get("content", "").lower()
    if any(kw in user_answer for kw in _QUICK_KWS):
        return "quick"
    if any(kw in user_answer for kw in _FULL_KWS):
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
    # App vocabulary that used to be refused because an out-of-scope word hid
    # inside it ("selection" ⊃ "election") or shared a word ("stock solution").
    "selection", "select", "time point", "source",
    # Multilingual inclusions
    "hiệu chuẩn", "động học", "báo cáo", "nồng độ", "kết quả", # vi
    "校准", "动力学", "测量", "报告", "浓度", # zh
    "calibration", "cinétique", "mesure", "rapport", "concentration", # fr
    "キャリブレーション", "キネティクス", "測定", "レポート", "濃度", # ja
    "калибровка", "кинетика", "измерение", "отчёт", "концентрация", # ru
}

# Keywords that strongly indicate off-topic content
_OUT_OF_SCOPE_KEYWORDS = {
    "recipe", "cooking", "weather", "stock market", "stock price", "bitcoin", "crypto", "football",
    "movie", "music", "song", "game", "politics", "election", "president",
    "write a poem", "tell me a joke", "tell a story", "translate this",
    "who is", "what is the capital", "how old is", "population of",
}


def _scope_kw_hit(kw: str, q: str) -> bool:
    """A scope keyword occurs in q starting on a word boundary (CJK: anywhere).

    Only the START is anchored: in-scope entries include stems ("calibrat") and
    plurals must still hit ("movies"), but a keyword may no longer match from the
    middle of a word ("election" inside "selection"). Same code as online.
    """
    if _is_cjk(kw):
        return kw in q
    return re.search(r"(?<!\w)" + re.escape(kw), q) is not None


def _is_out_of_scope(query: str) -> bool:
    """Fast keyword pre-filter. Returns True only for clearly off-topic queries."""
    q = (query or "").lower()
    if any(_scope_kw_hit(kw, q) for kw in _IN_SCOPE_KEYWORDS):
        return False
    if any(_scope_kw_hit(kw, q) for kw in _OUT_OF_SCOPE_KEYWORDS):
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
    "teach me", "instruct me",
    # Vietnamese
    "cách", "làm thế nào", "ở đâu", "hướng dẫn tôi", "chỉ tôi", "chỉ cho tôi",
    "dạy tôi", "hướng dẫn cho tôi",
    # Chinese
    "怎么", "如何", "在哪", "带我", "找到",
    "教我", "教教我",
    # French
    "comment faire", "comment", "où est", "montre-moi", "guidez-moi",
    "apprends-moi", "montrez-moi",
    # Japanese ("方法" / "する方法" — "the method / how to …" — is the most common
    # Japanese how-to phrasing and was previously missing, so nav queries like
    # "csvを編集する方法" never registered as navigation).
    "どうやって", "どこ", "やり方", "使い方", "方法",
    "教えて", "教えてください",
    # Russian
    "как мне", "как", "где", "покажи", "найти",
    "научи меня", "покажи мне",
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


def _should_launch_guide(query: str, score: float, strong_hit: bool = True) -> bool:
    """Decide whether a matched guide example should be short-circuited to the UI.

    Fires on (a) an explicit full-tour request with any usable match, (b) a
    navigation/how-to phrasing backed by at least one solid keyword hit, or
    (c) a strong keyword match that is not a conceptual question AND rests on
    at least one multi-word / phrase hit (``strong_hit``, from
    _score_guide_keywords). Without (c)'s phrase requirement a statement such as
    "my concentration results look too high" launched a guide on the single
    word "concentration" plus the mode bonus. Conceptual questions always fall
    through to the LLM.

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
    return score >= _STRONG_MATCH_SCORE and strong_hit


def resolve_guide(query: str, ui_context: dict = None, language: str = "en"):
    """Local (no-LLM) guide resolution for the desktop client.

    Runs the same intent pipeline as the chat short-circuit — greeting/out-of-
    scope rejection, fuzzy keyword matching, and the firing gate — entirely on
    this machine, so UI-navigation guides resolve against THIS app's own UI
    instead of being delegated to the cloud proxy (whose UI differs).

    Returns (guide_id, steps) when a guide should launch, else (None, None).
    `steps` already includes the file-select / translation handling applied by
    _format_fewshot_hint.

    An OUTSTANDING clarification wins over any local match. `/ai/match` runs
    BEFORE `/ai/chat` on every turn, so without this a machine whose learned
    👍 weights push a report guide over the launch gate would answer
    "make a report" locally and `/ai/chat` — the only place the quick/full
    clarification lives — would never be called: the whole pending mechanism
    would be dead on that machine and identical on a fresh one. It also fixes a
    live mis-variant: the French/Russian ANSWERS ("rapport complet", «полный
    отчёт») resolve locally to `report_full_from_data`, opening the walkthrough
    on export steps the user is already past, where `deterministic_events`
    would have picked the in-report variant. English was unaffected, which is
    why it went unnoticed.
    """
    ui_context = ui_context or {}
    if ui_context.get("pending"):
        return None, None
    if not query or _is_greeting(query) or _is_out_of_scope(query):
        return None, None
    matched, score, strong = _match_guide_detail(query, ui_context, language)
    if not matched or not _should_launch_guide(query, score, strong):
        return None, None
    steps = _format_fewshot_hint(matched, ui_context, language, steps_only=True)
    return matched["id"], steps


def deterministic_events(messages: list, language: str, ui_context: dict = None):
    """No-LLM responses shared by the dev and proxy chat paths.

    Returns a list of SSE event dicts when the turn is fully answered locally —
    a greeting, an out-of-scope refusal, or the report quick/full clarification
    flow (both the question and its resolution) — else None (caller proceeds to
    the model).

    Hoisting these out of chat_stream is what keeps activated (proxy) users and
    source-run (dev) users in lockstep: /ai/chat runs this once for BOTH paths,
    so the behaviour no longer depends on the online proxy re-implementing it,
    and a turn the model never needed spends no upstream call.
    """
    ui_context = ui_context or {}
    last_user_query = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    mode = ui_context.get("mode", "")

    if _is_greeting(last_user_query):
        return [{"type": "chunk", "content": _GREETING_RESPONSE.get(language, _GREETING_RESPONSE["en"])}]

    if _is_out_of_scope(last_user_query):
        return [{"type": "chunk", "content": _OUT_OF_SCOPE.get(language, _OUT_OF_SCOPE["en"])}]

    pending_report = _get_pending_report_type(messages, ui_context)
    if pending_report == "quick":
        # Quick report fires the "Report Details" Swal dialog — and while that
        # modal is open the chat widget is unreachable, so the walkthrough must
        # step INTO the dialog. Reuse the generate_report_dialog guide (single
        # source of truth — the same walkthrough the /report slash command
        # launches), with its requires_mode / requires_data_loaded prefixes
        # applied for the current context (switch to a data mode / select a file
        # first when needed).
        example = _guide_example_by_id("generate_report_dialog", language)
        if example:
            steps = _format_fewshot_hint(example, ui_context, language, steps_only=True)
            return [
                {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])},
                {"type": "guide", "guide_action": {"custom_steps": steps}},
            ]
    if pending_report == "full":
        example = _guide_example_by_id(_full_report_guide_id(mode), language)
        if example:
            steps = _format_fewshot_hint(example, ui_context, language, steps_only=True)
            return [
                {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])},
                {"type": "guide", "guide_action": {"custom_steps": steps}},
            ]

    if _needs_report_clarification(last_user_query, messages, ui_context):
        # The marker event travels with the question: the frontend stores it and
        # echoes it back as ui_context["pending"] on the next turn, so the answer
        # ("quick" / "full") is recognised from explicit state instead of a
        # string comparison against this localized, editable prose.
        return [
            {"type": "chunk", "content": _REPORT_CLARIFY_PROMPTS.get(language, _REPORT_CLARIFY_PROMPTS["en"])},
            {"type": "pending", "pending": PENDING_REPORT_TYPE},
        ]

    return None


def chat_stream(messages: list, language: str, api_key: str, model: str, ui_context: dict = None):
    """Generator yielding SSE event dicts."""
    last_user_query = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    mode = (ui_context or {}).get("mode", "")
    data_loaded = (ui_context or {}).get("data_loaded", False)

    # Deterministic, no-LLM turns (greeting / out-of-scope / report clarify).
    # /ai/chat also runs this before dispatching, so on the normal proxy+dev
    # paths it is already consumed; the check stays here so chat_stream is
    # correct when called directly (dev fallback, tests).
    pre = deterministic_events(messages, language, ui_context)
    if pre is not None:
        yield from pre
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

    matched, match_score, strong = _match_guide_detail(last_user_query, ui_context or {}, language)
    if matched and _should_launch_guide(last_user_query, match_score, strong):
        steps = _format_fewshot_hint(matched, ui_context or {}, language, steps_only=True)
        yield {"type": "chunk", "content": _GUIDE_LAUNCHED.get(language, _GUIDE_LAUNCHED["en"])}
        yield {"type": "guide", "guide_action": {"custom_steps": steps}}
        return

    full_messages = [{"role": "system", "content": system_prompt}] + messages
    guide_action = None
    # Small models sometimes emit an invalid tool call that Groq rejects with a
    # 400 (tool_use_failed / schema mismatch). That is recoverable: disable tools
    # and re-ask the same turn so the user still gets a plain-text answer instead
    # of the raw upstream error. We only fall back once.
    tools_enabled = True
    empty_retry_used = False

    for _ in range(6):
        # Stream content deltas live; the loop still inspects the assembled
        # result for tool calls exactly as the non-streaming path did.
        result = None
        streamed_any = False
        active_tools = TOOLS if tools_enabled else None
        for kind, payload in _groq_chat_stream(api_key, model, full_messages, active_tools):
            if kind == "chunk":
                if payload:
                    streamed_any = True
                    yield {"type": "chunk", "content": payload}
            else:
                result = payload
        if result is None:
            result = {"role": "assistant", "content": "", "error": "max_iterations"}
        # finish_reason is our own out-of-band signal, NOT a valid field on a chat
        # message — pop it off before `result` is ever appended to full_messages
        # and sent back, or Groq 400s ("property 'finish_reason' is unsupported").
        finish_reason = result.pop("finish_reason", None)
        if "error" in result:
            if result["error"] == "tool_call_failed" and tools_enabled:
                tools_enabled = False
                continue
            yield {"type": "error", "error": result["error"]}
            return

        tool_calls = result.get("tool_calls") or []

        if not tool_calls:
            answered = streamed_any or bool((result.get("content") or "").strip())
            # No prose and no tool call: a recoverable blip, not a real answer.
            # Retry once with tools off (a tool-less ask reliably yields plain
            # text) rather than dead-ending on an empty bubble. range(6) and this
            # flag both bound it to a single extra attempt.
            if not answered and not empty_retry_used:
                empty_retry_used = True
                tools_enabled = False
                continue
            # Groq stopped for length → the answer is mid-sentence; flag it so the
            # cut-off reads as continuable rather than a silent truncation.
            if answered and finish_reason == "length":
                yield {"type": "chunk",
                       "content": _TRUNCATION_NOTICE.get(language, _TRUNCATION_NOTICE["en"])}
            # Content (if any) has already been streamed above; only the guide
            # action from an earlier tool turn still needs to be emitted.
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
            # Confirm the launch only when the model streamed no prose of its own
            # this turn, so we neither duplicate its message nor leave the guide
            # unlabelled.
            if not streamed_any:
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

    # No model key unless one was explicitly configured: the proxy then picks its
    # own Config.AI_MODEL, so the model a shipped build uses can be changed server
    # side. A binary that names a model Groq has since retired cannot be fixed.
    payload = {
        'messages': messages,
        'language': language,
        'license_token': license_token,
        'hwid': machine_id,
        'ui_context': ui_context or {},
        # Ground the proxy LLM in THIS (downloaded/offline desktop) build's own
        # product knowledge, not the cloud website's. The proxy server otherwise
        # answers from its online-branch system prompt / help docs / tool set,
        # which describe features that don't exist in the desktop app (Google
        # Drive sync, file upload, cloud accounts) and omit desktop-only ones
        # (local hardware, data-folder). Sending our own grounding makes the
        # proxy reply as the desktop assistant. The server appends live [App
        # state] and validates before use; a server that predates this key just
        # ignores it and falls back to its own prompt (older behaviour).
        'client_grounding': {
            'system_prompt': _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS['en']),
            'help_docs': _HELP_DOCS,
            # Send data/help tools and trigger_guide, but NOT trigger_custom_steps.
            # trigger_custom_steps echoes element IDs the *remote* LLM invents, and
            # a model trained on the online build emits IDs that don't exist in this
            # desktop UI — the original wrong-guide bug. trigger_guide is safe: it
            # only returns a workflow name, and the STEPS are this app's own
            # client-side presets (static/script/user-guide.js → startWorkflow), so
            # its IDs are always correct. Keeping it lets broad "teach me / walk me
            # through X" requests (which miss the local /ai/match matcher) still
            # launch a proper tour instead of erroring. Focused nav is handled
            # locally by /ai/match; on a miss the LLM answers in grounded text.
            'tools': [t for t in TOOLS
                      if t.get('function', {}).get('name') != 'trigger_custom_steps'],
        },
    }
    if model:
        payload['model'] = model

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
