"""Virtual controller: STATE parsing, the link's command handling, and the
routes' one-owner rule (src/device_link.py, routes/hardware_routes.py)."""

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
    "interval=1;intervalunit=min;bat=3.91"
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
                 lambda: client.post('/device/calibration', json={'run': True})):
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


def test_calibration_route_empty_body_clears_the_factors(client):
    with patch.object(device_link.link, 'set_calibration_factors', return_value=True) as write, \
         patch.object(device_link.link, 'calibration_factors', return_value=[1.0] * 4), \
         patch.object(device_link.link, 'state', return_value={}):
        rv = client.post('/device/calibration', json={})
    write.assert_called_once_with(None)
    assert rv.get_json()['factors'] == [1.0] * 4


def test_calibration_route_rejects_non_numbers(client):
    rv = client.post('/device/calibration', json={'factors': ['a']})
    assert rv.status_code == 400


def test_calibration_route_rejects_an_empty_factor_list(client):
    """An empty list is not "clear them" — that is the empty body — and sending
    it on would be a no-op the operator read as a change."""
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
