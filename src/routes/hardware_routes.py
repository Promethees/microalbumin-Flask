from flask import Blueprint, jsonify, request, Response, stream_with_context
import os
import sys
import platform
import subprocess
import signal
import state
import live_stream
import device_link
import device_config
from script_monitor import check_log_for_errors, check_log_for_session_start, check_log_for_end_reason
from file_path import is_reserved_data_folder_name, RESERVED_ARCHIVE_FOLDER
from validators import validate_json

hardware_bp = Blueprint('hardware', __name__)

# Data capture uses the CDC (USB serial) transport by default: a single logger
# subprocess (log_cdc_data.py) owns the serial port for the whole session — it
# sends the start commands, waits for the device ACKs, then reads the data
# stream on the same connection. Flask must NOT also open the port (one owner
# only). The device's keyboard-typing path is reserved as a manual fallback the
# user triggers with the device's Left button (see firmware serial_manager.py).


def clear_logs():
    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass


def clear_current_output_marker():
    """Blank log/current_output.txt at the start of a run.

    The logger writes this marker (the live CSV path) only once it has received
    the device's full header (log_cdc_data.handle_main_header). Until then the
    file still holds the *previous* session's path, so "View live data" — which
    is enabled the instant run_script succeeds — would resolve /api/current_output
    to a stale file from a prior run. Blanking it makes that endpoint return 204
    ("still writing"), so the client keeps polling until the new session's header
    lands. Kept in sync with file_routes.api_current_output / log_cdc_data.py."""
    try:
        marker_path = os.path.join(state.script_dir, 'log', 'current_output.txt')
        os.makedirs(os.path.dirname(marker_path), exist_ok=True)
        with open(marker_path, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass


def _measure_trigger_path():
    """Path of the manual-capture trigger file. /measure_point drops it and the
    running logger (log_cdc_data.CDCDataCollector) polls + consumes it to send a
    MEASURE command to the device. Kept in sync with log_cdc_data.trigger_path."""
    return os.path.join(state.script_dir, 'log', 'measure_trigger.txt')


def clear_measure_trigger():
    """Remove any stale manual-measure trigger at the start of a run so the first
    MEASURE reflects a real button press, not a leftover from a prior session."""
    try:
        path = _measure_trigger_path()
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _control_trigger_path():
    """Path of the pause/resume trigger file. Same IPC shape as the measure
    trigger (Flask cannot touch the serial port — the logger owns it), but the
    file holds the DESIRED STATE token ("PAUSE" / "RESUME") rather than being a
    bare flag: an unconsumed write is simply overwritten, so last press wins,
    which is exactly the right semantics for two opposite commands.
    Kept in sync with log_cdc_data.control_path."""
    return os.path.join(state.script_dir, 'log', 'control_trigger.txt')


def clear_control_trigger():
    """Drop any stale pause/resume request and clear the paused flag, so a new
    run never starts mid-pause because of a leftover from the previous session."""
    state.reading_paused = False
    try:
        path = _control_trigger_path()
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _request_pause_state(paused):
    """Shared body of /pause_reading and /resume_reading: drop the control
    trigger the running logger polls and forwards to the device."""
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No reading session is running'}), 409
    try:
        path = _control_trigger_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('PAUSE' if paused else 'RESUME')
        state.reading_paused = bool(paused)
        return jsonify({
            'status': 'success',
            'paused': state.reading_paused,
            'message': 'Reading paused' if paused else 'Reading resumed',
        })
    except Exception as e:
        verb = 'pause' if paused else 'resume'
        return jsonify({'status': 'failure', 'message': f'Failed to {verb} reading: {str(e)}'}), 500


def _logger_command(base_dir, base_name, timeout_sec, interval_sec, axis="time", manual=False):
    """Build the CDC logger subprocess command. CDC needs no elevated privileges.

    Frozen: there is no python interpreter or log_cdc_data.py on disk, so we
    re-invoke the app binary itself in --cdc-logger mode (sys.executable IS the
    binary; main.py dispatches the collector before Flask loads).
    Dev: run log_cdc_data.py with the running interpreter (which has pyserial)."""
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, '--cdc-logger']
    else:
        script_path = os.path.join(state.bundle_dir, 'log_cdc_data.py')
        if "window" in platform.system().lower():
            venv_python = os.path.join(state.script_dir, 'venv', 'Scripts', 'python.exe')
            python_exe = venv_python if os.path.exists(venv_python) else sys.executable
        else:
            python_exe = sys.executable or 'python3'
        cmd = [python_exe, script_path]
    cmd += ['--base-dir', base_dir, '--base-name', base_name]
    if timeout_sec is not None:
        cmd += ['--timeout-sec', str(float(timeout_sec))]
    if interval_sec is not None:
        cmd += ['--interval-sec', str(float(interval_sec))]
    cmd += ['--axis', 'turn' if axis == 'turn' else 'time']
    if manual:
        cmd += ['--manual']
    return cmd


@hardware_bp.route('/run_script', methods=['POST'])
@validate_json({
    'subfolder': (str, '', False),
    'base_name': (str, 'colorimeter_data', False),
    'timeout_sec': (float, None, False),
    'interval_sec': (float, None, False),
    'axis': (str, 'time', False),
    'manual': (bool, False, False)
})
def run_script(validated_data):
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})

    subfolder = validated_data['subfolder'].strip()
    base_name = validated_data['base_name']
    timeout_sec = validated_data['timeout_sec']
    interval_sec = validated_data['interval_sec']
    axis = 'turn' if str(validated_data.get('axis', 'time')).strip().lower() == 'turn' else 'time'
    # Manual point-mode capture: device idles and emits one row per /measure_point.
    # A manual reading is a turn, so manual forces the turn axis regardless of axis.
    manual = bool(validated_data.get('manual', False))
    if manual:
        axis = 'turn'

    # Subfolder must be a simple name with no path traversal
    if subfolder and any(c in subfolder for c in ('/', '\\', '..')):
        return jsonify({'status': 'failure', 'message': 'Invalid subfolder name'}), 400
    # "root" is reserved by the data-archive feature (see file_path.py).
    if subfolder and is_reserved_data_folder_name(subfolder):
        return jsonify({'status': 'failure', 'message': f"'{RESERVED_ARCHIVE_FOLDER}' is a reserved folder name and cannot be used"}), 400
    if any(c in base_name for c in ('/', '\\', '..')):
        return jsonify({'status': 'failure', 'message': 'Invalid base name'}), 400

    # Resolve and create the target directory under data/
    data_root = os.path.join(state.script_dir, 'data')
    if subfolder:
        abs_dir = os.path.normpath(os.path.join(data_root, subfolder))
        # Guard against path traversal that somehow escaped the name check
        if not abs_dir.startswith(data_root + os.sep) and abs_dir != data_root:
            return jsonify({'status': 'failure', 'message': 'Invalid subfolder'}), 400
        base_dir = abs_dir
    else:
        abs_dir = data_root
        base_dir = abs_dir

    os.makedirs(abs_dir, exist_ok=True)

    cmd = _logger_command(base_dir, base_name, timeout_sec, interval_sec, axis, manual)

    # Fresh log so device/session detection reflects only this run.
    clear_logs()
    # Stale-marker guard: clear the live-file marker so "View live data" can't
    # resolve to the previous session's CSV before this run writes its header.
    clear_current_output_marker()
    # Drop any leftover manual-measure trigger so the first press is a real one.
    clear_measure_trigger()
    # Same for a leftover pause/resume request — a new run always starts running.
    clear_control_trigger()
    # The virtual controller may be holding the port open between commands
    # (src/device_link.py). Hand it over before the logger is spawned — one owner
    # at a time is the whole contract, and the logger has no way to wait its turn.
    device_link.link.close()

    try:
        with open(state.log_file, 'a', encoding='utf-8') as f:
            state.process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            # A missing device makes the logger exit almost immediately
            # (connect_to_device scans the ports and raises BEFORE any settle
            # delay), so a short window is enough to surface device_not_found. A
            # connected device keeps the logger alive (it settles + handshakes),
            # so this times out and we report success — and the shorter wait lets
            # the client start its timer/polling ~1.5s sooner.
            state.process.wait(timeout=0.5)
            error = check_log_for_errors(state.log_file)
            state.process = None
            if error == "device_not_found":
                return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected. Please connect the device and try again.'})
            return jsonify({'status': 'failure', 'message': 'Failed to start reading session. Please check the device connection.'})
        except subprocess.TimeoutExpired:
            return jsonify({'status': 'success', 'message': 'Script is running'})
    except Exception as e:
        state.process = None
        return jsonify({'status': 'failure', 'message': f'Failed to start script: {str(e)}'})


@hardware_bp.route('/measure_point', methods=['POST'])
def measure_point():
    """Manual point-mode capture: request one on-demand reading from the device.

    Flask cannot write to the serial port (the logger subprocess owns it), so we
    drop a trigger file the running logger polls and forwards as a MEASURE command
    (log_cdc_data._check_measure_trigger). Only valid while a session is running."""
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No reading session is running'}), 409
    try:
        path = _measure_trigger_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('1')
        return jsonify({'status': 'success', 'message': 'Measurement requested'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': f'Failed to request measurement: {str(e)}'}), 500


@hardware_bp.route('/pause_reading', methods=['POST'])
def pause_reading():
    """Pause a live reading session: hold off the device's interval streaming
    without ending the run. Only valid while a session is running."""
    return _request_pause_state(True)


@hardware_bp.route('/resume_reading', methods=['POST'])
def resume_reading():
    """Resume a paused reading session (see /pause_reading)."""
    return _request_pause_state(False)


# ── virtual controller ──────────────────────────────────────────────────
# Working the device's own keypad from the app, while no reading session is
# running. Only then: during a run the logger subprocess owns the serial port
# (see src/device_link.py), and the controls that make sense mid-run — pause,
# stop, measure — are the routes above.

def _session_is_running():
    return state.process is not None and state.process.poll() is None


def _controller_busy_response():
    return jsonify({
        'status': 'busy',
        'message': 'The controller is unavailable while a reading session is running',
    }), 409


@hardware_bp.route('/device/state', methods=['GET'])
def device_state():
    """Snapshot of the device: mode, measurement, channels, live values, battery.

    Returns 409 while a session runs rather than an error, so the client can show
    the controller as unavailable instead of as broken.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'device_not_found', 'message': str(e)}), 503


@hardware_bp.route('/device/button', methods=['POST'])
@validate_json({'button': (str, None, True)})
def device_button(validated_data):
    """Press one button on the device (BTN:) — the virtual keypad."""
    if _session_is_running():
        return _controller_busy_response()
    button = validated_data['button'].strip().lower()
    try:
        device_link.link.press(button)
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    # The press may have changed the screen, the blank, the gain — anything the
    # controller draws. Returning the new state with the ACK saves the client a
    # follow-up round trip and removes the window where the UI shows the old one.
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


@hardware_bp.route('/device/channels', methods=['POST'])
@validate_json({'channels': (list, None, True)})
def device_channels(validated_data):
    """Set the device's active multiplexer channels (CHANNELS:).

    Runtime only — the device reverts to its configuration.json on a power cycle,
    because CircuitPython cannot write its own filesystem (see the firmware's
    Colorimeter.set_active_channels). /device/channels/save is what makes a
    channel set outlive the power cycle, and it is a separate press because
    writing that file reboots the board.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        channels = [int(channel) for channel in validated_data['channels']]
    except (TypeError, ValueError):
        return jsonify({'status': 'failure', 'message': 'Channels must be whole numbers'}), 400
    if not channels:
        return jsonify({'status': 'failure', 'message': 'Select at least one channel'}), 400
    if len(set(channels)) != len(channels):
        return jsonify({'status': 'failure', 'message': 'Duplicate channels'}), 400
    try:
        device_link.link.set_channels(channels)
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


def _saved_setting(key):
    """What configuration.json on the drive holds for one key, if it is reachable.

    Same contract as _saved_calibration: never raises. The drive being absent is
    an ordinary state — the device can be connected for serial only, or the
    volume not mounted yet — and the panel says so rather than showing an error.
    """
    root = device_config.find_device_root()
    if root is None:
        return None, None
    try:
        data = device_config.read_configuration(root)
    except device_config.DeviceConfigError:
        return root, None
    return root, data.get(key)


def _save_setting_response(write, value):
    """Write one setting to the drive and answer with what is now saved.

    The board reloads the instant its filesystem changes, so this restarts the
    device — which is what makes the setting outlive the power cycle, and also
    why the open port is dropped afterwards: it is a handle to a device that is
    about to go away.
    """
    if _session_is_running():
        return _controller_busy_response()

    root = device_config.find_device_root()
    if root is None:
        return jsonify({
            'status': 'failure',
            'message': ('No CIRCUITPY drive found. Connect the colorimeter by USB and let '
                        'the drive mount, then try again.'),
        }), 404

    try:
        path = write(root, value)
    except device_config.DeviceConfigError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

    device_link.link.close()
    return jsonify({'status': 'success', 'saved': value, 'drive': root, 'path': path})


@hardware_bp.route('/device/channels/save', methods=['POST'])
def device_channels_save():
    """Write the channels the device is running on into its configuration.json.

    The set comes from the device (STATE), not from the browser: what gets saved
    must be what is actually in force. A cached array would save a selection the
    operator ticked but never applied — and the panel deliberately keeps those
    two apart, because unticking a box and having the board reboot for it is not
    what anyone meant by ticking a box.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        # Not `state`: that is the module this blueprint reads state.process from,
        # and shadowing it here leaves a function whose next use of it raises
        # UnboundLocalError.
        device_state = device_link.link.state()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    channels = device_state.get('chans') or []
    if not channels:
        return jsonify({'status': 'failure',
                        'message': 'The device did not report any active channels'}), 502
    return _save_setting_response(device_config.write_active_channels, channels)


@hardware_bp.route('/device/uvchannel', methods=['GET'])
def device_uv_channels():
    """The spectral channels the UV build offers, in device order (UVCHAN?).

    Asked for rather than assumed: the panel draws one control per name the
    device reports, the same way the calibration fields are labelled from
    CALIBTAGS?. `channels: null` means firmware that predates the command — the
    panel then stays a readout with a Save beside it, which is what it was
    before the selector existed.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        channels = device_link.link.uv_channels()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'device_not_found', 'message': str(e)}), 503
    return jsonify({'status': 'success', 'channels': channels})


@hardware_bp.route('/device/uvchannel', methods=['POST'])
@validate_json({'channel': (str, None, True)})
def device_uv_channel_set(validated_data):
    """Point the device's sensor at one spectral channel (UVCHAN:).

    Runtime only — CircuitPython mounts its own filesystem read-only while
    code.py runs, so the device comes back on its configuration.json after a
    power cycle. /device/uvchannel/save is the separate press that makes the
    choice outlive one, and it is separate because writing that file reboots the
    board.
    """
    if _session_is_running():
        return _controller_busy_response()
    channel = validated_data['channel'].strip()
    if not channel:
        return jsonify({'status': 'failure', 'message': 'Choose a spectral channel'}), 400
    try:
        device_link.link.set_uv_channel(channel)
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    # The new channel with the ACK: the panel would otherwise show the old one
    # until the next poll came round, on the one control whose whole point is
    # which wavelength the device is reading.
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


@hardware_bp.route('/device/uvchannel/save', methods=['POST'])
def device_uv_channel_save():
    """Write the spectral channel the UV build is measuring into its config.

    Same rule as the channel set above: the value is the device's, read back
    from STATE. There is no host command to change it — it is cycled on the
    keypad (or by the panel pressing that key) — so the browser has no version
    of it to send even if it wanted to.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        device_state = device_link.link.state()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    channel = device_state.get('uvchan') or ''
    if not channel:
        return jsonify({'status': 'failure',
                        'message': 'The device did not report a spectral channel'}), 502
    return _save_setting_response(device_config.write_uv_channel, channel)


@hardware_bp.route('/device/sensor-settings', methods=['GET'])
def device_sensor_settings():
    """What the sensors are running on, and what the drive would restore.

    Both halves in one request, because the panel needs them to answer one
    question — "will this survive the next power cycle?" — and the drive is a USB
    volume worth reading once. `settings: null` means firmware that predates
    SENSCFG?, and the panel then offers no Save rather than one the device would
    refuse.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        settings = device_link.link.sensor_config()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'device_not_found', 'message': str(e)}), 503

    root = device_config.find_device_root()
    saved = None
    if root is not None and settings:
        try:
            data = device_config.read_configuration(root)
        except device_config.DeviceConfigError:
            saved = None
        else:
            # Only the keys the device named. The rest of that file is the
            # operator's and is none of this panel's business.
            saved = {key: data.get(key) for key in settings}
    return jsonify({'status': 'success', 'settings': settings,
                    'saved': saved, 'drive': root})


@hardware_bp.route('/device/sensor-settings/save', methods=['POST'])
def device_sensor_settings_save():
    """Write the sensors' gain and integration time into the device's config.

    What the DEVICE reports, never what the browser cached — the same rule the
    channel and calibration saves follow, so a gain dialled in on the keypad is
    saveable from here without the two having exchanged anything first. The keys
    are the device's too: this build's own names for the setting, which is the
    only reason one route can serve four key schemes.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        settings = device_link.link.sensor_config()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    if not settings:
        return jsonify({'status': 'failure',
                        'message': "This device's firmware cannot report its sensor settings"}), 502
    return _save_setting_response(device_config.write_sensor_settings, settings)


@hardware_bp.route('/device/config/saved', methods=['GET'])
def device_config_saved():
    """What the drive's configuration.json holds for the settings the panel saves.

    One request for both, because the panel needs them to answer the same
    question — "will this survive the next power cycle?" — and the drive is a
    USB volume worth reading once rather than twice. Answers with a null drive
    rather than a failure when none is mounted: that is a state to show, not an
    error to raise.
    """
    root = device_config.find_device_root()
    if root is None:
        return jsonify({'status': 'success', 'drive': None, 'saved': {}})
    try:
        data = device_config.read_configuration(root)
    except device_config.DeviceConfigError as e:
        return jsonify({'status': 'success', 'drive': root, 'saved': {}, 'message': str(e)})
    saved = {
        device_config.CHANNELS_KEY: data.get(device_config.CHANNELS_KEY),
        device_config.UV_CHANNEL_KEY: data.get(device_config.UV_CHANNEL_KEY),
    }
    return jsonify({'status': 'success', 'drive': root, 'saved': saved})


@hardware_bp.route('/device/menu', methods=['GET'])
def device_menu():
    """The device's menu entries, in device order (MENU?).

    Its own list: the entries are the default measurements plus every key in the
    device's calibrations.json plus the built-ins, so the host cannot derive it.
    Answered separately from /device/state because it changes only when the
    device reboots, while the state is polled every 1.5 s.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        return jsonify({'status': 'success', 'items': device_link.link.menu_items()})
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502


@hardware_bp.route('/device/menu', methods=['POST'])
@validate_json({'index': (int, None, True)})
def device_menu_select(validated_data):
    """Open one menu entry on the device by index (MENU:).

    The index addresses the list /device/menu returned; the device runs its own
    menu handler on it, so opening an entry from here does exactly what choosing
    it on the keypad does.
    """
    if _session_is_running():
        return _controller_busy_response()
    index = validated_data['index']
    if index < 0:
        return jsonify({'status': 'failure', 'message': 'Menu index must be a whole number'}), 400
    try:
        device_link.link.select_menu(index)
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    # Opening an entry changes the screen — and, for a measurement, what the
    # device is measuring — so the fresh state rides back with the ACK the same
    # way it does for a button press.
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


@hardware_bp.route('/device/concentration', methods=['GET'])
def device_concentration():
    """The units the device's concentration screen offers (CONC?).

    The current value is not here — it is `conc`/`cunit` in /device/state, which
    the panel is already polling. This answers the one thing the state does not
    carry, and the client asks for it once per connection.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        return jsonify({'status': 'success', 'units': device_link.link.concentration_units()})
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502


@hardware_bp.route('/device/concentration', methods=['POST'])
@validate_json({'value': (float, None, False), 'unit': (str, None, False)})
def device_concentration_set(validated_data):
    """Set the device's concentration (CONC:).

    A null/absent value means **Unknown**, which is a real state on that screen
    rather than a missing field. Negatives are refused here as well as on the
    device: the keypad clamps at zero, so no operator can reach one.
    """
    if _session_is_running():
        return _controller_busy_response()
    value = validated_data['value']
    unit = (validated_data['unit'] or '').strip() or None
    if value is not None and value < 0:
        return jsonify({'status': 'failure', 'message': 'Concentration cannot be negative'}), 400
    try:
        device_link.link.set_concentration(value, unit)
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


@hardware_bp.route('/device/disconnect', methods=['POST'])
def device_disconnect():
    """Release the serial port now (the controller's connection switch).

    The idle reaper drops the port after 30 s of quiet anyway, but a user who
    turns the connection off is usually about to hand the port to something else
    — a firmware update, a serial monitor — and waiting out the reaper looks like
    the switch did nothing. Safe to call when nothing is open: close() no-ops.
    """
    device_link.link.close()
    return jsonify({'status': 'success'})


@hardware_bp.route('/device/timing', methods=['GET'])
def device_timing():
    """The units the device's settings screen offers (TIMING?).

    The values themselves are `timeout`/`timeoutunit`/`interval`/`intervalunit`
    in /device/state, which the panel already polls.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        return jsonify({'status': 'success', 'units': device_link.link.timing_units()})
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502


@hardware_bp.route('/device/timing', methods=['POST'])
@validate_json({
    'timeout_value': (float, None, False),
    'timeout_unit': (str, None, False),
    'interval_value': (float, None, True),
    'interval_unit': (str, None, True),
})
def device_timing_set(validated_data):
    """Set the device's timeout and transmission interval (TIMING:).

    A null timeout means **no timeout** — a real setting rather than a missing
    field: the run then goes until it is stopped. The device is the authority on
    whether the pair is legal (the timeout has to outlast the interval), and its
    refusal carries the reason.
    """
    if _session_is_running():
        return _controller_busy_response()
    timeout_value = validated_data['timeout_value']
    interval_value = validated_data['interval_value']
    if timeout_value is not None and timeout_value < 0:
        return jsonify({'status': 'failure', 'message': 'Timeout cannot be negative'}), 400
    if interval_value <= 0:
        return jsonify({'status': 'failure', 'message': 'Interval must be more than zero'}), 400
    if timeout_value is not None and not validated_data['timeout_unit']:
        return jsonify({'status': 'failure', 'message': 'A timeout needs a unit'}), 400
    try:
        device_link.link.set_timing(
            timeout_value, validated_data['timeout_unit'],
            interval_value, validated_data['interval_unit'])
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    try:
        return jsonify({'status': 'success', 'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'state': None})


def _saved_calibration():
    """The factors configuration.json holds, typed, if the drive is reachable.

    Reported beside the running factors so the panel can say whether a
    calibration will survive a power cycle. Never raises, for the reason
    _saved_setting gives.
    """
    root, saved = _saved_setting(device_config.FACTOR_KEY)
    if not isinstance(saved, list):
        return root, None
    try:
        return root, [float(factor) for factor in saved]
    except (TypeError, ValueError):
        return root, None


@hardware_bp.route('/device/calibration', methods=['GET'])
def device_calibration():
    """The device's raw count factors, one per sensing element (CALIB?).

    A separate route from /device/state even though the state carries `rcf`,
    because the two are different views: `rcf` is the active channels in stream
    order, for display beside the gains, while this is the whole array — the
    shape configuration.json holds and the shape a write back to the device has
    to take. On the multi-channel build that array is indexed by multiplexer
    channel; on the single-measurement builds it is one entry per spectral
    channel or per sensor. `tags` names them either way.

    Answers with what is *saved* as well as what is running, so the panel can
    tell the operator whether the calibration in force will survive the next
    power cycle. They differ constantly and the difference matters: the device
    cannot write that file, so every pass is runtime-only until it is saved.
    """
    if _session_is_running():
        return _controller_busy_response()
    try:
        factors = device_link.link.calibration_factors()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502
    # What the device calls each entry, so the panel can label one field per
    # factor. Never fatal: a firmware without the command still has factors, and
    # numbered fields are worse than named ones but not wrong.
    try:
        tags = device_link.link.calibration_tags()
    except device_link.DeviceLinkError:
        tags = None
    drive, saved = _saved_calibration()
    return jsonify({'status': 'success', 'factors': factors, 'tags': tags,
                    'saved': saved, 'drive': drive})


@hardware_bp.route('/device/calibration/save', methods=['POST'])
def device_calibration_save():
    """Write the device's current factors into its own configuration.json.

    The factors come from the device (CALIB?), not from the browser: what gets
    saved must be what is actually in force, including a calibration the
    operator just ran on the keypad. A cached array would save a snapshot of
    whatever the panel last happened to see.

    Writing the file makes CircuitPython reload, so the device restarts and
    comes back running these factors — which is exactly what "save" should mean
    here, and also why this is refused mid-session like every other control.
    The serial link is dropped afterwards so the next command reconnects to the
    rebooted device rather than through a handle to the one that went away.
    """
    if _session_is_running():
        return _controller_busy_response()

    root = device_config.find_device_root()
    if root is None:
        return jsonify({
            'status': 'failure',
            'message': ('No CIRCUITPY drive found. Connect the colorimeter by USB and let '
                        'the drive mount, then try again.'),
        }), 404

    try:
        factors = device_link.link.calibration_factors()
    except device_link.DeviceLinkError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 502

    try:
        path = device_config.write_raw_count_factor(root, factors)
    except device_config.DeviceConfigError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

    # The board is rebooting on account of that write; the open port is about to
    # become a handle to a device that is not there.
    device_link.link.close()
    return jsonify({'status': 'success', 'factors': factors, 'saved': factors,
                    'drive': root, 'path': path})


@hardware_bp.route('/device/calibration', methods=['POST'])
@validate_json({'factors': (list, None, False), 'run': (bool, None, False),
                'clear': (bool, None, False)})
def device_calibration_set(validated_data):
    """Run a calibration pass, or write factors outright (CALIBRATE / CALIB:).

    Three requests through one route, because they are three ways of setting the
    same array:

      {"run": true}        measure the channels now and apply what comes out
      {"factors": [...]}   write these factors
      {"clear": true}      clear every factor back to 1.0

    The clear is spelled out rather than being what an empty body happens to do.
    It throws away a calibration the operator may have spent a bench session on,
    and a request that says nothing should do nothing — an empty body is what a
    dropped field or a malformed client sends, not a decision to discard.

    Runtime only. The device cannot write its own configuration.json (see
    /device/channels), so a calibration the operator wants to keep has to be
    copied into the file on the CIRCUITPY drive — the response carries the
    factors in exactly the order that file wants them.
    """
    if _session_is_running():
        return _controller_busy_response()

    factors = validated_data['factors']
    if validated_data['run']:
        try:
            factors = device_link.link.run_calibration()
        except device_link.DeviceLinkError as e:
            # The device's refusals name the channel and the cause ("channel 2
            # reading zero: LED off?"), which is the whole value of showing them.
            return jsonify({'status': 'failure', 'message': str(e)}), 502
    else:
        if factors is not None:
            try:
                factors = [float(factor) for factor in factors]
            except (TypeError, ValueError):
                return jsonify({'status': 'failure', 'message': 'Factors must be numbers'}), 400
            if not factors:
                return jsonify({'status': 'failure', 'message': 'Send at least one factor'}), 400
        elif not validated_data['clear']:
            # No factors, no run, no clear: nothing was asked for. Falling through
            # here would send CALIB:reset and discard the calibration.
            return jsonify({
                'status': 'failure',
                'message': 'Send factors, run:true, or clear:true',
            }), 400
        try:
            device_link.link.set_calibration_factors(factors)
        except device_link.DeviceLinkError as e:
            return jsonify({'status': 'failure', 'message': str(e)}), 502
        try:
            factors = device_link.link.calibration_factors()
        except device_link.DeviceLinkError:
            factors = None

    try:
        return jsonify({'status': 'success', 'factors': factors,
                        'state': device_link.link.state()})
    except device_link.DeviceLinkError:
        return jsonify({'status': 'success', 'factors': factors, 'state': None})


@hardware_bp.route('/stream_session', methods=['GET'])
def stream_session():
    """SSE tail of the running session: new CSV rows + new log text, pushed.

    Replaces the client's 500 ms ``/get_data`` chart poll and 2 s ``/get_logs``
    poll for the duration of a run (see src/live_stream.py). Deliberately does
    NOT own the run-end transition: it emits an ``end`` event and closes, and the
    client calls /check_status, which remains the single place that decides why a
    session finished and clears the log.
    """
    return Response(
        stream_with_context(live_stream.iter_session_events()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            # Belt-and-braces against a buffering intermediary; the app is local,
            # but a user-configured proxy would otherwise hold every frame.
            'X-Accel-Buffering': 'no',
        },
    )


def _running_status():
    """The 'running' answer. `paused`, `manual` and `interval_sec` let a
    reloaded page resync its controls with a run already going: Pause/Resume
    for a timed run, Measure now for a manual one, and the session clock's
    interval. The last two are read off the logger's own command line."""
    raw = getattr(state.process, 'args', None)
    args = list(raw) if isinstance(raw, (list, tuple)) else []
    interval = None
    if '--interval-sec' in args:
        try:
            interval = float(args[args.index('--interval-sec') + 1])
        except (IndexError, ValueError):
            interval = None
    return jsonify({'status': 'running', 'message': 'Script is running',
                    'paused': state.reading_paused, 'manual': '--manual' in args,
                    'interval_sec': interval})


@hardware_bp.route('/check_status', methods=['GET'])
def check_status():
    if state.process is None:
        return jsonify({'status': 'not_running', 'message': 'No process running'})

    # `?peek=1` is the page-load probe: it answers "is a run going" and changes
    # nothing. The plain call below is the one that ends a finished run
    # (clears the process and the log) and reports why — a reloading tab must
    # not consume that answer before the tab that started the run sees it.
    if request.args.get('peek') == '1':
        if state.process.poll() is None:
            return _running_status()
        return jsonify({'status': 'ending', 'message': 'Session is ending'})

    error = check_log_for_errors(state.log_file)
    if error:
        state.process = None
        state.reading_paused = False
        clear_logs()
        if error == "device_not_found":
            return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected during runtime.'})
        return jsonify({'status': 'failure', 'message': 'Device communication error detected during runtime.'})

    if state.process.poll() is None:
        return _running_status()

    # The logger exited: a clean end-of-session (device timeout / user stop)
    # always logs "New session started"; a handshake failure does not.
    started = check_log_for_session_start(state.log_file)
    # Why it ended (read BEFORE clear_logs) so the UI can announce a device-button
    # stop distinctly from a timeout.
    reason = check_log_for_end_reason(state.log_file)
    state.process = None
    state.reading_paused = False
    # Session is over — reset the log file here, the authoritative server-side
    # completion point. The frontend only clears logs via terminateScript()
    # (the fetchLogs/terminate path); when this status poll detects completion
    # first, that path never runs, so without this the log file is left dirty.
    clear_logs()
    if started:
        # A disconnection is not a clean finish: the data captured before the
        # device vanished is real and saved, but the series is shorter than the
        # operator asked for, and saying "completed" would hide that.
        if reason == 'disconnected':
            return jsonify({
                'status': 'warning',
                'message': ('The device disconnected during the reading and did not come back. '
                            'The rows captured before it dropped have been saved.'),
            })
        message = {
            'stopped': 'Session stopped manually on the device.',
            'timeout': 'Session ended due to timeout.',
        }.get(reason, 'Reading session completed.')
        return jsonify({'status': 'success', 'message': message})
    return jsonify({'status': 'failure', 'message': 'Reading session ended before any data was captured.'})


@hardware_bp.route('/terminate_script', methods=['POST'])
def terminate_script():
    state.reading_paused = False
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No process running'})

    os_name = platform.system().lower()
    try:
        if "window" in os_name:
            # No POSIX process-group signalling: terminate the logger; closing
            # the port drops DTR, which the firmware detects to stop talking.
            state.process.terminate()
            try:
                state.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                state.process.kill()
            state.process = None
            return jsonify({'status': 'success'})

        # POSIX: SIGINT first lets the CDC logger's handler run — it sends "0"
        # to the device and closes the port before exiting. Escalate if it hangs.
        pgid = os.getpgid(state.process.pid)
        os.killpg(pgid, signal.SIGINT)
        try:
            state.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGTERM)
            try:
                state.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
        state.process = None
        return jsonify({'status': 'success'})
    except ProcessLookupError:
        state.process = None
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})


@hardware_bp.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(state.log_file):
        with open(state.log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})
