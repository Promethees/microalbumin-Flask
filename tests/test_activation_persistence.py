"""Persistence + caching tests for src/activation.py.

These exercise the on-disk activation.json read/write path and the module-level
_token_cache. The verifier suite (test_activation.py) bypasses both by
monkeypatching get_license_token directly, so this is the only place save(),
load(), and the cache behaviour are run. No signing keys are needed, so this
file is deliberately separate from test_activation.py (whose module-level
skipif would otherwise skip these too on a keyless checkout).
"""

import json

import pytest

import activation


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """activation caches the token in a module global. Reset it around every test
    so a write here cannot leak into another test (or the rest of the suite)."""
    activation._token_cache = ...
    yield
    activation._token_cache = ...


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(tmp_path / 'activation.json'))
    assert activation.save('tok-123') is True
    assert activation.load() == {'license_token': 'tok-123'}


def test_save_updates_token_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(tmp_path / 'a.json'))
    activation.save('fresh')
    # served straight from the cache that save() primed — no second disk read needed
    assert activation.get_license_token() == 'fresh'


def test_get_license_token_caches_first_load(monkeypatch, tmp_path):
    path = tmp_path / 'a.json'
    path.write_text(json.dumps({'license_token': 'on-disk'}))
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(path))

    assert activation.get_license_token() == 'on-disk'
    # mutate the file afterwards; the cached value must persist
    path.write_text(json.dumps({'license_token': 'changed'}))
    assert activation.get_license_token() == 'on-disk'


def test_get_license_token_is_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(tmp_path / 'nope.json'))
    assert activation.get_license_token() is None


def test_load_returns_empty_dict_on_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(tmp_path / 'nope.json'))
    assert activation.load() == {}


def test_load_returns_empty_dict_on_corrupt_json(monkeypatch, tmp_path):
    path = tmp_path / 'a.json'
    path.write_text('{ this is not valid json')
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(path))
    assert activation.load() == {}


def test_save_returns_false_when_path_unwritable(monkeypatch, tmp_path):
    # Point the path at a directory: opening it for writing raises, which save()
    # swallows and reports as False rather than propagating.
    unwritable = tmp_path / 'a-directory'
    unwritable.mkdir()
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', str(unwritable))
    assert activation.save('x') is False
