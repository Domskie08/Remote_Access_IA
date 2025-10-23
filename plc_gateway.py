#!/usr/bin/env python3
import socket
import threading

PLC_IP = "192.168.0.10"   # <-- change to your PLC IP
PLC_PORT = 102

PI_LISTEN_IP = "0.0.0.0"
PI_LISTEN_PORT = 102

plc_lock = threading.Lock()

def handle_client(client_socket, client_addr):
    print(f"[INFO] Student connected: {client_addr}")

    if not plc_lock.acquire(blocking=False):
        client_socket.send(b"PLC BUSY, try again later.\n")
        client_socket.close()
        return

    try:
        plc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        plc_socket.connect((PLC_IP, PLC_PORT))

        def forward(src, dst):
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)

        t1 = threading.Thread(target=forward, args=(client_socket, plc_socket))
        t2 = threading.Thread(target=forward, args=(plc_socket, client_socket))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    finally:
        plc_lock.release()
        client_socket.close()
        print(f"[INFO] PLC free now.")

def start_gateway():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((PI_LISTEN_IP, PI_LISTEN_PORT))
    server.listen(5)
    print(f"[INFO] PLC Gateway listening on {PI_LISTEN_IP}:{PI_LISTEN_PORT}")

    while True:
        client_socket, client_addr = server.accept()
        threading.Thread(target=handle_client, args=(client_socket, client_addr)).start()

if __name__ == "__main__":
    start_gateway()
