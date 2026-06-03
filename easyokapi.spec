# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the no-source EasyOKAPI desktop build.

Produces a onedir bundle named ``EasyOKAPI``: the Python runtime + all backend
modules are compiled to bytecode inside the binary (no .py on disk). Read-only
assets (templates/, static/, json defaults, guide files, sample_data) are bundled
and resolve at runtime from sys._MEIPASS (see src/state.py). Writable user data
(data/, json/, report/, log/) lives in a per-user app-data dir, not here.

Data capture uses the CDC serial collector (log_cdc_data.py), re-invoked as a
hidden ``--cdc-logger`` mode of this same binary — so the collector and its src
deps must be bundled as hidden imports. No HID / sudo path remains.

Build via ``python tools/package.py`` (reads ENCODE_SOURCE from .env), or directly
with ``pyinstaller easyokapi.spec``.
"""

import os

ROOT = os.path.abspath(os.getcwd())


def _data(rel, dest='.'):
    """(source, dest) tuple, included only if the source exists."""
    src = os.path.join(ROOT, rel)
    return (src, dest) if os.path.exists(src) else None


_candidate_datas = [
    _data('templates', 'templates'),
    _data('static', 'static'),
    _data('json', 'json'),
    _data('guide_translations', 'guide_translations'),
    _data('guide_training.json', '.'),
    _data('sample_data', 'sample_data'),
]
datas = [d for d in _candidate_datas if d is not None]

# Modules imported dynamically: the re-entrant CDC logger (main.py imports
# log_cdc_data when invoked with --cdc-logger) and the Flask blueprints under
# src/. pyserial's list_ports backend is loaded lazily, so name it explicitly.
hiddenimports = [
    'log_cdc_data',
    'send_command',
    'get_next_filename',
    'serial',
    'serial.tools.list_ports',
    'routes.core_routes',
    'routes.file_routes',
    'routes.hardware_routes',
    'routes.math_routes',
    'routes.ai_routes',
    'routes.update_routes',
]

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[ROOT, os.path.join(ROOT, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest', '_pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EasyOKAPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowless; the app runs hidden and serves a browser UI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EasyOKAPI',
)
