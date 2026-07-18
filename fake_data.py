import socket
import math
import time
import sys

HOST = '127.0.0.1'
PORT = 9234

def quaternion_from_yaw(yaw):
    half = yaw / 2.0
    return (0.0, math.sin(half), 0.0, math.cos(half))

def format_packet(index, x, y, z, qx, qy, qz, qw):
    return f"{1} {index} {x:.4f} {y:.4f} {z:.4f} {qx:.4f} {qy:.4f} {qz:.4f} {qw:.4f}\n"

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Fake data server listening on port {PORT}...")
    print("READY")
    sys.stdout.flush()

    conn, addr = server.accept()
    print(f"vrbridge connected: {addr}")

    print("Type 'begin' to start sending fake tracking data to OSC")

    while True:
        cmd = input().strip().lower()
        if cmd == 'begin':
            break
        print("Type 'begin' to start")

    print("Sending fake tracking data...")
    angle = 0.0
    SPEED = 0.005
    try:
        while True:
            qx, qy, qz, qw = quaternion_from_yaw(angle)
            hmd = format_packet(0,  0.0, 1.7,  0.0, qx, qy, qz, qw)
            lc  = format_packet(1, -0.3, 1.2,  0.3, qx, qy, qz, qw)
            rc  = format_packet(2,  0.3, 1.2,  0.3, qx, qy, qz, qw)
            conn.sendall((hmd + lc + rc).encode('utf-8'))
            angle += SPEED
            if angle >= 2 * math.pi:
                angle = 0.0
            time.sleep(0.011)
    except KeyboardInterrupt:
        print("Fake data stopped")
        conn.close()
        server.close()
        sys.exit(0)

if __name__ == '__main__':
    main()