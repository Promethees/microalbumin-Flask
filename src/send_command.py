import serial.tools.list_ports
import time 

def connect_to_device(vid = 0x239A, pid = 0x8034):
    """Automatically find and connect to Device"""

    # Find the port
    port = None
    for p in serial.tools.list_ports.comports():
        if p.vid == vid and p.pid == pid:
            port = p.device
            break
    
    if not port:
        raise Exception("Device (Pybadge) not found. Is it connected?")
    
    # Configure and open serial connection
    ser = serial.Serial(
        port=port,
        baudrate=115200,
        timeout=1,
        write_timeout=1
    )
    
    # Wait for connection to establish
    time.sleep(2)
    return ser

# Helper function to send commands and wait for acknowledgments
def send_command_and_wait_ack(pybadge, commands, expected_acks, error_acks, timeout=5):
    # Flush input buffer to clear any residual data
    pybadge.reset_input_buffer()
    
    # Ensure commands are newline-terminated and send as a chunk
    command_chunk = "".join(cmd if cmd.endswith("\n") else cmd + "\n" for cmd in commands)
    print(f"Sending command chunk: {command_chunk.strip()}")
    pybadge.write(command_chunk.encode())
    pybadge.flush()  # Ensure all data is sent
    time.sleep(0.2 * len(commands))  # Adjust delay based on number of commands
    
    start_time = time.time()
    responses_received = []
    
    while len(responses_received) < len(commands) and time.time() - start_time < timeout:
        if pybadge.in_waiting:
            response = pybadge.readline().decode('utf-8').strip()
            if response:  # Ignore empty responses
                print(f"Received response: {response}")
                responses_received.append(response)
                
                # Check responses in order of expected acks
                for i, (cmd, expected_ack, error_ack) in enumerate(zip(commands, expected_acks, error_acks)):
                    if i >= len(responses_received):
                        break
                    response = responses_received[i]
                    if response == expected_ack:
                        print(f"Success: {expected_ack} received for {cmd.strip()}")
                    elif response == error_ack:
                        error_msg = f"Failed to process {cmd.split(':')[0] if ':' in cmd else cmd} command on PyBadge"
                        print(f"Error: {error_msg}")
                        return False, error_msg
                    else:
                        error_msg = f"Unexpected response: {response} for {cmd.strip()}"
                        print(f"Error: {error_msg}")
                        return False, error_msg
                
                # If all expected responses are received, return success
                if len(responses_received) == len(commands):
                    all_success = all(responses_received[i] == expected_acks[i] for i in range(len(commands)))
                    if all_success:
                        return True, None
                    else:
                        error_msg = f"Not all responses matched expected acks"
                        print(f"Error: {error_msg}")
                        return False, error_msg
        time.sleep(0.1)
    
    error_msg = f"Timeout: Received {len(responses_received)}/{len(commands)} acknowledgments for commands {', '.join(cmd.strip() for cmd in commands)}"
    print(f"Timeout: {error_msg}")
    return False, error_msg