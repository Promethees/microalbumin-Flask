"""Guards for the WCAG 2.2 Level AA conformance claim covering the desktop app.

The statement published at https://www.easyokapi.cbbiotec.vn/accessibility
covers this application and its installers as well as the web app. Nothing in
the code fails loudly when the markup drifts away from it: a `<label>` deleted
in a refactor, a skip link lost when a header is rewritten, a live region turned
back into a plain div, a High Contrast guard dropped from a new NSIS helper.
Each of those quietly breaks a criterion the project claims to meet, and each
looks fine on screen. This file is where they get caught.

These are *static* checks over the templates, the stylesheets, the scripts and
the installer sources. They cannot replace testing with a real screen reader —
roughly a third of what matters is machine-checkable, and the published
statement says exactly that. Every assertion names the success criterion it
defends, so a failure tells you which sentence has just stopped being true.

See `Rule.md` §2.36 and docs/accessibility/INSTALLERS.md.
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

# The pages a user can land on. `index.html` is the app; the rest are the
# standalone screens that load no stylesheet of their own.
STANDALONE_PAGES = (
    'legal.html', 'activate.html', 'goodbye.html',
    'restart_required.html', 'restarting.html',
    'license_banned.html', 'license_blocked.html', 'license_reverify.html',
)
ALL_PAGES = ('index.html',) + STANDALONE_PAGES


def read(*parts):
    with io.open(os.path.join(*parts), encoding='utf-8') as f:
        return f.read()


def template(name):
    return read(TEMPLATES, name)


# ── A tolerant tag collector ──────────────────────────────────────────────────
# The templates are Jinja, not HTML: `{% for %}` and `{{ t('x') }}` are not
# markup. html.parser is lenient enough to walk them, and every check below only
# needs tag names and attributes, never a well-formed tree.

JINJA_COMMENT = re.compile(r'\{#.*?#\}', re.S)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []          # [(name, {attr: value}), ...] in document order
        self._open = []
        self.text_of = {}       # id(entry) -> accumulated text
        self.in_label = set()   # ids of entries nested inside a <label>

    def handle_starttag(self, tag, attrs):
        entry = (tag, dict(attrs))
        self.tags.append(entry)
        # `<label>Text <input></label>` is a valid association and needs no
        # `for` — most checkboxes in this app use it.
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


# ── 2.4.1 Bypass Blocks / 1.3.1 landmarks ─────────────────────────────────────

def test_the_app_has_a_skip_link_ahead_of_the_instrument_rail():
    markup = template('index.html')
    assert 'class="skip-link"' in markup, \
        'no skip link — a keyboard user tabs the whole left rail to reach the data'
    assert 'href="#main-content"' in markup
    body = markup.index('<body')
    skip = markup.index('class="skip-link"')
    rail = markup.index('id="top-left-scrollable"')
    assert body < skip < rail, 'the skip link is not the first thing in the body'


@pytest.mark.parametrize('page', ALL_PAGES)
def test_every_page_has_exactly_one_main_landmark(page):
    mains = parse(template(page)).find('main')
    assert len(mains) == 1, '%s: expected one <main>, found %d' % (page, len(mains))


def test_landmark_tags_are_balanced_in_the_app_template():
    markup = template('index.html')
    for tag in ('main', 'aside', 'header', 'footer'):
        opened = len(re.findall(r'<%s\b' % tag, markup))
        closed = len(re.findall(r'</%s>' % tag, markup))
        assert opened == closed, \
            'index.html: <%s> %d open / %d closed' % (tag, opened, closed)


# ── 4.1.3 Status Messages ─────────────────────────────────────────────────────

def test_the_app_ships_both_live_regions():
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
    assert 'display: none' not in block
    assert 'clip-path' in block or 'clip:' in block


def test_error_helper_announces():
    js = read(STATIC, 'script', 'short-hands.js')
    assert 'const $showText' in js
    tail = js[js.index('const $showText'):]
    assert 'announceAlert(' in tail[:600], \
        '$showText displays an error without announcing it (3.3.1)'


# ── 1.3.1 / 3.3.2 Labels ──────────────────────────────────────────────────────

@pytest.mark.parametrize('page', ALL_PAGES)
def test_every_form_control_has_an_accessible_name(page):
    markup = template(page)
    labelled = set(re.findall(r'<label[^>]*\sfor="([^"]+)"', markup))
    p = parse(markup)

    unnamed = []
    for entry in p.tags:
        name, attrs = entry
        if name not in ('input', 'select', 'textarea'):
            continue
        if attrs.get('type') in ('hidden', 'submit', 'button', 'reset'):
            continue
        el_id = attrs.get('id', '')
        named = (
            el_id in labelled
            or 'aria-label' in attrs
            or 'aria-labelledby' in attrs
            or id(entry) in p.in_label
            # A checkbox or radio is written as `<label><input> Text</label>`.
            or attrs.get('type') in ('checkbox', 'radio')
        )
        if not named:
            unnamed.append(el_id or '<%s with no id>' % name)

    assert not unnamed, \
        '%s: controls with no accessible name (1.3.1/3.3.2): %s' % (page, unnamed)


# ── 4.1.2 Name, Role, Value ───────────────────────────────────────────────────

def test_collapsible_headings_are_buttons_that_report_their_state():
    markup = template('index.html')
    p = parse(markup)

    toggles = [(n, a) for n, a in p.tags
               if 'folder-section-toggle' in a.get('class', '')]
    assert len(toggles) >= 8, 'the collapsible section toggles have gone missing'

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
    css = read(STATIC, 'style.css')
    # The selector appears twice — the layout rule, and the accessibility
    # override that adds the visibility. Either carrying it is enough: the
    # later declaration is the one that applies.
    blocks = [css[m.end():css.index('}', m.end())]
              for m in re.finditer(r'\.section-collapse\.collapsed\s*\{', css)]
    assert blocks, 'the collapsed-panel rule has gone'
    assert any('visibility: hidden' in b for b in blocks), \
        'a collapsed section still holds focusable controls (2.4.3)'


def test_icon_only_buttons_carry_a_text_name():
    markup = template('index.html')
    p = parse(markup)
    EMOJI = re.compile('[\U0001F300-\U0001FAFF←-⇿☀-➿⬀-⯿️]')

    offenders = []
    for entry in p.find('button'):
        attrs = entry[1]
        text = p.text_of.get(id(entry), '')
        if EMOJI.sub('', text).strip() or 'aria-label' in attrs or 'sr-only' in text:
            continue
        offenders.append(attrs.get('id') or text.strip())

    assert not offenders, \
        'buttons whose whole name is an icon (4.1.2): %s' % offenders


def test_the_chrome_controls_are_real_buttons():
    """Each used to be a <div>/<img>/<span> with an onclick."""
    markup = template('index.html')
    for needle in ('<button type="button" id="logo"',
                   '<button type="button" class="toggle-container" id="toggleContainer"',
                   'button type="button" class="app-version-badge"'):
        assert needle in markup, 'not a button any more: %s' % needle


# ── 1.3.1 Tables ──────────────────────────────────────────────────────────────

def test_table_headers_declare_their_scope():
    markup = template('index.html')
    for _, attrs in parse(markup).find('th'):
        assert attrs.get('scope') in ('col', 'row'), \
            'a <th> has no scope — the association is left to guesswork'


def test_sortable_headers_are_operable_and_report_their_order():
    """A `<th onclick>` cannot be reached from the keyboard (2.1.1), and the
    arrow glyph was the only sign of the current sort (1.4.1)."""
    markup = template('index.html')
    assert 'onclick="sortJsonTable' not in markup, \
        'a sortable header still carries an onclick instead of data-sort-call'
    assert 'onclick="sortFileTable' not in markup
    assert markup.count('data-sort-call=') >= 4
    assert 'aria-sort=' in markup

    js = read(STATIC, 'script', 'a11y.js')
    assert 'upgradeSortableHeaders' in js, \
        'nothing promotes the server-rendered headers to buttons'


def test_the_file_tables_keep_their_semantics_after_a_refresh():
    """The renderers replace the whole table with innerHTML.

    Whatever the template shipped (caption, thead, scope) is gone the first
    time a fetch resolves, so the renderer has to rebuild it.
    """
    js = read(STATIC, 'script', 'navigation.js')
    for needed in ('_tableCaption(', '_sortHeaderCell(', '_rowBtnLabel('):
        assert needed in js, 'the accessible table scaffolding is gone: %s' % needed

    head = js[js.index('function _sortHeaderCell'):]
    head = head[:head.index('\n}')]
    for needed in ('scope="col"', 'aria-sort', 'sort-btn'):
        assert needed in head, '_sortHeaderCell no longer emits %s' % needed

    # 2.4.4 — three columns of identical "Select / Delete / Edit" say nothing
    # out of context, so each row button names its row.
    for renderer in ('renderJsonRows', 'renderFileRows', 'renderReportRows'):
        body = js[js.index('function %s' % renderer):]
        nxt = body.find('\nfunction ')
        body = body[:nxt if nxt != -1 else len(body)]
        assert 'aria-label="${_rowBtnLabel(' in body, \
            '%s: row buttons are unnamed' % renderer
        assert 'aria-pressed=' in body, \
            '%s: the selected row is marked by colour alone (1.4.1)' % renderer


# ── 1.1.1 Non-text Content ────────────────────────────────────────────────────

def test_every_chart_gets_a_data_table():
    chart_js = read(STATIC, 'script', 'generate-chart.js')
    assert 'buildChartDataTable(' in chart_js, \
        'generateChart no longer publishes a text alternative for the plot'

    a11y_js = read(STATIC, 'script', 'a11y.js')
    assert "setAttribute('role', 'img')" in a11y_js
    assert 'scope' in a11y_js, 'the generated data table has unassociated headers'


def test_decorative_images_are_hidden_from_assistive_technology():
    for _, attrs in parse(template('index.html')).find('img'):
        assert 'alt' in attrs, 'an <img> has no alt attribute'
        if attrs.get('alt') == '':
            assert attrs.get('aria-hidden') == 'true', \
                'a decorative image is not aria-hidden'


# ── 2.1.1 Keyboard ────────────────────────────────────────────────────────────

def test_scrollable_panels_are_reachable_from_the_keyboard():
    js = read(STATIC, 'script', 'a11y.js')
    assert 'enhanceScrollableRegions' in js
    for selector in ('#top-left-scrollable', '#chart-container'):
        assert selector in js, 'the %s scroller lost its keyboard fallback' % selector


def test_the_user_guide_is_a_dialogue_you_can_leave():
    js = read(STATIC, 'script', 'user-guide.js')
    assert "setAttribute('role', 'dialog')" in js
    assert "setAttribute('aria-modal', 'true')" in js
    assert "'Escape'" in js, 'the guide covers the app with no keyboard way out'
    assert '_returnFocusTo' in js, 'focus is not handed back when the guide closes'


# ── 1.4.13 Content on Hover or Focus ──────────────────────────────────────────

def test_the_hint_bubble_is_dismissible_hoverable_and_described():
    js = read(STATIC, 'script', 'tooltip.js')
    assert "'Escape'" in js, 'the hint bubble cannot be dismissed (1.4.13)'
    assert 'aria-describedby' in js, 'the hint text never reaches a screen reader'

    css = read(STATIC, 'style.css')
    visible = css[css.index('#okapi-tooltip.visible'):]
    visible = visible[:visible.index('}')]
    assert 'pointer-events: auto' in visible, \
        'the bubble cannot be hovered, so a long hint cannot be read under magnification'


# ── The stylesheet primitives ─────────────────────────────────────────────────

def test_stylesheet_keeps_its_accessibility_primitives():
    css = read(STATIC, 'style.css')
    for token in (':focus-visible', '.skip-link', '.sr-only',
                  'prefers-reduced-motion', 'forced-colors', '--error-ink'):
        assert token in css, 'style.css no longer defines %s' % token


@pytest.mark.parametrize('page', STANDALONE_PAGES)
def test_standalone_pages_load_the_shared_primitives(page):
    """They carry their own inline CSS and load no stylesheet."""
    assert '_a11y_head.html' in template(page), \
        '%s: no focus ring, no .sr-only, no reduced-motion opt-out' % page


# ── The installers ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('script', ('setup.nsi', 'setup-frozen.nsi'))
def test_windows_installer_honours_high_contrast(script):
    """High Contrast exists so the user can pick colours they can read.

    Painting over it with a hard-coded indigo theme takes that away, so every
    theming helper has to bail out when the flag is set.
    """
    nsi = read(ROOT, 'installer-win', script)
    assert 'DetectHighContrast' in nsi, '%s: no High Contrast detection' % script
    assert 'SPI_GETHIGHCONTRAST' in nsi

    # A compile-time InstallColors cannot be turned off at run time.
    assert not re.search(r'^\s*InstallColors\b', nsi, re.M), \
        '%s: InstallColors burns the theme into the binary' % script

    helpers = re.findall(r'^Function (_Dark\w*|_OnGUIInit)\b', nsi, re.M)
    assert helpers, '%s: no theming helpers found — did they move?' % script
    for fn in helpers:
        body = nsi[nsi.index('Function %s\n' % fn):]
        body = body[:body.index('FunctionEnd')]
        assert '$HighContrast' in body, \
            '%s: %s paints over High Contrast' % (script, fn)


def test_no_installer_dialogue_is_timed():
    """2.2.1 Timing Adjustable — nothing in an install may expire."""
    for folder in ('installer-mac', 'installer-linux', 'installer-win'):
        base = os.path.join(ROOT, folder)
        for name in os.listdir(base):
            path = os.path.join(base, name)
            if not os.path.isfile(path) or name.endswith(('.bmp', '.ico', '.png')):
                continue
            try:
                body = read(base, name)
            except (UnicodeDecodeError, OSError):
                continue
            assert 'giving up after' not in body, \
                '%s/%s: a dialogue times out on its own' % (folder, name)


def test_the_linux_installer_has_a_documented_non_graphical_route():
    """Tk exposes almost nothing to AT-SPI, so this is the supported path."""
    setup = read(ROOT, 'installer-linux', 'setup.sh')
    for flag in ('--token', '--no-gui', 'EASYOKAPI_NO_GUI'):
        assert flag in setup, 'setup.sh no longer offers %s' % flag

    ui = read(ROOT, 'installer-linux', 'setup_ui.py')
    assert 'EASYOKAPI_NO_GUI' in ui, 'setup_ui.py cannot be opted out of'
    assert '<Escape>' in ui, 'the setup window cannot be cancelled from the keyboard'
    assert 'highlightthickness' in ui, 'Tk buttons have no visible focus ring (2.4.7)'


def test_the_splash_screen_stands_aside_for_a_screen_reader():
    """A borderless, always-on-top window no screen reader can see is only in
    the way; it reports on stdout instead."""
    for folder in ('installer-mac', 'installer-linux'):
        splash = read(ROOT, folder, 'splash.py')
        assert '_screen_reader_running' in splash, '%s: splash never stands aside' % folder
        assert 'EASYOKAPI_NO_SPLASH' in splash
        assert 'VoiceOver' in splash and 'orca' in splash


def test_the_two_splash_copies_stay_identical():
    """They are duplicated by design; a fix to one must reach the other."""
    assert read(ROOT, 'installer-mac', 'splash.py') == \
        read(ROOT, 'installer-linux', 'splash.py'), \
        'installer-mac/splash.py and installer-linux/splash.py have drifted'


def test_no_token_field_is_masked():
    """A masked field reads as "bullet" per character and hides a bad paste,
    for a single-use token that expires in 30 minutes."""
    # The script explains in a comment why the field is not masked, so the
    # check has to look at the code rather than at the reasoning.
    scpt = '\n'.join(ln for ln in read(ROOT, 'installer-mac', 'run.scpt').split('\n')
                     if not ln.lstrip().startswith('--'))
    assert 'with hidden answer' not in scpt, \
        'the macOS token dialogue masks the field'
    assert 'show="●"' not in read(ROOT, 'installer-linux', 'setup_ui.py').split(
        'def _on_toggle_hide')[0], 'the Linux token field is masked by default'
    sh = '\n'.join(ln for ln in read(ROOT, 'installer-linux', 'setup.sh').split('\n')
                   if not ln.lstrip().startswith('#'))
    assert 'read -rsp' not in sh, \
        'the terminal prompt echoes nothing, so a screen reader announces nothing'


def test_the_installer_accessibility_guide_exists():
    guide = read(ROOT, 'docs', 'accessibility', 'INSTALLERS.md')
    for section in ('Windows', 'macOS', 'Linux', 'What is still not good enough'):
        assert section in guide, 'INSTALLERS.md lost its %s section' % section


# ── Catalogs ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('lang', LANGS)
def test_every_accessibility_name_is_translated(lang):
    catalog = json.load(io.open(os.path.join(CATALOGS, '%s.json' % lang),
                                encoding='utf-8'))
    english = json.load(io.open(os.path.join(CATALOGS, 'en.json'), encoding='utf-8'))
    missing = [k for k in english if k.startswith('a11y.')
               and not catalog.get(k, '').strip()]
    assert not missing, '%s: untranslated accessibility names: %s' % (lang, missing[:5])


def test_every_aria_key_used_in_the_markup_exists():
    """`data-i18n-aria` naming a key that is not in the catalog leaves the
    control with the English fallback for ever, silently."""
    english = json.load(io.open(os.path.join(CATALOGS, 'en.json'), encoding='utf-8'))
    used = set(re.findall(r'data-i18n-aria="([^"]+)"', template('index.html')))
    missing = sorted(k for k in used if k not in english)
    assert not missing, 'aria keys with no catalog entry: %s' % missing
