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


def _patch_apply_pending(platform_key):
    """Common patches so apply_pending_swap_and_exit reaches the swap branch."""
    return [
        patch.object(u, '_is_frozen', return_value=True),
        patch.object(u, 'read_pending_swap', return_value=r'C:\staged\EasyOKAPI'),
        patch.object(u, '_bundle_root', return_value=r'C:\App\EasyOKAPI'),
        patch.object(u, '_current_port', return_value=5099),
        patch.object(u, '_bundle_exe_name', return_value='EasyOKAPI.exe'),
        patch.object(u, '_relaunch_extra_args', return_value=[]),
        patch.object(u, '_platform_key', return_value=platform_key),
        patch.object(u, '_shutdown_current_process'),
        patch.object(u.os, '_exit'),  # apply_pending_swap_and_exit ends with os._exit(0)
    ]


def test_apply_pending_swap_windows_keeps_marker_for_coordinator():
    # On Windows the swap is elevated + async, so the marker must NOT be cleared here
    # — the coordinator clears it only after the swap actually succeeds. (The old bug
    # cleared it unconditionally, orphaning the staged bundle when the swap failed.)
    import contextlib
    with contextlib.ExitStack() as es:
        for p in _patch_apply_pending('win'):
            es.enter_context(p)
        spawn = es.enter_context(patch.object(u, '_spawn_windows_swapper'))
        clear = es.enter_context(patch.object(u, '_clear_pending_swap'))
        u.apply_pending_swap_and_exit()
        spawn.assert_called_once()
        clear.assert_not_called()


def test_apply_pending_swap_posix_clears_marker():
    import contextlib
    with contextlib.ExitStack() as es:
        for p in _patch_apply_pending('mac'):
            es.enter_context(p)
        spawn = es.enter_context(patch.object(u, '_spawn_posix_swapper'))
        clear = es.enter_context(patch.object(u, '_clear_pending_swap'))
        u.apply_pending_swap_and_exit()
        spawn.assert_called_once()
        clear.assert_called_once()


# ── swap-relauncher script builders ──────────────────────────────────────────

def test_posix_swap_script_has_move_and_relaunch():
    s = u._build_posix_swap_script()
    assert 'mv "$LIVE" "$OLD"' in s
    assert 'mv "$NEW" "$LIVE"' in s
    assert '"$LIVE/$EXE" "$@" &' in s


def test_windows_swap_script_is_elevated_helper_doing_only_the_move():
    # The elevated helper does the privileged dir swap + ACL reset and writes a
    # result marker — but must NOT relaunch the app (that happens non-elevated).
    s = u._build_windows_swap_script(
        r'C:\App\EasyOKAPI', r'C:\Data\_update_staging\EasyOKAPI',
        'EasyOKAPI.exe', r'C:\Data\_update_swap_result.txt', r'C:\Data\log\update_swap.txt')
    # MUST stop on the first error: otherwise a failed (non-terminating) Move-Item
    # would fall through and nest the new build inside the old install.
    assert "$ErrorActionPreference = 'Stop'" in s
    assert 'Move-Item -Force -LiteralPath $live $old' in s
    assert 'Move-Item -Force -LiteralPath $new $live' in s
    # Guard so the new build is never moved INTO a surviving $live.
    assert 'if (Test-Path $live) { throw' in s
    assert 'icacls' in s                      # reset ACLs so the install stays admin-only
    assert "Set-Content -Path $res -Value 'OK'" in s
    assert 'Start-Process' not in s           # relaunch is the coordinator's job, not here


def test_windows_coordinator_elevates_then_relaunches_nonelevated():
    s = u._build_windows_coordinator_script(
        r'C:\App\EasyOKAPI', 5099, 'EasyOKAPI.exe', ['--port', '5099'],
        r'C:\Data\_update_swap.ps1', r'C:\Data\_update_swap_result.txt',
        r'C:\Data\log\update_swap.txt')
    assert '$port = 5099' in s
    assert '-Verb RunAs' in s                 # elevate the swap (UAC)
    assert '-Wait' in s                       # wait for the elevated swap to finish
    # relaunch is a plain (non-elevated) Start-Process of the app, carrying its args
    assert 'Start-Process -FilePath $exePath' in s
    assert '--port' in s
    assert 'Remove-Item -Force $pend' in s    # clear pending marker only on success


# ── powershell resolution (frozen-safe spawn) ────────────────────────────────
# A frozen PyInstaller process can run with a stripped PATH, so a bare
# 'powershell' makes Popen raise FileNotFoundError — which silently aborted the
# swap-coordinator spawn. _powershell_exe() resolves the absolute System32 path.

def test_powershell_exe_resolves_absolute_path_under_system_root(tmp_path):
    ps = tmp_path / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    ps.parent.mkdir(parents=True)
    ps.write_bytes(b'')
    with patch.dict(u.os.environ, {'SystemRoot': str(tmp_path)}):
        resolved = u._powershell_exe()
    assert resolved == str(ps)
    assert os.path.isabs(resolved)


def test_powershell_exe_falls_back_to_bare_name_when_missing(tmp_path):
    # %SystemRoot% exists but holds no powershell.exe — fall back to bare 'powershell'
    # rather than returning a path that does not exist.
    with patch.dict(u.os.environ, {'SystemRoot': str(tmp_path)}):
        assert u._powershell_exe() == 'powershell'


def test_powershell_exe_defaults_systemroot_when_env_absent():
    # %SystemRoot% can be absent in a sanitised frozen environment; the helper must
    # still produce a candidate (default C:\Windows) instead of raising.
    env = {k: v for k, v in u.os.environ.items() if k != 'SystemRoot'}
    with patch.dict(u.os.environ, env, clear=True):
        # No assertion on existence (depends on host); it must simply not raise and
        # return a non-empty string.
        assert u._powershell_exe()


def test_spawn_windows_swapper_uses_resolved_powershell(tmp_path):
    # The coordinator must be spawned via the resolved absolute powershell path,
    # not bare 'powershell' (the root cause of the silent swap failure).
    with patch.object(u.state, 'script_dir', str(tmp_path)), \
         patch.object(u, '_powershell_exe', return_value=r'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'), \
         patch('subprocess.Popen') as popen:
        u._spawn_windows_swapper(
            r'C:\App\EasyOKAPI', r'C:\Data\_update_staging\EasyOKAPI',
            5099, 'EasyOKAPI.exe', [])
    popen.assert_called_once()
    argv = popen.call_args[0][0]
    assert argv[0] == r'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'
    assert argv[-1].endswith('_update_coordinator.ps1')
    # The coordinator + swap scripts were written to the data dir before the spawn.
    assert os.path.isfile(os.path.join(str(tmp_path), '_update_coordinator.ps1'))
    assert os.path.isfile(os.path.join(str(tmp_path), '_update_swap.ps1'))
    # Flags must NOT include DETACHED_PROCESS: powershell.exe is a console app and
    # DETACHED_PROCESS gives it no console, so it exits before running the script
    # (the silent "no swap, no log, reopens on old version" failure). It must run
    # hidden via CREATE_NO_WINDOW, which still gives the child a console.
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    flags = popen.call_args[1]['creationflags']
    assert not (flags & DETACHED_PROCESS), 'DETACHED_PROCESS stops the powershell child from running'
    assert flags & CREATE_NO_WINDOW
    # cwd must be the data dir, NOT the install dir: the coordinator stays alive
    # during the elevated move, and Windows can't rename a dir that is a running
    # process's cwd — holding the install dir would make the new build nest inside
    # the old one.
    assert popen.call_args[1].get('cwd') == str(tmp_path)


def test_restart_windows_spawn_is_not_detached(monkeypatch):
    # Same console-app constraint for the source-build relauncher: no DETACHED_PROCESS.
    import subprocess
    with patch.object(u, '_powershell_exe', return_value=r'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'), \
         patch.object(u, '_current_port', return_value=5099), \
         patch.object(u, '_build_windows_relaunch_script', return_value='echo hi'), \
         patch.object(u, '_shutdown_current_process'), \
         patch.object(u.os, '_exit', side_effect=SystemExit), \
         patch.object(subprocess, 'Popen') as popen:
        try:
            u._restart_windows()
        except SystemExit:
            pass
    popen.assert_called_once()
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    flags = popen.call_args[1]['creationflags']
    assert not (flags & DETACHED_PROCESS)
    assert flags & CREATE_NO_WINDOW


# ── version check: semver comparison ─────────────────────────────────────────
# An update is offered only for a strictly greater semver (an equal version is
# already installed). A non-semver server string ('latest', etc.) always offers.

def _fake_version_resp(version, notes=''):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {'version': version, 'release_notes': notes}
    return resp


@pytest.mark.parametrize('latest, current, expected', [
    ('1.2.0', '1.1.11', True),     # newer → update available
    ('1.1.11', '1.1.11', False),   # equal → no re-download (strict >)
    ('1.1.10', '1.1.11', False),   # older → no update
    ('latest', '1.1.11', True),    # non-semver → always available
])
def test_check_for_update_semver_comparison(latest, current, expected):
    with patch.object(u.activation_mod, 'get_license_token', return_value='tok'), \
         patch.object(u.activation_mod, 'get_hwid', return_value='hw'), \
         patch.object(u.state, 'APP_VERSION', current), \
         patch.object(u.requests, 'get', return_value=_fake_version_resp(latest)):
        result = u.check_for_update()
    assert result['update_available'] is expected
    assert result['current'] == current
    assert result['latest'] == latest


# ── source-mode apply: _PRESERVE data protection + GitHub prefix strip ────────

def _make_source_tar(path, names):
    """Build a .tar.gz whose members are the given relative file paths."""
    with tarfile.open(path, 'w:gz') as tf:
        for name in names:
            data = name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_apply_tarball_preserves_user_data_and_strips_prefix(tmp_path):
    archive = tmp_path / 'src.tar.gz'
    _make_source_tar(str(archive), [
        'repo-abc123/main.py',
        'repo-abc123/src/state.py',
        'repo-abc123/data/keep.csv',      # _PRESERVE dir — must not be overwritten
        'repo-abc123/activation.json',    # _PRESERVE file — license must survive
    ])
    # Pre-existing user data + license that an update must leave untouched.
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'keep.csv').write_text('ORIGINAL')
    (tmp_path / 'activation.json').write_text('LICENSE')

    with patch.object(u.state, 'script_dir', str(tmp_path)):
        updated = u._apply_tarball(str(archive))

    # Source files applied, with the GitHub 'owner-repo-hash/' wrapper stripped.
    assert os.path.isfile(os.path.join(str(tmp_path), 'main.py'))
    assert os.path.isfile(os.path.join(str(tmp_path), 'src', 'state.py'))
    assert 'main.py' in updated
    assert 'src/state.py' in updated
    # Preserved entries skipped — user data + license bytes unchanged.
    assert (tmp_path / 'data' / 'keep.csv').read_text() == 'ORIGINAL'
    assert (tmp_path / 'activation.json').read_text() == 'LICENSE'
    assert 'data/keep.csv' not in updated
    assert 'activation.json' not in updated


def test_tar_shared_prefix_detects_wrapper_and_rejects_mixed():
    M = lambda name: type('M', (), {'name': name})()
    assert u._tar_shared_prefix([M('repo-abc/a.py'), M('repo-abc/b/c.py')]) == 'repo-abc'
    assert u._tar_shared_prefix([M('repo-abc/a.py'), M('other/b.py')]) is None
    assert u._tar_shared_prefix([]) is None


# ── version parsing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('value, expected', [
    ('1.2.3', (1, 2, 3)),
    ('1.2', (1, 2)),       # partial semver still parses
    ('latest', None),      # non-numeric → not comparable
    ('', None),            # empty → not comparable
    ('1.2.x', None),       # one bad segment fails the whole parse
])
def test_version_tuple_parsing(value, expected):
    assert u._version_tuple(value) == expected


# ── pre-update data backup ───────────────────────────────────────────────────

def test_backup_user_data_copies_dirs_when_frozen(tmp_path):
    root = tmp_path / 'install'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'a.csv').write_text('A')
    (root / 'report').mkdir()
    (root / 'report' / 'r.html').write_text('R')
    with patch.object(u.state, 'script_dir', str(root)), \
         patch.object(u, '_is_frozen', return_value=True):
        u._backup_user_data()
    backup = tmp_path / 'install_data'
    assert (backup / 'data' / 'a.csv').read_text() == 'A'
    assert (backup / 'report' / 'r.html').read_text() == 'R'


def test_backup_user_data_noop_when_not_frozen(tmp_path):
    root = tmp_path / 'install'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'a.csv').write_text('A')
    with patch.object(u.state, 'script_dir', str(root)), \
         patch.object(u, '_is_frozen', return_value=False):
        u._backup_user_data()
    assert not (tmp_path / 'install_data').exists()


def test_backup_user_data_replaces_stale_backup(tmp_path):
    root = tmp_path / 'install'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'new.csv').write_text('NEW')
    backup = tmp_path / 'install_data'
    (backup / 'data').mkdir(parents=True)
    (backup / 'data' / 'stale.csv').write_text('STALE')  # must be cleared
    with patch.object(u.state, 'script_dir', str(root)), \
         patch.object(u, '_is_frozen', return_value=True):
        u._backup_user_data()
    assert (backup / 'data' / 'new.csv').read_text() == 'NEW'
    assert not (backup / 'data' / 'stale.csv').exists()
