import os
import re
import sys
import shutil
import platform
import tarfile
import zipfile
import requests
import state
import activation as activation_mod


_PRESERVE = frozenset({
    'data', 'report', 'json', 'log',
    'activation.json', 'ai_settings.json', 'user_settings.json',
    'ai_feedback.jsonl', 'ai_guide_weights.json',
    '.env',
})


def _auth_headers(token):
    """Bearer token + this machine's fingerprint.

    The server binds a permanent token to one machine; sending X-Machine-Id lets
    it reject a token presented from a different machine (hardware lock applied to
    version checks and update downloads, not just the activation gate).
    """
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    headers['X-Machine-Id'] = activation_mod.get_hwid()
    return headers

# ── Frozen (no-source) vs source distribution ────────────────────────────────
# Two update mechanisms share check_for_update() but diverge in download_and_apply:
#   • Source build (dev / ENCODE_SOURCE=false): download a .py source tarball and
#     overwrite files in place, then pip-install + restart (the historical flow).
#   • Frozen build (PyInstaller onedir, ENCODE_SOURCE=true): there is no .py on
#     disk, so we download the platform's onedir *bundle* archive, stage it in the
#     writable app-data dir, then a detached helper swaps the install dir and
#     relaunches. No pip step (deps are inside the binary).
#
# The server contract (served by the online branch — see P4):
#   GET /api/version                          → {version, release_notes}   (unchanged)
#   GET /api/download                         → source tarball             (unchanged)
#   GET /api/download?platform=<k>&kind=bundle → frozen onedir archive for <k>
#       <k> ∈ {mac, win, linux}; archive is .zip on win, .tar.gz elsewhere; it
#       expands to a single top-level "EasyOKAPI/" dir holding the executable +
#       _internal/ (exactly PyInstaller's COLLECT output).

_BUNDLE_NAME = 'EasyOKAPI'  # PyInstaller COLLECT name (the onedir folder + exe)


def _is_frozen():
    return getattr(sys, 'frozen', False)


def _platform_key():
    """Map the running OS to the server's ?platform= key."""
    p = sys.platform
    if p.startswith('win'):
        return 'win'
    if p == 'darwin':
        return 'mac'
    return 'linux'


def _bundle_root():
    """Directory holding the running frozen executable (the onedir COLLECT dir).

    e.g. <install>/EasyOKAPI/  (contains EasyOKAPI[.exe] + _internal/). Only
    meaningful when frozen.
    """
    return os.path.dirname(os.path.abspath(sys.executable))


def _bundle_exe_name():
    return f'{_BUNDLE_NAME}.exe' if _platform_key() == 'win' else _BUNDLE_NAME


_UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyOKAPI'


def refresh_uninstall_entry():
    """Keep the Windows Add/Remove Programs entry in sync with the running build.

    The installer registers the uninstall entry, but an in-app binary swap
    replaces the executable without touching the registry — so the entry (and the
    version shown in Settings > Apps) would keep advertising the previous build.
    On each startup we rewrite it to the current APP_VERSION.

    Written under HKCU so the un-elevated app can update it (HKLM would need
    admin, which the running app does not have). Also clears any stale HKLM entry
    left by an older installer. Frozen Windows only; best-effort and silent.
    """
    if not _is_frozen() or not sys.platform.startswith('win'):
        return
    try:
        import winreg
    except Exception:
        return
    install_dir = _bundle_root()
    version = state.APP_VERSION
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as k:
            winreg.SetValueEx(k, 'DisplayName', 0, winreg.REG_SZ, f'EasyOKAPI {version}')
            winreg.SetValueEx(k, 'DisplayVersion', 0, winreg.REG_SZ, version)
            winreg.SetValueEx(k, 'DisplayIcon', 0, winreg.REG_SZ,
                              os.path.join(install_dir, _bundle_exe_name()))
            winreg.SetValueEx(k, 'UninstallString', 0, winreg.REG_SZ,
                              '"' + os.path.join(install_dir, 'Uninstall.exe') + '"')
            winreg.SetValueEx(k, 'QuietUninstallString', 0, winreg.REG_SZ,
                              '"' + os.path.join(install_dir, 'Uninstall.exe') + '" /S')
            winreg.SetValueEx(k, 'InstallLocation', 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(k, 'Publisher', 0, winreg.REG_SZ, 'HTBiotec')
            winreg.SetValueEx(k, 'NoModify', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, 'NoRepair', 0, winreg.REG_DWORD, 1)
    except Exception:
        pass
    # Best-effort: drop a stale machine-wide entry from an older HKLM installer so
    # Add/Remove Programs does not show two EasyOKAPI rows. Silently ignored when
    # the app is not elevated (the common case) — the installer also clears it.
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY)
    except Exception:
        pass


def _version_tuple(v):
    """Parse 'X.Y.Z' into (X, Y, Z). Returns None if v is not a semver string."""
    try:
        parts = tuple(int(x) for x in str(v).split('.'))
        return parts if parts else None
    except Exception:
        return None


def check_for_update():
    """Call the online server and return version comparison info.

    Returns dict: {current, latest, update_available, release_notes}.
    Raises requests.RequestException on network failure.
    """
    token = activation_mod.get_license_token()
    headers = _auth_headers(token)
    # Failover across the service bases (§2.17): the branded domain can be down
    # while the deployment behind it is fine. This runs before every download, so
    # it is also what keeps the remembered base fresh for the streaming calls.
    resp, _base = activation_mod.service_request('GET', '/api/version', headers=headers)
    if resp is None:
        raise requests.RequestException('Could not reach any EasyOKAPI update server')
    resp.raise_for_status()
    data = resp.json()
    latest = str(data.get('version', '') or '')
    latest_t = _version_tuple(latest)
    current_t = _version_tuple(state.APP_VERSION)
    # If the server returns a valid semver, only a strictly greater version counts as
    # an update (an equal version is already installed — no re-download).
    # If the server returns a non-semver string ('latest', etc.), always allow download —
    # it means a build is available but not yet tagged; the banner won't show the version string.
    update_available = True if latest_t is None else (latest_t > (current_t or (0,)))
    return {
        'current': state.APP_VERSION,
        'latest': latest,
        'update_available': update_available,
        'release_notes': data.get('release_notes', ''),
    }


def _backup_user_data():
    """Best-effort safety copy of the user's data before applying an update.

    Mirrors the Windows installer's Documents\\EasyOKAPI_data backup so an in-app
    update also leaves a fallback copy (the data folder itself is never touched by
    the update, but a spare copy is reassuring). Copies data/json/report to a
    sibling '<data-root>_data' folder. Frozen builds only; never raises.
    """
    if not _is_frozen():
        return
    try:
        backup_root = os.path.normpath(state.script_dir) + '_data'
        for name in ('data', 'json', 'report'):
            src = os.path.join(state.script_dir, name)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(backup_root, name)
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
    except Exception:
        pass


def download_and_apply(progress_cb=None):
    """Download the update from the server and apply it.

    progress_cb(pct: int, label: str) is called at each stage.
    Returns list of relative paths that were updated (source mode) or the staged
    bundle path (frozen mode).
    Raises RuntimeError if not activated, or requests.RequestException on failure.

    Frozen builds swap a binary bundle (no .py on disk); source builds overwrite
    .py files in place. The branch is chosen by sys.frozen.
    """
    token = activation_mod.get_license_token()
    if not token:
        raise RuntimeError('App is not activated — cannot download update.')

    _backup_user_data()  # safety copy before any update work (best-effort)

    if _is_frozen():
        return _download_and_stage_bundle(token, progress_cb)

    _emit(progress_cb, 5, 'Connecting to update server...')

    # A stream commits to one host before the first byte, so it takes the best
    # known base rather than probing; check_for_update() ran first and has
    # already moved it to whatever is answering.
    url = f"{activation_mod.service_base()}/api/download"
    headers = _auth_headers(token)
    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get('Content-Length', 0))
    tmp_path = os.path.join(state.script_dir, '_update_download.tar.gz')

    _emit(progress_cb, 10, 'Downloading update...')

    downloaded = 0
    with open(tmp_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_cb:
                    pct = 10 + int(downloaded / total * 60)
                    _emit(progress_cb, pct, f'Downloading... {downloaded // 1024} KB / {total // 1024} KB')

    _emit(progress_cb, 72, 'Applying update...')
    updated = _apply_tarball(tmp_path)
    _sync_version_file()

    _emit(progress_cb, 80, 'Installing dependencies...')
    _install_requirements()

    _emit(progress_cb, 90, 'Cleaning up...')
    try:
        os.remove(tmp_path)
    except OSError:
        pass

    _emit(progress_cb, 100, f'Done — {len(updated)} files updated.')
    return updated


def _emit(cb, pct, label):
    if cb:
        cb(pct, label)


def _tar_shared_prefix(members):
    """Return the single top-level directory name shared by all tar members, or None.

    GitHub tarballs wrap everything in 'owner-repo-commithash/' — detect and strip it.
    """
    names = [m.name.replace('\\', '/') for m in members]
    if not names:
        return None
    first = names[0].split('/')[0]
    if first and all(n.split('/')[0] == first for n in names):
        return first
    return None


def _apply_tarball(tar_path):
    project_root = state.script_dir
    updated = []
    with tarfile.open(tar_path, 'r:gz') as tf:
        members = tf.getmembers()
        prefix = _tar_shared_prefix(members)
        for member in members:
            name = member.name.replace('\\', '/')
            if prefix and name.startswith(prefix + '/'):
                name = name[len(prefix) + 1:]
            if not name:
                continue
            top = name.split('/')[0]
            if top in _PRESERVE:
                continue
            if member.isdir():
                continue
            if not member.isfile():
                continue
            dest = os.path.join(project_root, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            src = tf.extractfile(member)
            if src:
                with open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                updated.append(name)
    return updated


def _sync_version_file():
    """Rewrite VERSION.txt to match the freshly-applied source version.

    VERSION.txt is created by the installers and read back by them to show the
    installed version, but it is not part of the source tarball — so an in-app
    update would leave it pointing at the old version, misleading a later
    installer run. We read the new APP_VERSION from the just-extracted state.py
    (the authoritative value the app reports after restart) and rewrite
    VERSION.txt in the installers' 'vX.Y.Z' format. Best-effort: never fails the
    update.
    """
    try:
        state_path = os.path.join(state.script_dir, 'src', 'state.py')
        with open(state_path, 'r', encoding='utf-8') as f:
            m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
        if not m:
            return
        version = m.group(1).lstrip('v')
        with open(os.path.join(state.script_dir, 'VERSION.txt'), 'w', encoding='utf-8') as f:
            f.write(f'v{version}\n')
    except Exception:
        pass


def _requirements_path():
    """Return the requirements file in the project root.

    A single cross-platform requirements.txt is used on all OSes.
    """
    return os.path.join(state.script_dir, 'requirements.txt')


def _install_requirements():
    """Install/upgrade dependencies into the running venv after applying an update.

    The in-app update only overwrites source files — it never touches the venv —
    so an update that adds a new dependency would otherwise relaunch into code
    that crashes on ImportError. Running ``pip install -r <requirements>`` with
    the venv interpreter (``sys.executable``) is idempotent (already-satisfied
    packages are skipped) and picks up anything new. Raises RuntimeError on
    failure so the caller reports the update as failed rather than relaunching a
    broken app.
    """
    import subprocess

    req = _requirements_path()
    if not os.path.isfile(req):
        return

    creationflags = 0
    if platform.system().lower().startswith('win'):
        creationflags = 0x08000000  # CREATE_NO_WINDOW — the app runs hidden

    proc = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-r', req],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, creationflags=creationflags,
    )
    if proc.returncode != 0:
        tail = (proc.stdout or '')[-800:]
        raise RuntimeError(
            f'Dependency install failed (pip exit {proc.returncode}):\n{tail}')


# ── Frozen (no-source) binary-swap update ────────────────────────────────────
# Downloads the platform onedir bundle, stages it in the writable app-data dir,
# and records a pending swap. The actual directory swap + relaunch is deferred to
# a detached OS-shell helper spawned at finalize time (apply_pending_swap_and_exit)
# — a running process can't reliably replace its own install dir in place
# (Windows locks loaded DLLs; even on POSIX the port must free first).

def _archive_ext():
    return 'zip' if _platform_key() == 'win' else 'tar.gz'


def _bundle_archive_url():
    return (f"{activation_mod.service_base()}/api/download"
            f"?platform={_platform_key()}&kind=bundle")


def _staging_dir():
    return os.path.join(state.script_dir, '_update_staging')


def _pending_swap_path():
    return os.path.join(state.script_dir, '_pending_update.txt')


def _download_and_stage_bundle(token, progress_cb=None):
    """Download + extract the platform onedir bundle into a staging dir.

    Returns the staged onedir root (the dir holding the new executable). The swap
    itself happens later via apply_pending_swap_and_exit(). Raises RuntimeError /
    requests.RequestException on failure.
    """
    _emit(progress_cb, 5, 'Connecting to update server...')
    headers = _auth_headers(token)
    resp = requests.get(_bundle_archive_url(), headers=headers, stream=True, timeout=180)
    resp.raise_for_status()

    total = int(resp.headers.get('Content-Length', 0))
    archive_path = os.path.join(state.script_dir, f'_update_bundle.{_archive_ext()}')

    _emit(progress_cb, 10, 'Downloading update...')
    downloaded = 0
    with open(archive_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_cb:
                    pct = 10 + int(downloaded / total * 60)
                    _emit(progress_cb, pct,
                          f'Downloading... {downloaded // 1024} KB / {total // 1024} KB')

    _emit(progress_cb, 74, 'Extracting update...')
    staged_root = _extract_bundle(archive_path)
    _verify_staged_bundle(staged_root)

    try:
        os.remove(archive_path)
    except OSError:
        pass

    _record_pending_swap(staged_root)
    _emit(progress_cb, 100, 'Update downloaded — restart to apply.')
    return [staged_root]


def _reject_unsafe_members(names, dest):
    """Raise if any archive member would resolve outside dest (path traversal).

    zipfile's extractall() has no traversal filter at all, and tarfile's only
    arrived in 3.12 (and is not the default until 3.14), so a crafted archive
    with '../' or absolute members could write outside the staging dir. We
    validate every member name against the staging root before extracting
    either format, belt-and-braces with tarfile's own filter below.
    """
    dest = os.path.abspath(dest)
    for name in names:
        target = os.path.abspath(os.path.join(dest, name))
        if target != dest and not target.startswith(dest + os.sep):
            raise RuntimeError(f'Unsafe path in update archive: {name}')


def _extract_bundle(archive_path):
    """Extract the bundle archive and return the staged onedir root.

    The archive expands to a single top-level 'EasyOKAPI/' dir (PyInstaller's
    COLLECT output). We extract into a clean staging dir and return the path to
    that onedir folder (the one containing the executable).
    """
    staging = _staging_dir()
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    if archive_path.endswith('.zip'):
        with zipfile.ZipFile(archive_path) as zf:
            _reject_unsafe_members(zf.namelist(), staging)
            zf.extractall(staging)
    else:
        with tarfile.open(archive_path, 'r:gz') as tf:
            _reject_unsafe_members(tf.getnames(), staging)
            # 'data' is the 3.14 default; naming it silences the 3.12 warning and
            # pins the behaviour. It keeps the exec bit the onedir launcher needs.
            tf.extractall(staging, filter='data')

    # Prefer the conventional EasyOKAPI/ folder; otherwise find the dir holding
    # the executable (handles archives with or without a top-level wrapper).
    exe_name = _bundle_exe_name()
    direct = os.path.join(staging, _BUNDLE_NAME)
    if os.path.isfile(os.path.join(direct, exe_name)):
        return direct
    for root, _dirs, files in os.walk(staging):
        if exe_name in files:
            return root
    raise RuntimeError('Update archive did not contain the application bundle.')


def _verify_staged_bundle(staged_root):
    exe = os.path.join(staged_root, _bundle_exe_name())
    if not os.path.isfile(exe):
        raise RuntimeError('Staged update is missing its executable.')
    # _internal/ holds the Python runtime + bundled datas; its absence means a
    # truncated/corrupt download.
    if not os.path.isdir(os.path.join(staged_root, '_internal')):
        raise RuntimeError('Staged update is incomplete (no _internal directory).')


def _record_pending_swap(staged_root):
    with open(_pending_swap_path(), 'w', encoding='utf-8') as f:
        f.write(staged_root)


def read_pending_swap():
    """Return the staged onedir root recorded by a completed frozen download, or None."""
    try:
        with open(_pending_swap_path(), 'r', encoding='utf-8') as f:
            path = f.read().strip()
        return path if path and os.path.isdir(path) else None
    except OSError:
        return None


def _clear_pending_swap():
    try:
        os.remove(_pending_swap_path())
    except OSError:
        pass


# Every artifact the update flow writes into the data root. The swap helpers run
# after this process exits, so nothing can delete them on the way out — they are
# swept on the NEXT startup instead (see cleanup_stale_artifacts).
_ARTIFACT_FILES = (
    '_update_swap.ps1',
    '_update_coordinator.ps1',
    '_update_swap_result.txt',
    '_update_bundle.zip',
    '_update_bundle.tar.gz',
    '_update_download.tar.gz',
)
_ARTIFACT_GLOBS = (
    '_update_*_swap.sh',  # posix swap script (current naming)
    'tmp*_swap.sh',       # posix swap script written by builds before the rename
)


def cleanup_stale_artifacts():
    """Delete leftover update scratch files from the data root. Never raises.

    The binary-swap flow writes its helper scripts, result file and staging dir
    into ``state.script_dir`` and then exits so the helpers can run — so there is
    no point at which the flow itself can clean up. Nothing did, so every update
    left a growing pile behind: the two .ps1 helpers, the swap result, an empty
    ``_update_staging/``, and (posix) one ``mkstemp`` swap script per update,
    accumulating forever.

    Called on startup, which is exactly once per completed swap (the relaunched
    build sweeps its predecessor's mess) and also catches artifacts orphaned by a
    download that crashed mid-flight.

    Skipped entirely while a swap is still pending: a failed or UAC-declined
    Windows swap deliberately keeps the staged bundle, marker and scripts so the
    next finalize can retry, and sweeping them would strand the update.
    """
    import glob

    root = state.script_dir
    try:
        if read_pending_swap():
            return  # a retry is armed — its artifacts are still live
        # A marker pointing at a staging dir that no longer exists is itself stale
        # (read_pending_swap returns None for it, so the guard above let us through).
        _clear_pending_swap()

        paths = [os.path.join(root, name) for name in _ARTIFACT_FILES]
        for pattern in _ARTIFACT_GLOBS:
            paths.extend(glob.glob(os.path.join(root, pattern)))
        for path in paths:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        # The staged bundle is moved OUT of here by a successful swap, leaving an
        # empty shell; a failed download can leave a full one. Both are disposable
        # once no swap is pending.
        shutil.rmtree(_staging_dir(), ignore_errors=True)
    except Exception:
        pass


def _relaunch_extra_args():
    """The CLI args to relaunch with (everything after the executable)."""
    return list(sys.argv[1:])


def apply_pending_swap_and_exit():
    """Spawn a detached helper that swaps in the staged bundle and relaunches,
    then exit this process so the port frees and the install dir is unlocked.

    No-op (returns False) when not frozen or there is no staged update.
    """
    if not _is_frozen():
        return False
    staged_root = read_pending_swap()
    if not staged_root:
        return False

    live_root = _bundle_root()
    port = _current_port()
    exe_name = _bundle_exe_name()
    extra = _relaunch_extra_args()

    if _platform_key() == 'win':
        _spawn_windows_swapper(live_root, staged_root, port, exe_name, extra)
        # Do NOT clear the pending marker here. The Windows swap runs elevated in a
        # detached coordinator and may fail or be declined at the UAC prompt; the
        # coordinator clears the marker only AFTER the swap actually succeeds, so a
        # failed swap leaves the staged bundle in place for a retry instead of being
        # silently orphaned (the old bug: marker cleared regardless → stuck on old).
    else:
        _spawn_posix_swapper(live_root, staged_root, port, exe_name, extra)
        _clear_pending_swap()
    _shutdown_current_process()
    os._exit(0)


def _spawn_posix_swapper(live_root, staged_root, port, exe_name, extra_args):
    import subprocess
    import tempfile

    script = _build_posix_swap_script()
    # '_update_' prefix so cleanup_stale_artifacts can glob these unambiguously —
    # mkstemp's default 'tmp' prefix is too generic to delete on sight.
    fd, path = tempfile.mkstemp(prefix='_update_', suffix='_swap.sh',
                                dir=state.script_dir)
    with os.fdopen(fd, 'w') as f:
        f.write(script)
    os.chmod(path, 0o755)
    cmd = ['sh', path, live_root, staged_root, str(port), exe_name] + list(extra_args)
    # Detached so it outlives this process (which is about to exit).
    subprocess.Popen(cmd, start_new_session=True, close_fds=True)


def _build_posix_swap_script():
    """sh script: wait for the port to free, swap dirs, relaunch the new exe.

    Args: LIVE NEW PORT EXE [relaunch args…]. Port-free is probed with lsof/nc
    when present (fixed short sleep otherwise); the swap is atomic moves with a
    rollback if the second move fails.

    The uninstaller lives one level ABOVE the swapped dir on both posix layouts
    (Linux ``/opt/EasyOKAPI/uninstall.sh`` beside ``/opt/EasyOKAPI/EasyOKAPI/``;
    mac ``…/Contents/Resources/uninstall.command`` beside
    ``…/Resources/EasyOKAPI/``), so the swap does not carry it — meaning it was
    never updated at all, and an install predating the uninstaller never gained
    one. The new bundle now ships its uninstaller inside the onedir, and we copy
    it up into the parent after a successful swap. Best-effort and non-fatal: a
    bundle without one leaves the existing uninstaller untouched (mirroring the
    Windows prefer-bundled/else-keep-old rule), and a parent dir we cannot write
    (a root-owned /opt with the app running as the user) must not fail an
    otherwise-applied update.
    """
    return (
        '#!/bin/sh\n'
        'LIVE="$1"; NEW="$2"; PORT="$3"; EXE="$4"; shift 4\n'
        'i=0\n'
        'while [ $i -lt 84 ]; do\n'
        '  if command -v lsof >/dev/null 2>&1; then\n'
        '    lsof -i "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break\n'
        '  elif command -v nc >/dev/null 2>&1; then\n'
        '    nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1 || break\n'
        '  else\n'
        '    sleep 5; break\n'
        '  fi\n'
        '  sleep 0.3; i=$((i+1))\n'
        'done\n'
        'OLD="$LIVE.old-$$"\n'
        'mv "$LIVE" "$OLD" || exit 1\n'
        'if ! mv "$NEW" "$LIVE"; then mv "$OLD" "$LIVE"; exit 1; fi\n'
        'rm -rf "$OLD"\n'
        'PARENT=$(dirname "$LIVE")\n'
        'for U in uninstall.sh uninstall.command; do\n'
        '  if [ -f "$LIVE/$U" ] && [ -w "$PARENT" ]; then\n'
        '    cp "$LIVE/$U" "$PARENT/$U" 2>/dev/null && chmod +x "$PARENT/$U" 2>/dev/null\n'
        '  fi\n'
        'done\n'
        '"$LIVE/$EXE" "$@" &\n'
    )


def _powershell_exe():
    """Absolute path to powershell.exe (frozen-safe).

    A bare 'powershell' relies on PATH, but a PyInstaller-frozen process can run
    with a stripped/sanitised PATH that does not include System32 — making
    ``subprocess.Popen(['powershell', ...])`` raise FileNotFoundError. The swap
    coordinator is spawned exactly this way, so a failed spawn silently aborted
    the binary swap (the update reached 100% then reopened on the old version).
    Resolve the full path from %SystemRoot% so the spawn does not depend on PATH;
    fall back to bare 'powershell' only if the expected location is missing.
    """
    system_root = os.environ.get('SystemRoot') or r'C:\Windows'
    candidate = os.path.join(system_root, 'System32', 'WindowsPowerShell',
                             'v1.0', 'powershell.exe')
    return candidate if os.path.isfile(candidate) else 'powershell'


def _ps_sq(value):
    """Escape a value for embedding inside a PowerShell single-quoted '...' literal."""
    return str(value).replace("'", "''")


# The install dir is normally under %PROGRAMFILES% (admin-only) while the app runs
# NON-elevated, so the directory swap must be elevated. Two scripts cooperate:
#
#   • the ELEVATED helper (_WIN_SWAP_PS1) does ONLY the privileged work — move the
#     live dir aside, move the staged bundle in, settle Uninstall.exe (prefer the
#     bundled one, else carry the old across), reset ACLs so a user-owned staging
#     dir does not leave the install user-writable — then writes OK / FAIL: <msg>
#     to a result file. Launched with -Verb RunAs (one UAC prompt).
#   • the NON-elevated COORDINATOR (_WIN_COORD_PS1) waits for the app's port to
#     free, runs the elevated helper and waits for it, then on success clears the
#     pending-swap marker and relaunches the app — crucially as a child of THIS
#     (non-elevated) process, so the relaunched app does NOT inherit admin (which
#     would corrupt the user-owned data dir). On failure it leaves the staged
#     bundle + marker for a retry and shows a dialog. Both log to update_swap.txt.
#
# Templates use @@PLACEHOLDER@@ markers (PowerShell's own {} braces make str.format
# / f-strings impractical); values are substituted with _ps_sq-escaped literals.

# $ErrorActionPreference='Stop' is MANDATORY: without it a failed Move-Item is a
# NON-terminating error that try/catch does NOT catch, so the script would blunder
# past a failed "move live aside" straight into "move new in" — and since $live
# still exists, Move-Item nests the new build INSIDE it (EasyOKAPI\EasyOKAPI) and
# then writes OK. With 'Stop', a failed move is terminating → caught → rolled back
# → reported FAIL → marker kept for retry. Only the two dir moves are fatal; the
# Uninstall copy / .old cleanup / ACL reset are best-effort (wrapped) so they can't
# turn an applied swap into a false failure (or a rollback over the new install).
_WIN_SWAP_PS1 = r'''
$ErrorActionPreference = 'Stop'
$live = '@@LIVE@@'; $new = '@@NEW@@'; $exe = '@@EXE@@'; $res = '@@RES@@'; $log = '@@LOG@@'
function Log($m){ try { New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null; Add-Content -Path $log -Value ('[' + (Get-Date).ToString('s') + '] [elevated] ' + $m) } catch {} }
$old = "$live.old"
try {
  Log 'swap start'
  if (Test-Path $old) { Remove-Item -Recurse -Force $old }
  # The live install can stay briefly locked after the app exits (a lingering file
  # handle, AV scan, etc.); retry the move-aside instead of failing on the first try.
  $moved = $false
  for ($i = 0; $i -lt 20; $i++) {
    try { Move-Item -Force -LiteralPath $live $old; $moved = $true; break }
    catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $moved) { throw ('live install still locked, could not move aside: ' + $live) }
  # Guard against ever nesting the new build inside a surviving $live.
  if (Test-Path $live) { throw ('live install dir unexpectedly still present: ' + $live) }
  Move-Item -Force -LiteralPath $new $live
  # Uninstall.exe lives INSIDE the swapped directory, so the move above takes it
  # with the old build. Prefer the uninstaller the NEW bundle ships, so uninstaller
  # fixes actually reach updated installs; only carry the previous one across when
  # the bundle has none (a bundle built before it was included). Without this the
  # install keeps its original uninstaller forever — see Rule.md §2.25.
  if (Test-Path (Join-Path $live 'Uninstall.exe')) {
    Log 'uninstaller: using the copy shipped in the new bundle'
  } else {
    $u = Join-Path $old 'Uninstall.exe'
    if (Test-Path $u) { try { Copy-Item $u (Join-Path $live 'Uninstall.exe') -Force; Log 'uninstaller: bundle shipped none, carried the previous one across' } catch { Log ('uninstall copy failed: ' + $_.Exception.Message) } }
  }
  try { Remove-Item -Recurse -Force $old } catch { Log ('old dir left for later cleanup: ' + $_.Exception.Message) }
  try { icacls $live /reset /T /C /Q | Out-Null; Log 'acl reset ok' } catch { Log ('acl reset failed: ' + $_.Exception.Message) }
  Set-Content -Path $res -Value 'OK' -Encoding ascii
  Log 'swap ok'
} catch {
  $msg = $_.Exception.Message
  try { if ((Test-Path $old) -and (-not (Test-Path $live))) { Move-Item -Force $old $live } } catch {}
  Set-Content -Path $res -Value ('FAIL: ' + $msg) -Encoding ascii
  Log ('swap failed: ' + $msg)
}
'''

_WIN_COORD_PS1 = r'''
$live = '@@LIVE@@'; $port = @@PORT@@; $exe = '@@EXE@@'; $res = '@@RES@@'; $log = '@@LOG@@'; $pend = '@@PEND@@'
function Log($m){ try { New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null; Add-Content -Path $log -Value ('[' + (Get-Date).ToString('s') + '] [coord] ' + $m) } catch {} }
function Test-Listening($p){ try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $p); $c.Close(); return $true } catch { return $false } }
Log 'waiting for app to exit'
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) { if (-not (Test-Listening $port)) { break }; Start-Sleep -Milliseconds 300 }
$ok = $false
try {
  Log 'launching elevated swap (UAC)'
  Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -ArgumentList '@@SWAPARGS@@'
  if ((Test-Path $res) -and ((Get-Content $res -Raw).Trim() -eq 'OK')) { $ok = $true }
} catch { Log ('elevation declined/failed: ' + $_.Exception.Message) }
if ($ok) {
  try { Remove-Item -Force $pend -ErrorAction SilentlyContinue } catch {}
  $exePath = Join-Path $live $exe
  Start-Process -FilePath $exePath @@ARGCLAUSE@@-WorkingDirectory $live -WindowStyle Hidden
  Log 'swap ok; relaunched non-elevated'
} else {
  Log 'swap NOT applied; staged bundle + pending marker kept for retry'
  try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('@@MSG@@', 'EasyOKAPI Update') | Out-Null } catch {}
}
'''


def _swap_log_path():
    return os.path.join(state.script_dir, 'log', 'update_swap.txt')


def _build_windows_swap_script(live_root, staged_root, exe_name, result_txt, log_txt):
    """The ELEVATED helper script (run via -Verb RunAs): the privileged swap only.

    Moves the live install dir aside, moves the staged bundle in, carries
    Uninstall.exe across, resets ACLs (so a user-owned staging dir does not leave
    the install user-writable), and writes OK / FAIL: <msg> to result_txt. Does NOT
    relaunch the app — that must happen non-elevated (see the coordinator).
    """
    return (_WIN_SWAP_PS1
            .replace('@@LIVE@@', _ps_sq(live_root))
            .replace('@@NEW@@', _ps_sq(staged_root))
            .replace('@@EXE@@', _ps_sq(exe_name))
            .replace('@@RES@@', _ps_sq(result_txt))
            .replace('@@LOG@@', _ps_sq(log_txt)))


def _build_windows_coordinator_script(live_root, port, exe_name, extra_args,
                                      swap_ps1, result_txt, log_txt):
    """The NON-elevated coordinator script: wait → elevate swap → relaunch / report.

    Waits for the app's port to free, runs the elevated swap helper (one UAC
    prompt) and waits for it, then on success clears the pending-swap marker and
    relaunches the app as a child of THIS non-elevated process (so it does not
    inherit admin). On failure it leaves the staged bundle + marker for a retry and
    shows a dialog.
    """
    # Elevated launch args as ONE string so the -File path survives spaces (e.g. a
    # Documents path under "C:\Users\First Last"); Start-Process -ArgumentList does
    # not quote array elements, so we quote the path ourselves.
    swap_args = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{}"'.format(swap_ps1)
    arg_clause = ''
    if extra_args:
        arg_clause = '-ArgumentList @(' + ', '.join(_ps_arg(a) for a in extra_args) + ') '
    msg = ('EasyOKAPI could not finish updating — it needs administrator permission '
           'to replace its program files. Please relaunch EasyOKAPI and run Update '
           'again, approving the permission prompt.')
    return (_WIN_COORD_PS1
            .replace('@@LIVE@@', _ps_sq(live_root))
            .replace('@@PORT@@', str(int(port)))
            .replace('@@EXE@@', _ps_sq(exe_name))
            .replace('@@RES@@', _ps_sq(result_txt))
            .replace('@@LOG@@', _ps_sq(log_txt))
            .replace('@@PEND@@', _ps_sq(_pending_swap_path()))
            .replace('@@SWAPARGS@@', _ps_sq(swap_args))
            .replace('@@ARGCLAUSE@@', arg_clause)
            .replace('@@MSG@@', _ps_sq(msg)))


def _spawn_windows_swapper(live_root, staged_root, port, exe_name, extra_args):
    import subprocess

    swap_ps1 = os.path.join(state.script_dir, '_update_swap.ps1')
    coord_ps1 = os.path.join(state.script_dir, '_update_coordinator.ps1')
    result_txt = os.path.join(state.script_dir, '_update_swap_result.txt')
    log_txt = _swap_log_path()

    # Clear any stale result so the coordinator never reads a previous run's outcome.
    try:
        if os.path.exists(result_txt):
            os.remove(result_txt)
    except OSError:
        pass

    with open(swap_ps1, 'w', encoding='utf-8') as f:
        f.write(_build_windows_swap_script(live_root, staged_root, exe_name, result_txt, log_txt))
    with open(coord_ps1, 'w', encoding='utf-8') as f:
        f.write(_build_windows_coordinator_script(
            live_root, port, exe_name, extra_args, swap_ps1, result_txt, log_txt))

    # NOTE: do NOT use DETACHED_PROCESS here. powershell.exe is a console app;
    # DETACHED_PROCESS gives the child no console at all, so the PowerShell host
    # fails to initialise and the process exits immediately WITHOUT running the
    # script (no swap, no update_swap.txt — the silent "reopens on old version"
    # failure). CREATE_NO_WINDOW already runs it hidden with its own console, and
    # the child still outlives this (exiting) parent. CREATE_NEW_PROCESS_GROUP
    # shields it from any Ctrl+C/Break aimed at our group.
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    # cwd MUST be outside the install dir. The coordinator inherits the app's cwd,
    # which is the install dir ($live, set by the launcher's -WorkingDirectory). It
    # stays alive (waiting on the elevated swap) during the move, and Windows cannot
    # rename a directory that is a running process's current directory — so the
    # elevated "move $live aside" would fail and the new build would nest inside the
    # old one. Run the coordinator from the data dir instead, which is never inside
    # the install dir.
    subprocess.Popen(
        [_powershell_exe(), '-NoProfile', '-NonInteractive',
         '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', coord_ps1],
        creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
        cwd=state.script_dir,
    )


def restart_after_delay(delay_secs=1.5):
    """Restart the current process after a short delay (non-blocking).

    Mac/Linux: os.execv replaces the process image in place — atomic, and the
    same image rebinds the port (Werkzeug sets SO_REUSEADDR).

    Windows: a process cannot relaunch itself after os._exit(), and the dev
    server's port lingers briefly after exit. The old code spawned the new
    instance and *then* hard-exited, so the new process raced the dying one for
    the port, failed to bind, and (being launched -WindowStyle Hidden) died with
    no visible window — bricking the app until the stray process was killed.

    Instead we spawn a *detached* PowerShell relauncher that waits for the port
    to be released, starts a fresh hidden instance, and shows a dialog if it
    never comes up. Only then does this process free the port via os._exit().
    """
    import threading
    import time

    def _do_restart():
        time.sleep(delay_secs)
        if platform.system().lower().startswith('win'):
            _restart_windows()
        else:
            os.execv(sys.executable, [sys.executable] + _relaunch_argv())

    threading.Thread(target=_do_restart, daemon=False).start()


def _relaunch_argv():
    """argv for the relaunched instance, forced to not auto-open a browser tab.

    The restarting tab reloads itself (restarting.html) and consumes the one-shot
    reset-display marker. A second tab auto-opened by the fresh instance would race
    that reload for the marker, so the user-facing tab could miss the default-display
    reset (kinetics mode + selected button). Suppress it with --no-browser.
    """
    argv = list(sys.argv)
    if '--no-browser' not in argv:
        argv.append('--no-browser')
    return argv


def _current_port():
    try:
        return int(state.args.port)
    except Exception:
        return 5099


def _shutdown_current_process():
    """Best-effort stop of the data-logger subprocess so it is not orphaned on exit."""
    try:
        import browser_mgt
        browser_mgt.cleanup(state.process, state.log_file, state.args)
    except Exception:
        pass


def _ps_quote(s):
    """Quote a value as a PowerShell single-quoted string literal."""
    return "'" + str(s).replace("'", "''") + "'"


def _ps_arg(s):
    """Quote a process argument for ``Start-Process -ArgumentList``.

    Start-Process joins the ArgumentList elements with spaces to form the child
    command line and does NOT quote elements that contain spaces. So passing a
    bare path like ``C:\\Program Files\\EasyOKAPI\\code\\main.py`` makes Python
    receive a split argv (``C:\\Program`` + ``Files\\...``) and fail to start.
    We therefore embed double quotes around the value (mirroring launcher.ps1)
    and wrap the whole thing as a PowerShell single-quoted literal.
    """
    content = '"' + str(s).replace('"', '\\"') + '"'
    return "'" + content.replace("'", "''") + "'"


def _build_windows_relaunch_script(cmd, cwd, port):
    """Build a one-line PowerShell relauncher script (statements joined by ';').

    Port readiness is probed with a .NET ``TcpClient`` connect to
    ``127.0.0.1:<port>`` rather than ``Get-NetTCPConnection``. That cmdlet lives
    in the NetTCPIP module, which is absent on some Windows builds; the old code
    fell back to a fixed ``Start-Sleep -Seconds 3`` there, re-introducing the
    port race that bricked the relaunch (the new instance tried to bind before
    the dying one freed the port, ``app.run`` → ``sys.exit(1)``, and — being
    hidden — died silently). A connect probe works on every Windows PowerShell
    version and is immune to ``SO_REUSEADDR`` (which would let a *bind* succeed
    while the dying process still holds the port, so "can I bind?" is not a
    reliable "is it free?" — "can I connect?" is).
    """
    exe_q = _ps_quote(cmd[0])
    cwd_q = _ps_quote(cwd)
    args = cmd[1:]
    arg_clause = ''
    if args:
        arg_list = ', '.join(_ps_arg(a) for a in args)
        arg_clause = f"-ArgumentList @({arg_list}) "
    msg = ('EasyOKAPI did not come back up after the update. '
           'Please relaunch it from the Start menu or desktop shortcut.')
    return (
        f"$port = {int(port)}; "
        # True while something is actively listening on the loopback port.
        "function Test-Listening($p) { "
        "  try { $c = New-Object System.Net.Sockets.TcpClient; "
        "    $c.Connect('127.0.0.1', $p); $c.Close(); return $true } "
        "  catch { return $false } "
        "}; "
        # Wait for the dying instance to release the port (up to ~20s).
        "$deadline = (Get-Date).AddSeconds(20); "
        "while ((Get-Date) -lt $deadline) { "
        "  if (-not (Test-Listening $port)) { break }; Start-Sleep -Milliseconds 300 "
        "} "
        f"Start-Process -FilePath {exe_q} {arg_clause}-WorkingDirectory {cwd_q} -WindowStyle Hidden; "
        # Wait for the fresh instance to come back up (up to ~20s).
        "$up = $false; $check = (Get-Date).AddSeconds(20); "
        "while ((Get-Date) -lt $check) { "
        "  if (Test-Listening $port) { $up = $true; break }; Start-Sleep -Milliseconds 400 "
        "} "
        "if (-not $up) { "
        "  try { Add-Type -AssemblyName PresentationFramework; "
        f"    [System.Windows.MessageBox]::Show({_ps_quote(msg)}, 'EasyOKAPI Update') | Out-Null "
        "  } catch {} "
        "}"
    )


def _restart_windows():
    import subprocess

    port = _current_port()
    cwd = os.getcwd()
    cmd = [sys.executable] + _relaunch_argv()

    # Not DETACHED_PROCESS: powershell.exe needs a console or it exits before
    # running. CREATE_NO_WINDOW runs it hidden (with a console) and it outlives
    # this exiting parent. See _spawn_windows_swapper for the full rationale.
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(
            [_powershell_exe(), '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
             '-Command', _build_windows_relaunch_script(cmd, cwd, port)],
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
            close_fds=True,
        )
    except Exception as e:
        # If the detached relauncher cannot be spawned, fall back to the naive
        # relaunch so the user is not left with nothing running.
        print(f"[update] Detached relaunch failed ({e}); using direct relaunch.")
        subprocess.Popen(cmd, cwd=cwd)
        os._exit(0)
        return

    _shutdown_current_process()
    os._exit(0)
