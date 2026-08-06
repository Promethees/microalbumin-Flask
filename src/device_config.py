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

# The keys this module owns. Everything else in the file is the operator's.
#
# All three are settings the device can change at runtime and cannot persist:
# CircuitPython cannot write its own filesystem, so a channel set, a spectral
# channel or a calibration lives only until the next power cycle unless the host
# writes it here.
FACTOR_KEY = "raw_count_factor"
CHANNELS_KEY = "active_channels"          # multi-channel build: which mux channels carry a sensor
UV_CHANNEL_KEY = "channel"                # UV build: which spectral channel is measured

# A JSON value on one line: an array, a string, a number, or a literal. Enough
# for every key here, and deliberately not a parser — see _replace_value.
_VALUE = r'(?:\[[^\]]*\]|"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)'


def _key_line(key):
    """Matches `"key" : <value>`, keeping whatever spacing the file already uses
    around the colon so a hand-aligned file stays aligned."""
    return re.compile(
        r'^([ \t]*"' + re.escape(key) + r'"[ \t]*:[ \t]*)' + _VALUE, re.MULTILINE)


def _anchor_line(key):
    return re.compile(r'^([ \t]*)"' + re.escape(key) + r'"[ \t]*:.*$', re.MULTILINE)


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


def _format_scalar(value):
    """One JSON scalar, written the way this file writes them.

    Floats keep four decimals because that is the precision a factor is compared
    at on both sides; an int stays an int, because a channel number written as
    0.0000 would be a channel number nobody could read.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def _format_value(value):
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_scalar(item) for item in value) + "]"
    return _format_scalar(value)


def _format_array(factors):
    return _format_value([float(factor) for factor in factors])


def _replace_value(text, key, value, anchor_key=None):
    """Return `text` with `key` set to `value`, and nothing else touched.

    A targeted edit rather than json.dumps of a parsed object: this file is
    written and read by hand — aligned colons, a comment-free but deliberate
    key order — and a round trip through the parser would reformat all of it to
    save one line. It also cannot corrupt a setting it never looked at.

    `anchor_key` is where a missing key is inserted: beside the setting it
    belongs with, so a file the operator opens afterwards still reads in the
    order it was written in.
    """
    formatted = _format_value(value)

    replaced, count = _key_line(key).subn(lambda m: m.group(1) + formatted, text, count=1)
    if count:
        return replaced

    if anchor_key:
        anchor = _anchor_line(anchor_key).search(text)
        if anchor:
            indent = anchor.group(1)
            line = f'{indent}"{key}" : {formatted},'
            return text[:anchor.end()] + "\n" + line + text[anchor.end():]

    # Not even that: first line after the opening brace.
    brace = _OPEN_BRACE.search(text)
    if brace:
        line = f'  "{key}" : {formatted},'
        return text[:brace.end()] + "\n" + line + text[brace.end():]

    raise DeviceConfigError(f"Could not find where to put {key} in {CONFIGURATION_FILE}")


def _replace_factor(text, factors):
    """raw_count_factor, beside active_channels when the file has no key yet."""
    return _replace_value(text, FACTOR_KEY, [float(factor) for factor in factors],
                          anchor_key=CHANNELS_KEY)


def _write(root, edit):
    """Apply one targeted edit to the device's configuration.json.

    Returns the path written. Raises DeviceConfigError and leaves the file as it
    was if anything about the result would not parse.
    """
    if not is_device_root(root):
        raise DeviceConfigError(f"{root} does not look like a CircuitPython drive")

    path = configuration_path(root)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            original = handle.read()
    except OSError as error:
        raise DeviceConfigError(f"Could not read {CONFIGURATION_FILE}: {error}")

    updated = edit(original)

    # Parse before writing, not after. The device reloads the moment this file
    # changes, so a file that does not parse is a device sitting on an error
    # screen — and the check costs nothing here.
    try:
        json.loads(updated)
    except ValueError as error:
        raise DeviceConfigError(f"Refusing to write invalid JSON: {error}")

    _atomic_write(path, updated)
    return path


def write_raw_count_factor(root, factors):
    """Save the raw count factors into the device's configuration.json."""
    if not factors:
        raise DeviceConfigError("No factors to save")
    return _write(root, lambda text: _replace_factor(text, factors))


def write_active_channels(root, channels):
    """Save the multiplexer channels the device is running on.

    Written first in the file when the key is missing, because it is the setting
    every per-channel key below it is indexed by — a reader who cannot see which
    channels are active cannot read the rest.

    The values are validated here as well as in the route: this is the function
    that touches the file, and a channel list the firmware would reject at boot
    leaves the device on an error screen with no drive-side way back except
    editing the file by hand.
    """
    try:
        channels = [int(channel) for channel in channels]
    except (TypeError, ValueError):
        raise DeviceConfigError("Channels must be whole numbers")
    if not channels:
        raise DeviceConfigError("No channels to save")
    if len(set(channels)) != len(channels):
        raise DeviceConfigError("Duplicate channels")
    if any(channel < 0 for channel in channels):
        raise DeviceConfigError("Channels must not be negative")
    return _write(root, lambda text: _replace_value(text, CHANNELS_KEY, channels))


def write_uv_channel(root, channel):
    """Save the spectral channel the UV build is measuring ("UVA"/"UVB"/"UVC").

    The names are the device's own (its STATE says which one is in force), not a
    list kept here: a build that grew a fourth would otherwise be unable to save
    the channel it is actually using.
    """
    channel = (channel or "").strip()
    if not channel:
        raise DeviceConfigError("No channel to save")
    if not channel.replace("_", "").isalnum():
        # It goes into a JSON string on a device that reloads on the write; keep
        # it to what a channel name can be rather than trusting the wire.
        raise DeviceConfigError(f"{channel} is not a channel name")
    return _write(root, lambda text: _replace_value(text, UV_CHANNEL_KEY, channel))


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
