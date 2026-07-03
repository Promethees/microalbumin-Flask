/* UI localization (i18n) applier for Easy OKAPI.
 *
 * The server injects the active language's catalog into index.html as
 * `const UI_STRINGS` (a flat key -> string map) and the active code as
 * `const UI_LANG`. These are global *lexical* bindings (top-level const), read
 * here by bare name — NOT via `window.`, where they do not appear. This module:
 *   - exposes `t(key, fallback)` for dynamic strings (Swal dialogs, etc.), and
 *   - applies translations to tagged DOM elements via `applyTranslations()`.
 *
 * Tagging contract on elements in index.html (English text stays in place as
 * the fallback, so source builds / a missing catalog still read fine):
 *   data-i18n="key"        -> textContent
 *   data-i18n-html="key"   -> innerHTML (for strings with inline markup)
 *   data-i18n-hint="key"   -> data-hint attribute (tooltip.js reads this)
 *   data-i18n-ph="key"     -> placeholder
 *   data-i18n-aria="key"   -> aria-label
 *
 * Changing the UI language reloads the page (see init.js), so this only ever
 * runs against the catalog the server already rendered with — no live
 * re-translation of two languages at once.
 */
(function () {
    'use strict';

    // NOTE: index.html declares the catalog as `const UI_STRINGS = {...}`. A
    // top-level `const`/`let` creates a global *lexical* binding, NOT a property
    // on `window`, so `window.UI_STRINGS` is undefined. Read the bare global
    // binding by name (guarded with typeof), exactly like the page reads
    // USER_SETTINGS. Reading window.UI_STRINGS here left STRINGS empty and made
    // every string fall back to English regardless of the chosen language.
    const STRINGS = (typeof UI_STRINGS !== 'undefined' && UI_STRINGS) ? UI_STRINGS : {};
    const LANG = (typeof UI_LANG !== 'undefined' && UI_LANG) ? UI_LANG : 'en';

    // Look up a translation. Falls back to the supplied English literal (or the
    // key itself) so an unmigrated/missing string is never blank.
    function t(key, fallback) {
        if (key == null) return fallback != null ? fallback : '';
        const v = STRINGS[key];
        if (typeof v === 'string') return v;
        return fallback != null ? fallback : key;
    }

    const ATTR_MAP = [
        ['data-i18n', 'text'],
        ['data-i18n-html', 'html'],
        ['data-i18n-hint', 'data-hint'],
        ['data-i18n-ph', 'placeholder'],
        ['data-i18n-aria', 'aria-label']
    ];

    function _applyOne(el, datasetAttr, target) {
        const key = el.getAttribute(datasetAttr);
        if (!key) return;
        const translated = STRINGS[key];
        if (typeof translated !== 'string') return; // keep the in-place English fallback
        if (target === 'text') {
            el.textContent = translated;
        } else if (target === 'html') {
            el.innerHTML = translated;
        } else {
            el.setAttribute(target, translated);
        }
    }

    // Translate `root` and its descendants in place. Safe to call repeatedly and
    // on dynamically-built subtrees (e.g. the settings modal).
    function applyTranslations(root) {
        root = root || document;
        for (let i = 0; i < ATTR_MAP.length; i++) {
            const datasetAttr = ATTR_MAP[i][0];
            const target = ATTR_MAP[i][1];
            const nodes = root.querySelectorAll('[' + datasetAttr + ']');
            for (let j = 0; j < nodes.length; j++) {
                _applyOne(nodes[j], datasetAttr, target);
            }
        }
    }

    window.t = t;
    window.applyTranslations = applyTranslations;
    window.UI_I18N = { t: t, applyTranslations: applyTranslations, lang: LANG };

    document.addEventListener('DOMContentLoaded', function () {
        applyTranslations(document);
    });
})();
