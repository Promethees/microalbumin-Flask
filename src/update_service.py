import os
import re
import sys
import shutil
import platform
import tarfile
import requests
import state
import activation as activation_mod


_PRESERVE = frozenset({
    'data', 'report', 'json', 'log',
    'activation.json', 'ai_settings.json', 'user_settings.json',
    '.env',
})


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
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    url = f"{activation_mod.AI_SERVICE_URL}/api/version"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    latest = str(data.get('version', '') or '')
    latest_t = _version_tuple(latest)
    current_t = _version_tuple(state.APP_VERSION)
    # If the server returns a valid semver, compare with >= (same version still allows re-download).
    # If the server returns a non-semver string ('latest', etc.), always allow download —
    # it means a build is available but not yet tagged; the banner won't show the version string.
    update_available = True if latest_t is None else (latest_t > (current_t or (0,)))
    return {
        'current': state.APP_VERSION,
        'latest': latest,
        'update_available': update_available,
        'release_notes': data.get('release_notes', ''),
    }


def download_and_apply(progress_cb=None):
    """Download the update tarball from the server and apply it in-place.

    progress_cb(pct: int, label: str) is called at each stage.
    Returns list of relative paths that were updated.
    Raises RuntimeError if not activated, or requests.RequestException on failure.
    """
    token = activation_mod.get_license_token()
    if not token:
        raise RuntimeError('App is not activated — cannot download update.')

    _emit(progress_cb, 5, 'Connecting to update server...')

    url = f"{activation_mod.AI_SERVICE_URL}/api/download"
    headers = {'Authorization': f'Bearer {token}'}
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
            os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_do_restart, daemon=False).start()


def _current_port():
    try:
        return int(state.args.port)
    except Exception:
        return 5099


def _shutdown_current_process():
    """Best-effort stop of the HID subprocess so it is not orphaned on exit."""
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
    cmd = [sys.executable] + list(sys.argv)

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(
            ['powershell', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
             '-Command', _build_windows_relaunch_script(cmd, cwd, port)],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
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
