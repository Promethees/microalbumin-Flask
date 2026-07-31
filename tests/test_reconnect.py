"""Mid-session recovery in the CDC logger (log_cdc_data.py).

A CircuitPython board re-enumerates on auto-reload, on a brownout, and on a
jiggled cable. Before this, one SerialException out of the read loop ended the
run and truncated the CSV; these tests pin down that the run survives instead,
that the file stays ONE series across the gap, and that a device which never
comes back is announced as a disconnection rather than a clean finish.
"""

import os
import time
from unittest.mock import patch

import pytest
import serial

import log_cdc_data
from log_cdc_data import CDCDataCollector
from script_monitor import check_log_for_end_reason


HEADER = "Timestamp,Value:1,Value:2"
METADATA = [
    "# Measurement: Absorbance",
    "# Unit: NONE",
    "# Concentration: NONE",
    "# ConcenUnit: ng/µL",
]


@pytest.fixture
def collector(tmp_path):
    """A collector whose log/ and data/ live in tmp_path, mid-session."""
    with patch.object(log_cdc_data.state, "script_dir", str(tmp_path)):
        (tmp_path / "log").mkdir()
        made = CDCDataCollector(
            base_dir=str(tmp_path / "data"), timeout_sec=600, interval_sec=1)
        for line in METADATA:
            made.process_line(line)
        made.process_line(HEADER)
        assert made.session_started
        yield made


def rows_of(collector):
    with open(collector.output_file, encoding="utf-8") as f:
        return [line.strip() for line in f if not line.startswith("#")][1:]


def test_reconnect_keeps_one_series_across_the_gap(collector):
    """The resumed device restarts its clock; the file must not."""
    collector.process_line("0.00,0.100,0.200")
    collector.process_line("1.00,0.110,0.210")
    assert collector.rows_written == 2

    # Gone for eight seconds, then back.
    collector._session_wall_start = time.time() - 8.0
    with patch.object(log_cdc_data, "RECONNECT_DELAYS", (0,)), \
         patch.object(log_cdc_data, "connect_to_device") as connect, \
         patch.object(CDCDataCollector, "_send_start_commands", return_value=(True, None)):
        connect.return_value.port = "/dev/fake"
        reader = collector._reconnect("device re-enumerated")

    assert reader is not None
    assert collector.reconnects == 1
    assert collector.x_offset == pytest.approx(8.0, abs=0.5)

    # The device starts over at 0.00; the row lands after the rows already saved.
    collector.process_line("0.00,0.120,0.220")
    written = rows_of(collector)
    assert [r.split(",")[0] for r in written[:2]] == ["0.00", "1.00"]
    assert float(written[2].split(",")[0]) == pytest.approx(8.0, abs=0.5)
    assert written[2].endswith("0.120,0.220")


def test_turn_numbering_continues_after_a_reconnect(collector):
    collector.x_label = "Turn"
    collector.rows_written = 3

    with patch.object(log_cdc_data, "RECONNECT_DELAYS", (0,)), \
         patch.object(log_cdc_data, "connect_to_device") as connect, \
         patch.object(CDCDataCollector, "_send_start_commands", return_value=(True, None)):
        connect.return_value.port = "/dev/fake"
        collector._reconnect("cable")

    assert collector._shift_x("1") == "4"
    assert collector._shift_x("2") == "5"


def test_remaining_timeout_is_not_restarted_by_a_reconnect(collector):
    """Four reconnects must not buy the run four more timeouts."""
    collector._session_wall_start = time.time() - 120.0
    assert collector._remaining_timeout() == pytest.approx(480.0, abs=1.0)

    captured = {}

    def fake_start(self, timeout_override=None):
        captured["timeout"] = timeout_override
        return True, None

    with patch.object(log_cdc_data, "RECONNECT_DELAYS", (0,)), \
         patch.object(log_cdc_data, "connect_to_device") as connect, \
         patch.object(CDCDataCollector, "_send_start_commands", fake_start):
        connect.return_value.port = "/dev/fake"
        collector._reconnect("cable")

    assert captured["timeout"] == pytest.approx(480.0, abs=1.0)


def test_timeout_elapsed_while_away_ends_the_session(collector):
    collector._session_wall_start = time.time() - 700.0  # budget was 600
    with patch.object(log_cdc_data, "RECONNECT_DELAYS", (0,)), \
         patch.object(log_cdc_data, "connect_to_device") as connect:
        connect.return_value.port = "/dev/fake"
        assert collector._reconnect("cable") is None
    assert collector.running is False
    assert check_log_for_end_reason(collector.log_file_path) == "timeout"


def test_device_that_never_returns_is_reported_as_a_disconnection(collector):
    collector.process_line("0.00,0.100,0.200")

    with patch.object(log_cdc_data, "RECONNECT_WINDOW", 0.05), \
         patch.object(log_cdc_data, "RECONNECT_DELAYS", (0.01,)), \
         patch.object(log_cdc_data, "connect_to_device",
                      side_effect=serial.SerialException("no such port")):
        assert collector._reconnect("unplugged") is None

    assert collector.running is False
    # The UI must not call this a completed reading — and must not mistake it for
    # the fatal "PyBadge not found", which tears the session down from
    # /check_status while a recovery is still in flight.
    assert check_log_for_end_reason(collector.log_file_path) == "disconnected"
    with open(collector.log_file_path, encoding="utf-8") as f:
        assert "PyBadge not found" not in f.read()
    # The row captured before the drop is still on disk.
    assert rows_of(collector) == ["0.00,0.100,0.200"]


def test_silence_watchdog_only_watches_streaming_sessions(collector):
    collector._last_line_at = time.time() - 3600

    assert collector._silence_exceeded() is True

    collector.paused = True
    assert collector._silence_exceeded() is False
    collector.paused = False

    collector.manual = True
    assert collector._silence_exceeded() is False
    collector.manual = False

    # Inside the allowance for the configured interval, silence is normal.
    collector.interval_sec = 60
    collector._last_line_at = time.time() - 30
    assert collector._silence_exceeded() is False
