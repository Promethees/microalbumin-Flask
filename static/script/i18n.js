/* UI localization (i18n) runtime for the Easy OKAPI web app.
 *
 * The page's *markup* is already translated server-side — templates/index.html
 * renders `{{ t('key') }}` (see src/i18n.py), so there is no flash of English
 * and no dependency on this file for anything the server drew. What this file
 * exists for is the other half: the strings the app builds at runtime — Swal
 * dialogs, table rows, chart labels — which the server never sees.
 *
 * index.html injects the active catalog as `window.UI_STRINGS` and the active
 * code as `window.UI_LANG`. Both are set as window properties (not a top-level
 * `const`, which would create a lexical binding invisible to other scripts),
 * because the app's scripts are separate files.
 *
 * Also applies translations to tagged DOM, for subtrees built by JavaScript:
 *   data-i18n="key"        -> textContent
 *   data-i18n-html="key"   -> innerHTML (for strings with inline markup)
 *   data-i18n-hint="key"   -> data-hint attribute (tooltip.js reads this)
 *   data-i18n-ph="key"     -> placeholder
 *   data-i18n-aria="key"   -> aria-label
 *   data-i18n-title="key"  -> title
 *
 * Changing language navigates to another URL (the language lives in the path),
 * so this only ever runs against the catalog the server rendered with.
 */
(function () {
    'use strict';

    var STRINGS = window.UI_STRINGS || {};
    var LANG = window.UI_LANG || 'en';

    // Look up a translation. Falls back to the supplied English literal (or the
    // key itself) so an unmigrated/missing string is never blank.
    function t(key, fallback) {
        if (key == null) return fallback != null ? fallback : '';
        var v = STRINGS[key];
        if (typeof v === 'string') return v;
        return fallback != null ? fallback : key;
    }

    // t() with {placeholder} substitution: t('x', 'fallback', {n: 3}).
    function tf(key, fallback, values) {
        var out = t(key, fallback);
        if (!values) return out;
        for (var name in values) {
            if (Object.prototype.hasOwnProperty.call(values, name)) {
                out = out.split('{' + name + '}').join(values[name]);
            }
        }
        return out;
    }

    var ATTR_MAP = [
        ['data-i18n', 'text'],
        ['data-i18n-html', 'html'],
        ['data-i18n-hint', 'data-hint'],
        ['data-i18n-ph', 'placeholder'],
        ['data-i18n-aria', 'aria-label'],
        ['data-i18n-title', 'title']
    ];

    function _applyOne(el, datasetAttr, target) {
        var key = el.getAttribute(datasetAttr);
        if (!key) return;
        var translated = STRINGS[key];
        if (typeof translated !== 'string') return; // keep the in-place fallback
        if (target === 'text') {
            el.textContent = translated;
        } else if (target === 'html') {
            el.innerHTML = translated;
        } else {
            el.setAttribute(target, translated);
        }
    }

    // Translate `root` and its descendants in place. Safe to call repeatedly and
    // on dynamically-built subtrees.
    function applyTranslations(root) {
        root = root || document;
        for (var i = 0; i < ATTR_MAP.length; i++) {
            var datasetAttr = ATTR_MAP[i][0];
            var target = ATTR_MAP[i][1];
            var nodes = root.querySelectorAll('[' + datasetAttr + ']');
            for (var j = 0; j < nodes.length; j++) {
                _applyOne(nodes[j], datasetAttr, target);
            }
        }
    }

    window.t = t;
    window.tf = tf;
    window.applyTranslations = applyTranslations;
    window.UI_I18N = { t: t, tf: tf, applyTranslations: applyTranslations, lang: LANG };

    document.addEventListener('DOMContentLoaded', function () {
        applyTranslations(document);
    });
})();
