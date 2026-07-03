"""Stable per-machine hardware fingerprint used to hardware-lock activation.

A permanent activation token is bound to exactly one machine by embedding this
fingerprint as its ``hwid`` claim. The desktop client recomputes the fingerprint
on startup and refuses to run if it does not match the token (so a copied
``activation.json`` — or a whole copied install folder — fails on a second
machine), and the server records the same fingerprint to enforce a one-machine
seat limit per license.

The fingerprint is a SHA-256 hex digest of a canonical string:

    easyokapi-hwid-v1|<os>|<raw-id>

where ``<os>`` is ``win`` / ``mac`` / ``linux`` and ``<raw-id>`` is a stable,
OS-provided machine identifier, lower-cased:

    win   → HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    mac   → IOPlatformUUID (ioreg)
    linux → /etc/machine-id (or /var/lib/dbus/machine-id)

IMPORTANT: the Windows recipe is mirrored byte-for-byte by the installer's
PowerShell (installer-win/setup-frozen.nsi), so the token the installer requests
at install time matches the fingerprint the app computes at runtime. If you
change the salt (``_HWID_VERSION``), the ``win`` branch, or the canonical string
format, update that PowerShell too or installs will fail their first launch.
"""

import hashlib
import platform
import subprocess

# Bump only on a deliberate fingerprint-format change. Bumping invalidates every
# existing permanent token (every machine produces a new hwid → re-activation).
_HWID_VERSION = 'easyokapi-hwid-v1'

_UNKNOWN = 'unknown'


def _os_tag():
    system = platform.system().lower()
    if system.startswith('win') or system == 'nt':
        return 'win'
    if system == 'darwin':
        return 'mac'
    return 'linux'


def _windows_machine_guid():
    r"""HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid — stable per OS install."""
    try:
        import winreg
        # 64-bit view: MachineGuid lives in the native hive, so force KEY_WOW64_64KEY
        # to read the same value a 64-bit PowerShell (the installer) sees.
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Cryptography',
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            val, _ = winreg.QueryValueEx(key, 'MachineGuid')
        return (val or '').strip()
    except Exception:
        return ''


def _macos_platform_uuid():
    """IOPlatformUUID from ioreg — stable per physical Mac."""
    try:
        out = subprocess.check_output(
            ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode('utf-8', 'replace')
        for line in out.splitlines():
            if 'IOPlatformUUID' in line:
                # ... "IOPlatformUUID" = "XXXXXXXX-...."
                return line.split('=', 1)[1].strip().strip('"').strip()
    except Exception:
        pass
    return ''


def _linux_machine_id():
    """/etc/machine-id (systemd) — stable per OS install."""
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                val = f.read().strip()
            if val:
                return val
        except Exception:
            continue
    return ''


def _raw_machine_id(os_tag):
    if os_tag == 'win':
        return _windows_machine_guid()
    if os_tag == 'mac':
        return _macos_platform_uuid()
    return _linux_machine_id()


def get_hwid():
    """Return the machine fingerprint as a 64-char lowercase hex SHA-256 digest.

    Deterministic on a given machine. When the OS identifier cannot be read we
    fall back to the literal ``unknown`` so the function never raises — such a
    machine simply produces a constant, non-unique fingerprint (its activation
    will not be hardware-distinct, which is the safe-but-degraded outcome rather
    than a crash).
    """
    os_tag = _os_tag()
    raw = (_raw_machine_id(os_tag) or _UNKNOWN).strip().lower()
    canonical = '{}|{}|{}'.format(_HWID_VERSION, os_tag, raw)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def is_resolvable():
    """True when a real OS machine identifier was found (not the fallback).

    Lets callers warn that hardware locking is degraded on an exotic host.
    """
    return bool(_raw_machine_id(_os_tag()))


if __name__ == '__main__':  # manual check: python src/hwid.py
    print('os      :', _os_tag())
    print('resolved:', is_resolvable())
    print('hwid    :', get_hwid())
