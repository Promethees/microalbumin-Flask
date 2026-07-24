"""Tests for the CDC serial helpers in src/send_command.py.

These cover the two failure modes that made host-initiated sessions unreliable
(see Rule.md §2.28): picking the wrong CDC port when the board exposes both a
console and a data endpoint, and fragmented lines once the port timeout is short
enough to keep the manual-measure trigger responsive.

No hardware required — a fake serial object stands in for the port.
"""

import os
import sys

import pytest

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import send_command  # noqa: E402
from send_command import LineReader, send_command_and_wait_ack  # noqa: E402


class FakeSerial:
    """Minimal pyserial stand-in: replays scripted chunks, records writes."""

    def __init__(self, chunks=None):
        self.chunks = list(chunks or [])
        self.written = b""
        self.in_waiting = 0
        self.closed = False

    def read(self, n):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data):
        self.written += bytes(data)
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True

    def feed(self, *chunks):
        self.chunks.extend(chunks)


# ── LineReader ──────────────────────────────────────────────────────────────

def test_line_reader_reassembles_split_lines():
    ser = FakeSerial([b"ACK_ST", b"ART\nACK_TIME", b"OUT\n"])
    reader = LineReader(ser)
    out = []
    for _ in range(4):
        out += reader.read_lines()
    assert out == ["ACK_START", "ACK_TIMEOUT"]


def test_line_reader_never_emits_a_fragment():
    """A trailing chunk with no newline must be held back, not returned."""
    ser = FakeSerial([b"1,0.5,0.6\n", b"2,0.7"])
    reader = LineReader(ser)
    out = []
    for _ in range(3):
        out += reader.read_lines()
    assert out == ["1,0.5,0.6"]
    assert reader.buffer == b"2,0.7"


def test_line_reader_emits_fragment_once_completed():
    ser = FakeSerial([b"2,0.7", b",0.8\n"])
    reader = LineReader(ser)
    out = []
    for _ in range(3):
        out += reader.read_lines()
    assert out == ["2,0.7,0.8"]


def test_line_reader_handles_multiple_lines_in_one_chunk():
    ser = FakeSerial([b"# Unit: None\n# Concentration: None\nTurn,Value:1\n"])
    reader = LineReader(ser)
    assert reader.read_lines() == [
        "# Unit: None", "# Concentration: None", "Turn,Value:1"]


def test_line_reader_survives_undecodable_bytes():
    ser = FakeSerial([b"\xff\xfe bad\n"])
    reader = LineReader(ser)
    assert len(reader.read_lines()) == 1  # replaced, not raised


# ── port probing ────────────────────────────────────────────────────────────

def test_probe_replies_accept_legacy_firmware():
    """ERR_UNKNOWN must stay accepted: firmware predating PING answers that,
    and tightening to ACK_PING alone would orphan every un-updated device."""
    assert "ACK_PING" in send_command.PROBE_REPLIES
    assert "ERR_UNKNOWN" in send_command.PROBE_REPLIES


@pytest.mark.parametrize("noise", [
    "loop_dt 380.645",                    # firmware debug print on the console port
    "Adafruit CircuitPython 9.2.7",       # console banner
    "code.py output:",
    "",
])
def test_console_noise_is_not_a_probe_reply(noise):
    assert noise not in send_command.PROBE_REPLIES


def test_connect_to_device_raises_when_no_candidate(monkeypatch):
    monkeypatch.setattr(send_command.serial.tools.list_ports, "comports", lambda: [])
    with pytest.raises(Exception) as exc:
        send_command.connect_to_device()
    assert "not found" in str(exc.value)


def test_connect_to_device_skips_the_port_that_does_not_answer(monkeypatch):
    """The console port is probed first and must be rejected, not returned."""
    class Port:
        def __init__(self, device):
            self.device = device
            self.vid, self.pid = 0x239A, 0x8034

    monkeypatch.setattr(
        send_command.serial.tools.list_ports, "comports",
        lambda: [Port("/dev/console-port"), Port("/dev/data-port")])

    answered = FakeSerial()
    probed = []

    def fake_probe(port):
        probed.append(port)
        return answered if port == "/dev/data-port" else None

    monkeypatch.setattr(send_command, "_probe", fake_probe)

    assert send_command.connect_to_device() is answered
    assert probed == ["/dev/console-port", "/dev/data-port"]


def test_connect_to_device_raises_when_nothing_answers(monkeypatch):
    class Port:
        def __init__(self, device):
            self.device = device
            self.vid, self.pid = 0x239A, 0x8034

    monkeypatch.setattr(
        send_command.serial.tools.list_ports, "comports",
        lambda: [Port("/dev/a"), Port("/dev/b")])
    monkeypatch.setattr(send_command, "_probe", lambda port: None)

    with pytest.raises(Exception) as exc:
        send_command.connect_to_device()
    assert "probe" in str(exc.value)


# ── handshake ───────────────────────────────────────────────────────────────

# TIMEOUT deliberately does not end in 0: the retry test counts standalone
# b"0\n" stop commands, and "TIMEOUT:60\n" would collide with that substring.
CMDS = ["1\n", "TIMEOUT:65\n", "AXIS:turn\n", "INTERVAL:5\n"]
ACKS = ["ACK_START", "ACK_TIMEOUT", "ACK_AXIS", "ACK_INTERVAL"]
ERRS = ["ERR_START", "ERR_TIMEOUT", "ERR_AXIS", "ERR_INTERVAL"]


def test_handshake_succeeds_on_clean_acks():
    ser = FakeSerial([b"ACK_START\nACK_TIMEOUT\nACK_AXIS\nACK_INTERVAL\n"])
    ok, err = send_command_and_wait_ack(ser, CMDS, ACKS, ERRS, timeout=2)
    assert (ok, err) == (True, None)


def test_handshake_ignores_interleaved_noise():
    """Stray console output or a data row from an earlier session must not be
    treated as a failed ACK — that turned a transient into a dead run."""
    ser = FakeSerial([
        b"loop_dt 380.645\n",
        b"ACK_START\n",
        b"1,OVFL,OVFL,-0.000\n",
        b"ACK_TIMEOUT\nACK_AXIS\n",
        b"# Measurement: Absorbance\n",
        b"ACK_INTERVAL\n",
    ])
    ok, err = send_command_and_wait_ack(ser, CMDS, ACKS, ERRS, timeout=2)
    assert (ok, err) == (True, None)


def test_handshake_fails_fast_on_device_error_without_retrying():
    ser = FakeSerial([b"ACK_START\nERR_TIMEOUT\n"])
    ok, err = send_command_and_wait_ack(ser, CMDS, ACKS, ERRS, timeout=2, attempts=3)
    assert ok is False
    assert "TIMEOUT" in err
    # exactly one chunk sent: a device-side rejection must not be retried
    assert ser.written.count(b"AXIS:turn") == 1


def test_handshake_stops_device_before_each_retry():
    """A previous attempt may have started a session; the retry must send 0
    first so it matches ACKs against an idle device, not a live data stream."""
    ser = FakeSerial([])  # never answers -> exhausts all attempts
    ok, err = send_command_and_wait_ack(ser, CMDS, ACKS, ERRS, timeout=0.2, attempts=3)
    assert ok is False
    assert "Timeout" in err
    assert ser.written.count(b"0\n") == 2  # one before each of the 2 retries


def test_handshake_reports_timeout_when_device_is_silent():
    ser = FakeSerial([])
    ok, err = send_command_and_wait_ack(ser, CMDS, ACKS, ERRS, timeout=0.2, attempts=1)
    assert ok is False
    assert "0/4 acknowledgments" in err
