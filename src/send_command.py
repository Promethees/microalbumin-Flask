import serial
import serial.tools.list_ports
import time

# Poll cadence for the serial port. Deliberately short: the read loops below and
# in log_cdc_data.py only get to do other work (check the manual-measure trigger,
# re-check a deadline) between reads, so a long port timeout becomes latency the
# user feels on every "Measure now" press. LineReader keeps framing correct at
# this cadence — a bare readline() with a short timeout returns half lines.
PORT_TIMEOUT = 0.15

# Per-port budget for the PING probe in connect_to_device(). The device answers
# within one firmware main-loop period (~0.17 s measured), but a device that is
# mid-handshake can be busy for about a second, so allow for that.
PROBE_TIMEOUT = 1.5

# Any of these proves we are talking to the CDC *data* endpoint. ACK_PING is the
# explicit reply; ERR_UNKNOWN is what firmware predating the PING command answers
# to an unrecognised token, so the probe works against existing devices too.
PROBE_REPLIES = ("ACK_PING", "ERR_UNKNOWN")


class LineReader:
    """Assemble complete newline-terminated lines from a serial port.

    pyserial's readline() hands back whatever it has when the port timeout
    expires, so a short timeout — which we want, so callers can poll other work
    between reads — makes it return fragments. Those fragments then fail command
    ACK matching and get logged as corrupt data rows. Buffering here keeps the
    poll cadence tight without ever emitting a partial line.
    """

    def __init__(self, ser):
        self.serial = ser
        self.buffer = b""

    def read_lines(self):
        """Return the complete lines available now (possibly none).

        Blocks at most one port timeout: reads whatever is waiting, or waits on a
        single byte so the caller does not spin.
        """
        waiting = self.serial.in_waiting
        chunk = self.serial.read(waiting if waiting else 1)
        if chunk:
            self.buffer += chunk
        if b"\n" not in self.buffer:
            return []
        parts = self.buffer.split(b"\n")
        self.buffer = parts[-1]
        return [p.decode("utf-8", errors="replace").strip() for p in parts[:-1]]

    def drain(self, seconds=0.3):
        """Discard everything the device sends for `seconds`, and reset framing."""
        end = time.time() + seconds
        while time.time() < end:
            if self.serial.in_waiting:
                self.serial.read(self.serial.in_waiting)
            else:
                time.sleep(0.02)
        try:
            self.serial.reset_input_buffer()
        except Exception:
            pass
        self.buffer = b""


def _probe(port):
    """Open `port` and check whether it is the PyBadge CDC *data* endpoint.

    Returns the open Serial on success, None otherwise. Sends PING, which the
    firmware answers on the data channel and which is inert on the console
    channel (CircuitPython does not read stdin while code.py runs).
    """
    try:
        ser = serial.Serial(port, 115200, timeout=PORT_TIMEOUT, write_timeout=1)
    except Exception:
        return None
    try:
        time.sleep(0.3)  # brief settle; opening CDC data does not reset the board
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        ser.flush()
        reader = LineReader(ser)
        end = time.time() + PROBE_TIMEOUT
        while time.time() < end:
            for line in reader.read_lines():
                if line in PROBE_REPLIES:
                    ser.reset_input_buffer()
                    return ser
        ser.close()
        return None
    except Exception:
        try:
            ser.close()
        except Exception:
            pass
        return None


def connect_to_device(vid=0x239A, pid=0x8034):
    """Find and open the PyBadge CDC data port.

    A board booted with `usb_cdc.enable(console=True, data=True)` exposes TWO
    ports, and on macOS they are indistinguishable by USB metadata — identical
    vid, pid, description, hwid, serial_number and interface. Picking the first
    match therefore lands on the console (REPL) port about half the time, where
    commands are silently ignored and the session start fails with either a
    handshake timeout or an "Unexpected response" from stray console output.
    So probe each candidate and keep the one that actually answers.
    """
    candidates = [p.device for p in serial.tools.list_ports.comports()
                  if p.vid == vid and p.pid == pid]

    if not candidates:
        raise Exception("Device (Pybadge) not found. Is it connected?")

    for port in candidates:
        ser = _probe(port)
        if ser is not None:
            return ser

    raise Exception(
        "Device (Pybadge) found on {} but no port answered the data-channel "
        "probe. Is boot.py enabling usb_cdc data (usb_cdc.enable(data=True))?"
        .format(", ".join(candidates)))


# Helper function to send commands and wait for acknowledgments
def send_command_and_wait_ack(pybadge, commands, expected_acks, error_acks, timeout=5, attempts=3):
    # Retry the whole start-command chunk a few times: if the device was still
    # booting when the first attempt's ACK window elapsed, a resend usually
    # succeeds — far cheaper than a large fixed pre-connect delay.
    last_error = None
    reader = LineReader(pybadge)
    ack_tokens = set(expected_acks) | set(error_acks)

    for attempt in range(attempts):
        if attempt:
            # A previous attempt may have timed out *after* the device already
            # started a session, in which case it is now streaming header and
            # data lines. Stop it and drain, so this attempt starts from a known
            # idle device instead of matching data rows against ACKs.
            try:
                pybadge.write(b"0\n")
                pybadge.flush()
            except Exception:
                pass
            time.sleep(0.3)
        reader.drain()

        # Ensure commands are newline-terminated and send as a chunk
        command_chunk = "".join(cmd if cmd.endswith("\n") else cmd + "\n" for cmd in commands)
        print(f"Sending command chunk (attempt {attempt + 1}/{attempts}): {command_chunk.strip()}")
        pybadge.write(command_chunk.encode())
        pybadge.flush()  # Ensure all data is sent

        start_time = time.time()
        responses_received = []
        failure = None

        while len(responses_received) < len(commands) and time.time() - start_time < timeout:
            for response in reader.read_lines():
                if not response:
                    continue
                if response not in ack_tokens:
                    # Not an acknowledgment: leftover console noise, a stray data
                    # row from an earlier session, or a device banner. Treating
                    # these as fatal is what turned a transient into a failed run,
                    # so skip and keep waiting for the real ACK.
                    print(f"Ignoring non-ack line: {response}")
                    continue

                index = len(responses_received)
                responses_received.append(response)
                if response == expected_acks[index]:
                    print(f"Success: {response} received for {commands[index].strip()}")
                elif response == error_acks[index]:
                    cmd = commands[index]
                    failure = f"Failed to process {cmd.split(':')[0] if ':' in cmd else cmd.strip()} command on PyBadge"
                    print(f"Error: {failure}")
                    break
                else:
                    failure = f"Unexpected response: {response} for {commands[index].strip()}"
                    print(f"Error: {failure}")
                    break

                if len(responses_received) == len(commands):
                    return True, None

            if failure:
                break

        if failure:
            # A wrong/error ACK is a real device-side rejection, not a timing
            # problem — retrying the same chunk would only repeat it.
            return False, failure

        last_error = f"Timeout: Received {len(responses_received)}/{len(commands)} acknowledgments for commands {', '.join(cmd.strip() for cmd in commands)}"
        print(f"Timeout (attempt {attempt + 1}/{attempts}): {last_error}")

    return False, last_error
