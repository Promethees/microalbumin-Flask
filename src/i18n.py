"""UI localization (i18n) for the Easy OKAPI web service.

Ported from the desktop branch's ``src/i18n.py`` (same catalog format and the
same ``en.json``-is-the-baseline rule) and extended with the pieces a public
web site needs that a single-user desktop app does not:

  * **The URL carries the language, not a setting.** English lives at the bare
    path (``/terms``) and is the canonical URL; every other language lives under
    a prefix (``/vi/terms``). A crawler therefore sees seven real, separately
    indexable documents instead of one page that changes under a cookie.
  * **A cookie only remembers a preference.** It never changes what a given URL
    renders — that would make the canonical English URL non-deterministic for
    crawlers and caches. It is read on ``/`` alone, to send a returning visitor
    to the language they last chose.

Per-language flat key->string catalogs live in ``ui_translations/<lang>.json``
at the repo root. A non-English catalog is overlaid onto English so any missing
key falls back to English; loading is best-effort and cached per process, so a
missing or broken file yields English rather than raising into a request.

Technical terms (mode names, units, Absorbance, maxRate, rSquared, CSV/JSON,
brand names) are intentionally left in English inside every catalog.
"""

import json
import os

from flask import g, redirect, request, url_for
from markupsafe import Markup

DEFAULT_UI_LANG = "en"

# Single source of truth for the supported language codes + native names. Mirrors
# ai_settings.SUPPORTED_LANGUAGES so the interface language and the assistant's
# own language offer the same seven options and never drift.
SUPPORTED_UI_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "中文 (简体)",
    "fr": "Français",
    "ja": "日本語",
    "ru": "Русский",
    "ko": "한국어",
}

# The codes that appear as a URL prefix — everything except the default, which
# is served from the bare path. Used to build the Flask `any(...)` converter.
PREFIXED_LANGUAGES = tuple(c for c in SUPPORTED_UI_LANGUAGES if c != DEFAULT_UI_LANG)

# BCP-47 tags for <html lang> and hreflang. `zh` in the catalogs is Simplified.
HTML_LANG_TAGS = {
    "en": "en",
    "vi": "vi",
    "zh": "zh-Hans",
    "fr": "fr",
    "ja": "ja",
    "ru": "ru",
    "ko": "ko",
}

# Languages whose legal text is a translation of an English original. Rendered
# with the "the English version governs" notice (see `legal.governing_notice`).
LANG_COOKIE = "ui_lang"
LANG_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # one year

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRANSLATIONS_DIR = os.path.join(_ROOT, "ui_translations")

# Per-language merged-catalog cache: {lang: {key: value}}.
_cache = {}


def normalize_lang(lang) -> str:
    """Return ``lang`` if it is a supported code, else the default (``en``)."""
    if isinstance(lang, str) and lang in SUPPORTED_UI_LANGUAGES:
        return lang
    return DEFAULT_UI_LANG


def _read_file(lang: str) -> dict:
    """Read one raw ``<lang>.json`` catalog; ``{}`` on any failure."""
    path = os.path.join(_TRANSLATIONS_DIR, "{}.json".format(lang))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def load_catalog(lang: str) -> dict:
    """Return the merged catalog for ``lang`` (English baseline + overlay).

    Missing keys in the requested language fall back to the English value. The
    result is cached per language.
    """
    lang = normalize_lang(lang)
    if lang in _cache:
        return _cache[lang]

    merged = dict(_read_file(DEFAULT_UI_LANG))
    if lang != DEFAULT_UI_LANG:
        merged.update(_read_file(lang))  # overlay translated keys over English

    _cache[lang] = merged
    return merged


def clear_cache() -> None:
    """Drop the in-memory catalog cache (used by tests)."""
    _cache.clear()


# ── Per-request language ──────────────────────────────────────────────────────

def current_lang() -> str:
    """The language this request renders in.

    Set by the URL prefix (``/vi/terms``) via `flask.g`; bare paths are English,
    unconditionally, so the canonical URL always serves the canonical text.
    """
    return normalize_lang(getattr(g, "ui_lang", None))


def best_match_from_header(accept_language: str) -> str:
    """Pick the best supported language from an ``Accept-Language`` header.

    Only ever used to *suggest* a language on ``/`` — never to decide what a
    given URL renders.
    """
    if not accept_language:
        return DEFAULT_UI_LANG
    ranked = []
    for part in accept_language.split(","):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        if params.startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                quality = 0.0
        ranked.append((quality, tag.strip().lower()))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    for _, tag in ranked:
        base = tag.split("-")[0]
        if base in SUPPORTED_UI_LANGUAGES:
            return base
    return DEFAULT_UI_LANG


def preferred_lang() -> str:
    """The visitor's remembered/likely language: cookie first, then browser."""
    cookie = request.cookies.get(LANG_COOKIE)
    if isinstance(cookie, str) and cookie in SUPPORTED_UI_LANGUAGES:
        return cookie
    return best_match_from_header(request.headers.get("Accept-Language", ""))


def translate(key, fallback=None):
    """Look up ``key`` in the active catalog.

    Falls back to the supplied English literal, then to the key itself, so an
    unmigrated or missing string is never blank.
    """
    if key is None:
        return fallback if fallback is not None else ""
    value = load_catalog(current_lang()).get(key)
    if isinstance(value, str):
        return value
    return fallback if fallback is not None else key


def translate_html(key, fallback=None):
    """`translate`, but the result is trusted as markup.

    For catalog strings that carry inline markup (a link inside a sentence).
    Catalogs are first-party files shipped with the app, not user input.
    """
    return Markup(translate(key, fallback))


# ── URL wiring ────────────────────────────────────────────────────────────────
# Page endpoints that get a language-prefixed twin of their rule. These are the
# indexable pages; English stays on the bare path and is the canonical URL.
LOCALIZED_ENDPOINTS = (
    "landing",
    "terms",
    "privacy",
    "contact",
    "index",
    "account.signup_page",
    "account.login_page",
    "account.forgot_password_page",
    "account.reset_password_page",
)

# One-shot pages nobody links to and no crawler should index (they are reached
# from an email or an OAuth redirect, and carry `noindex`). Prefixing their URLs
# would be pointless, so they render in the visitor's remembered language.
COOKIE_LANG_ENDPOINTS = (
    "account.verify_email",
    "auth.auth_google_callback",
)


def url_for_lang(code, endpoint=None, external=False, **overrides):
    """URL for the current page (or ``endpoint``) in language ``code``.

    Used by the language picker and the ``hreflang`` block. Passing
    ``lang=None`` for English is what suppresses the prefix: `inject_lang`
    below leaves an explicit ``lang`` alone, and Werkzeug drops ``None`` values
    before matching a rule, so the bare rule wins.
    """
    endpoint = endpoint or request.endpoint
    if not endpoint:
        return "/"
    args = dict(request.view_args or {})
    args.update(overrides)
    args.pop("lang", None)
    args["lang"] = None if code == DEFAULT_UI_LANG else code
    if external:
        args["_external"] = True
    return url_for(endpoint, **args)


def lang_alternates(external=False):
    """``(code, html_lang_tag, url)`` for every language of the current page.

    Empty when the current endpoint has no language-prefixed twin, so the
    ``hreflang`` block and the picker both disappear on pages that are not
    localized by URL.
    """
    if request.endpoint not in LOCALIZED_ENDPOINTS:
        return []
    return [(code, HTML_LANG_TAGS[code], url_for_lang(code, external=external))
            for code in SUPPORTED_UI_LANGUAGES]


def init_app(app):
    """Install the language-aware URL layer and the Jinja helpers."""
    converter = "any({}):lang".format(",".join(PREFIXED_LANGUAGES))

    # Mirror each localized rule under /<lang>/. Done once at import time, after
    # every blueprint is registered, so route declarations stay untouched.
    for rule in list(app.url_map.iter_rules()):
        if rule.endpoint not in LOCALIZED_ENDPOINTS:
            continue
        app.add_url_rule(
            "/<{}>{}".format(converter, rule.rule),
            endpoint=rule.endpoint,
            view_func=app.view_functions[rule.endpoint],
            methods=sorted(rule.methods - {"HEAD", "OPTIONS"}),
        )

    @app.url_value_preprocessor
    def pull_lang(endpoint, values):
        """Take ``lang`` out of the view args and onto `g`.

        The view functions know nothing about language, so the prefix must not
        reach them as a keyword argument.
        """
        code = values.pop("lang", None) if values else None
        if code is None and endpoint in COOKIE_LANG_ENDPOINTS:
            code = preferred_lang()
        g.ui_lang = normalize_lang(code)

    @app.url_defaults
    def inject_lang(endpoint, values):
        """Keep the active language across every ``url_for`` on the page."""
        if "lang" in values:
            return
        code = getattr(g, "ui_lang", DEFAULT_UI_LANG)
        if code == DEFAULT_UI_LANG:
            return
        if app.url_map.is_endpoint_expecting(endpoint, "lang"):
            values["lang"] = code

    @app.after_request
    def remember_lang(response):
        """Persist the language the visitor is actually reading.

        Only written when it differs from what the cookie already says, so a
        steady-state page view sends no ``Set-Cookie`` at all.
        """
        code = getattr(g, "ui_lang", None)
        if code and request.endpoint in LOCALIZED_ENDPOINTS \
                and request.cookies.get(LANG_COOKIE) != code:
            response.set_cookie(LANG_COOKIE, code,
                                max_age=LANG_COOKIE_MAX_AGE,
                                samesite="Lax",
                                secure=not app.debug)
        return response

    @app.route("/set-language/<code>")
    def set_language(code):
        """The language picker's target: remember ``code``, then go to ``next``.

        The picker cannot just link straight at the translated URL, because the
        landing page redirects a visitor with a remembered language — a direct
        link to ``/`` would bounce someone who deliberately picked English back
        to their old language. Going through here writes the cookie *first*.

        ``next`` is accepted only as a same-site absolute path, so this cannot
        be used as an open redirect.
        """
        code = normalize_lang(code)
        target = request.args.get("next") or "/"
        if not target.startswith("/") or target.startswith("//"):
            target = "/"
        response = redirect(target)
        response.set_cookie(LANG_COOKIE, code,
                            max_age=LANG_COOKIE_MAX_AGE,
                            samesite="Lax",
                            secure=not app.debug)
        return response

    def picker_url(code):
        """Language-picker href: the switch endpoint carrying the target URL."""
        return url_for("set_language", code=code, next=url_for_lang(code))

    app.jinja_env.globals.update(
        picker_url=picker_url,
        ui_strings=lambda: load_catalog(current_lang()),
        t=translate,
        t_html=translate_html,
        ui_lang=current_lang,
        ui_lang_tag=lambda: HTML_LANG_TAGS[current_lang()],
        ui_languages=SUPPORTED_UI_LANGUAGES,
        lang_alternates=lang_alternates,
        url_for_lang=url_for_lang,
        default_ui_lang=DEFAULT_UI_LANG,
    )
