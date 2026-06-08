"""Tests for the machine-fingerprint module (src/hwid.py)."""

import hashlib

import pytest

import hwid


def test_hwid_is_64_hex_chars():
    h = hwid.get_hwid()
    assert len(h) == 64
    assert all(c in '0123456789abcdef' for c in h)


def test_hwid_is_deterministic():
    assert hwid.get_hwid() == hwid.get_hwid()


def test_hwid_matches_documented_recipe(monkeypatch):
    # The canonical string is 'easyokapi-hwid-v1|<os>|<raw lowercased>'. The
    # Windows installer's PowerShell reproduces exactly this — pin it so a change
    # is caught here.
    monkeypatch.setattr(hwid, '_os_tag', lambda: 'win')
    monkeypatch.setattr(hwid, '_raw_machine_id', lambda os_tag: 'ABC-123-DEF')
    expected = hashlib.sha256(b'easyokapi-hwid-v1|win|abc-123-def').hexdigest()
    assert hwid.get_hwid() == expected


def test_hwid_differs_per_machine(monkeypatch):
    monkeypatch.setattr(hwid, '_os_tag', lambda: 'win')
    monkeypatch.setattr(hwid, '_raw_machine_id', lambda os_tag: 'machine-A')
    a = hwid.get_hwid()
    monkeypatch.setattr(hwid, '_raw_machine_id', lambda os_tag: 'machine-B')
    b = hwid.get_hwid()
    assert a != b


def test_hwid_never_raises_on_unknown(monkeypatch):
    # When the OS id cannot be read we fall back to a constant, not a crash.
    monkeypatch.setattr(hwid, '_raw_machine_id', lambda os_tag: '')
    assert len(hwid.get_hwid()) == 64
    assert hwid.is_resolvable() is False


# ── OS tag mapping ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('system,expected', [
    ('Windows', 'win'),
    ('nt', 'win'),
    ('Darwin', 'mac'),
    ('Linux', 'linux'),
    ('FreeBSD', 'linux'),   # anything unrecognised falls through to linux
])
def test_os_tag_maps_platform(monkeypatch, system, expected):
    monkeypatch.setattr(hwid.platform, 'system', lambda: system)
    assert hwid._os_tag() == expected


# ── Per-OS raw-id dispatch ────────────────────────────────────────────────────

def test_raw_machine_id_dispatches_by_os(monkeypatch):
    monkeypatch.setattr(hwid, '_windows_machine_guid', lambda: 'WIN')
    monkeypatch.setattr(hwid, '_macos_platform_uuid', lambda: 'MAC')
    monkeypatch.setattr(hwid, '_linux_machine_id', lambda: 'LIN')
    assert hwid._raw_machine_id('win') == 'WIN'
    assert hwid._raw_machine_id('mac') == 'MAC'
    assert hwid._raw_machine_id('linux') == 'LIN'


# ── is_resolvable() positive case ─────────────────────────────────────────────

def test_is_resolvable_true_when_machine_id_present(monkeypatch):
    monkeypatch.setattr(hwid, '_raw_machine_id', lambda os_tag: 'real-id')
    assert hwid.is_resolvable() is True


# ── macOS ioreg parsing (the only OS reader with real parsing logic) ──────────

def test_macos_platform_uuid_parses_ioreg_output(monkeypatch):
    sample = (
        b'  +-o IOPlatformExpertDevice  <class IOPlatformExpertDevice>\n'
        b'      "model" = <"MacBookPro18,1">\n'
        b'      "IOPlatformUUID" = "ABCD1234-5678-90EF-AAAA-BBBBCCCCDDDD"\n'
    )
    monkeypatch.setattr(hwid.subprocess, 'check_output', lambda *a, **k: sample)
    assert hwid._macos_platform_uuid() == 'ABCD1234-5678-90EF-AAAA-BBBBCCCCDDDD'


def test_macos_platform_uuid_empty_on_subprocess_error(monkeypatch):
    def boom(*_a, **_k):
        raise OSError('ioreg not found')
    monkeypatch.setattr(hwid.subprocess, 'check_output', boom)
    assert hwid._macos_platform_uuid() == ''
