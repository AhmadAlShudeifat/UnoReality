import socket
import re
import threading
from pythonosc.udp_client import SimpleUDPClient

OSCADRESS = '127.0.0.1'
OSCPORT = 39570

VMTPATH = "/VMT/Room/Unity"

sO = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sO.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sO.bind(('127.0.0.1', 2893))
sO.listen(1)

testsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
testsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
testsocket.bind(('127.0.0.1', 3289))
testsocket.listen(1)

on = 0
hmd = 0
lc = 1
rc = 2
to = 0.0

hmd_qx = 0.0
hmd_qy = 0.0
hmd_qz = 0.0
hmd_qw = 1.0
hmd_x = 0.0
hmd_y = 0.0
hmd_z = 0.0

lc_qx = 0.0
lc_qy = 0.0
lc_qz = 0.0
lc_qw = 1.0
lc_x = 0.0
lc_y = 0.0
lc_z = 0.0

rc_qx = 0.0
rc_qy = 0.0
rc_qz = 0.0
rc_qw = 1.0
rc_x = 0.0
rc_y = 0.0
rc_z = 0.0

client = SimpleUDPClient(OSCADRESS, OSCPORT)

# client.send_message("/vmt/room/moveuser", [0, 1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]) (this is how the format should look like)

def hmd_tracking(numbers):
    global hmd_qw, hmd_qx, hmd_qy, hmd_qz, hmd_x, hmd_y, hmd_z, on
    if numbers[1] != '0':
         return
    on = int(numbers[0])
    hmd_x = float(numbers[3])
    hmd_y = float(numbers[4])
    hmd_z = float(numbers[5])
    hmd_qx = float(numbers[6])
    hmd_qy = float(numbers[7])
    hmd_qz = float(numbers[8])
    hmd_qw = float(numbers[9])

    hmd_packet = [hmd, on, to, hmd_x, hmd_y, hmd_z, hmd_qx, hmd_qy, hmd_qz, hmd_qw]
    client.send_message(VMTPATH, hmd_packet)

def lc_tracking(numbers):
     global lc_qw, lc_qx, lc_qy, lc_qz, lc_x, lc_y, lc_z, on
     if numbers[1] != '1':
         return
     on = int(numbers[0])
     lc_x = float(numbers[3])
     lc_y = float(numbers[4])
     lc_z = float(numbers[5])
     lc_qx = float(numbers[6])
     lc_qy = float(numbers[7])
     lc_qz = float(numbers[8])
     lc_qw = float(numbers[9])

     lc_packet = [lc, on, to, lc_x, lc_y, lc_z, lc_qx, lc_qy, lc_qz, lc_qw]
     client.send_message(VMTPATH, lc_packet)
     

def rc_tracking(numbers):
     global rc_qw, rc_qx, rc_qy, rc_qz, rc_x, rc_y, rc_z, on
     if numbers[1] != '2':
         return
     on = int(numbers[0])
     rc_x = float(numbers[3])
     rc_y = float(numbers[4])
     rc_z = float(numbers[5])
     rc_qx = float(numbers[6])
     rc_qy = float(numbers[7])
     rc_qz = float(numbers[8])
     rc_qw = float(numbers[9])
     
     rc_packet = [rc, on, to, rc_x, rc_y, rc_z, rc_qx, rc_qy, rc_qz, rc_qw]
     client.send_message(VMTPATH, rc_packet)

def RunAllTrackers(numbers):
    if len(numbers) < 10:
        return
    lc_tracking(numbers)
    rc_tracking(numbers)
    hmd_tracking(numbers)

def hmdloop():
    
     ts, addr = testsocket.accept()
     while True:
            raw_text = ts.recv(4096).decode('utf-8').strip()
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", raw_text)
            RunAllTrackers(numbers)

def lc_rcloop():
    lc_rc, addr = sO.accept()
    while True:
        rawtext = lc_rc.recv(4096).decode('utf-8').strip()
        if not rawtext:
            break
        number = re.findall(r"[-+]?\d*\.\d+|\d+", rawtext)
        RunAllTrackers(number)

hmd_tracker = threading.Thread(target=hmdloop, daemon=True)
hand_tracker = threading.Thread(target=lc_rcloop, daemon=True)

try:
    hmd_tracker.start()
    hand_tracker.start()
    while True:
        threading.Event().wait(1.0)
except KeyboardInterrupt:
     print("Stopping the VR Bridge")
