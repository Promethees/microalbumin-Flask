"""Virtual controller: STATE parsing, the link's command handling, and the
routes' one-owner rule (src/device_link.py, routes/hardware_routes.py)."""

import json
import time

import pytest
from unittest.mock import MagicMock, patch

import device_link
import device_config
import state


# ── STATE parsing ────────────────────────────────────────────────────────────

SAMPLE_STATE = (
    "STATE fw=0.1.0;caps=btn,state,channels;mode=MEASURE;meas=Absorbance;units=;"
    "vals=0.412,OVFL;blanked=1;needsblank=1;talking=0;paused=0;transport=;"
    "chans=0,3;maxchan=4;gains=high,high;itimes=600ms,600ms;sel=;menupos=0;"
    "menuitem=Absorbance;conc=;cunit=ng/µL;timeout=20;timeoutunit=min;"
    "interval=1;intervalunit=min;bat=3.91;batpct=63"
)


def test_parse_state_types_the_known_fields():
    parsed = device_link.parse_state(SAMPLE_STATE)
    assert parsed['mode'] == 'MEASURE'
    assert parsed['meas'] == 'Absorbance'
    assert parsed['chans'] == [0, 3]
    assert parsed['maxchan'] == 4
    assert parsed['blanked'] == 1
    assert parsed['caps'] == ['btn', 'state', 'channels']
    assert parsed['gains'] == ['high', 'high']
    assert parsed['bat'] == '3.91'
    assert parsed['batpct'] == 63


def test_parse_state_battery_percent_empty_before_first_reading():
    """The firmware sends batpct= until the battery filter has a reading."""
    assert device_link.parse_state("STATE bat=0.00;batpct=")['batpct'] is None


def test_parse_state_older_firmware_has_no_battery_percent():
    assert 'batpct' not in device_link.parse_state("STATE bat=3.91")


def test_parse_state_keeps_overflow_sentinel_verbatim():
    """OVFL is not a number and must survive as text — the readout shows it."""
    assert device_link.parse_state(SAMPLE_STATE)['vals'] == ['0.412', 'OVFL']


def test_parse_state_empty_fields_do_not_become_zero():
    """"" means "not applicable" (no sensor selected, no concentration set)."""
    parsed = device_link.parse_state(SAMPLE_STATE)
    assert parsed['sel'] is None
    assert parsed['conc'] == ''
    assert parsed['units'] == ''


def test_parse_state_tolerates_a_line_without_the_prefix():
    parsed = device_link.parse_state("mode=MENU;menupos=3")
    assert parsed['mode'] == 'MENU'
    assert parsed['menupos'] == 3


# ── DeviceLink command handling ──────────────────────────────────────────────

class FakeLink(device_link.DeviceLink):
    """A link whose exchange is scripted, so the operations can be tested
    without a serial port. Only the transport is faked — the reply handling
    under test is the real thing."""

    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)
        self.sent = []

    def command(self, command, matches):
        self.sent.append(command)
        if not self.replies:
            raise device_link.DeviceLinkError("no reply")
        return self.replies.pop(0)


def test_press_sends_the_button_name():
    link = FakeLink(["ACK_BTN"])
    assert link.press('menu') is True
    assert link.sent == ['BTN:menu']


def test_press_refused_raises():
    link = FakeLink(["ERR_BTN"])
    with pytest.raises(device_link.DeviceLinkError):
        link.press('left')


def test_press_on_firmware_without_the_command_says_so():
    """Firmware predating the controller answers ERR_UNKNOWN to any new token."""
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.press('menu')
    assert 'firmware' in str(excinfo.value)


def test_set_channels_formats_the_payload():
    link = FakeLink(["ACK_CHANNELS"])
    assert link.set_channels([0, 3]) is True
    assert link.sent == ['CHANNELS:0,3']


def test_set_channels_surfaces_the_device_reason():
    """The reason names the channel with no sensor — the only actionable part."""
    link = FakeLink(["ERR_CHANNELS sensor on mux channel 2 missing? nack"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_channels([0, 2])
    assert 'mux channel 2' in str(excinfo.value)


def test_state_parses_the_reply():
    link = FakeLink([SAMPLE_STATE])
    assert link.state()['chans'] == [0, 3]


def test_menu_items_splits_the_list():
    link = FakeLink(["MENUITEMS Absorbance,Transmittance,glucose,Settings"])
    assert link.menu_items() == ['Absorbance', 'Transmittance', 'glucose', 'Settings']
    assert link.sent == ['MENU?']


def test_menu_items_keeps_an_empty_entry():
    """The index is the address MENU: takes, so a blank name may not be dropped
    — doing so would shift every entry after it onto the wrong screen."""
    link = FakeLink(["MENUITEMS Absorbance,,Settings"])
    assert link.menu_items() == ['Absorbance', '', 'Settings']


def test_menu_items_on_an_empty_menu():
    link = FakeLink(["MENUITEMS "])
    assert link.menu_items() == []


def test_menu_items_on_firmware_without_the_command_says_so():
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.menu_items()
    assert 'firmware' in str(excinfo.value)


def test_select_menu_sends_the_index():
    link = FakeLink(["ACK_MENU"])
    assert link.select_menu(3) is True
    assert link.sent == ['MENU:3']


def test_concentration_units_splits_the_list():
    link = FakeLink(["CONCUNITS ng/µL,nM,%,CFU,OD600"])
    assert link.concentration_units() == ['ng/µL', 'nM', '%', 'CFU', 'OD600']
    assert link.sent == ['CONC?']


def test_set_concentration_sends_a_whole_number_without_a_decimal():
    """The device prints the value verbatim and its keypad only makes whole
    numbers, so 12.0 must go out as "12"."""
    link = FakeLink(["ACK_CONC"])
    link.set_concentration(12.0, 'nM')
    assert link.sent == ['CONC:12,nM']


def test_set_concentration_keeps_a_fraction():
    link = FakeLink(["ACK_CONC"])
    link.set_concentration(2.5)
    assert link.sent == ['CONC:2.5']


def test_set_concentration_none_is_unknown():
    """Unknown is a value on that screen, not a missing one."""
    link = FakeLink(["ACK_CONC"])
    link.set_concentration(None)
    assert link.sent == ['CONC:none']


def test_set_concentration_surfaces_the_device_reason():
    link = FakeLink(["ERR_CONC unknown unit"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_concentration(1, 'mM')
    assert 'unknown unit' in str(excinfo.value)


# ── raw count calibration ────────────────────────────────────────────────────

def test_calibration_factors_parses_the_array():
    link = FakeLink(["CALFACTORS 1.0000,1.0217,0.9834,1.0000"])
    assert link.calibration_factors() == [1.0, 1.0217, 0.9834, 1.0]
    assert link.sent == ['CALIB?']


def test_run_calibration_answers_with_what_it_derived():
    """One round trip: the device measures, applies and reports, so there is no
    window where the host shows factors the device is not using."""
    link = FakeLink(["CALFACTORS 1.2500,1.0000,1.0000,0.8333"])
    assert link.run_calibration() == [1.25, 1.0, 1.0, 0.8333]
    assert link.sent == ['CALIBRATE']


def test_run_calibration_surfaces_the_device_reason():
    """The reason names the holder to look at — the actionable part."""
    link = FakeLink(["ERR_CALIB channel 2 reading zero: LED off?"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.run_calibration()
    assert 'channel 2' in str(excinfo.value)


def test_calibration_on_firmware_without_the_command_says_so():
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.calibration_factors()
    assert 'firmware' in str(excinfo.value)


def test_set_calibration_factors_formats_the_payload():
    link = FakeLink(["ACK_CALIB"])
    assert link.set_calibration_factors([1.0, 1.0217, 0.9834, 1.0]) is True
    assert link.sent == ['CALIB:1,1.0217,0.9834,1']


def test_set_calibration_factors_none_clears_them():
    link = FakeLink(["ACK_CALIB"])
    link.set_calibration_factors(None)
    assert link.sent == ['CALIB:reset']


def test_set_calibration_factors_surfaces_the_device_reason():
    link = FakeLink(["ERR_CALIB factor 50 outside 0.1..10.0"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_calibration_factors([1.0, 50.0])
    assert 'outside' in str(excinfo.value)


def test_calibration_tags_names_the_entries():
    """The panel labels one field per factor from the device's own names, so a
    build the host has never heard of still comes up labelled."""
    link = FakeLink(["CALTAGS Sen 90,Sen 180"])
    assert link.calibration_tags() == ['Sen 90', 'Sen 180']
    assert link.sent == ['CALIBTAGS?']


def test_calibration_tags_on_firmware_without_the_command_are_none():
    """Not an error: that firmware still has factors, and the fields fall back
    to being numbered."""
    link = FakeLink(["ERR_UNKNOWN"])
    assert link.calibration_tags() is None


def test_parse_state_types_the_raw_count_factors():
    """rcf rides beside gains/itimes: one entry per ACTIVE channel, in order."""
    parsed = device_link.parse_state(SAMPLE_STATE + ";rcf=1.000,0.983")
    assert parsed['rcf'] == [1.0, 0.983]


def test_parse_state_without_rcf_on_older_firmware():
    assert 'rcf' not in device_link.parse_state(SAMPLE_STATE)


def test_parse_state_types_the_factor_revision():
    """rcfrev is how a keypad-side calibration reaches the host: rcf shows only
    the active channels, so a change elsewhere in the array is invisible."""
    parsed = device_link.parse_state(SAMPLE_STATE + ";rcfrev=7")
    assert parsed['rcfrev'] == 7


# ── configuration.json on the device's drive ─────────────────────────────────

BOOT_OUT = "Adafruit CircuitPython 9.2.7 on 2025-04-01; Adafruit Pybadge with samd51j19"

CONFIG_WITH_FACTORS = """{
  "active_channels" : [0, 2, 3],
  "raw_count_factor" : [1.0000, 1.0000, 1.0000, 1.0000],
  "gain_sensor_0"     : "med",
  "precision" : 3
}
"""

CONFIG_WITHOUT_FACTORS = """{
  "active_channels" : [0, 2, 3],
  "gain_sensor_0"     : "med",
  "precision" : 3
}
"""


@pytest.fixture
def drive(tmp_path):
    (tmp_path / device_config.BOOT_OUT_FILE).write_text(BOOT_OUT)
    (tmp_path / device_config.CONFIGURATION_FILE).write_text(CONFIG_WITH_FACTORS)
    return tmp_path


def test_drive_is_identified_by_boot_out(drive, tmp_path_factory):
    assert device_config.is_device_root(str(drive))
    # A directory that merely exists is not a colorimeter. This is the check
    # standing between "save a calibration" and "overwrite a stranger's file".
    stranger = tmp_path_factory.mktemp('stranger')
    assert not device_config.is_device_root(str(stranger))


def test_write_replaces_only_the_factor_line(drive):
    device_config.write_raw_count_factor(str(drive), [1.0, 1.0, 0.9834, 1.0217])
    text = (drive / device_config.CONFIGURATION_FILE).read_text()
    assert '"raw_count_factor" : [1.0000, 1.0000, 0.9834, 1.0217]' in text
    # Everything else byte-for-byte: this file is hand-edited, and a round trip
    # through json.dumps would reformat all of it to change one line.
    before = [l for l in CONFIG_WITH_FACTORS.splitlines() if 'raw_count_factor' not in l]
    after = [l for l in text.splitlines() if 'raw_count_factor' not in l]
    assert before == after


def test_write_inserts_the_key_when_absent(drive):
    (drive / device_config.CONFIGURATION_FILE).write_text(CONFIG_WITHOUT_FACTORS)
    device_config.write_raw_count_factor(str(drive), [1.0, 1.0, 0.5, 1.0])
    data = device_config.read_configuration(str(drive))
    assert data['raw_count_factor'] == [1.0, 1.0, 0.5, 1.0]
    assert data['precision'] == 3


def test_write_inserts_the_key_after_an_anchor_that_ends_its_object(drive):
    """The anchor carries no comma when it is the last key of its object.

    Inserting after it used to emit the anchor's missing comma as a trailing one
    on the new key, so the file came out unparseable and the write was refused —
    a Save that could never succeed on a configuration.json whose last key is
    active_channels, which is where a board with no calibration yet puts it.
    """
    (drive / device_config.CONFIGURATION_FILE).write_text(
        '{\n  "precision" : 3,\n  "active_channels" : [0, 2, 3]\n}\n')
    device_config.write_raw_count_factor(str(drive), [1.0, 0.5, 1.0])
    data = device_config.read_configuration(str(drive))
    assert data['raw_count_factor'] == [1.0, 0.5, 1.0]
    assert data['active_channels'] == [0, 2, 3]
    assert data['precision'] == 3


def test_write_replaces_a_value_that_spans_more_than_its_line(drive):
    """The value was described by a pattern that stopped at the first `]`, so a
    nested or wrapped array came out half-replaced and the write guard rejected
    the result — a Save that failed with a parse error on a good file."""
    for original in (
            '{\n  "raw_count_factor" : [[1, 2], [3, 4]],\n  "precision" : 3\n}\n',
            '{\n  "raw_count_factor" : [\n    1.0,\n    2.0\n  ],\n  "precision" : 3\n}\n',
    ):
        (drive / device_config.CONFIGURATION_FILE).write_text(original)
        device_config.write_raw_count_factor(str(drive), [0.5, 1.0])
        data = device_config.read_configuration(str(drive))
        assert data['raw_count_factor'] == [0.5, 1.0]
        assert data['precision'] == 3


def test_write_is_not_fooled_by_a_bracket_inside_a_string(drive):
    """Brackets, commas and escaped quotes inside a string must not end the
    value: the key after it would be swallowed into the replacement."""
    (drive / device_config.CONFIGURATION_FILE).write_text(
        '{\n  "channel" : "A],B",\n  "precision" : 3\n}\n')
    device_config.write_uv_channel(str(drive), 'UVB')
    data = device_config.read_configuration(str(drive))
    assert data['channel'] == 'UVB'
    assert data['precision'] == 3


def test_write_refuses_a_factor_that_would_round_away(drive):
    """Four decimals is the file's precision, so 0.00004 lands as 0.0000 — a
    channel silenced rather than corrected, with nothing on screen saying so."""
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_raw_count_factor(str(drive), [1.0, 0.00004])
    # Unchanged: the refusal happens before anything is written.
    assert device_config.read_configuration(str(drive))['raw_count_factor'] == [1.0] * 4
    # The precision the device actually works in still goes through.
    device_config.write_raw_count_factor(str(drive), [1.0, 0.1234, 1.0, 1.0])
    assert device_config.read_configuration(str(drive))['raw_count_factor'][1] == 0.1234


def test_windows_drive_probe_skips_the_floppy_letters():
    """A and B are never assigned to removable USB storage, and probing them
    blocks on a mapped floppy or a dead network drive parked there."""
    with patch.object(device_config.platform, 'system', return_value='Windows'):
        roots = device_config.candidate_roots()
    assert roots[0] == 'C:\\'
    assert not any(root.startswith(('A:', 'B:')) for root in roots)
    assert len(roots) == 24


def test_darwin_drive_probe_is_the_one_volume_path():
    with patch.object(device_config.platform, 'system', return_value='Darwin'):
        assert device_config.candidate_roots() == ['/Volumes/CIRCUITPY']


def test_write_refuses_a_directory_that_is_not_a_board(tmp_path):
    (tmp_path / device_config.CONFIGURATION_FILE).write_text(CONFIG_WITH_FACTORS)
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_raw_count_factor(str(tmp_path), [1.0])


def test_write_leaves_the_file_alone_when_the_result_would_not_parse(drive):
    """The device reloads the instant this file changes, so invalid JSON is a
    device sitting on an error screen — checked before the write, not after."""
    broken = '{ "active_channels" : [0, 3],\n  "raw_count_factor" : [1.0],\n'
    (drive / device_config.CONFIGURATION_FILE).write_text(broken)
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_raw_count_factor(str(drive), [1.0, 1.0, 1.0, 1.0])
    assert (drive / device_config.CONFIGURATION_FILE).read_text() == broken


def test_save_route_writes_what_the_device_reports(client, drive):
    """Not what the browser cached: a calibration run on the keypad must be
    what gets saved."""
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'calibration_factors',
                      return_value=[1.0, 1.0, 0.9834, 1.0217]), \
         patch.object(device_link.link, 'close') as close:
        rv = client.post('/device/calibration/save')
    assert rv.status_code == 200
    assert rv.get_json()['saved'] == [1.0, 1.0, 0.9834, 1.0217]
    assert device_config.read_configuration(str(drive))['raw_count_factor'] == \
        [1.0, 1.0, 0.9834, 1.0217]
    # The write reboots the board, so the open handle is to a device that is
    # about to disappear.
    close.assert_called_once()


def test_save_route_404_when_no_drive(client):
    with patch.object(device_config, 'find_device_root', return_value=None):
        rv = client.post('/device/calibration/save')
    assert rv.status_code == 404
    assert 'CIRCUITPY' in rv.get_json()['message']


def test_calibration_route_reports_saved_alongside_running(client, drive):
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'calibration_factors',
                      return_value=[1.0, 1.0, 0.9834, 1.0]):
        rv = client.get('/device/calibration')
    body = rv.get_json()
    assert body['factors'] == [1.0, 1.0, 0.9834, 1.0]
    assert body['saved'] == [1.0, 1.0, 1.0, 1.0]      # the file still has the old ones
    assert body['drive'] == str(drive)


def test_calibration_route_survives_an_absent_drive(client):
    """Plugged in for serial with no volume mounted is an ordinary state, not a
    failed request."""
    with patch.object(device_config, 'find_device_root', return_value=None), \
         patch.object(device_link.link, 'calibration_factors', return_value=[1.0] * 4):
        rv = client.get('/device/calibration')
    assert rv.status_code == 200
    assert rv.get_json()['saved'] is None
    assert rv.get_json()['drive'] is None


def test_concentration_on_firmware_without_the_command_says_so():
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.concentration_units()
    assert 'firmware' in str(excinfo.value)


def test_timing_units_splits_the_list():
    link = FakeLink(["TIMINGUNITS sec,min,hour"])
    assert link.timing_units() == ['sec', 'min', 'hour']
    assert link.sent == ['TIMING?']


def test_set_timing_formats_the_payload():
    link = FakeLink(["ACK_TIMING"])
    link.set_timing(20, 'min', 1, 'min')
    assert link.sent == ['TIMING:20,min,1,min']


def test_set_timing_no_timeout():
    """No timeout is a setting, not a missing field: the run goes until stopped."""
    link = FakeLink(["ACK_TIMING"])
    link.set_timing(None, None, 30, 'sec')
    assert link.sent == ['TIMING:none,,30,sec']


def test_set_timing_surfaces_the_device_reason():
    """The device owns the rule that the timeout must outlast the interval, and
    its wording is the part the operator can act on."""
    link = FakeLink(["ERR_TIMING timeout is not longer than the interval"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_timing(1, 'min', 2, 'min')
    assert 'not longer than' in str(excinfo.value)


def test_select_menu_surfaces_the_device_reason():
    link = FakeLink(["ERR_MENU out of range"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.select_menu(99)
    assert 'out of range' in str(excinfo.value)


def test_reaper_frees_its_slot_when_it_exits(monkeypatch):
    """The reaper drops the port after IDLE_TIMEOUT so a firmware update or a
    serial monitor can claim it. It ends itself when it does, and the next
    _open_locked() starts a fresh one — which only works if the slot is empty.

    _start_reaper used to ask is_alive(), which stays True for the moment a
    returning thread takes to unwind: an open landing in that window saw a live
    reaper that would never loop again and declined to replace it, leaving the
    new connection unwatched until something called close().
    """
    monkeypatch.setattr(device_link, 'REAP_INTERVAL', 0.01)
    link = device_link.DeviceLink()
    port = MagicMock()
    port.is_open = True
    link._serial = port
    link._last_used = 0.0  # monotonic() is far past this, so already idle

    link._start_reaper()
    reaper = link._reaper
    reaper.join(timeout=5)

    assert not reaper.is_alive()
    port.close.assert_called_once()
    assert link._reaper is None, "a finished reaper must not hold the slot"

    # And the slot being free is what lets the next connection get a reaper.
    link._serial = MagicMock()
    link._start_reaper()
    assert link._reaper is not None and link._reaper is not reaper
    link._serial = None  # let it exit


def test_reaper_is_not_started_twice_for_one_connection(monkeypatch):
    """The guard still has to hold for a reaper that is genuinely running,
    or every command would spawn another thread onto the same port."""
    monkeypatch.setattr(device_link, 'REAP_INTERVAL', 30)
    link = device_link.DeviceLink()
    link._serial = MagicMock()
    link._last_used = time.monotonic()
    link._start_reaper()
    first = link._reaper
    link._start_reaper()
    assert link._reaper is first


def test_state_on_firmware_without_the_controller_says_so():
    """STATE? gets ERR_UNKNOWN from firmware predating the controller, same as
    every other new token."""
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.state()
    assert 'firmware' in str(excinfo.value)


def test_state_matcher_recognises_the_refusals():
    """FakeLink answers whatever the predicate says, so the predicate is checked
    directly here — it is the part that decides between a prompt error and a
    stall. An unmatched ERR_UNKNOWN costs REPLY_TIMEOUT, then the reconnect, then
    REPLY_TIMEOUT again, on a command polled every 1.5 s."""
    link = device_link.DeviceLink()
    captured = []

    def fake_command(command, matches):
        captured.append(matches)
        return "STATE mode=MENU"

    with patch.object(link, 'command', side_effect=fake_command):
        link.state()
    matches = captured[0]
    assert matches("STATE mode=MENU")
    assert matches("ERR_STATE")
    assert matches("ERR_UNKNOWN")


def test_exchange_ignores_lines_that_are_not_the_reply():
    """A banner or the tail of an earlier session must not pass for an answer."""
    link = device_link.DeviceLink()
    port = MagicMock()
    reader = MagicMock()
    reader.read_lines.side_effect = [["Auto-reload is on."], ["ACK_BTN"]]
    link._serial = port
    link._reader = reader
    assert link._exchange_locked("BTN:menu", lambda line: line == "ACK_BTN") == "ACK_BTN"


def test_command_retries_once_on_a_dead_port():
    """A device unplugged and replugged leaves a handle that never answers;
    one retry on a fresh connection is what makes the controller recover."""
    link = device_link.DeviceLink()
    calls = []

    def fake_open():
        calls.append('open')
        link._serial = MagicMock()
        link._reader = MagicMock()

    with patch.object(link, '_open_locked', side_effect=fake_open), \
         patch.object(link, '_exchange_locked',
                      side_effect=[device_link.DeviceLinkError('gone'), 'ACK_BTN']):
        assert link.command('BTN:menu', lambda line: True) == 'ACK_BTN'
    assert len(calls) == 2


def test_command_gives_up_after_the_retry():
    link = device_link.DeviceLink()
    with patch.object(link, '_open_locked'), \
         patch.object(link, '_exchange_locked',
                      side_effect=device_link.DeviceLinkError('gone')):
        with pytest.raises(device_link.DeviceLinkError):
            link.command('BTN:menu', lambda line: True)


# ── routes ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from main import app
    app.config['TESTING'] = True
    state.process = None
    with app.test_client() as test_client:
        yield test_client
    state.process = None


def _running_process():
    process = MagicMock()
    process.poll.return_value = None
    return process


def test_state_route_returns_the_parsed_state(client):
    with patch.object(device_link.link, 'state', return_value={'mode': 'MENU'}):
        rv = client.get('/device/state')
    assert rv.status_code == 200
    assert rv.get_json()['state'] == {'mode': 'MENU'}


def test_state_route_503_when_no_device(client):
    with patch.object(device_link.link, 'state',
                      side_effect=device_link.DeviceLinkError('not found')):
        rv = client.get('/device/state')
    assert rv.status_code == 503
    assert rv.get_json()['status'] == 'device_not_found'


def test_controller_is_unavailable_during_a_session(client):
    """The port has one owner: while the logger holds it, every controller route
    refuses rather than opening a second handle on the same device."""
    state.process = _running_process()
    for call in (lambda: client.get('/device/state'),
                 lambda: client.post('/device/button', json={'button': 'menu'}),
                 lambda: client.post('/device/channels', json={'channels': [0]}),
                 lambda: client.get('/device/menu'),
                 lambda: client.post('/device/menu', json={'index': 0}),
                 lambda: client.get('/device/concentration'),
                 lambda: client.post('/device/concentration', json={'value': 1}),
                 lambda: client.get('/device/timing'),
                 lambda: client.post('/device/timing',
                                     json={'interval_value': 1, 'interval_unit': 'min'}),
                 lambda: client.get('/device/calibration'),
                 lambda: client.post('/device/calibration', json={'run': True}),
                 lambda: client.get('/device/uvchannel'),
                 lambda: client.post('/device/uvchannel', json={'channel': 'UVB'})):
        rv = call()
        assert rv.status_code == 409
        assert rv.get_json()['status'] == 'busy'


def test_button_route_returns_the_new_state(client):
    with patch.object(device_link.link, 'press', return_value=True) as press, \
         patch.object(device_link.link, 'state', return_value={'mode': 'MENU'}):
        rv = client.post('/device/button', json={'button': 'menu'})
    press.assert_called_once_with('menu')
    assert rv.get_json()['state'] == {'mode': 'MENU'}


def test_button_route_lowercases_the_name(client):
    with patch.object(device_link.link, 'press', return_value=True) as press, \
         patch.object(device_link.link, 'state', return_value={}):
        client.post('/device/button', json={'button': '  MENU '})
    press.assert_called_once_with('menu')


def test_button_route_502_when_the_device_refuses(client):
    with patch.object(device_link.link, 'press',
                      side_effect=device_link.DeviceLinkError('refused')):
        rv = client.post('/device/button', json={'button': 'left'})
    assert rv.status_code == 502


def test_channels_route_rejects_an_empty_or_duplicate_set(client):
    assert client.post('/device/channels', json={'channels': []}).status_code == 400
    assert client.post('/device/channels', json={'channels': [1, 1]}).status_code == 400


def test_channels_route_rejects_non_numbers(client):
    rv = client.post('/device/channels', json={'channels': ['a']})
    assert rv.status_code == 400


def test_channels_route_applies_the_set(client):
    with patch.object(device_link.link, 'set_channels', return_value=True) as apply, \
         patch.object(device_link.link, 'state', return_value={'chans': [0, 1]}):
        rv = client.post('/device/channels', json={'channels': [0, 1]})
    apply.assert_called_once_with([0, 1])
    assert rv.get_json()['state']['chans'] == [0, 1]


def test_menu_route_returns_the_items(client):
    with patch.object(device_link.link, 'menu_items', return_value=['Absorbance', 'Settings']):
        rv = client.get('/device/menu')
    assert rv.status_code == 200
    assert rv.get_json()['items'] == ['Absorbance', 'Settings']


def test_menu_route_502_when_the_device_cannot_list_it(client):
    with patch.object(device_link.link, 'menu_items',
                      side_effect=device_link.DeviceLinkError('no menu')):
        rv = client.get('/device/menu')
    assert rv.status_code == 502


def test_menu_route_opens_an_entry_and_returns_the_new_state(client):
    with patch.object(device_link.link, 'select_menu', return_value=True) as select, \
         patch.object(device_link.link, 'state', return_value={'mode': 'MEASURE'}):
        rv = client.post('/device/menu', json={'index': 2})
    select.assert_called_once_with(2)
    assert rv.get_json()['state'] == {'mode': 'MEASURE'}


def test_menu_route_rejects_a_negative_index(client):
    assert client.post('/device/menu', json={'index': -1}).status_code == 400


def test_menu_route_accepts_index_zero(client):
    """0 is a real entry — the first one — and must not read as a missing field."""
    with patch.object(device_link.link, 'select_menu', return_value=True) as select, \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/menu', json={'index': 0})
    assert rv.status_code == 200
    select.assert_called_once_with(0)


def test_concentration_route_returns_the_units(client):
    with patch.object(device_link.link, 'concentration_units', return_value=['nM', '%']):
        rv = client.get('/device/concentration')
    assert rv.status_code == 200
    assert rv.get_json()['units'] == ['nM', '%']


def test_concentration_route_sets_value_and_unit(client):
    with patch.object(device_link.link, 'set_concentration', return_value=True) as apply, \
         patch.object(device_link.link, 'state', return_value={'conc': '250'}):
        rv = client.post('/device/concentration', json={'value': 250, 'unit': 'nM'})
    apply.assert_called_once_with(250.0, 'nM')
    assert rv.get_json()['state']['conc'] == '250'


def test_concentration_route_null_value_is_unknown(client):
    """A null value is Unknown — a real state on that screen, not a bad field."""
    with patch.object(device_link.link, 'set_concentration', return_value=True) as apply, \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/concentration', json={'value': None, 'unit': 'nM'})
    assert rv.status_code == 200
    apply.assert_called_once_with(None, 'nM')


def test_concentration_route_rejects_a_negative(client):
    """The keypad clamps at zero, so no operator can reach a negative."""
    rv = client.post('/device/concentration', json={'value': -1})
    assert rv.status_code == 400


def test_concentration_route_502_when_the_device_refuses(client):
    with patch.object(device_link.link, 'set_concentration',
                      side_effect=device_link.DeviceLinkError('unknown unit')):
        rv = client.post('/device/concentration', json={'value': 1, 'unit': 'mM'})
    assert rv.status_code == 502


def test_timing_route_returns_the_units(client):
    with patch.object(device_link.link, 'timing_units', return_value=['sec', 'min', 'hour']):
        rv = client.get('/device/timing')
    assert rv.get_json()['units'] == ['sec', 'min', 'hour']


def test_timing_route_sets_both_values(client):
    with patch.object(device_link.link, 'set_timing', return_value=True) as apply, \
         patch.object(device_link.link, 'state', return_value={'timeout': '20'}):
        rv = client.post('/device/timing', json={
            'timeout_value': 20, 'timeout_unit': 'min',
            'interval_value': 1, 'interval_unit': 'min'})
    apply.assert_called_once_with(20.0, 'min', 1.0, 'min')
    assert rv.get_json()['state']['timeout'] == '20'


def test_timing_route_null_timeout_runs_until_stopped(client):
    with patch.object(device_link.link, 'set_timing', return_value=True) as apply, \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/timing', json={
            'timeout_value': None, 'interval_value': 30, 'interval_unit': 'sec'})
    assert rv.status_code == 200
    apply.assert_called_once_with(None, None, 30.0, 'sec')


def test_timing_route_rejects_a_zero_interval(client):
    rv = client.post('/device/timing', json={'interval_value': 0, 'interval_unit': 'min'})
    assert rv.status_code == 400


def test_timing_route_needs_a_unit_for_a_timeout(client):
    rv = client.post('/device/timing', json={
        'timeout_value': 5, 'interval_value': 1, 'interval_unit': 'min'})
    assert rv.status_code == 400


def test_calibration_route_returns_the_factors(client):
    with patch.object(device_link.link, 'calibration_factors',
                      return_value=[1.0, 1.02, 0.98, 1.0]):
        rv = client.get('/device/calibration')
    assert rv.status_code == 200
    assert rv.get_json()['factors'] == [1.0, 1.02, 0.98, 1.0]


def test_calibration_route_502_when_the_device_cannot_report_them(client):
    with patch.object(device_link.link, 'calibration_factors',
                      side_effect=device_link.DeviceLinkError('no calibration')):
        rv = client.get('/device/calibration')
    assert rv.status_code == 502


def test_calibration_route_runs_a_pass_and_returns_the_result(client):
    with patch.object(device_link.link, 'run_calibration',
                      return_value=[1.25, 1.0, 1.0, 0.8333]) as run, \
         patch.object(device_link.link, 'state', return_value={'rcf': [1.25, 0.8333]}):
        rv = client.post('/device/calibration', json={'run': True})
    run.assert_called_once_with()
    body = rv.get_json()
    assert body['factors'] == [1.25, 1.0, 1.0, 0.8333]
    assert body['state']['rcf'] == [1.25, 0.8333]


def test_calibration_route_shows_why_a_pass_was_refused(client):
    """The device names the holder; a bare failure would send the operator
    looking at the wrong slot."""
    with patch.object(device_link.link, 'run_calibration',
                      side_effect=device_link.DeviceLinkError('channel 2 reading zero: LED off?')):
        rv = client.post('/device/calibration', json={'run': True})
    assert rv.status_code == 502
    assert 'channel 2' in rv.get_json()['message']


def test_calibration_route_writes_explicit_factors(client):
    with patch.object(device_link.link, 'set_calibration_factors', return_value=True) as write, \
         patch.object(device_link.link, 'calibration_factors', return_value=[1.0, 1.02, 1.0, 1.0]), \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/calibration', json={'factors': [1, 1.02, 1, 1]})
    write.assert_called_once_with([1.0, 1.02, 1.0, 1.0])
    assert rv.get_json()['factors'] == [1.0, 1.02, 1.0, 1.0]


def test_calibration_route_clears_the_factors_when_asked(client):
    with patch.object(device_link.link, 'set_calibration_factors', return_value=True) as write, \
         patch.object(device_link.link, 'calibration_factors', return_value=[1.0] * 4), \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/calibration', json={'clear': True})
    write.assert_called_once_with(None)
    assert rv.get_json()['factors'] == [1.0] * 4


def test_calibration_route_refuses_a_body_that_asks_for_nothing(client):
    """An empty body used to mean "discard the calibration".

    It is what a dropped field or a malformed client sends, and the cost of
    reading it as a decision is a bench session's work gone with no way back —
    the device cannot recover the factors it was running. The discard says so
    now, and a request that asks for nothing does nothing.
    """
    with patch.object(device_link.link, 'set_calibration_factors') as write:
        for body in ({}, {'run': False}, {'factors': None}):
            rv = client.post('/device/calibration', json=body)
            assert rv.status_code == 400, body
    write.assert_not_called()


def test_calibration_route_rejects_non_numbers(client):
    rv = client.post('/device/calibration', json={'factors': ['a']})
    assert rv.status_code == 400


def test_calibration_route_rejects_an_empty_factor_list(client):
    """An empty list is not "clear them" — clear:true is — and sending it on
    would be a no-op the operator read as a change."""
    rv = client.post('/device/calibration', json={'factors': []})
    assert rv.status_code == 400


# ── saving a runtime setting to the drive ────────────────────────────────────

def test_write_active_channels_keeps_the_rest_of_the_file(drive):
    device_config.write_active_channels(str(drive), [0, 3])
    text = (drive / device_config.CONFIGURATION_FILE).read_text()
    assert '"active_channels" : [0, 3]' in text
    # Channel numbers stay whole: [0.0000, 3.0000] is a file nobody can read,
    # and the firmware's checker rejects a non-integer channel outright.
    before = [l for l in CONFIG_WITH_FACTORS.splitlines() if 'active_channels' not in l]
    after = [l for l in text.splitlines() if 'active_channels' not in l]
    assert before == after


def test_write_active_channels_refuses_a_set_the_device_would_reject(drive):
    """Checked here as well as in the route: this is the function that touches
    the file, and a bad set leaves the device on an error screen at boot with no
    way back except editing the drive by hand."""
    for bad in ([], [0, 0], [-1], ['a']):
        with pytest.raises(device_config.DeviceConfigError):
            device_config.write_active_channels(str(drive), bad)


def test_write_uv_channel_replaces_the_string(drive):
    (drive / device_config.CONFIGURATION_FILE).write_text(
        '{\n  "gain": "1024x",\n  "channel": "UVC"\n}\n')
    device_config.write_uv_channel(str(drive), 'UVA')
    data = device_config.read_configuration(str(drive))
    assert data['channel'] == 'UVA'
    assert data['gain'] == '1024x'


def test_write_uv_channel_inserts_the_key_when_absent(drive):
    (drive / device_config.CONFIGURATION_FILE).write_text('{\n  "gain": "1024x"\n}\n')
    device_config.write_uv_channel(str(drive), 'UVB')
    assert device_config.read_configuration(str(drive))['channel'] == 'UVB'


def test_write_uv_channel_refuses_a_name_that_is_not_one(drive):
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_uv_channel(str(drive), 'UV"C')


def test_write_uv_channel_refuses_a_name_outside_ascii(drive):
    """str.isalnum() is true of any unicode letter or numeral, so the old check
    passed names the firmware could never match against its own. The value is
    written to a device that reloads on the write and comes back looking for a
    channel by that name."""
    for name in ('UVÅ', 'ⅣⅤ', 'UV A', 'UV-A', 'UV\nA'):
        with pytest.raises(device_config.DeviceConfigError):
            device_config.write_uv_channel(str(drive), name)
    # The names the device actually sends still go through.
    device_config.write_uv_channel(str(drive), 'UVA')
    assert device_config.read_configuration(str(drive))['channel'] == 'UVA'


def test_channels_save_route_writes_what_the_device_reports(client, drive):
    """Not the ticked boxes: Save writes the set in force, so it can never
    persist a selection the operator never applied."""
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'state', return_value={'chans': [0, 3]}), \
         patch.object(device_link.link, 'close') as close:
        rv = client.post('/device/channels/save')
    assert rv.status_code == 200
    assert rv.get_json()['saved'] == [0, 3]
    assert device_config.read_configuration(str(drive))['active_channels'] == [0, 3]
    # The write reboots the board, so the open port is a handle to a device that
    # is going away.
    close.assert_called_once()


def test_channels_save_route_without_a_drive_says_so(client):
    with patch.object(device_config, 'find_device_root', return_value=None), \
         patch.object(device_link.link, 'state', return_value={'chans': [0, 3]}):
        rv = client.post('/device/channels/save')
    assert rv.status_code == 404


def test_uvchannel_save_route_writes_the_running_channel(client, drive):
    (drive / device_config.CONFIGURATION_FILE).write_text(
        '{\n  "gain": "1024x",\n  "channel": "UVC"\n}\n')
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'state', return_value={'uvchan': 'UVA'}), \
         patch.object(device_link.link, 'close'):
        rv = client.post('/device/uvchannel/save')
    assert rv.status_code == 200
    assert device_config.read_configuration(str(drive))['channel'] == 'UVA'


def test_saved_config_route_reports_the_file_and_the_drive(client, drive):
    with patch.object(device_config, 'find_device_root', return_value=str(drive)):
        rv = client.get('/device/config/saved')
    body = rv.get_json()
    assert body['drive'] == str(drive)
    assert body['saved']['active_channels'] == [0, 2, 3]


def test_saved_config_route_with_no_drive_is_not_an_error(client):
    """A device connected for serial only is an ordinary state — the panel says
    "no drive", it does not raise."""
    with patch.object(device_config, 'find_device_root', return_value=None):
        rv = client.get('/device/config/saved')
    assert rv.status_code == 200
    assert rv.get_json()['drive'] is None


def test_disconnect_route_releases_the_port(client):
    """The connection switch: releasing now rather than waiting out the 30 s idle
    reaper, because the user is usually handing the port to something else."""
    with patch.object(device_link.link, 'close') as close:
        rv = client.post('/device/disconnect')
    assert rv.status_code == 200
    close.assert_called_once()


def test_run_script_releases_the_port_first(client):
    """The logger cannot wait its turn, so the link must be closed before the
    subprocess is spawned — otherwise the run fails on a port we hold."""
    with patch.object(device_link.link, 'close') as close, \
         patch('routes.hardware_routes.subprocess.Popen') as popen:
        popen.return_value.wait.side_effect = TimeoutError
        popen.return_value.poll.return_value = None
        client.post('/run_script', json={'base_name': 'x'})
    close.assert_called_once()


# ── the UV build's spectral channel ──────────────────────────────────────────
# One sensor, three photodiodes: the host picks one (UVCHAN:) rather than
# activating a set the way CHANNELS: does on the multiplexer build.

def test_uv_channels_splits_the_list():
    link = FakeLink(["UVCHANNELS UVA,UVB,UVC"])
    assert link.uv_channels() == ['UVA', 'UVB', 'UVC']
    assert link.sent == ['UVCHAN?']


def test_uv_channels_on_firmware_without_the_command_are_none():
    """Older UV firmware only cycles the channel with Right; the panel then
    stays a readout instead of drawing a selector the device would refuse."""
    link = FakeLink(["ERR_UNKNOWN"])
    assert link.uv_channels() is None


def test_set_uv_channel_sends_the_name(monkeypatch):
    monkeypatch.setattr(device_link.time, 'sleep', lambda _seconds: None)
    link = FakeLink(["ACK_UVCHAN"])
    assert link.set_uv_channel('UVB') is True
    assert link.sent == ['UVCHAN:UVB']


def test_set_uv_channel_surfaces_the_device_reason():
    link = FakeLink(["ERR_UVCHAN unknown channel"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_uv_channel('UVZ')
    assert 'unknown channel' in str(excinfo.value)


def test_set_uv_channel_on_firmware_without_the_command_says_so():
    link = FakeLink(["ERR_UNKNOWN"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.set_uv_channel('UVB')
    assert 'firmware' in str(excinfo.value)


def test_uv_channel_route_lists_what_the_device_reports(client):
    with patch.object(device_link.link, 'uv_channels', return_value=['UVA', 'UVB', 'UVC']):
        rv = client.get('/device/uvchannel')
    assert rv.status_code == 200
    assert rv.get_json()['channels'] == ['UVA', 'UVB', 'UVC']


def test_uv_channel_route_reports_firmware_without_the_command_as_null(client):
    with patch.object(device_link.link, 'uv_channels', return_value=None):
        rv = client.get('/device/uvchannel')
    assert rv.status_code == 200
    assert rv.get_json()['channels'] is None


def test_uv_channel_route_sets_and_returns_the_new_state(client):
    with patch.object(device_link.link, 'set_uv_channel', return_value=True) as setter, \
         patch.object(device_link.link, 'state', return_value={'uvchan': 'UVB'}):
        rv = client.post('/device/uvchannel', json={'channel': 'UVB'})
    setter.assert_called_once_with('UVB')
    assert rv.get_json()['state'] == {'uvchan': 'UVB'}


def test_uv_channel_route_rejects_an_empty_choice(client):
    with patch.object(device_link.link, 'set_uv_channel') as setter:
        rv = client.post('/device/uvchannel', json={'channel': '   '})
    assert rv.status_code == 400
    setter.assert_not_called()


def test_uv_channel_route_surfaces_the_device_refusal(client):
    with patch.object(device_link.link, 'set_uv_channel',
                      side_effect=device_link.DeviceLinkError('unknown channel')):
        rv = client.post('/device/uvchannel', json={'channel': 'UVZ'})
    assert rv.status_code == 502
    assert 'unknown channel' in rv.get_json()['message']


# ── the sensors' gain and integration time ───────────────────────────────────
# Four builds hold this one setting under four key schemes, so the device names
# its own keys and the host writes them verbatim rather than assembling any.

def test_sensor_config_parses_the_pairs():
    link = FakeLink(["SENSCFG gain_sensor_0=med;itime_sensor_0=500ms"])
    assert link.sensor_config() == {'gain_sensor_0': 'med', 'itime_sensor_0': '500ms'}
    assert link.sent == ['SENSCFG?']


def test_sensor_config_on_a_single_sensor_build():
    link = FakeLink(["SENSCFG gain=1024x;integration_time=32ms"])
    assert link.sensor_config() == {'gain': '1024x', 'integration_time': '32ms'}


def test_sensor_config_on_firmware_without_the_command_is_none():
    link = FakeLink(["ERR_UNKNOWN"])
    assert link.sensor_config() is None


def test_sensor_config_surfaces_the_device_reason():
    link = FakeLink(["ERR_SENSCFG unknown setting"])
    with pytest.raises(device_link.DeviceLinkError) as excinfo:
        link.sensor_config()
    assert 'unknown setting' in str(excinfo.value)


def test_write_sensor_settings_replaces_every_key_in_one_write(drive):
    device_config.write_sensor_settings(str(drive), {
        'gain_sensor_0': 'high', 'itime_sensor_0': '600ms'})
    data = device_config.read_configuration(str(drive))
    assert data['gain_sensor_0'] == 'high'
    assert data['itime_sensor_0'] == '600ms'


def test_write_sensor_settings_refuses_a_key_that_is_not_a_sensor_setting(drive):
    before = (drive / device_config.CONFIGURATION_FILE).read_text()
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_sensor_settings(str(drive), {'startup': 'Absorbance'})
    assert (drive / device_config.CONFIGURATION_FILE).read_text() == before


def test_write_sensor_settings_refuses_a_value_the_device_could_not_read(drive):
    """It goes into a JSON string on a board that reloads on the write, and the
    firmware matches it against a fixed table."""
    before = (drive / device_config.CONFIGURATION_FILE).read_text()
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_sensor_settings(str(drive), {'gain': 'med"; DROP'})
    assert (drive / device_config.CONFIGURATION_FILE).read_text() == before


def test_write_sensor_settings_refuses_an_empty_set(drive):
    with pytest.raises(device_config.DeviceConfigError):
        device_config.write_sensor_settings(str(drive), {})


def test_sensor_settings_route_reports_saved_alongside_running(client, drive):
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'sensor_config',
                      return_value={'gain_sensor_0': 'high', 'itime_sensor_0': '600ms'}):
        rv = client.get('/device/sensor-settings')
    body = rv.get_json()
    assert body['settings'] == {'gain_sensor_0': 'high', 'itime_sensor_0': '600ms'}
    # The file still holds what it held — that difference is what enables Save.
    assert body['saved']['gain_sensor_0'] != 'high'
    assert body['drive'] == str(drive)


def test_sensor_settings_route_on_firmware_without_the_command(client, drive):
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'sensor_config', return_value=None):
        rv = client.get('/device/sensor-settings')
    assert rv.status_code == 200
    assert rv.get_json()['settings'] is None


def test_sensor_settings_save_writes_what_the_device_reports(client, drive):
    """Not what the browser cached: a gain dialled in on the keypad must be what
    gets saved."""
    with patch.object(device_config, 'find_device_root', return_value=str(drive)), \
         patch.object(device_link.link, 'sensor_config',
                      return_value={'gain_sensor_0': 'high', 'itime_sensor_0': '600ms'}), \
         patch.object(device_link.link, 'close') as close:
        rv = client.post('/device/sensor-settings/save')
    assert rv.status_code == 200
    assert device_config.read_configuration(str(drive))['gain_sensor_0'] == 'high'
    # The write reboots the board, so the open handle is to a device that is
    # about to disappear.
    close.assert_called_once()


def test_sensor_settings_save_404_when_no_drive(client):
    with patch.object(device_config, 'find_device_root', return_value=None), \
         patch.object(device_link.link, 'sensor_config', return_value={'gain': 'med'}):
        rv = client.post('/device/sensor-settings/save')
    assert rv.status_code == 404


def test_write_sensor_settings_inserts_a_missing_itime_beside_its_gain(tmp_path):
    """A file can hold a gain and no integration time — the firmware falls back
    to its default for a missing key. The new key belongs under the gain it goes
    with, not at the top of a file whose order the operator chose."""
    (tmp_path / device_config.BOOT_OUT_FILE).write_text(BOOT_OUT)
    (tmp_path / device_config.CONFIGURATION_FILE).write_text(
        '{\n'
        '  "active_channels" : [0, 2],\n'
        '  "gain_sensor_2"     : "med",\n'
        '  "startup" : "Absorbance"\n'
        '}\n')
    device_config.write_sensor_settings(str(tmp_path), {
        'gain_sensor_2': 'max', 'itime_sensor_2': '100ms'})

    text = (tmp_path / device_config.CONFIGURATION_FILE).read_text()
    assert device_config.read_configuration(str(tmp_path))['itime_sensor_2'] == '100ms'
    assert text.index('gain_sensor_2') < text.index('itime_sensor_2') < text.index('startup')


# ── the same path on all four builds ─────────────────────────────────────────
# One setting, four key schemes. The firmware half is verified by each branch's
# own SENSCFG? reply; this is the host half — parse the reply, write it into a
# configuration.json shaped like that build's, and check the values land while
# everything the device did not report stays exactly as it was.
#
# The files below are the real ones, trimmed of keys this path never touches.

BUILD_CONFIGS = {
    'main': ('{\n'
             '  "gain" : "med",\n'
             '  "integration_time" : "500ms",\n'
             '  "raw_count_factor" : [1.0],\n'
             '  "startup" : "Absorbance",\n'
             '  "precision" : 3\n}\n',
             'SENSCFG gain=high;integration_time=200ms'),
    'open-plus': ('{\n'
                  '  "gain_sensor_90"      : "max",\n'
                  '  "itime_sensor_90"     : "600ms",\n'
                  '  "gain_sensor_180"     : "high",\n'
                  '  "itime_sensor_180"    : "600ms",\n'
                  '  "raw_count_factor"    : [1.0, 1.0],\n'
                  '  "startup" : "Absorbance"\n}\n',
                  'SENSCFG gain_sensor_90=high;itime_sensor_90=200ms;'
                  'gain_sensor_180=low;itime_sensor_180=100ms'),
    'open-extra': ('{\n'
                   '  "active_channels" : [0, 2, 3],\n'
                   '  "gain_sensor_0"     : "med",\n'
                   '  "itime_sensor_0"    : "500ms",\n'
                   '  "gain_sensor_1"     : "med",\n'
                   '  "itime_sensor_1"    : "500ms",\n'
                   '  "gain_sensor_2"     : "med",\n'
                   '  "itime_sensor_2"    : "500ms",\n'
                   '  "startup" : "Absorbance"\n}\n',
                   # Only channels 0 and 2 are open, so only they are reported.
                   'SENSCFG gain_sensor_0=high;itime_sensor_0=200ms;'
                   'gain_sensor_2=low;itime_sensor_2=100ms'),
    'open-uv': ('{\n'
                '  "gain": "1024x",\n'
                '  "integration_time": "32ms",\n'
                '  "channel": "UVC",\n'
                '  "raw_count_factor": [1.0, 1.0, 1.0],\n'
                '  "precision": 3\n}\n',
                'SENSCFG gain=512x;integration_time=64ms'),
}


@pytest.mark.parametrize('build', sorted(BUILD_CONFIGS))
def test_sensor_settings_round_trip_on_every_build(build, tmp_path):
    config, reply = BUILD_CONFIGS[build]
    (tmp_path / device_config.BOOT_OUT_FILE).write_text(BOOT_OUT)
    (tmp_path / device_config.CONFIGURATION_FILE).write_text(config)

    settings = FakeLink([reply]).sensor_config()
    assert settings, f'{build}: nothing parsed out of its own reply'

    device_config.write_sensor_settings(str(tmp_path), settings)
    after = device_config.read_configuration(str(tmp_path))
    before = json.loads(config)

    for key, value in settings.items():
        assert after[key] == value, f'{build}: {key} did not land'
    for key, value in before.items():
        if key not in settings:
            assert after[key] == value, f'{build}: {key} changed and should not have'


def test_an_inactive_channels_settings_are_left_alone(tmp_path):
    """The multi-channel build reports only the channels it has a sensor open
    on. A slot the operator is not using keeps the gain they put there."""
    config, reply = BUILD_CONFIGS['open-extra']
    (tmp_path / device_config.BOOT_OUT_FILE).write_text(BOOT_OUT)
    (tmp_path / device_config.CONFIGURATION_FILE).write_text(config)

    settings = FakeLink([reply]).sensor_config()
    assert 'gain_sensor_1' not in settings, 'channel 1 is not open; it must not be reported'

    device_config.write_sensor_settings(str(tmp_path), settings)
    after = device_config.read_configuration(str(tmp_path))
    assert after['gain_sensor_1'] == 'med'
    assert after['itime_sensor_1'] == '500ms'
