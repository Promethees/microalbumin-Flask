"""Read and edit the colorimeter's configuration.json on its CIRCUITPY drive.

The device cannot write this file. CircuitPython mounts its own filesystem
read-only unless boot.py remounts it, and remounting hands the drive to the
board and takes it away from this machine — so the firmware's own calibration is
runtime-only and dies at the next power cycle. The host is the side that *can*
write it, because the drive is simply mounted here.

That also makes the write the way a calibration is applied for good: CircuitPython
watches its filesystem and reloads when the USB host changes a file, so saving the
factors restarts the device and it comes back running them. The reload is the
reason the routes only allow this while no reading session is in progress.

Nothing here writes a file it did not first recognise as a colorimeter's
(boot_out.txt naming CircuitPython), and nothing rewrites more of it than the one
key it was asked to change.
"""

import json
import os
import platform
import re
import string
import tempfile

CONFIGURATION_FILE = "configuration.json"
BOOT_OUT_FILE = "boot_out.txt"
VOLUME_NAME = "CIRCUITPY"

# The key this module owns. Everything else in the file is the operator's.
FACTOR_KEY = "raw_count_factor"

# Matches the key and its array, keeping whatever spacing the file already uses
# around the colon so a hand-aligned file stays aligned.
_FACTOR_LINE = re.compile(
    r'^([ \t]*"' + FACTOR_KEY + r'"[ \t]*:[ \t]*)\[[^\]]*\]', re.MULTILINE)

# Where a new key is inserted when the file has none: after active_channels,
# which is the setting it belongs beside.
_ANCHOR_LINE = re.compile(r'^([ \t]*)"active_channels"[ \t]*:.*$', re.MULTILINE)
_OPEN_BRACE = re.compile(r'^\s*\{[ \t]*$', re.MULTILINE)


class DeviceConfigError(Exception):
    """The drive could not be found, read, or safely written."""


def candidate_roots():
    """Every path a CIRCUITPY drive plausibly mounts at on this machine."""
    system = platform.system().lower()
    if system == "darwin":
        return [os.path.join("/Volumes", VOLUME_NAME)]
    if system == "windows":
        # No volume-label lookup: checking each letter for the board's own
        # boot_out.txt identifies it without a ctypes call into kernel32.
        return [f"{letter}:\\" for letter in string.ascii_uppercase]
    # Linux and the rest. The user-owned mount points first, since that is
    # where a desktop session puts removable media.
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    roots = []
    for base in (f"/media/{user}", f"/run/media/{user}", "/media", "/mnt"):
        if user or not base.endswith(user):
            roots.append(os.path.join(base, VOLUME_NAME))
    return roots


def is_device_root(path):
    """True when `path` looks like a CircuitPython board's drive.

    Checked before every write. A stale mount point, or a USB stick someone
    labelled CIRCUITPY, is the difference between saving a calibration and
    overwriting a stranger's file.
    """
    try:
        with open(os.path.join(path, BOOT_OUT_FILE), "r", encoding="utf-8", errors="replace") as handle:
            return "circuitpython" in handle.read(400).lower()
    except OSError:
        return False


def find_device_root():
    """The mounted CIRCUITPY drive, or None."""
    for path in candidate_roots():
        if is_device_root(path):
            return path
    return None


def configuration_path(root):
    return os.path.join(root, CONFIGURATION_FILE)


def read_configuration(root):
    """Parse the device's configuration.json. Raises DeviceConfigError."""
    path = configuration_path(root)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise DeviceConfigError(f"Could not read {CONFIGURATION_FILE}: {error}")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise DeviceConfigError(f"{CONFIGURATION_FILE} is not valid JSON: {error}")
    if not isinstance(data, dict):
        raise DeviceConfigError(f"{CONFIGURATION_FILE} is not a JSON object")
    return data


def _format_array(factors):
    return "[" + ", ".join(f"{float(factor):.4f}" for factor in factors) + "]"


def _replace_factor(text, factors):
    """Return `text` with raw_count_factor set, and nothing else touched.

    A targeted edit rather than json.dumps of a parsed object: this file is
    written and read by hand — aligned colons, a comment-free but deliberate
    key order — and a round trip through the parser would reformat all of it to
    save one line. It also cannot corrupt a setting it never looked at.
    """
    array = _format_array(factors)

    replaced, count = _FACTOR_LINE.subn(lambda m: m.group(1) + array, text, count=1)
    if count:
        return replaced

    # No key yet: put it beside active_channels, matching that line's indent.
    anchor = _ANCHOR_LINE.search(text)
    if anchor:
        indent = anchor.group(1)
        line = f'{indent}"{FACTOR_KEY}" : {array},'
        return text[:anchor.end()] + "\n" + line + text[anchor.end():]

    # Not even that: first line after the opening brace.
    brace = _OPEN_BRACE.search(text)
    if brace:
        line = f'  "{FACTOR_KEY}" : {array},'
        return text[:brace.end()] + "\n" + line + text[brace.end():]

    raise DeviceConfigError(f"Could not find where to put {FACTOR_KEY} in {CONFIGURATION_FILE}")


def write_raw_count_factor(root, factors):
    """Save the factors into the device's configuration.json.

    Returns the path written. Raises DeviceConfigError and leaves the file as it
    was if anything about the result would not parse.
    """
    if not is_device_root(root):
        raise DeviceConfigError(f"{root} does not look like a CircuitPython drive")
    if not factors:
        raise DeviceConfigError("No factors to save")

    path = configuration_path(root)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            original = handle.read()
    except OSError as error:
        raise DeviceConfigError(f"Could not read {CONFIGURATION_FILE}: {error}")

    updated = _replace_factor(original, factors)

    # Parse before writing, not after. The device reloads the moment this file
    # changes, so a file that does not parse is a device sitting on an error
    # screen — and the check costs nothing here.
    try:
        json.loads(updated)
    except ValueError as error:
        raise DeviceConfigError(f"Refusing to write invalid JSON: {error}")

    _atomic_write(path, updated)
    return path


def _atomic_write(path, text):
    """Write `text` to `path` via a temporary file in the same directory.

    The rename is what the device sees, so it never reads a half-written file —
    it watches for changes and reloads on them, and the window between "opened
    for writing" and "finished" is exactly when it would look.
    """
    directory = os.path.dirname(path) or "."
    handle = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".cfg", suffix=".tmp")
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise DeviceConfigError(f"Could not write {CONFIGURATION_FILE}: {error}")
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if temporary is not None and os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
