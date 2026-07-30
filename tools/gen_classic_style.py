"""Generate the `body.ui-classic` layer by diffing a released stylesheet against the current one.

    usage:  git show a544ab1:static/style.css > /tmp/ref.css     # v1.3.11
            python3 tools/gen_classic_style.py /tmp/ref.css static/style.css /tmp/classic.css

    Then splice the output into static/style.css between the BEGIN/END GENERATED
    CLASSIC LAYER markers. Rules the redesign *added* have no counterpart in the
    reference and so cannot be diffed — they are undone by the hand-written reset
    block that follows the markers; keep that list in step.

Why generated rather than hand-written: the redesign rewrote ~519 colour
literals *inside* rules (e.g. `body.dark { background-color: #111827 }` became
`#0e1113`). Redefining tokens cannot undo that — a custom property does not
override a concrete declaration — so a hand-written token block restored only
the parts of the old look that happened to read from tokens. This walks both
sheets and emits an override for every declaration whose value actually differs,
which is exact by construction and regenerable.

"""
import re
import sys
from collections import OrderedDict

REF = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ref.css'
CUR = sys.argv[2] if len(sys.argv) > 2 else 'static/style.css'
OUT = sys.argv[3] if len(sys.argv) > 3 else '/tmp/classic_generated.css'

# Declarations that describe the page's *structure* rather than its look, or that
# belong to the new markup: overriding them would fight the layout rather than
# restore the old skin.
SKIP_PROPS = {
    'content', 'animation-name', 'z-index', 'position', 'display', 'inset',
    'grid-template-columns', 'flex-direction',
}

# Selectors we do not prefix (they cannot be scoped under body) or do not want.
SKIP_SELECTOR_RE = re.compile(
    r'^(html|:root|\*|@|::selection|::-webkit-scrollbar|body::|#session-strip|\.strip-|\.init-trace|\.init-orb|\.num\b|\.lbl\b)'
)


def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def parse(css):
    """-> OrderedDict[(media, selector)] = OrderedDict[prop] = value

    A flat parser is enough here: the sheets use plain rules plus @media /
    @keyframes blocks, no nesting beyond one level.
    """
    css = strip_comments(css)
    rules = OrderedDict()
    i, n = 0, len(css)
    media_stack = []
    while i < n:
        brace = css.find('{', i)
        if brace == -1:
            break
        head = css[i:brace].strip()
        if head.startswith('@'):
            at = head.split('{')[0].strip()
            # find the matching close brace of this at-rule
            depth, j = 1, brace + 1
            while j < n and depth:
                if css[j] == '{':
                    depth += 1
                elif css[j] == '}':
                    depth -= 1
                j += 1
            body = css[brace + 1:j - 1]
            if at.startswith('@media'):
                inner = parse(body)
                for (m, sel), decls in inner.items():
                    key = (at if not m else f'{at} && {m}', sel)
                    rules.setdefault(key, OrderedDict()).update(decls)
            # @keyframes / @font-face / @import: not part of the skin diff
            i = j
            continue
        close = css.find('}', brace)
        if close == -1:
            break
        body = css[brace + 1:close]
        decls = OrderedDict()
        for part in body.split(';'):
            if ':' not in part:
                continue
            prop, _, val = part.partition(':')
            prop, val = prop.strip(), val.strip()
            if not prop or not val:
                continue
            decls[prop] = val
        for sel in head.split(','):
            sel = sel.strip()
            if sel:
                rules.setdefault(('', sel), OrderedDict()).update(decls)
        i = close + 1
    return rules


def scope(sel):
    """Prefix a selector so it only applies under body.ui-classic, and so it
    outranks the instrument rule it is overriding (one extra class = +0,1,0).

    v1.3.11 writes theme rules two ways — `body.dark X` and a bare `.dark X`.
    Both mean the class on <body>, so a leading `.dark`/`.light` has to be folded
    into the body compound, not treated as an ancestor element.
    """
    sel = sel.strip()
    for theme in ('.dark', '.light'):
        if sel == theme:
            return 'body.ui-classic' + theme
        if sel.startswith(theme + ' ') or sel.startswith(theme + '.') or sel.startswith(theme + ':'):
            return 'body.ui-classic' + theme + sel[len(theme):]
    if sel == 'body':
        return 'body.ui-classic'
    if sel.startswith('body'):
        return 'body.ui-classic' + sel[4:]
    return 'body.ui-classic ' + sel


def main():
    ref = parse(open(REF).read())
    cur = parse(open(CUR).read())

    out_by_media = OrderedDict()
    stats = {'changed': 0, 'restored_rules': 0, 'removed_decls': 0}

    for (media, sel), rdecls in ref.items():
        if SKIP_SELECTOR_RE.match(sel):
            continue
        cdecls = cur.get((media, sel))
        diff = OrderedDict()
        if cdecls is None:
            # a rule the redesign deleted outright — restore it whole
            for p, v in rdecls.items():
                if p in SKIP_PROPS or p.startswith('--'):
                    continue
                diff[p] = v
            if diff:
                stats['restored_rules'] += 1
        else:
            for p, v in rdecls.items():
                if p in SKIP_PROPS or p.startswith('--'):
                    continue
                now = cdecls.get(p)
                if now is None:
                    # the redesign dropped this declaration (e.g. backdrop-filter)
                    diff[p] = v
                    stats['removed_decls'] += 1
                elif _norm(now) != _norm(v):
                    diff[p] = v
                    stats['changed'] += 1
        if diff:
            out_by_media.setdefault(media, OrderedDict())[scope(sel)] = diff

    chunks = []
    for media, rules in out_by_media.items():
        body = []
        for sel, decls in rules.items():
            decl_text = '\n'.join(f'    {p}: {v};' for p, v in decls.items())
            body.append(f'{sel} {{\n{decl_text}\n}}')
        text = '\n\n'.join(body)
        if media:
            at = media.split(' && ')[0]
            text = at + ' {\n' + '\n'.join('    ' + l if l.strip() else l for l in text.split('\n')) + '\n}'
        chunks.append(text)

    open(OUT, 'w').write('\n\n'.join(chunks) + '\n')
    print('rules:', sum(len(r) for r in out_by_media.values()),
          '| changed decls:', stats['changed'],
          '| re-added decls:', stats['removed_decls'],
          '| restored whole rules:', stats['restored_rules'])


def _norm(v):
    v = re.sub(r'\s+', ' ', v.strip().lower())
    v = v.replace(', ', ',')
    return v


if __name__ == '__main__':
    main()
