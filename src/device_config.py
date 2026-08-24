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

# The sensors' gain and integration time are the fourth, and the only one whose
# key NAMES differ per build — `gain`/`integration_time`, `gain_sensor_90`,
# `gain_sensor_<channel>`. They are not listed here for that reason: the device
# reports its own keys (SENSCFG?) and this module writes what it is handed,
# after checking each name looks like one of them.
_SENSOR_KEY = re.compile(r'^(gain|itime|integration_time)(_[A-Za-z0-9_]+)?$')

# A gain or integration time as the firmware's tables spell it: "med", "500ms",
# "1024x", "32ms". Constrained because it goes into a JSON string on a device
# that reloads on the write, and the firmware matches it against a fixed table —
# a value outside this is one the board would come back from with a settings
# error on screen.
_SENSOR_VALUE = re.compile(r'^[A-Za-z0-9]+$')

def _key_prefix(key):
    """Matches the `"key" :` in front of a value, keeping whatever spacing the
    file already uses around the colon so a hand-aligned file stays aligned.

    Group 1 is the indent, which is what an inserted key lines itself up with.
    """
    return re.compile(
        r'^([ \t]*)"' + re.escape(key) + r'"[ \t]*:[ \t]*', re.MULTILINE)


def _value_end(text, start):
    """Offset just past the JSON value beginning at `start`, or None.

    A scanner rather than a pattern. The pattern this replaces described a value
    as one line — `\\[[^\\]]*\\]` for an array — so it stopped at the first `]`
    and a nested array came out half-replaced, which the write guard then caught
    as invalid JSON: a Save that failed with a parse error on a file that was
    perfectly good. Depth is counted and strings are tracked, so a bracket, a
    comma or a newline inside either does not end the value early.
    """
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                if depth == 0:
                    return index + 1
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            if depth == 0:
                # The bracket closing the object this key lives in, reached
                # without one of our own: the value was a bare scalar and ended
                # before it.
                return index
            depth -= 1
            if depth == 0:
                return index + 1
        elif depth == 0 and char in ",\r\n":
            return index
    return None


def _find_value(text, key):
    """`(prefix match, offset just past the value)` for `key`, or None."""
    match = _key_prefix(key).search(text)
    if match is None:
        return None
    end = _value_end(text, match.end())
    if end is None or end <= match.end():
        return None
    # A bare scalar ends at its terminator, so trailing spaces before a comma or
    # a newline would otherwise be swallowed into the replacement.
    while end > match.end() and text[end - 1] in " \t":
        end -= 1
    return match, end


_OPEN_BRACE = re.compile(r'^\s*\{[ \t]*$', re.MULTILINE)

# A comma after a key's value, wherever the file puts it — same line, or the next
# one on a file that leads its lines with it. Its absence is what says the key is
# the last of its object.
_FOLLOWING_COMMA = re.compile(r'[ \t]*\r?\n?[ \t]*,')

# What a spectral channel may be called. ASCII only, because the firmware's own
# names are ("UVA", "UVB", …) and the value is written to a device that reloads
# on the write.
_CHANNEL_NAME = re.compile(r'[A-Za-z0-9_]+')


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
        #
        # From C: on. A and B are the floppy letters, and a machine that still
        # has one mapped — or a disconnected network drive parked there — makes
        # the probe block on a device that was never going to be a PyBadge.
        # Windows has not assigned either to removable USB storage.
        return [f"{letter}:\\" for letter in string.ascii_uppercase[2:]]
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

    found = _find_value(text, key)
    if found:
        match, end = found
        return text[:match.end()] + formatted + text[end:]

    if anchor_key:
        # The anchor's whole `"key" : value` span, not just its line: the value
        # is what the new key goes after, and a comma may sit past the end of it.
        found = _find_value(text, anchor_key)
        if found:
            anchor, anchor_end = found
            indent = anchor.group(1)
            line = f'{indent}"{key}" : {formatted}'
            separator = _FOLLOWING_COMMA.match(text, anchor_end)
            if separator:
                # A comma already follows the anchor, so more keys come after it:
                # slot in behind that comma and carry one of our own for them.
                return text[:separator.end()] + "\n" + line + "," + text[separator.end():]
            # No comma: the anchor is the last key of its object, and the new key
            # takes that place. It gets no trailing comma — the anchor gets the
            # one it never needed — because a comma before `}` is not JSON, and
            # the device reloads on the write and would come back on an error
            # screen.
            return text[:anchor_end] + ",\n" + line + text[anchor_end:]

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
    try:
        factors = [float(factor) for factor in factors]
    except (TypeError, ValueError):
        raise DeviceConfigError("Factors must be numbers")
    # The file is written with four decimals, so anything under half of the last
    # place lands as 0.0000 — a factor that silences its channel instead of
    # correcting it, saved without anything on screen having said so. The
    # device's own range is 0.1..10x, so a number this small is already wrong;
    # refusing it beats writing a zero the operator cannot see.
    if any(0 < abs(factor) < 0.00005 for factor in factors):
        raise DeviceConfigError("A factor is too small to save")
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
    if not _CHANNEL_NAME.fullmatch(channel):
        # It goes into a JSON string on a device that reloads on the write; keep
        # it to what a channel name can be rather than trusting the wire. Spelled
        # as an explicit character set because str.isalnum() is true of any
        # unicode letter or numeral — "UVÅ" and "ⅣⅤ" passed it — and the firmware
        # matches these names against ASCII identifiers of its own.
        raise DeviceConfigError(f"{channel} is not a channel name")
    return _write(root, lambda text: _replace_value(text, UV_CHANNEL_KEY, channel))


def _sensor_anchor(key):
    """The key this one should be inserted beside: the other half of its pair.

    `gain` pairs with `integration_time` on the single-sensor builds and
    `gain_sensor_0` with `itime_sensor_0` on the rest — the two halves of one
    sensor's settings, which is where a reader expects to find them.

    Both directions, not just gain to itime: a file can hold a gain and no
    integration time (the firmware falls back to its default for a missing key),
    and anchoring only one way sent the new `itime_sensor_2` to the top of the
    file, above `active_channels`, instead of under the gain it belongs to. The
    value was right and the JSON parsed — it just read like a different file.
    """
    if key == "gain":
        return "integration_time"
    if key == "integration_time":
        return "gain"
    if key.startswith("gain_"):
        return "itime_" + key[len("gain_"):]
    if key.startswith("itime_"):
        return "gain_" + key[len("itime_"):]
    return None


def write_sensor_settings(root, settings):
    """Save the sensors' gain and integration time, whatever this build calls them.

    `settings` is {config key: value} exactly as the device reported it
    (SENSCFG?), never a set of names assembled here: the four builds hold this
    one setting under four different key schemes, and a host that guessed would
    write a key the firmware never reads — which fails silently, because the
    device simply falls back to its default and the operator sees the setting
    "not stick" with nothing to point at.

    Every key is checked before anything is written, and all of them go into one
    edit, so a device is never left with sensor 0 saved and sensor 1 not.
    Sensors the device did not report are left alone: a channel with no sensor on
    it has no gain in force, and its configured value is the operator's.
    """
    if not settings:
        raise DeviceConfigError("No sensor settings to save")

    checked = []
    for key, value in settings.items():
        key = (key or "").strip()
        value = ("" if value is None else str(value)).strip()
        if not _SENSOR_KEY.match(key):
            raise DeviceConfigError(f"{key} is not a gain or integration time setting")
        if not _SENSOR_VALUE.match(value):
            raise DeviceConfigError(f"{value} is not a setting this device could read back")
        checked.append((key, value))

    def edit(text):
        # Each key beside the one it belongs with when the file has never held
        # it: a gain's own integration time, and failing that the startup
        # measurement, so an inserted pair does not land at the top of a file
        # whose order the operator chose.
        for key, value in checked:
            text = _replace_value(text, key, value, anchor_key=_sensor_anchor(key))
        return text

    return _write(root, edit)


def _atomic_write(path, text):
    """Write `text` to `path` via a temporary file in the same directory.

    What the rename buys is that configuration.json is never a truncated file:
    the board reads it at boot, and a write that died halfway through an
    in-place truncate-and-write would leave it holding nothing to boot from.

    It does not defer the board's reload — CircuitPython restarts on any change
    to its filesystem, and creating the temporary file here is already one. The
    device therefore reloads around this write, possibly more than once; that is
    expected, and is why the callers drop the serial link afterwards.
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
