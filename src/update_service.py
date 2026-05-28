import os
import sys
import shutil
import platform
import zipfile
import requests
import state
import activation as activation_mod


_PRESERVE = frozenset({
    'data', 'report', 'json', 'log',
    'activation.json', 'ai_settings.json', 'user_settings.json',
    '.env',
})


def _version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except Exception:
        return (0,)


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
    latest = str(data.get('version', state.APP_VERSION))
    return {
        'current': state.APP_VERSION,
        'latest': latest,
        'update_available': _version_tuple(latest) > _version_tuple(state.APP_VERSION),
        'release_notes': data.get('release_notes', ''),
    }


def download_and_apply(progress_cb=None):
    """Download the update zip from the server and apply it in-place.

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
    tmp_path = os.path.join(state.script_dir, '_update_download.zip')

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
    updated = _apply_zip(tmp_path)

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


def _shared_prefix(zf):
    """Return the single top-level directory prefix shared by all zip entries, or None."""
    names = zf.namelist()
    if not names:
        return None
    first = names[0].replace('\\', '/').split('/')[0]
    if first and '.' not in first and all(
        n.replace('\\', '/').split('/')[0] == first for n in names
    ):
        return first
    return None


def _apply_zip(zip_path):
    project_root = state.script_dir
    updated = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        prefix = _shared_prefix(zf)
        for entry in zf.infolist():
            name = entry.filename.replace('\\', '/')
            if prefix and name.startswith(prefix + '/'):
                name = name[len(prefix) + 1:]
            if not name:
                continue
            top = name.split('/')[0]
            if top in _PRESERVE:
                continue
            if entry.is_dir() or name.endswith('/'):
                continue
            dest = os.path.join(project_root, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(entry) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            updated.append(name)
    return updated


def restart_after_delay(delay_secs=1.5):
    """Restart the current Python process after a short delay (non-blocking)."""
    import threading
    import time

    def _do_restart():
        time.sleep(delay_secs)
        if platform.system().lower().startswith('win'):
            import subprocess
            subprocess.Popen([sys.executable] + sys.argv)
            os._exit(0)
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_do_restart, daemon=False).start()
