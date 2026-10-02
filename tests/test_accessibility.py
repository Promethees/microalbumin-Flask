"""Guards for the WCAG 2.2 Level AA conformance claim published at /accessibility.

The statement on that page is a promise, and nothing in the app fails loudly
when the markup drifts away from it: a `<label>` deleted in a refactor, a skip
link lost when a header is rewritten, a live region turned into a plain div —
each of those quietly breaks a criterion the site claims to meet, and each looks
fine on screen. This file is where they get caught.

These are *static* checks over the templates, the stylesheets and the scripts.
They do not import `main.py` (the online branch pulls in flask_socketio,
firebase and the rest, which the test venv does not install — see
tests/conftest.py for the same reasoning), and they cannot replace testing with
a real screen reader. Roughly a third of what matters is machine-checkable;
this is that third, and the accessibility statement says so in as many words.

Every assertion below names the success criterion it defends, so a failure
tells you which sentence of the published claim has just stopped being true.
"""
import io
import json
import os
import re
from html.parser import HTMLParser

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES = os.path.join(ROOT, 'templates')
STATIC = os.path.join(ROOT, 'static')
CATALOGS = os.path.join(ROOT, 'ui_translations')

LANGS = ('en', 'vi', 'zh', 'fr', 'ja', 'ru', 'ko')

# Full pages — the ones a visitor can land on. Partials (`_lang_head.html`,
# `_a11y_head.html`, …) and the documents that extend `legal_base.html` are
# checked through their frame instead.
FULL_PAGES = (
    'index.html', 'landing.html', 'legal_base.html',
    'login.html', 'signup.html', 'forgot_password.html',
    'reset_password.html', 'verify_email.html',
)

# Pages that carry a repeated navigation block and therefore owe a skip link
# (2.4.1). The account pages are a single card with no repeated navigation, so
# they are deliberately absent.
PAGES_WITH_NAV = ('index.html', 'landing.html', 'legal_base.html')


def read(*parts):
    with io.open(os.path.join(*parts), encoding='utf-8') as f:
        return f.read()


def template(name):
    return read(TEMPLATES, name)


# ── A tolerant tag collector ──────────────────────────────────────────────────
# The templates are Jinja, not HTML: `{% for %}` and `{{ t('x') }}` are not
# markup. html.parser is lenient enough to walk them, and every check below
# only needs tag names and attributes, never a well-formed tree.

JINJA_COMMENT = re.compile(r'\{#.*?#\}', re.S)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []          # [(name, {attr: value}), ...] in document order
        self._open = []
        self.text_of = {}       # id(tag entry) -> accumulated text
        self.in_label = set()   # ids of entries nested inside a <label>

    def handle_starttag(self, tag, attrs):
        entry = (tag, dict(attrs))
        self.tags.append(entry)
        # `<label>Text <input></label>` is a valid association and needs no
        # `for` — most of the checkboxes and the report title box use it.
        if any(open_entry[0] == 'label' for open_entry, _ in self._open):
            self.in_label.add(id(entry))
        self._open.append((entry, []))

    def handle_endtag(self, tag):
        while self._open:
            entry, chunks = self._open.pop()
            self.text_of[id(entry)] = ''.join(chunks)
            if entry[0] == tag:
                break

    def handle_data(self, data):
        for _, chunks in self._open:
            chunks.append(data)

    def close(self):
        super().close()
        while self._open:
            entry, chunks = self._open.pop()
            self.text_of.setdefault(id(entry), ''.join(chunks))

    def find(self, name):
        return [e for e in self.tags if e[0] == name]


def parse(markup):
    # A Jinja comment can quote markup while explaining it ("as a bare <img
    # onclick> this was…"); the parser would read that as a real tag.
    p = Tags()
    p.feed(JINJA_COMMENT.sub('', markup))
    p.close()
    return p


@pytest.fixture(scope='module')
def parsed():
    return {name: parse(template(name)) for name in FULL_PAGES}


# ── 2.4.1 Bypass Blocks ───────────────────────────────────────────────────────

@pytest.mark.parametrize('page', PAGES_WITH_NAV)
def test_page_with_repeated_navigation_has_a_skip_link(page):
    markup = template(page)
    assert 'class="skip-link"' in markup, \
        '%s: no skip link — a keyboard user has to tab the whole nav on every page' % page
    assert 'href="#main-content"' in markup, \
        '%s: the skip link does not point at #main-content' % page


@pytest.mark.parametrize('page', FULL_PAGES)
def test_every_full_page_has_exactly_one_main_landmark(page, parsed):
    mains = parsed[page].find('main')
    assert len(mains) == 1, '%s: expected one <main>, found %d' % (page, len(mains))
    assert mains[0][1].get('id') == 'main-content', \
        '%s: <main> must carry id="main-content" (the skip-link target)' % page


def test_the_skip_link_is_the_first_focusable_thing_in_the_body():
    """It has to come before the nav, or it is not a bypass."""
    for page in PAGES_WITH_NAV:
        markup = template(page)
        body = markup.index('<body>')
        skip = markup.index('class="skip-link"')
        assert skip > body, '%s: skip link is outside <body>' % page


# ── 4.1.3 Status Messages ─────────────────────────────────────────────────────

def test_the_web_app_ships_both_live_regions():
    """`announce()` / `announceAlert()` write into these; they must pre-exist.

    A live region created at the moment it has something to say is usually
    missed — the screen reader has to have been observing it beforehand.
    """
    markup = template('index.html')
    assert 'id="a11y-live-region"' in markup and 'aria-live="polite"' in markup
    assert 'id="a11y-alert-region"' in markup and 'aria-live="assertive"' in markup


def test_live_regions_are_not_display_none():
    """`display: none` hides a live region from assistive technology too."""
    css = read(STATIC, 'style.css')
    block = css[css.index('#a11y-live-region'):]
    block = block[:block.index('}')]
    assert 'display: none' not in block, \
        'the live region is display:none — nothing written into it is announced'
    assert 'clip-path' in block or 'clip:' in block


def test_error_helpers_announce():
    """`$showText` is the app's error path; writing to the DOM is not enough."""
    js = read(STATIC, 'script', 'short-hands.js')
    assert 'const $showText' in js
    tail = js[js.index('const $showText'):]
    assert 'announceAlert(' in tail[:600], \
        '$showText displays an error without announcing it (3.3.1)'


# ── 1.3.1 / 3.3.2 Labels ──────────────────────────────────────────────────────

LABELLED_BY_ANCESTOR = {
    # A honeypot, hidden from people and from assistive technology alike.
    'contact-website',
}


def _labelled_ids(markup):
    """Ids named by a `<label for=...>` anywhere in the template."""
    return set(re.findall(r'<label[^>]*\sfor="([^"]+)"', markup))


@pytest.mark.parametrize('page', FULL_PAGES + ('contact.html',))
def test_every_form_control_has_an_accessible_name(page):
    markup = template(page)
    labelled = _labelled_ids(markup)
    p = parse(markup)

    unnamed = []
    for entry in p.tags:
        name, attrs = entry
        if name not in ('input', 'select', 'textarea'):
            continue
        if attrs.get('type') in ('hidden', 'submit', 'button', 'reset'):
            continue
        el_id = attrs.get('id', '')
        if el_id in LABELLED_BY_ANCESTOR:
            continue
        named = (
            el_id in labelled
            or 'aria-label' in attrs
            or 'aria-labelledby' in attrs
            # `<label>Text <input></label>` — an implicit association, which is
            # how most of the checkboxes and the report title box are written.
            or id(entry) in p.in_label
        )
        if not named:
            unnamed.append(el_id or '<%s with no id>' % name)

    assert not unnamed, \
        '%s: controls with no accessible name (1.3.1/3.3.2): %s' % (page, unnamed)


# ── 4.1.2 Name, Role, Value ───────────────────────────────────────────────────

def test_collapsible_headings_are_buttons_that_report_their_state():
    """A clickable <h2> cannot be reached or operated from a keyboard."""
    markup = template('index.html')
    p = parse(markup)

    toggles = [(n, a) for n, a in p.tags
               if 'folder-section-toggle' in a.get('class', '')]
    assert toggles, 'the collapsible section toggles have disappeared'

    for name, attrs in toggles:
        assert name == 'button', \
            'a .folder-section-toggle is a <%s>, not a button (2.1.1)' % name
        assert attrs.get('aria-expanded') in ('true', 'false'), \
            'a section toggle does not report aria-expanded (4.1.2)'
        controls = attrs.get('aria-controls')
        assert controls, 'a section toggle has no aria-controls'
        assert 'id="%s"' % controls in markup, \
            'aria-controls="%s" points at nothing' % controls


def test_collapsed_panels_leave_the_tab_order():
    """`max-height: 0` hides a panel visually but keeps its buttons tabbable."""
    css = read(STATIC, 'style.css')
    block = css[css.index('.section-collapse.collapsed'):]
    block = block[:block.index('}')]
    assert 'visibility: hidden' in block, \
        'a collapsed section still holds focusable controls (2.4.3)'


def test_icon_only_buttons_carry_a_text_name():
    """An emoji is not an accessible name."""
    markup = template('index.html')
    p = parse(markup)

    EMOJI = re.compile(
        '[\U0001F300-\U0001FAFF←-⇿☀-➿⬀-⯿️]')

    offenders = []
    for entry in p.find('button'):
        attrs = entry[1]
        text = p.text_of.get(id(entry), '')
        stripped = EMOJI.sub('', text).strip()
        # Jinja expressions count as text: they render a word at request time.
        if stripped or 'aria-label' in attrs or 'sr-only' in text:
            continue
        offenders.append(attrs.get('id') or text.strip())

    assert not offenders, \
        'buttons whose whole name is an icon (4.1.2): %s' % offenders


def test_the_theme_toggle_and_the_logo_are_real_buttons():
    """Both used to be a <div>/<img> with an onclick — unreachable by keyboard."""
    markup = template('index.html')
    assert '<button type="button" class="toggle-container" id="toggleContainer"' in markup
    assert '<button type="button" id="logo"' in markup


# ── 1.3.1 Tables ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('page', ('index.html', 'privacy.html', 'terms.html',
                                  'accessibility.html'))
def test_table_headers_declare_their_scope(page):
    markup = template(page)
    for _, attrs in parse(markup).find('th'):
        assert attrs.get('scope') in ('col', 'row'), \
            '%s: a <th> has no scope — the association is left to guesswork' % page


def test_the_file_tables_keep_their_semantics_after_a_refresh():
    """The renderers replace the whole table with innerHTML.

    Whatever the template shipped (caption, thead, scope) is gone the first
    time a fetch resolves, so the renderer has to rebuild it.
    """
    js = read(STATIC, 'script', 'navigation.js')
    assert '_tableHead(' in js, 'the accessible table scaffolding is gone'
    head = js[js.index('function _tableHead'):]
    head = head[:head.index('\n}')]
    for needed in ('<caption', 'sr-only', '<thead', 'scope="col"'):
        assert needed in head, '_tableHead no longer emits %s' % needed

    # 2.4.4 — three columns of identical "Select / Delete / Edit" say nothing
    # out of context, so each row button names its row.
    assert '_rowBtnLabel(' in js
    for renderer in ('updateJSONTable', 'updateFileTable', 'updateReportTable'):
        body = js[js.index('function %s' % renderer):]
        body = body[:body.index('\nfunction ') if '\nfunction ' in body else len(body)]
        assert 'aria-label="${_rowBtnLabel(' in body, \
            '%s: row buttons are unnamed' % renderer


# ── 1.1.1 Non-text Content ────────────────────────────────────────────────────

def test_every_chart_gets_a_data_table():
    """A <canvas> is opaque to assistive technology; the numbers must exist too."""
    chart_js = read(STATIC, 'script', 'generate-chart.js')
    assert 'buildChartDataTable(' in chart_js, \
        'generateChart no longer publishes a text alternative for the plot'

    a11y_js = read(STATIC, 'script', 'a11y.js')
    assert "setAttribute('role', 'img')" in a11y_js
    assert "aria-label" in a11y_js
    assert 'scope' in a11y_js, 'the generated data table has unassociated headers'


def test_decorative_images_are_hidden_from_assistive_technology():
    """Empty alt is only half of it — a decorative image must not be announced."""
    for page in ('index.html',):
        for _, attrs in parse(template(page)).find('img'):
            assert 'alt' in attrs, '%s: an <img> has no alt attribute' % page
            if attrs.get('alt') == '':
                assert attrs.get('aria-hidden') == 'true', \
                    '%s: a decorative image is not aria-hidden' % page


# ── 2.1.1 Keyboard ────────────────────────────────────────────────────────────

def test_scrollable_panels_are_reachable_from_the_keyboard():
    js = read(STATIC, 'script', 'a11y.js')
    assert 'enhanceScrollableRegions' in js
    for selector in ('#top-left-scrollable', '#chart-container',
                     '#report-items-container', '.file-table-container'):
        assert selector in js, 'the %s scroller lost its keyboard fallback' % selector


# ── 1.4.13 Content on Hover or Focus ──────────────────────────────────────────

def test_the_hint_bubble_is_dismissible_hoverable_and_described():
    js = read(STATIC, 'script', 'tooltip.js')
    assert "'Escape'" in js, 'the hint bubble cannot be dismissed (1.4.13)'
    assert "aria-describedby" in js, 'the hint text never reaches a screen reader'

    css = read(STATIC, 'style.css')
    visible = css[css.index('#okapi-tooltip.visible'):]
    visible = visible[:visible.index('}')]
    assert 'pointer-events: auto' in visible, \
        'the bubble cannot be hovered, so a long hint cannot be read under magnification'


# ── 2.4.7 / 1.4.3 / 2.3.3 — the stylesheet primitives ─────────────────────────

@pytest.mark.parametrize('sheet,required', [
    ('style.css', (':focus-visible', '.skip-link', '.sr-only',
                   'prefers-reduced-motion', 'forced-colors')),
    ('landing.css', (':focus-visible', '.skip-link', '.sr-only',
                     'prefers-reduced-motion')),
])
def test_stylesheet_keeps_its_accessibility_primitives(sheet, required):
    css = read(STATIC, sheet)
    for token in required:
        assert token in css, '%s no longer defines %s' % (sheet, token)


def test_standalone_account_pages_load_the_shared_primitives():
    """They carry their own inline CSS and load neither app stylesheet."""
    for page in ('login.html', 'signup.html', 'forgot_password.html',
                 'reset_password.html', 'verify_email.html', 'callback.html'):
        assert '_a11y_head.html' in template(page), \
            '%s: no focus ring, no .sr-only, no reduced-motion opt-out' % page


def test_error_text_clears_the_contrast_floor():
    """Bare `red` is 4.0:1 on white — under the 4.5:1 that 1.4.3 requires."""
    css = read(STATIC, 'style.css')
    block = css[css.index('/* 1.4.3 Contrast (Minimum) for the error text'):]
    block = block[:block.index('body.dark')]
    assert 'var(--error-color-light)' in block
    assert 'color: red' not in block


# ── The published statement ───────────────────────────────────────────────────

def test_the_accessibility_statement_is_reachable_from_every_footer():
    for page in ('index.html', 'landing.html', 'legal_base.html'):
        assert "url_for('accessibility')" in template(page), \
            '%s: the statement is published but not linked' % page


def test_the_statement_is_localized_like_the_other_legal_documents():
    src = read(ROOT, 'src', 'i18n.py')
    endpoints = src[src.index('LOCALIZED_ENDPOINTS'):]
    endpoints = endpoints[:endpoints.index(')')]
    assert '"accessibility"' in endpoints, \
        '/vi/accessibility and friends do not exist — the statement is English-only'


def test_the_statement_states_a_conformance_target_and_its_gaps():
    """A statement with no limitations section is marketing, not a claim."""
    en = json.load(io.open(os.path.join(CATALOGS, 'en.json'), encoding='utf-8'))
    assert 'WCAG 2.2' in en['a11y.standard.p1']
    assert 'partially conformant' in en['a11y.standard.c1'].lower()
    # Every limitation must name a workaround; one without is a dead end.
    limits = [k for k in en if re.match(r'^a11y\.limits\.c\d+$', k)]
    assert len(limits) >= 3, 'the known-limitations list has been emptied'
    for key in limits:
        assert 'Workaround' in en[key], \
            '%s describes a barrier with no way round it' % key


def test_the_statement_gives_a_feedback_channel_and_a_response_time():
    en = json.load(io.open(os.path.join(CATALOGS, 'en.json'), encoding='utf-8'))
    assert 'working days' in en['a11y.feedback.p2'], \
        'the statement promises no response time'
    assert 'a11y.feedback.b_email' in en


@pytest.mark.parametrize('lang', LANGS)
def test_the_statement_is_published_in_every_language(lang):
    catalog = json.load(io.open(os.path.join(CATALOGS, '%s.json' % lang),
                                encoding='utf-8'))
    for key in ('a11y.title', 'a11y.lede', 'a11y.standard.c1',
                'a11y.limits.callout', 'a11y.feedback.p1',
                'a11y.installers.b1', 'a11y.skip_to_main'):
        assert catalog.get(key, '').strip(), '%s: %s is missing or empty' % (lang, key)
