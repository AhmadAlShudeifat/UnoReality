import socket
import cv2
import mediapipe as mp
import numpy as np
import threading
import queue
import time

MASTER_HOST = '127.0.0.1'
MASTER_PORT = 6738
BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 2893

frame_queue = queue.Queue(maxsize=2)
bridge_queue = queue.Queue(maxsize=1024)

mp_hands = mp.solutions.hands
hands_processor = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    model_complexity=0,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

def rx_matrix_to_quat(R):
    tr = np.trace(R)
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R[2,1] - R[1,2]) / S
        qy = (R[0,2] - R[2,0]) / S
        qz = (R[1,0] - R[0,1]) / S
    elif (R[0,0] > R[1,1]) and (R[0,0] > R[2,2]):
        S = np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2]) * 2
        qw = (R[2,1] - R[1,2]) / S
        qx = 0.25 * S
        qy = (R[0,1] + R[1,0]) / S
        qz = (R[0,2] + R[2,0]) / S
    elif R[1,1] > R[2,2]:
        S = np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2]) * 2
        qw = (R[0,2] - R[2,0]) / S
        qx = (R[0,1] + R[1,0]) / S
        qy = 0.25 * S
        qz = (R[1,2] + R[2,1]) / S
    else:
        S = np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1]) * 2
        qw = (R[1,0] - R[0,1]) / S
        qx = (R[0,2] + R[2,0]) / S
        qy = (R[1,2] + R[2,1]) / S
        qz = 0.25 * S
    return qx, qy, qz, qw

def compute_dist(p1, p2):
    return np.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

def bridge_socket_writer():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.connect((BRIDGE_HOST, BRIDGE_PORT))
            print("Connected to VR Bridge Sub-Server!")
            while True:
                data = bridge_queue.get()
                if data:
                    sock.sendall(data.encode('utf-8'))
        except Exception:
            time.sleep(2)

def mipi_camera_receiver():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.connect((MASTER_HOST, MASTER_PORT))
            print("Connected to Master ESP32 Camera Stream!")
            buffer = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk: break
                buffer += chunk
                while b'V' in buffer:
                    tag_idx = buffer.find(b'V')
                    buffer = buffer[tag_idx:]
                    if len(buffer) < 5: break
                    start_img = buffer.find(b'\xff\xd8')
                    if start_img == -1:
                        buffer = buffer[1:]
                        continue
                    end_img = buffer.find(b'\xff\xd9')
                    if end_img == -1: break
                    jpeg_data = buffer[start_img:end_img+2]
                    buffer = buffer[end_img+2:]
                    nparr = np.frombuffer(jpeg_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        try:
                            frame_queue.put_nowait(img)
                        except queue.Full:
                            try: frame_queue.get_nowait()
                            except queue.Empty: pass
                            frame_queue.put_nowait(img)
        except Exception:
            time.sleep(2)

def tracking_worker():
    while True:
        frame = frame_queue.get()
        if frame is None: continue
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands_processor.process(rgb_frame)
        if results.multi_hand_landmarks and results.multi_handedness:
            for idx, hand_lms in enumerate(results.multi_hand_landmarks):
                lbl = results.multi_handedness[idx].classification.label
                device_id = 1 if lbl == "Left" else 2
                lms = hand_lms.landmark
                wrist = lms[0]
                index_mcp = lms[5]
                pinky_mcp = lms[17]
                ref_dist = np.sqrt((wrist.x - index_mcp.x)**2 + (wrist.y - index_mcp.y)**2)
                pos_x = (wrist.x - 0.5) * 2.0
                pos_y = -(wrist.y - 0.5) * 2.0
                pos_z = 1.0 / (ref_dist + 0.001)
                v1 = np.array([index_mcp.x - wrist.x, index_mcp.y - wrist.y, index_mcp.z - wrist.z])
                v2 = np.array([pinky_mcp.x - wrist.x, pinky_mcp.y - wrist.y, pinky_mcp.z - wrist.z])
                norm_z = np.cross(v1, v2)
                norm_z /= np.linalg.norm(norm_z)
                norm_x = v1 / np.linalg.norm(v1)
                norm_y = np.cross(norm_z, norm_x)
                R = np.column_stack((norm_x, norm_y, norm_z))
                qx, qy, qz, qw = rx_matrix_to_quat(R)
                pinch = compute_dist(lms[4], lms[8]) < 0.04
                m_curl = compute_dist(lms[12], wrist) < compute_dist(lms[10], wrist)
                r_curl = compute_dist(lms[16], wrist) < compute_dist(lms[14], wrist)
                p_curl = compute_dist(lms[20], wrist) < compute_dist(lms[18], wrist)
                f_fist = m_curl and r_curl and p_curl
                enable_flag = 1 if (pinch or f_fist) else 0
                thumb_to_palm = compute_dist(lms[4], lms[17])
                joystick_flag = 1 if thumb_to_palm < 0.06 else 0
                
                tracking_packet = f"[{enable_flag},{device_id},0.0,{pos_x:.4f},{pos_y:.4f},{pos_z:.4f},{qx:.4f},{qy:.4f},{qz:.4f},{qw:.4f}]\n"
                try:
                    bridge_queue.put_nowait(tracking_packet)
                except queue.Full:
                    pass

if __name__ == "__main__":
    threading.Thread(target=mipi_camera_receiver, daemon=True).start()
    threading.Thread(target=bridge_socket_writer, daemon=True).start()
    tracking_worker()
