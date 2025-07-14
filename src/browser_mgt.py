import socket
import webbrowser
import os 
import signal
import datetime
import time
import subprocess
import argparse

def is_port_open(host, port):
    """Check if the specified port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

def open_browser(host, port):
    """Open the browser after a short delay to ensure server is running."""
    # Only open browser in the main process, not the reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        time.sleep(2)  # Wait for server to start
        if is_port_open(host, port):
            try:
                webbrowser.open(f'http://{host}:{port}')
                print(f"Opened browser at http://{host}:{port}")
            except Exception as e:
                print(f"Failed to open browser: {e}")
        else:
            print(f"Failed to verify server is running on port {port}. Please check if the port is in use or accessible.")

def close_port(port, exclude_pid=None):
    """Close processes using the specified port, excluding the given PID."""
    try:
        # Use lsof to find processes using the port
        result = subprocess.run(
            ['lsof', '-i', f':{port}', '-t'],
            capture_output=True,
            text=True,
            check=False
        )
        pids = result.stdout.strip().split('\n')
        current_pid = str(exclude_pid or os.getpid())
        for pid in pids:
            if pid and pid != current_pid:
                print(f"Terminating process {pid} using port {port}")
                subprocess.run(['kill', '-9', pid], check=False)
    except subprocess.CalledProcessError as e:
        print(f"Error closing port {port}: {e}")
    except FileNotFoundError:
        print("lsof not found; ensure lsof is installed (e.g., sudo apt install lsof)")

def cleanup():
    global process
    if process and process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process = None
    # Log cleanup action
    with open(log_file, 'a') as f:
        f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server shutting down, notifying clients to clear cache\n")
    # Close the Flask server port
    close_port(args.port)
    print("Cleaned up resources and closed port")