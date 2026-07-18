import serial
import socket
import sys
import os
import shutil
import tempfile
import subprocess
import time
import threading
import queue

SP = 'COM3'
BR = '500000'
FQBN = 'esp32:esp32:esp32p4'
FIRMWARE = 'C:/users/ahmad alshudeifat/desktop/unoreality/firmware.cpp'

MAINHOST = '192.168.1.50'
MAINPORT = 6738

mainqueue = queue.Queue(maxsize=4096)
mainlock = threading.Lock()

def find_cli():
        cli = shutil.which('arduino-cli')
        if cli: return cli
        candidates = [
            r'C:\Program Files\Arduino CLI\arduino-cli.exe',
            os.path.expanduser(r'~\AppData\Local\Arduino15\arduino-cli.exe'),
            os.path.expanduser('~/bin/arduino-cli'),
            os.path.expanduser('~/arduino-cli'),
        ]
        for c in candidates:
            if os.path.isfile(c): return c
        return None

def upload():
        cli = find_cli()
        if not cli:
            print("arduino-cli not found — install from https://arduino.github.io/arduino-cli")
            sys.exit(1)
        tmp        = tempfile.mkdtemp()
        sketch_dir = os.path.join(tmp, 'audio_sketch')
        os.makedirs(sketch_dir)
        try:
            with open(FIRMWARE, 'r') as source_file:
                actual_cpp_code = source_file.read()
        except Exception as e:
            print(f"Failed to read your firmware file path: {e}")
            sys.exit(1)
        with open(os.path.join(sketch_dir, 'audio_sketch.ino'), 'w') as f:
            f.write(actual_cpp_code)
        print("Compiling...")
        r = subprocess.run([cli, 'compile', '--fqbn', FQBN, sketch_dir], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr); sys.exit(1)
        print("Uploading...")
        r = subprocess.run([cli, 'upload', '-p', SP, '--fqbn', FQBN, sketch_dir], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr); sys.exit(1)
        print("Upload done — waiting for reset...")
        time.sleep(0.1)

upload()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', 7436))
s.listen(1)

sO = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sO.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sO.bind(('127.0.0.1', 9234))
sO.listen(1)

sT = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sT.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sT.bind(('127.0.0.1', 5438))
sT.listen(1)

sound, addr = s.accept() 
screen, addr = sT.accept()
tracker, addr = sO.accept()

print(f"Connecting to main Server at {MAINHOST}:{MAINPORT}...")
while True:
    try:
        mainsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mainsock.connect((MAINHOST, MAINPORT))
        print("Connected to main Socket Hub successfully!")
        break
    except Exception:
        print("main Socket server not ready retrying in 2 seconds...")
        time.sleep(2)

def mainwriterworker():
    while True:
        packet = mainqueue.get()
        if packet:
            try:
                with mainlock:
                    mainsock.sendall(packet)
            except Exception as e:
                print(f"main socket pipeline broken: {e}")
                break

threading.Thread(target=mainwriterworker, daemon=True).start()

def audio():
    print("connected to audio")
    while True:
        try:
            chunk = sound.recv(1024)
            if not chunk: break
            mainqueue.put(b'A' + chunk)
        except Exception:
            break

def tracking():
    print("connected to tracker")
    buffer = b""
    while True:
        try:
            chunk = tracker.recv(1024)
            if not chunk:
                break
            buffer += chunk

            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line:
                    continue
                mainqueue.put(b'T' + line + b'\n')

        except Exception as e:
            print("tracking error", e)
            break

def display():
    print("connected to display")
    while True:
        try:
            chunk = screen.recv(1024)
            if not chunk: break
            mainqueue.put(b'V' + chunk)
        except Exception:
            break

try:
     threading.Thread(target=audio, daemon=True).start()
     threading.Thread(target=display, daemon=True).start()
     threading.Thread(target=tracking, daemon=True).start()

     while True:
           time.sleep(0.1)
except KeyboardInterrupt:
     print("Stopping...")
finally:
    sound.close()
    screen.close()
    s.close()
    sO.close()
    sT.close()
    mainsock.close()