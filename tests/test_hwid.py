"""Tests for the machine-fingerprint module (src/hwid.py)."""

import hashlib
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
