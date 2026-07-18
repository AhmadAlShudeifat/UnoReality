import socket
import time
import threading
import queue
import cv2
import mss
import numpy as np
import struct

WIDTH = 1024
HEIGHT = 600
FPS = 60
FRAME_DELAY = 1.0 / FPS
HOST = '127.0.0.1'
PORT = 5438
JPEG_QUALITY = 80

write_queue = queue.Queue(maxsize=30)

def socket_writer(sock):
    while True:
        data = write_queue.get()
        if data:
            try:
                sock.sendall(data)
            except Exception:
                print("Socket video transmission failed.")
                break

def capture_thread():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            start_time = time.perf_counter()
            
            img = np.array(sct.grab(monitor))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            resized = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
            
            success, encoded_img = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if success:
                jpeg_bytes = encoded_img.tobytes()
                data_size = len(jpeg_bytes)
                
                header = b'VID!' + struct.pack('>I', data_size)
                packet = header + jpeg_bytes
                
                try:
                    write_queue.put_nowait(packet)
                except queue.Full:
                    pass
            
            elapsed = time.perf_counter() - start_time
            sleep_time = FRAME_DELAY - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

if __name__ == "__main__":
    print(f"Connecting to video broker at {HOST}:{PORT}...")
    threading.Thread(target=capture_thread, daemon=True).start()
    
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                print("Video stream connected to broker.")
                writer_thread = threading.Thread(target=socket_writer, args=(s,), daemon=True)
                writer_thread.start()
                while writer_thread.is_alive():
                    time.sleep(0.5)
        except (socket.error, KeyboardInterrupt):
            print("Broker unreachable. Reconnecting in 2 seconds...")
            time.sleep(2)
