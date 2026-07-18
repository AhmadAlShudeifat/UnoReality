# launcher.py

import subprocess
import time
import os

# =========================
# CONFIG
# =========================

# Path to Virtual Motion Tracker executable
# Change this if needed
VMT_PATH = r"C:\vmt_driver\vmt_manager/vmt_manager.exe"

# =========================
# START VR BRIDGE
# =========================

print("Starting vrbridge.py...")
subprocess.Popen(
    ["python", "vrbridge.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE
)

# wait 2 seconds
time.sleep(1)

# =========================
# START TRACKER
# =========================

print("Starting tt.py...")
subprocess.Popen(
    ["python", "tt.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE
)

# small delay so sockets initialize
time.sleep(2)

# =========================
# START VMT
# =========================

print("Starting Virtual Motion Tracker...")

if os.path.exists(VMT_PATH):
    subprocess.Popen([VMT_PATH])
else:
    print("VMT executable not found.")
    print("Edit VMT_PATH in launcher.py")