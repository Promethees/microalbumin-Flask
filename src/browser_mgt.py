import socket
import webbrowser
import os 
import signal
import datetime
import time
import subprocess
import platform

def is_port_open(host, port):
    """Check if the specified port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except OSError:
        return False
    finally:
        sock.close()

def open_browser(host, port):
    """Open the browser once the server is confirmed running."""
    url = f"http://{host}:{port}"
    sudo_user = os.environ.get("SUDO_USER")

    # Poll 127.0.0.1 directly — always resolves regardless of hosts-file state.
    if not wait_for_server('127.0.0.1', port):
        print(f"Server did not start on port {port} in time.")
        return

    try:
        open_url(url, sudo_user)
        print(f"Opened browser at {url}")
    except Exception as e:
        print(f"Failed to open browser: {e}")

def open_url(url, sudo_user=None):
    system = platform.system()
    if sudo_user and system == "Darwin":
        subprocess.run(["sudo", "-u", sudo_user, "open", url], check=False)
    elif sudo_user and system == "Linux":
        subprocess.run(["sudo", "-u", sudo_user, "xdg-open", url], check=False)
    else:
        webbrowser.open(url)

def wait_for_server(host, port, timeout=10, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(interval)
    return False

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

def cleanup(process, log_file, args):
    try:
        if process and process.poll() is None:
            if platform.system() == "Windows":
                # On Windows, terminate() is the standard way to stop a process
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            else:
                # On Unix, try SIGINT first for a graceful KeyboardInterrupt-style shutdown
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGINT)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Then try SIGTERM
                        os.killpg(pgid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            # Finally SIGKILL
                            os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process = None
    finally:
        # Log cleanup action
        with open(log_file, 'a') as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server shutting down, notifying clients to clear cache\n")
        # Close the Flask server port
        close_port(args.port)
        print("Cleaned up resources and closed port")

def ensure_host_mapping(alias, ip="127.0.0.1"):
    """
    Ensure alias is mapped to the given IP in the system hosts file.
    Requires admin/root privileges.
    """
    if platform.system() == "Windows":
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    else:  # Linux, macOS
        hosts_path = "/etc/hosts"

    try:
        # Read current hosts file
        with open(hosts_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Check if alias already mapped
        for line in lines:
            if alias in line:
                print(f"[INFO] '{alias}' already mapped in hosts file.")
                return

        # Append mapping
        with open(hosts_path, "a", encoding="utf-8") as f:
            f.write(f"\n{ip}   {alias}\n")

        print(f"[INFO] Added mapping: {ip} -> {alias} in {hosts_path}")

    except PermissionError:
        print(f"[ERROR] Permission denied while modifying {hosts_path}.")
        print("Run this script with administrator/root privileges.")
    except Exception as e:
        print(f"[ERROR] Failed to update hosts file: {e}")