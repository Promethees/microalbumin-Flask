"""Virtual controller: STATE parsing, the link's command handling, and the
routes' one-owner rule (src/device_link.py, routes/hardware_routes.py)."""

import pytest
from unittest.mock import MagicMock, patch

import device_link
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
                 lambda: client.post('/device/channels', json={'channels': [0]})):
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


def test_run_script_releases_the_port_first(client):
    """The logger cannot wait its turn, so the link must be closed before the
    subprocess is spawned — otherwise the run fails on a port we hold."""
    with patch.object(device_link.link, 'close') as close, \
         patch('routes.hardware_routes.subprocess.Popen') as popen:
        popen.return_value.wait.side_effect = TimeoutError
        popen.return_value.poll.return_value = None
        client.post('/run_script', json={'base_name': 'x'})
    close.assert_called_once()
