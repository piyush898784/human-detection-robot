"""
Human Detection Robot — Enhanced HUD with VitTrack + face_recognition
=====================================================================
Training: Put photos in  known_faces/<PersonName>/photo1.jpg  (multiple photos = better accuracy)
          OR a flat file  known_faces/<PersonName>.jpg
Run:      python final.py
Quit:     Press ESC
"""

import cv2
import numpy as np
import face_recognition
import os
import time
from datetime import datetime
from collections import deque

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
HORIZONTAL_FOV   = 60          # degrees
VERTICAL_FOV     = 45          # degrees
DETECT_EVERY_N   = 4           # run face_recognition every N frames
FACE_DIST_THRESH = 0.50        # lower = stricter match (0.6 is default)
VITTRACK_MODEL   = "vittrack.onnx"
KNOWN_FACES_DIR  = "known_faces"

# ─── Colours (BGR) ───────────────────────────
C_KNOWN   = (0, 255, 136)      # neon green
C_UNKNOWN = (51, 51, 255)      # red
C_CYAN    = (255, 200, 0)      # cyan
C_WHITE   = (255, 255, 255)
C_AMBER   = (0, 170, 255)
C_DIM     = (120, 120, 120)

# ─────────────────────────────────────────────
# HUD DRAWING HELPERS
# ─────────────────────────────────────────────

def hud_panel(frame, x, y, w, h, alpha=0.55, color=(15, 15, 25)):
    ov = frame.copy()
    cv2.rectangle(ov, (x, y), (x + w, y + h), color, -1)
    cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)


def corner_brackets(frame, x1, y1, x2, y2, color, t=2, seg=22):
    """Draw corner-bracket style bounding box with glow."""
    # Glow layer
    ov = frame.copy()
    for px, py, dx, dy in [(x1-2,y1-2,1,1),(x2+2,y1-2,-1,1),
                            (x1-2,y2+2,1,-1),(x2+2,y2+2,-1,-1)]:
        cv2.line(ov, (px,py), (px+dx*(seg+4),py), color, t*2)
        cv2.line(ov, (px,py), (px,py+dy*(seg+4)), color, t*2)
    cv2.addWeighted(ov, 0.35, frame, 0.65, 0, frame)
    # Main corners
    for px, py, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),
                            (x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(frame, (px,py), (px+dx*seg,py), color, t)
        cv2.line(frame, (px,py), (px,py+dy*seg), color, t)
    # Dashed border
    for p1, p2 in [((x1,y1),(x2,y1)), ((x1,y2),(x2,y2)),
                   ((x1,y1),(x1,y2)), ((x2,y1),(x2,y2))]:
        d = np.hypot(p2[0]-p1[0], p2[1]-p1[1])
        for i in np.arange(0, d, 10):
            r = i/d
            px = int(p1[0]*(1-r)+p2[0]*r)
            py = int(p1[1]*(1-r)+p2[1]*r)
            cv2.circle(frame, (px,py), 1, color, -1)


def crosshair(frame, cx, cy, sz=28, color=C_CYAN):
    cv2.line(frame, (cx-sz,cy), (cx+sz,cy), color, 1)
    cv2.line(frame, (cx,cy-sz), (cx,cy+sz), color, 1)
    cv2.circle(frame, (cx,cy), sz//3, color, 1)
    cv2.circle(frame, (cx,cy), 2, color, -1)


def pill_label(frame, text, x, y, bg_color, font_scale=0.55):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, 1)
    px, py = 8, 5
    ov = frame.copy()
    cv2.rectangle(ov, (x, y-th-py*2), (x+tw+px*2, y), bg_color, -1)
    cv2.addWeighted(ov, 0.80, frame, 0.20, 0, frame)
    cv2.putText(frame, text, (x+px, y-py), font, font_scale, C_WHITE, 1, cv2.LINE_AA)


def confidence_bar(frame, x, y, w, val, color):
    cv2.rectangle(frame, (x,y), (x+w, y+7), (40,40,40), -1)
    cv2.rectangle(frame, (x,y), (x+int(w*val), y+7), color, -1)
    cv2.rectangle(frame, (x,y), (x+w, y+7), C_DIM, 1)


def status_dot(frame, x, y, color, r=6):
    cv2.circle(frame, (x,y), r+2, (0,0,0), -1)
    cv2.circle(frame, (x,y), r, color, -1)


# ─────────────────────────────────────────────
# LOAD & TRAIN KNOWN FACES
# ─────────────────────────────────────────────

def load_known_faces(directory):
    """
    Supports two folder layouts:
      1. known_faces/Alice/img1.jpg  img2.jpg  ...   (multiple photos → averaged encoding)
      2. known_faces/Alice.jpg                        (single flat photo)
    Returns (encodings_list, names_list)
    """
    encodings, names = [], []
    os.makedirs(directory, exist_ok=True)

    # Layout 1 — subdirectories
    for entry in os.scandir(directory):
        if entry.is_dir():
            person_name = entry.name
            person_encs = []
            for img_file in os.scandir(entry.path):
                if img_file.name.lower().endswith(('.jpg','.jpeg','.png','.bmp')):
                    try:
                        img = face_recognition.load_image_file(img_file.path)
                        encs = face_recognition.face_encodings(img)
                        if encs:
                            person_encs.append(encs[0])
                    except Exception as e:
                        print(f"  ⚠ Skipped {img_file.path}: {e}")
            if person_encs:
                avg_enc = np.mean(person_encs, axis=0)  # average = more robust
                encodings.append(avg_enc)
                names.append(person_name)
                print(f"  ✔ {person_name}: trained on {len(person_encs)} photo(s)")

    # Layout 2 — flat files
    for img_file in os.scandir(directory):
        if img_file.is_file() and img_file.name.lower().endswith(('.jpg','.jpeg','.png','.bmp')):
            person_name = os.path.splitext(img_file.name)[0]
            if person_name in names:
                continue   # already loaded via subfolder
            try:
                img = face_recognition.load_image_file(img_file.path)
                encs = face_recognition.face_encodings(img)
                if encs:
                    encodings.append(encs[0])
                    names.append(person_name)
                    print(f"  ✔ {person_name}: trained on 1 photo")
            except Exception as e:
                print(f"  ⚠ Skipped {img_file.path}: {e}")

    return encodings, names


print("\n━━━ Loading known faces ━━━")
known_encodings, known_names = load_known_faces(KNOWN_FACES_DIR)
print(f"  Total known persons: {len(known_names)}\n")

# ─────────────────────────────────────────────
# KALMAN FILTER
# ─────────────────────────────────────────────
kalman = cv2.KalmanFilter(4, 2)
kalman.measurementMatrix = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
kalman.transitionMatrix  = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], np.float32)
kalman.processNoiseCov   = np.eye(4, dtype=np.float32) * 0.05
kalman_initialized = False


# ─────────────────────────────────────────────
# VITTRACK TRACKER SETUP
# ─────────────────────────────────────────────
def make_tracker():
    params = cv2.TrackerVit_Params()
    params.net = VITTRACK_MODEL
    return cv2.TrackerVit_create(params)


# ─────────────────────────────────────────────
# WEBCAM & STATE
# ─────────────────────────────────────────────
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Could not open webcam (index 0). Try changing VideoCapture index.")
    exit(1)

cv2.namedWindow("Human Detection Robot — HUD Monitor", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Human Detection Robot — HUD Monitor", 960, 600)

tracker       = make_tracker()
tracking      = False
tracked_name  = "Unknown"
conf_score    = 0.0
box_color     = C_UNKNOWN
trail         = deque(maxlen=40)

frame_idx  = 0
prev_time  = time.time()
fps_ema    = 0.0

yaw = pitch = 0.0
cmd = "● CENTERED"
success = False
last_bbox = None   # (x,y,w,h) of last detected face


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        break

    H, W, _ = frame.shape
    cx_f, cy_f = W // 2, H // 2
    frame_idx += 1

    # ── FPS ──────────────────────────────────
    now    = time.time()
    dt     = now - prev_time
    prev_time = now
    fps    = 1.0 / dt if dt > 0 else 0.0
    fps_ema = 0.85 * fps_ema + 0.15 * fps if fps_ema > 0 else fps

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # ── STATUS ───────────────────────────────
    s_text  = "SEARCHING"
    s_color = C_AMBER

    # ─────────────────────────────────────────
    # DETECTION PHASE  (every DETECT_EVERY_N frames OR tracker lost)
    # ─────────────────────────────────────────
    run_detection = (frame_idx % DETECT_EVERY_N == 0) or (not tracking)

    if run_detection:
        # face_recognition HOG detection — accurate, no extra model
        face_locs = face_recognition.face_locations(rgb, model="hog")

        if face_locs:
            # Pick the largest face (closest person)
            areas = [(r-t)*(ri-l) for (t,ri,b,l) in face_locs
                     for (r,b) in [(face_locs[0][2], face_locs[0][3])]]
            best  = max(range(len(face_locs)),
                        key=lambda i: (face_locs[i][2]-face_locs[i][0]) *
                                      (face_locs[i][1]-face_locs[i][3]))
            top, right, bottom, left = face_locs[best]
            bx, by = left, top
            bw, bh = right - left, bottom - top

            # ── RECOGNITION ──────────────────
            encs = face_recognition.face_encodings(rgb, [face_locs[best]])
            tracked_name = "Unknown"
            conf_score   = 0.0
            box_color    = C_UNKNOWN

            if encs and known_encodings:
                dists    = face_recognition.face_distance(known_encodings, encs[0])
                best_idx = int(np.argmin(dists))
                if dists[best_idx] < FACE_DIST_THRESH:
                    tracked_name = known_names[best_idx]
                    conf_score   = float(1.0 - dists[best_idx])
                    box_color    = C_KNOWN

            # ── RE-INIT VitTrack ─────────────
            tracker  = make_tracker()
            tracker.init(frame, (bx, by, bw, bh))
            tracking = True
            last_bbox = (bx, by, bw, bh)

            # ── Kalman reset ─────────────────
            mx = float(bx + bw / 2)
            my = float(by + bh / 2)
            kalman.statePre  = np.array([[mx],[my],[0.],[0.]], np.float32)
            kalman.statePost = np.array([[mx],[my],[0.],[0.]], np.float32)
            kalman_initialized = True

            trail.clear()

    # ─────────────────────────────────────────
    # TRACKING PHASE (VitTrack every frame)
    # ─────────────────────────────────────────
    if tracking:
        success, vit_box = tracker.update(frame)

        if success:
            s_text  = "TRACKING"
            s_color = C_KNOWN

            vx, vy, vw, vh = [int(v) for v in vit_box]
            cx = vx + vw // 2
            cy = vy + vh // 2

            # Kalman correct + predict
            if kalman_initialized:
                meas = np.array([[np.float32(cx)],[np.float32(cy)]])
                kalman.correct(meas)
                pred     = kalman.predict()
                smooth_x = int(pred[0][0])
                smooth_y = int(pred[1][0])
            else:
                smooth_x, smooth_y = cx, cy

            last_bbox = (vx, vy, vw, vh)
            trail.append((smooth_x, smooth_y))

            # ── Draw bounding box ─────────────
            corner_brackets(frame,
                            smooth_x - vw//2, smooth_y - vh//2,
                            smooth_x + vw//2, smooth_y + vh//2,
                            box_color)

            # ── Name pill ────────────────────
            pill_label(frame,
                       f"{tracked_name}  {int(conf_score*100)}%",
                       smooth_x - vw//2,
                       smooth_y - vh//2 - 6,
                       box_color)

            # ── Kalman trail ─────────────────
            if len(trail) > 1:
                for i in range(1, len(trail)):
                    a = i / len(trail)
                    col = tuple(int(c * a) for c in C_CYAN)
                    cv2.line(frame, trail[i-1], trail[i], col, max(1, int(2*a)))

            # ── Angles ───────────────────────
            yaw   = (smooth_x - cx_f) / W * HORIZONTAL_FOV
            pitch = (smooth_y - cy_f) / H * VERTICAL_FOV

            cmd = "● CENTERED"
            if   abs(yaw)   > 8:  cmd = "▶ TURN RIGHT" if yaw > 0 else "◀ TURN LEFT"
            elif abs(pitch) > 6:  cmd = "▼ LOOK DOWN"  if pitch > 0 else "▲ LOOK UP"

        else:
            tracking = False
            s_text   = "LOST"
            s_color  = C_UNKNOWN
            yaw      = pitch = 0.0
            cmd      = "● CENTERED"
            trail.clear()

    # ─────────────────────────────────────────
    # HUD RENDERING
    # ─────────────────────────────────────────

    # ── Header bar ───────────────────────────
    hud_panel(frame, 0, 0, W, 32, alpha=0.75)
    cv2.putText(frame, "HUMAN DETECTION ROBOT  —  HUD MONITOR",
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_CYAN, 1, cv2.LINE_AA)

    # ── Telemetry panel (top-left) ────────────
    hud_panel(frame, 10, 38, 210, 105)
    cv2.putText(frame, f"FPS   {fps_ema:5.1f}",
                (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.48, C_WHITE, 1)
    cv2.putText(frame, f"YAW   {yaw:+6.1f} deg",
                (20, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                C_CYAN if abs(yaw) < 8 else C_AMBER, 1)
    cv2.putText(frame, f"PITCH {pitch:+6.1f} deg",
                (20, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                C_CYAN if abs(pitch) < 6 else C_AMBER, 1)
    cv2.putText(frame, "CONF",
                (20, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_DIM, 1)
    confidence_bar(frame, 65, 114, 120, conf_score, box_color)

    # ── Status panel (top-right) ──────────────
    hud_panel(frame, W - 185, 38, 175, 44)
    status_dot(frame, W - 165, 60, s_color)
    cv2.putText(frame, s_text,
                (W - 148, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.60,
                C_WHITE, 1, cv2.LINE_AA)

    # ── Known persons badge (top-right below status) ──
    hud_panel(frame, W - 185, 88, 175, 32)
    cv2.putText(frame, f"Known: {len(known_names)} person(s)",
                (W - 178, 109), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_DIM, 1)

    # ── Command bar (bottom centre) ───────────
    if tracking and success:
        hud_panel(frame, W//2 - 110, H - 52, 220, 38, alpha=0.85)
        cv2.putText(frame, cmd,
                    (W//2 - 90, H - 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, C_CYAN, 1, cv2.LINE_AA)

    # ── Crosshair ────────────────────────────
    crosshair(frame, cx_f, cy_f)

    # ── Timestamp ────────────────────────────
    ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(frame, ts,
                (W - 195, H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_DIM, 1, cv2.LINE_AA)

    cv2.imshow("Human Detection Robot — HUD Monitor", frame)
    if cv2.waitKey(1) & 0xFF == 27:   # ESC to quit
        break

cap.release()
cv2.destroyAllWindows()