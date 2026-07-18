import pyaudiowpatch as pyaudio
import serial
import numpy as np
import time
import threading
import queue
import subprocess
import tempfile
import os
import sys
import shutil
from math import gcd
from scipy.signal import resample_poly, lfilter, lfilter_zi
import socket
import struct  

CHUNK_SIZE     = 1024
TARGET_RATE    = 48000
GATE_THRESHOLD = 0.004

p                = pyaudio.PyAudio()
wasapi_info      = p.get_host_api_info_by_type(pyaudio.paWASAPI)
default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
if not default_speakers["isLoopbackDevice"]:
    for loopback in p.get_loopback_device_info_generator():
        if default_speakers["name"] in loopback["name"]:
            default_speakers = loopback
            break

device_rate = int(default_speakers["defaultSampleRate"])
_g          = gcd(TARGET_RATE, device_rate)
UP          = TARGET_RATE // _g
DOWN        = device_rate // _g
print(f"System rate: {device_rate} Hz → {TARGET_RATE} Hz ({UP}↑ / {DOWN}↓)")

volume      = 1.0
volume_lock = threading.Lock()

def volume_thread():
    global volume
    print("Type 0–100 to set volume.")
    while True:
        try:
            val = float(input().strip())    
            if 0.0 <= val <= 100.0:
                with volume_lock:
                    volume = val / 100.0
                print(f"Volume: {val:.0f}%")
            else:
                print("Enter 0–100.")
        except ValueError:
            print("Numbers only.")
        except EOFError:
            break

    threading.Thread(target=volume_thread, daemon=True).start()

write_queue = queue.Queue(maxsize=1024)

def serial_writer(sock):
    while True:
        data = write_queue.get()
        if data:
            try:
                sock.sendall(data)
            except Exception:
                break

rng    = np.random.default_rng()
_dc_b  = np.array([1.0, -1.0])
_dc_a  = np.array([1.0, -0.9975])
_state = {
    'dc_zi': lfilter_zi(_dc_b, _dc_a) * 0.0,
    'e1': 0.0,
    'e2': 0.0,
}

def quantize(samples):
    n   = len(samples)
    d1  = rng.uniform(-128.0, 128.0, n)
    d2  = rng.uniform(-128.0, 128.0, n)
    e1  = _state['e1']
    e2  = _state['e2']
    out = np.empty(n, dtype=np.uint8)
    for i in range(n):
        x      = samples[i] + (d1[i] + d2[i]) * 0.5 + 2.0 * e1 * 0.9999 - e2 * 0.9998
        q      = int(min(255.0, max(0.0, (x + 32768.0) * 0.00390625)))
        out[i] = q
        err    = x - (float(q) * 256.0 - 32768.0)
        e2     = e1
        e1     = max(-512.0, min(512.0, err))
    _state['e1'] = e1
    _state['e2'] = e2
    return out

def callback(in_data, frame_count, time_info, status):
    audio = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
    with volume_lock:
        vol = volume
    resampled              = resample_poly(audio, UP, DOWN)
    resampled             *= vol
    resampled, _state['dc_zi'] = lfilter(_dc_b, _dc_a, resampled, zi=_state['dc_zi'])
    max_val                = float(np.max(np.abs(resampled))) / 32768.0
    gate                   = float(np.clip((max_val - GATE_THRESHOLD) / GATE_THRESHOLD, 0.0, 1.0))
    if gate == 0.0:
        _state['e1'] = 0.0
        _state['e2'] = 0.0
        out = np.full(len(resampled), 128, dtype=np.uint8)
    else:
        resampled *= gate
        out = quantize(resampled)
    try:
        write_queue.put_nowait(out.tobytes())
    except queue.Full:
        pass
    return (None, pyaudio.paContinue)

stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=device_rate,
    input=True,
    input_device_index=default_speakers["index"],
    stream_callback=callback,
    frames_per_buffer=CHUNK_SIZE,
)
stream.start_stream()
print("Streaming — Ctrl+C to stop.")

try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(('127.0.0.1', 7436))
            threading.Thread(target=serial_writer, args=(s,), daemon=True).start()
            while stream.is_active():
                time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopping...")
    stream.stop_stream()
    stream.close()
    p.terminate()