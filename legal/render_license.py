#!/usr/bin/env python3
"""Render legal/EULA.md into the two formats the installers need.

`EULA.md` is the single source of truth for the licence text. This script emits:

    legal/EULA.txt   plain text, CRLF, UTF-8 with BOM  — DMG, tarball, and any
                     NSIS build that prefers a text licence
    legal/EULA.rtf   RTF with a colour table            — the Windows installer's
                     MUI licence page

The RTF exists because the NSIS licence page is a RichEdit control on a dark
wizard. `MUI_LICENSEPAGE_BGCOLOR` sets its background, but nothing sets the text
colour of a *plain text* licence, so it renders black-on-indigo and is
unreadable. An RTF carries its own colour table, so the text comes out light.
Keep the \\cf1 colour here in step with CLR_FG in installer-win/setup*.nsi.

The whole file is embedded into the installer at compile time by `LicenseData`,
so it is not subject to NSIS's 1024-character string limit.

Usage:
    python3 legal/render_license.py           # write both outputs
    python3 legal/render_license.py --check   # exit 1 if either is stale (CI)
"""

import argparse
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'EULA.md')
OUT_TXT = os.path.join(HERE, 'EULA.txt')
OUT_RTF = os.path.join(HERE, 'EULA.rtf')

WRAP = 78

# Text colour for the RTF, as RGB. Mirrors CLR_FG (E2E8F0) in the NSIS scripts.
RTF_FG = (0xE2, 0xE8, 0xF0)


# ── Markdown → structured lines ───────────────────────────────────────────────

def _strip_inline(text):
    """Flatten the inline markdown the EULA actually uses."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)          # bold
    text = re.sub(r'`([^`]+)`', r'\1', text)              # code spans
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)   # links
    text = re.sub(r'<((?:https?|mailto):[^>]+)>', r'\1', text)    # autolinks
    return text


def parse(md):
    """Return a list of (kind, text) blocks.

    kind is one of: 'h1', 'h2', 'para', 'line', 'bullet', 'rule'. Blockquotes
    are dropped — the note pointing at this script is for maintainers, not for
    the person accepting the licence.

    'line' is a CommonMark hard break (source line ending in a backslash). The
    metadata header and the address blocks use it so they render as stacked
    lines instead of one run-on paragraph.
    """
    blocks = []
    para = []

    def flush(kind='para'):
        if para:
            blocks.append((kind, _strip_inline(' '.join(para))))
            para.clear()

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith('>'):                 # maintainer note — not licence text
            flush()
            continue
        if line.endswith('\\'):                  # hard break
            para.append(line[:-1].strip())
            flush('line')
            continue
        if not line.strip():
            flush()
            continue
        if re.fullmatch(r'-{3,}', line.strip()):
            flush()
            blocks.append(('rule', ''))
            continue
        if line.startswith('# '):
            flush()
            blocks.append(('h1', _strip_inline(line[2:].strip())))
            continue
        if line.startswith('## '):
            flush()
            blocks.append(('h2', _strip_inline(line[3:].strip())))
            continue
        if line.startswith('- '):
            flush()
            blocks.append(('bullet', _strip_inline(line[2:].strip())))
            continue

        para.append(line.strip())

    flush()
    return blocks


# ── Plain text ────────────────────────────────────────────────────────────────

def to_text(blocks):
    out = []
    for kind, text in blocks:
        if kind == 'rule':
            if out and out[-1] != '':
                out.append('')
            out.append('-' * WRAP)
            out.append('')
        elif kind == 'h1':
            out += [text.upper(), '=' * min(len(text), WRAP), '']
        elif kind == 'h2':
            if out and out[-1] != '':
                out.append('')
            out += [text, '-' * min(len(text), WRAP), '']
        elif kind == 'bullet':
            out += textwrap.wrap(text, WRAP, initial_indent='  * ',
                                 subsequent_indent='    ')
        elif kind == 'line':
            out += textwrap.wrap(text, WRAP, subsequent_indent='    ') or ['']
        else:
            out += textwrap.wrap(text, WRAP) or ['']
            out.append('')

    # Collapse runs of blank lines the block rules can produce.
    cleaned = []
    for line in out:
        if line == '' and cleaned and cleaned[-1] == '':
            continue
        cleaned.append(line)
    return '\r\n'.join(cleaned).rstrip() + '\r\n'


# ── RTF ───────────────────────────────────────────────────────────────────────

def _rtf_escape(text):
    text = text.replace('\\', r'\\').replace('{', r'\{').replace('}', r'\}')
    # RichEdit reads \uNNNN with a signed 16-bit code unit and an ASCII fallback.
    return ''.join(
        c if ord(c) < 128 else r'\u%d?' % (ord(c) - 65536 if ord(c) > 32767 else ord(c))
        for c in text
    )


def to_rtf(blocks):
    r, g, b = RTF_FG
    parts = [
        r'{\rtf1\ansi\ansicpg1252\deff0',
        r'{\fonttbl{\f0\fswiss\fcharset0 Segoe UI;}}',
        r'{\colortbl ;\red%d\green%d\blue%d;}' % (r, g, b),
        r'\viewkind4\uc1\cf1\fs19',
    ]

    for kind, text in blocks:
        esc = _rtf_escape(text)
        if kind == 'rule':
            parts.append(r'\pard\sa120\cf1\par')
        elif kind == 'h1':
            parts.append(r'\pard\sa160\cf1\b\fs28 %s\b0\fs19\par' % esc)
        elif kind == 'h2':
            parts.append(r'\pard\sb200\sa120\cf1\b %s\b0\par' % esc)
        elif kind == 'bullet':
            parts.append(r'\pard\fi-200\li400\sa80\cf1\bullet\tab %s\par' % esc)
        elif kind == 'line':
            parts.append(r'\pard\sa0\cf1 %s\par' % esc)
        else:
            parts.append(r'\pard\sa120\cf1 %s\par' % esc)

    parts.append('}')
    return '\r\n'.join(parts) + '\r\n'


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help='exit 1 if an output is missing or stale')
    args = ap.parse_args()

    with open(SRC, encoding='utf-8') as f:
        blocks = parse(f.read())

    # UTF-8 BOM: a Unicode NSIS installer requires one on a text licence, and it
    # keeps Notepad from mis-guessing the encoding of the DMG/tarball copy.
    wanted = {
        OUT_TXT: '﻿' + to_text(blocks),
        OUT_RTF: to_rtf(blocks),
    }

    stale = []
    for path, text in wanted.items():
        current = None
        if os.path.exists(path):
            # newline='' so the CRLFs survive the read and --check compares the
            # bytes we actually wrote, not universal-newline-translated ones.
            with open(path, encoding='utf-8', newline='') as f:
                current = f.read()
        if current != text:
            stale.append(path)
            if not args.check:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(text)

    if args.check:
        if stale:
            print('Stale, regenerate with `python3 legal/render_license.py`:')
            for p in stale:
                print('  ' + os.path.relpath(p, os.path.dirname(HERE)))
            return 1
        print('legal/EULA.txt and legal/EULA.rtf are up to date.')
        return 0

    for p in wanted:
        print('wrote ' + os.path.relpath(p, os.path.dirname(HERE)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
