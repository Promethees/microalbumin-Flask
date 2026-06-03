"""Unit tests for the frozen (no-source) binary-swap path in update_service.

These cover the pure/host-independent helpers — platform mapping, archive
extraction + verification, the pending-swap marker, the download/source branch,
and the swap-relauncher script builders. The actual directory swap + relaunch is
OS-shell-driven and is validated by the per-OS CI smoke test, not here.
"""

import io
import os
import tarfile

import pytest
from unittest.mock import patch, MagicMock

import update_service as u


# ── platform mapping ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('sys_platform, key, ext, exe', [
    ('darwin', 'mac', 'tar.gz', 'EasyOKAPI'),
    ('linux', 'linux', 'tar.gz', 'EasyOKAPI'),
    ('win32', 'win', 'zip', 'EasyOKAPI.exe'),
])
def test_platform_mapping(sys_platform, key, ext, exe):
    with patch.object(u.sys, 'platform', sys_platform):
        assert u._platform_key() == key
        assert u._archive_ext() == ext
        assert u._bundle_exe_name() == exe


def test_bundle_archive_url_carries_platform_and_kind():
    with patch.object(u.sys, 'platform', 'darwin'):
        url = u._bundle_archive_url()
    assert '/api/download' in url
    assert 'platform=mac' in url
    assert 'kind=bundle' in url


# ── download branch selection ────────────────────────────────────────────────

def test_download_and_apply_uses_bundle_path_when_frozen():
    with patch.object(u.activation_mod, 'get_license_token', return_value='tok'), \
         patch.object(u, '_is_frozen', return_value=True), \
         patch.object(u, '_download_and_stage_bundle', return_value=['/staged']) as staged, \
         patch.object(u, '_apply_tarball') as tarball:
        out = u.download_and_apply()
    assert out == ['/staged']
    staged.assert_called_once()
    tarball.assert_not_called()


def test_download_and_apply_raises_when_not_activated():
    with patch.object(u.activation_mod, 'get_license_token', return_value=None):
        with pytest.raises(RuntimeError):
            u.download_and_apply()


# ── archive extraction + verification ────────────────────────────────────────

def _make_onedir_tar(path, *, with_internal=True, exe_name='EasyOKAPI', wrap=True):
    """Build a .tar.gz that expands to an EasyOKAPI/ onedir (exe + _internal)."""
    prefix = 'EasyOKAPI/' if wrap else ''
    with tarfile.open(path, 'w:gz') as tf:
        data = b'binary'
        info = tarfile.TarInfo(f'{prefix}{exe_name}')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        if with_internal:
            d = tarfile.TarInfo(f'{prefix}_internal/lib.so')
            d.size = len(data)
            tf.addfile(d, io.BytesIO(data))


def test_extract_bundle_returns_onedir_root(tmp_path):
    archive = tmp_path / 'b.tar.gz'
    _make_onedir_tar(str(archive))
    with patch.object(u.state, 'script_dir', str(tmp_path)), \
         patch.object(u.sys, 'platform', 'darwin'):
        root = u._extract_bundle(str(archive))
        assert os.path.isfile(os.path.join(root, 'EasyOKAPI'))
        assert os.path.isdir(os.path.join(root, '_internal'))
        u._verify_staged_bundle(root)  # must not raise


def test_extract_bundle_finds_exe_without_wrapper(tmp_path):
    archive = tmp_path / 'b.tar.gz'
    _make_onedir_tar(str(archive), wrap=False)
    with patch.object(u.state, 'script_dir', str(tmp_path)), \
         patch.object(u.sys, 'platform', 'darwin'):
        root = u._extract_bundle(str(archive))
        assert os.path.isfile(os.path.join(root, 'EasyOKAPI'))


def test_verify_staged_bundle_rejects_missing_internal(tmp_path):
    archive = tmp_path / 'b.tar.gz'
    _make_onedir_tar(str(archive), with_internal=False)
    with patch.object(u.state, 'script_dir', str(tmp_path)), \
         patch.object(u.sys, 'platform', 'darwin'):
        root = u._extract_bundle(str(archive))
        with pytest.raises(RuntimeError):
            u._verify_staged_bundle(root)


# ── pending-swap marker ──────────────────────────────────────────────────────

def test_pending_swap_roundtrip(tmp_path):
    staged = tmp_path / 'staging' / 'EasyOKAPI'
    staged.mkdir(parents=True)
    with patch.object(u.state, 'script_dir', str(tmp_path)):
        assert u.read_pending_swap() is None
        u._record_pending_swap(str(staged))
        assert u.read_pending_swap() == str(staged)
        u._clear_pending_swap()
        assert u.read_pending_swap() is None


def test_read_pending_swap_none_when_path_gone(tmp_path):
    with patch.object(u.state, 'script_dir', str(tmp_path)):
        u._record_pending_swap(str(tmp_path / 'does_not_exist'))
        assert u.read_pending_swap() is None


def test_apply_pending_swap_noop_when_not_frozen():
    with patch.object(u, '_is_frozen', return_value=False):
        assert u.apply_pending_swap_and_exit() is False


# ── swap-relauncher script builders ──────────────────────────────────────────

def test_posix_swap_script_has_move_and_relaunch():
    s = u._build_posix_swap_script()
    assert 'mv "$LIVE" "$OLD"' in s
    assert 'mv "$NEW" "$LIVE"' in s
    assert '"$LIVE/$EXE" "$@" &' in s


def test_windows_swap_script_has_swap_and_start():
    s = u._build_windows_swap_script(
        r'C:\App\EasyOKAPI', r'C:\Data\_update_staging\EasyOKAPI',
        5099, 'EasyOKAPI.exe', ['--port', '5099'])
    assert 'Move-Item -Force $live $old' in s
    assert 'Move-Item -Force $new $live' in s
    assert 'Start-Process' in s
    assert '$port = 5099' in s
    assert '--port' in s
