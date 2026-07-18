import cv2
import mediapipe as mp
import numpy as np
import socket
import time
import math
import threading
import collections

# =========================================
# SOCKETS
#   head_sock (3289) — head tracker  (device 0)
#   hand_sock (2893) — hands         (devices 1, 2)
# =========================================

head_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
head_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
hand_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
hand_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

print("Connecting...")
head_sock.connect(("127.0.0.1", 3289))
hand_sock.connect(("127.0.0.1", 2893))
print("Connected.")

# =========================================
# CAMERA INTRINSICS
# =========================================

CAM_W  = 1280
CAM_H  = 720
CAM_FX = 700.0
CAM_FY = 700.0
CAM_CX = CAM_W / 2.0
CAM_CY = CAM_H / 2.0

# wrist-to-middle-knuckle real size in metres — adjust to your hand
HAND_REAL_SIZE_M = 0.085

# Nose-to-eye distance in metres — used for head depth estimation
# Average ~3.5 cm between nose tip and eye outer corner
HEAD_REAL_SIZE_M = 0.035

# =========================================
# ONE-EURO FILTER  — adaptive smoothing, stable when still, fast when moving
# =========================================

class OneEuro:
    def __init__(self, freq=60.0, min_cutoff=2.0, beta=0.08, d_cutoff=1.0):
        self.freq       = freq
        self.min_cutoff = min_cutoff
        self.beta       = beta
        self.d_cutoff   = d_cutoff
        self.x_prev     = None
        self.dx_prev    = 0.0
        self.t_prev     = None

    def _alpha(self, cutoff):
        te  = 1.0 / self.freq
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x, t=None):
        if t is None:
            t = time.time()
        if self.x_prev is None:
            self.x_prev  = x
            self.t_prev  = t
            return x
        dt = t - self.t_prev
        if dt > 0:
            self.freq = 1.0 / dt
        self.t_prev = t
        dx     = (x - self.x_prev) * self.freq
        a_d    = self._alpha(self.d_cutoff)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        self.dx_prev = dx_hat
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a      = self._alpha(cutoff)
        x_hat  = a * x + (1.0 - a) * self.x_prev
        self.x_prev = x_hat
        return x_hat

def make_filters(n, **kw):
    return [OneEuro(**kw) for _ in range(n)]

# =========================================
# MEDIAPIPE
# =========================================

BaseOptions       = mp.tasks.BaseOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Hands — position + rotation from landmarks
hand_detector = mp.tasks.vision.HandLandmarker.create_from_options(
    mp.tasks.vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path="hand_landmarker.task"),
        num_hands=2,
        running_mode=VisionRunningMode.VIDEO,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
)

# Face — position from landmark geometry + rotation from transformation matrix
face_detector = mp.tasks.vision.FaceLandmarker.create_from_options(
    mp.tasks.vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path="face_landmarker.task"),
        num_faces=1,
        running_mode=VisionRunningMode.VIDEO,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_facial_transformation_matrixes=True,
    )
)

# =========================================
# CAMERA
# =========================================

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
cap.set(cv2.CAP_PROP_FPS,          60)
cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
if not cap.isOpened():
    print("Camera failed"); exit()

# =========================================
# HELPERS
# =========================================

def send_packet(sock, device, x, y, z, qx, qy, qz, qw):
    msg = (f"1 {device} 0 "
           f"{x:.6f} {y:.6f} {z:.6f} "
           f"{qx:.6f} {qy:.6f} {qz:.6f} {qw:.6f}\n")
    try:
        sock.send(msg.encode())
    except Exception:
        pass

def pixel_to_world(px, py, z_m):
    x_m =  (px - CAM_CX) * z_m / CAM_FX
    y_m = -((py - CAM_CY) * z_m / CAM_FY)
    return x_m, y_m, -z_m

def mat4_to_quat(m):
    """Standard Shepperd method — stable across all rotations."""
    m00,m01,m02 = float(m[0][0]),float(m[0][1]),float(m[0][2])
    m10,m11,m12 = float(m[1][0]),float(m[1][1]),float(m[1][2])
    m20,m21,m22 = float(m[2][0]),float(m[2][1]),float(m[2][2])
    trace = m00 + m11 + m22
    if trace > 0:
        s  = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (m21 - m12) * s
        qy = (m02 - m20) * s
        qz = (m10 - m01) * s
    elif m00 > m11 and m00 > m22:
        s  = 2.0 * math.sqrt(max(1e-10, 1.0 + m00 - m11 - m22))
        qw = (m21 - m12) / s; qx = 0.25 * s
        qy = (m01 + m10) / s; qz = (m02 + m20) / s
    elif m11 > m22:
        s  = 2.0 * math.sqrt(max(1e-10, 1.0 + m11 - m00 - m22))
        qw = (m02 - m20) / s; qx = (m01 + m10) / s
        qy = 0.25 * s;        qz = (m12 + m21) / s
    else:
        s  = 2.0 * math.sqrt(max(1e-10, 1.0 + m22 - m00 - m11))
        qw = (m10 - m01) / s; qx = (m02 + m20) / s
        qy = (m12 + m21) / s; qz = 0.25 * s
    n = math.sqrt(qx*qx + qy*qy + qz*qz + qw*qw) + 1e-10
    return qx/n, qy/n, qz/n, qw/n

def build_rot_quat(forward, right):
    """Rotation quaternion from forward + right direction vectors."""
    fx,fy,fz = forward
    rx,ry,rz = right
    fn = math.sqrt(fx*fx+fy*fy+fz*fz) + 1e-9
    fx,fy,fz = fx/fn, fy/fn, fz/fn
    rn = math.sqrt(rx*rx+ry*ry+rz*rz) + 1e-9
    rx,ry,rz = rx/rn, ry/rn, rz/rn
    ux = ry*fz - rz*fy
    uy = rz*fx - rx*fz
    uz = rx*fy - ry*fx
    m  = [[rx,ux,-fx,0],[ry,uy,-fy,0],[rz,uz,-fz,0],[0,0,0,1]]
    return mat4_to_quat(m)

# =========================================
# SHARED TRACKER STATE
# head: device 0 — face landmark position + transformation matrix rotation
# left: device 1 — hand landmarks
# right: device 2 — hand landmarks
# =========================================

state_lock = threading.Lock()

# One-euro filters: x y z qx qy qz qw per device
# Head: tighter min_cutoff = very stable, beta = responsive to fast movement
head_f = make_filters(7, min_cutoff=3.0, beta=0.10)
lh_f   = make_filters(7, min_cutoff=3.0, beta=0.12)
rh_f   = make_filters(7, min_cutoff=3.0, beta=0.12)

head_state = dict(x=0.0, y=1.0, z=0.0, qx=0.0,qy=0.0,qz=0.0,qw=1.0, active=False)
lh_state   = dict(x=0.0, y=1.0, z=0.0, qx=0.0,qy=0.0,qz=0.0,qw=1.0, active=False)
rh_state   = dict(x=0.0, y=1.0, z=0.0, qx=0.0,qy=0.0,qz=0.0,qw=1.0, active=False)

# =========================================
# HAND WORKER THREAD
# =========================================

hand_frame_lock = threading.Lock()
_hand_frame     = [None, 0]
hand_evt        = threading.Event()

def hand_worker():
    while True:
        hand_evt.wait(); hand_evt.clear()
        with hand_frame_lock:
            if _hand_frame[0] is None: continue
            frame = _hand_frame[0]; ts = _hand_frame[1]

        W_px, H_px = frame.shape[1], frame.shape[0]
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = hand_detector.detect_for_video(mp_img, ts)

        new = {1: None, 2: None}
        if result.hand_landmarks:
            for idx, lm in enumerate(result.hand_landmarks):
                wrist    = lm[0]
                idx_mcp  = lm[5]
                mid_mcp  = lm[9]
                pink_mcp = lm[17]

                wx = wrist.x * W_px;   wy = wrist.y * H_px
                mx = mid_mcp.x * W_px; my = mid_mcp.y * H_px

                span_px = math.hypot(mx - wx, my - wy)
                z_m     = max(0.05, min(4.0,
                    (HAND_REAL_SIZE_M * CAM_FX) / max(span_px, 5)))

                tx, ty, tz = pixel_to_world(wx, wy, z_m)
                ty += 1.0   # centre height

                fwd = ((mid_mcp.x  - wrist.x)   * W_px,
                       (mid_mcp.y  - wrist.y)   * H_px,
                       (mid_mcp.z  - wrist.z)   * W_px)
                rgt = ((pink_mcp.x - idx_mcp.x) * W_px,
                       (pink_mcp.y - idx_mcp.y) * H_px,
                       (pink_mcp.z - idx_mcp.z) * W_px)

                qx, qy, qz, qw = build_rot_quat(fwd, rgt)
                hness  = result.handedness[idx][0].category_name
                device = 2 if hness == "Left" else 1
                new[device] = (tx, ty, tz, qx, qy, qz, qw)

        t = time.time()
        with state_lock:
            for dev, st, filt in ((1, lh_state, lh_f), (2, rh_state, rh_f)):
                if new[dev] is not None:
                    tx,ty,tz,qx,qy,qz,qw = new[dev]
                    st['x']  = filt[0](tx, t);  st['y']  = filt[1](ty, t)
                    st['z']  = filt[2](tz, t);  st['qx'] = filt[3](qx, t)
                    st['qy'] = filt[4](qy, t);  st['qz'] = filt[5](qz, t)
                    st['qw'] = filt[6](qw, t);  st['active'] = True
                else:
                    st['active'] = False

hand_thread = threading.Thread(target=hand_worker, daemon=True)
hand_thread.start()

# =========================================
# FACE WORKER THREAD
# Head position: derived from face landmark geometry (inter-eye distance -> depth)
# Head rotation: from facial_transformation_matrixes (full 4x4, no gimbal lock)
# Same pipeline as hands — no blue blob, no color tracking
# =========================================

face_frame_lock = threading.Lock()
_face_frame     = [None, 0]
face_evt        = threading.Event()

# Landmark indices (MediaPipe 478-point model)
NOSE_TIP      = 4
LEFT_EYE_OUT  = 263   # outer corner left eye
RIGHT_EYE_OUT = 33    # outer corner right eye

# Real inter-eye distance in metres (~6.3 cm average)
EYE_DIST_REAL_M = 0.063

def face_worker():
    while True:
        face_evt.wait(); face_evt.clear()
        with face_frame_lock:
            if _face_frame[0] is None: continue
            frame = _face_frame[0]; ts = _face_frame[1]

        W_px, H_px = frame.shape[1], frame.shape[0]
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = face_detector.detect_for_video(mp_img, ts)

        t = time.time()
        with state_lock:
            s = head_state
            if result.face_landmarks and result.facial_transformation_matrixes:
                lm = result.face_landmarks[0]

                # --- Position: inter-eye distance gives depth ---
                le = lm[LEFT_EYE_OUT]
                re = lm[RIGHT_EYE_OUT]

                eye_px = math.hypot(
                    (le.x - re.x) * W_px,
                    (le.y - re.y) * H_px
                )
                z_m = max(0.1, min(3.0,
                    (EYE_DIST_REAL_M * CAM_FX) / max(eye_px, 5)))

                # Use nose tip as the anchor point for XY
                nose = lm[NOSE_TIP]
                tx, ty, tz = pixel_to_world(nose.x * W_px, nose.y * H_px, z_m)
                ty += 1.0   # centre height

                # --- Rotation: full 4x4 from MediaPipe ---
                mat = result.facial_transformation_matrixes[0]
                m   = np.array(mat.data).reshape(4, 4)
                qx, qy, qz, qw = mat4_to_quat(m)

                s['x']  = head_f[0](tx, t);  s['y']  = head_f[1](ty, t)
                s['z']  = head_f[2](tz, t);  s['qx'] = head_f[3](qx, t)
                s['qy'] = head_f[4](qy, t);  s['qz'] = head_f[5](qz, t)
                s['qw'] = head_f[6](qw, t);  s['active'] = True
            else:
                s['active'] = False

face_thread = threading.Thread(target=face_worker, daemon=True)
face_thread.start()

# =========================================
# MAIN LOOP  — camera capture + dispatch only
# =========================================

prev = time.time()

while True:
    ret, frame = cap.read()
    if not ret: continue

    frame = cv2.flip(frame, 1)
    ts    = int(time.time() * 1000)

    # Dispatch latest frame to both worker threads (non-blocking)
    fc = frame.copy()
    with hand_frame_lock:
        _hand_frame[0] = fc; _hand_frame[1] = ts
    hand_evt.set()

    with face_frame_lock:
        _face_frame[0] = fc; _face_frame[1] = ts
    face_evt.set()

    # ------------------------------------------------------------------
    # SEND PACKETS  (snapshot state, release lock immediately)
    # ------------------------------------------------------------------
    with state_lock:
        hs = dict(head_state)
        ls = dict(lh_state)
        rs = dict(rh_state)

    if hs['active']:
        send_packet(head_sock, 0,
                    hs['x'],hs['y'],hs['z'],
                    hs['qx'],hs['qy'],hs['qz'],hs['qw'])
    if ls['active']:
        send_packet(hand_sock, 1,
                    ls['x'],ls['y'],ls['z'],
                    ls['qx'],ls['qy'],ls['qz'],ls['qw'])
    if rs['active']:
        send_packet(hand_sock, 2,
                    rs['x'],rs['y'],rs['z'],
                    rs['qx'],rs['qy'],rs['qz'],rs['qw'])

    # ------------------------------------------------------------------
    # OVERLAY
    # ------------------------------------------------------------------
    H, W = frame.shape[:2]

    if hs['active']:
        cv2.putText(frame,
            f"HEAD x:{hs['x']:.2f} y:{hs['y']:.2f} z:{hs['z']:.2f}",
            (20,80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,80,0), 2)
    if ls['active']:
        cv2.putText(frame,
            f"L x:{ls['x']:.2f} y:{ls['y']:.2f} z:{ls['z']:.2f}",
            (20,110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 2)
    if rs['active']:
        cv2.putText(frame,
            f"R x:{rs['x']:.2f} y:{rs['y']:.2f} z:{rs['z']:.2f}",
            (20,140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,100), 2)

    now  = time.time()
    fps  = 1.0 / max(now - prev, 1e-6)
    prev = now
    cv2.putText(frame, f"FPS:{int(fps)}", (20,40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

    cv2.imshow("VR Tracking", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
head_sock.close()
hand_sock.close()