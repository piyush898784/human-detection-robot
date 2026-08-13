import cv2
import numpy as np
import os
import time
import base64
import math
from datetime import datetime
from collections import deque
from threading import Thread, Lock
from flask import Flask, render_template, Response, request, jsonify
from flask_socketio import SocketIO, emit

# Optional imports with graceful fallbacks
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False
    print("Warning: face_recognition not installed. Face recognition disabled.")

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("Warning: mediapipe not installed. Falling back to Haar Cascade / HOG.")

MODEL_PATH = "blaze_face_short_range.tflite"
VITTRACK_MODEL = "vittrack.onnx"
KNOWN_FACES_DIR = "known_faces"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'robot-hud-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Shared variables
frame_lock = Lock()
latest_frame = None

# Colors (BGR for OpenCV)
C_KNOWN   = (0, 255, 136)      # Neon Green
C_UNKNOWN = (51, 51, 255)      # Red
C_CYAN    = (255, 212, 0)      # Cyan
C_WHITE   = (255, 255, 255)
C_AMBER   = (0, 170, 255)      # Amber
C_DIM     = (140, 140, 140)
C_DARK    = (15, 15, 25)


# ─────────────────────────────────────────────
# HUD DRAWING HELPERS
# ─────────────────────────────────────────────

def hud_panel(frame, x, y, w, h, alpha=0.60, color=C_DARK):
    """Draw a semi-transparent HUD background panel."""
    h_f, w_f, _ = frame.shape
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(w_f, int(x + w)), min(h_f, int(y + h))
    if x2 <= x1 or y2 <= y1:
        return
    sub = frame[y1:y2, x1:x2]
    rect = np.full_like(sub, color, dtype=np.uint8)
    cv2.addWeighted(rect, alpha, sub, 1.0 - alpha, 0, sub)
    # Add thin border
    cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 70, 90), 1)


def corner_brackets(frame, x1, y1, x2, y2, color, t=2, seg=18):
    """Draw tactical sci-fi corner bracket bounding box with corner glows."""
    h_f, w_f, _ = frame.shape
    x1, y1 = max(2, int(x1)), max(2, int(y1))
    x2, y2 = min(w_f - 3, int(x2)), min(h_f - 3, int(y2))
    if x2 <= x1 or y2 <= y1:
        return

    # Glow layer
    ov = frame.copy()
    for px, py, dx, dy in [(x1-1, y1-1, 1, 1), (x2+1, y1-1, -1, 1),
                           (x1-1, y2+1, 1, -1), (x2+1, y2+1, -1, -1)]:
        cv2.line(ov, (px, py), (px + dx * (seg + 4), py), color, t * 2)
        cv2.line(ov, (px, py), (px, py + dy * (seg + 4)), color, t * 2)
    cv2.addWeighted(ov, 0.35, frame, 0.65, 0, frame)

    # Main corners
    for px, py, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1),
                           (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(frame, (px, py), (px + dx * seg, py), color, t, cv2.LINE_AA)
        cv2.line(frame, (px, py), (px, py + dy * seg), color, t, cv2.LINE_AA)

    # Dashed border
    for p1, p2 in [((x1, y1), (x2, y1)), ((x1, y2), (x2, y2)),
                   ((x1, y1), (x1, y2)), ((x2, y1), (x2, y2))]:
        d = int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        if d > 0:
            for i in range(0, d, 8):
                r = i / float(d)
                px = int(p1[0] * (1 - r) + p2[0] * r)
                py = int(p1[1] * (1 - r) + p2[1] * r)
                cv2.circle(frame, (px, py), 1, color, -1)


def crosshair(frame, cx, cy, sz=26, color=C_CYAN):
    """Draw tactical center reticle."""
    cx, cy = int(cx), int(cy)
    cv2.line(frame, (cx - sz, cy), (cx - 8, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx + 8, cy), (cx + sz, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - sz), (cx, cy - 8), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy + 8), (cx, cy + sz), color, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), sz // 2, color, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 2, color, -1)


def pill_label(frame, text, x, y, bg_color, font_scale=0.50):
    """Draw a clean pill label above detected targets."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, 1)
    px, py = 8, 4
    x1 = int(x)
    y1 = int(y - th - py * 2)
    x2 = int(x + tw + px * 2)
    y2 = int(y)

    h_f, w_f, _ = frame.shape
    if y1 < 0:
        y1 = int(y)
        y2 = int(y + th + py * 2)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_f, x2), min(h_f, y2)

    if x2 > x1 and y2 > y1:
        sub = frame[y1:y2, x1:x2]
        rect = np.full_like(sub, bg_color, dtype=np.uint8)
        cv2.addWeighted(rect, 0.85, sub, 0.15, 0, sub)
        cv2.rectangle(frame, (x1, y1), (x2, y2), C_WHITE, 1)
        cv2.putText(frame, text, (x1 + px, y2 - py), font, font_scale, C_WHITE, 1, cv2.LINE_AA)


def confidence_bar(frame, x, y, w, val, color):
    """Draw segmented/smooth confidence progress bar."""
    x, y, w = int(x), int(y), int(w)
    val = max(0.0, min(1.0, float(val)))
    cv2.rectangle(frame, (x, y), (x + w, y + 6), (35, 40, 50), -1)
    fill_w = int(w * val)
    if fill_w > 0:
        cv2.rectangle(frame, (x, y), (x + fill_w, y + 6), color, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + 6), C_DIM, 1)


def status_dot(frame, x, y, color, r=5):
    """Draw glowing status indicator dot."""
    x, y = int(x), int(y)
    cv2.circle(frame, (x, y), r + 2, (0, 0, 0), -1)
    cv2.circle(frame, (x, y), r, color, -1)


# ─────────────────────────────────────────────
# FACE DETECTION & TRACKING ENGINE
# ─────────────────────────────────────────────

class FaceDetectionEngine:
    def __init__(self):
        self.known_faces_dir = KNOWN_FACES_DIR
        os.makedirs(self.known_faces_dir, exist_ok=True)

        self.known_encodings = []
        self.known_names = []
        self.load_known_faces()

        # Face Detector (MediaPipe Tasks or OpenCV Cascade fallback)
        self.face_detector = None
        self.cascade_detector = None
        self.init_detectors()

        # Kalman filter setup
        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0],
                                                  [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix  = np.array([[1, 0, 1, 0],
                                                  [0, 1, 0, 1],
                                                  [0, 0, 1, 0],
                                                  [0, 0, 0, 1]], np.float32)
        self.kalman.processNoiseCov   = np.eye(4, dtype=np.float32) * 0.03
        self.kalman_initialized = False

        # Camera FOV constants
        self.HORIZONTAL_FOV = 60
        self.VERTICAL_FOV   = 45

        # Tracker state
        self.tracker      = None
        self.tracking     = False
        self.tracked_name = "Unknown"
        self.confidence   = 0.0
        self.last_bbox    = None
        self.trail        = deque(maxlen=30)

        # Telemetry
        self.events        = deque(maxlen=100)
        self.yaw           = 0.0
        self.pitch         = 0.0
        self.command       = "● CENTERED"
        self.fps           = 0
        self.start_time    = time.time()
        self.camera_online = False
        self.frame_count   = 0
        self.last_fps_time = time.time()
        self.render_hud_overlay = True

        # Simulation state (for testing without physical camera)
        self.sim_angle = 0.0

    def init_detectors(self):
        if MEDIAPIPE_AVAILABLE and os.path.exists(MODEL_PATH):
            try:
                base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
                options = mp_vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.55
                )
                self.face_detector = mp_vision.FaceDetector.create_from_options(options)
                print("[+] MediaPipe BlazeFace Detector initialized successfully.")
            except Exception as e:
                print(f"MediaPipe initialization warning: {e}")
                self.face_detector = None

        # Fallback Haar Cascade
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(cascade_path):
                self.cascade_detector = cv2.CascadeClassifier(cascade_path)
        except Exception:
            pass

    def load_known_faces(self):
        """Loads faces from both subdirectories and flat files, averaging multiple photos."""
        self.known_encodings = []
        self.known_names = []
        if not FACE_REC_AVAILABLE:
            return

        print("\n=== Loading Known Faces for Robot HUD ===")
        # Layout 1: Subdirectories (known_faces/Alice/photo1.jpg)
        for entry in os.scandir(self.known_faces_dir):
            if entry.is_dir():
                person_name = entry.name
                person_encs = []
                for img_file in os.scandir(entry.path):
                    if img_file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                        try:
                            img = face_recognition.load_image_file(img_file.path)
                            encs = face_recognition.face_encodings(img)
                            if encs:
                                person_encs.append(encs[0])
                        except Exception as e:
                            print(f"  [!] Skipped {img_file.path}: {e}")
                if person_encs:
                    avg_enc = np.mean(person_encs, axis=0)
                    self.known_encodings.append(avg_enc)
                    self.known_names.append(person_name)
                    print(f"  [+] {person_name}: trained on {len(person_encs)} photo(s)")

        # Layout 2: Flat files (known_faces/Alice.jpg)
        for img_file in os.scandir(self.known_faces_dir):
            if img_file.is_file() and img_file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                person_name = os.path.splitext(img_file.name)[0]
                if person_name in self.known_names:
                    continue
                try:
                    img = face_recognition.load_image_file(img_file.path)
                    encs = face_recognition.face_encodings(img)
                    if encs:
                        self.known_encodings.append(encs[0])
                        self.known_names.append(person_name)
                        print(f"  [+] {person_name}: trained on 1 flat photo")
                except Exception as e:
                    print(f"  [!] Skipped {img_file.path}: {e}")

        print(f"Total known faces loaded: {len(self.known_names)}\n")

    def add_face(self, name, image_bytes):
        if not FACE_REC_AVAILABLE:
            return False, "face_recognition module not installed"

        temp_path = f"temp_{name}.jpg"
        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        try:
            img = face_recognition.load_image_file(temp_path)
            enc = face_recognition.face_encodings(img)
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            return False, str(e)

        if not enc:
            if os.path.exists(temp_path): os.remove(temp_path)
            return False, "No face detected in image"

        save_path = os.path.join(self.known_faces_dir, f"{name}.jpg")
        cv_img = cv2.imread(temp_path)
        cv_img = cv2.resize(cv_img, (200, 200))
        cv2.imwrite(save_path, cv_img)
        if os.path.exists(temp_path): os.remove(temp_path)

        # Reload faces to update encodings
        self.load_known_faces()
        socketio.emit('status_update', self.get_status())
        return True, "Success"

    def remove_face(self, name):
        removed = False
        if name in self.known_names:
            idx = self.known_names.index(name)
            self.known_names.pop(idx)
            if idx < len(self.known_encodings):
                self.known_encodings.pop(idx)
            removed = True

        for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            path = os.path.join(self.known_faces_dir, f"{name}{ext}")
            if os.path.exists(path):
                os.remove(path)
                removed = True

        dir_path = os.path.join(self.known_faces_dir, name)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            import shutil
            shutil.rmtree(dir_path, ignore_errors=True)
            removed = True

        socketio.emit('status_update', self.get_status())
        return removed

    def get_faces(self):
        faces = []
        for name in self.known_names:
            found = False
            for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                p = os.path.join(self.known_faces_dir, f"{name}{ext}")
                if os.path.exists(p):
                    with open(p, "rb") as img_file:
                        b64 = base64.b64encode(img_file.read()).decode('utf-8')
                        faces.append({"name": name, "thumbnail": b64})
                        found = True
                    break
            if not found:
                dir_p = os.path.join(self.known_faces_dir, name)
                if os.path.exists(dir_p) and os.path.isdir(dir_p):
                    for f in os.listdir(dir_p):
                        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                            with open(os.path.join(dir_p, f), "rb") as img_file:
                                b64 = base64.b64encode(img_file.read()).decode('utf-8')
                                faces.append({"name": name, "thumbnail": b64})
                            break
        return faces

    def log_event(self, name, action, confidence=None):
        evt = {
            "timestamp":  time.time(),
            "name":       name,
            "action":     action,
            "confidence": confidence
        }
        self.events.append(evt)
        socketio.emit('detection_event', evt)

    def detect_face_locations(self, frame, rgb):
        """Returns list of (x, y, w, h) bounding boxes."""
        h, w, _ = frame.shape
        boxes = []

        # 1. MediaPipe Tasks API
        if self.face_detector is not None:
            try:
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = self.face_detector.detect(mp_image)
                if result.detections:
                    for det in result.detections:
                        bb = det.bounding_box
                        bx = max(0, bb.origin_x)
                        by = max(0, bb.origin_y)
                        bw = min(w - bx, bb.width)
                        bh = min(h - by, bb.height)
                        score = det.categories[0].score if det.categories else 0.8
                        boxes.append((bx, by, bw, bh, score))
                    return boxes
            except Exception as e:
                pass

        # 2. face_recognition HOG detector
        if FACE_REC_AVAILABLE:
            try:
                locs = face_recognition.face_locations(rgb, model="hog")
                for (top, right, bottom, left) in locs:
                    bx = left
                    by = top
                    bw = right - left
                    bh = bottom - top
                    boxes.append((bx, by, bw, bh, 0.85))
                if boxes:
                    return boxes
            except Exception:
                pass

        # 3. Haar Cascade fallback
        if self.cascade_detector is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.cascade_detector.detectMultiScale(gray, 1.2, 4, minSize=(40, 40))
            for (x, y, bw, bh) in faces:
                boxes.append((x, y, bw, bh, 0.70))

        return boxes

    def process_frame(self, frame):
        h, w, _ = frame.shape
        cx_f, cy_f = w // 2, h // 2

        # FPS calculation
        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps           = self.frame_count
            self.frame_count   = 0
            self.last_fps_time = now

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        status_text = "SEARCHING"
        status_color = C_AMBER

        # Run Face Detection if not currently tracking or periodic re-scan
        if not self.tracking or (self.frame_count % 8 == 0):
            detected_boxes = self.detect_face_locations(frame, rgb)

            if detected_boxes:
                # Select the largest face (closest subject)
                best_box = max(detected_boxes, key=lambda b: b[2] * b[3])
                bx, by, bw, bh = best_box[0], best_box[1], best_box[2], best_box[3]
                det_score = best_box[4] if len(best_box) > 4 else 0.75

                # Perform face recognition
                new_name = "Unknown"
                conf = det_score

                if FACE_REC_AVAILABLE and self.known_encodings:
                    try:
                        face_loc = [(by, bx + bw, by + bh, bx)]
                        encs = face_recognition.face_encodings(rgb, face_loc)
                        if encs:
                            distances = face_recognition.face_distance(self.known_encodings, encs[0])
                            best_idx  = int(np.argmin(distances))
                            if distances[best_idx] < 0.55:
                                new_name = self.known_names[best_idx]
                                conf = float(1.0 - distances[best_idx])
                    except Exception as e:
                        print(f"Face encoding error: {e}")

                action = "IDENTIFIED" if new_name != "Unknown" else "SEARCHING"
                if new_name != self.tracked_name or not self.tracking:
                    self.log_event(new_name, action, conf)

                self.tracked_name = new_name
                self.confidence   = conf
                self.tracking     = True
                self.last_bbox    = (bx, by, bw, bh)

                # Initialize tracker
                try:
                    self.tracker = cv2.TrackerCSRT_create()
                    self.tracker.init(frame, (bx, by, bw, bh))
                except Exception:
                    self.tracker = None

                # Initialize Kalman Filter
                mx = float(bx + bw / 2)
                my = float(by + bh / 2)
                self.kalman.statePre  = np.array([[mx], [my], [0.], [0.]], np.float32)
                self.kalman.statePost = np.array([[mx], [my], [0.], [0.]], np.float32)
                self.kalman_initialized = True
                self.trail.clear()

        # Update tracker
        if self.tracking:
            success = False
            if self.tracker is not None:
                try:
                    success, bbox = self.tracker.update(frame)
                except Exception:
                    success = False
            else:
                success = True
                bbox = self.last_bbox

            if success and bbox is not None:
                status_text  = "TRACKING"
                status_color = C_KNOWN

                x, y, bw, bh = map(int, bbox)
                cx = x + bw // 2
                cy = y + bh // 2

                # Kalman filter correction & prediction
                if self.kalman_initialized:
                    meas = np.array([[np.float32(cx)], [np.float32(cy)]])
                    self.kalman.correct(meas)
                    pred = self.kalman.predict()
                    smooth_x = int(pred[0][0])
                    smooth_y = int(pred[1][0])
                else:
                    smooth_x, smooth_y = cx, cy

                self.last_bbox = (x, y, bw, bh)
                self.trail.append((smooth_x, smooth_y))

                # Angles relative to camera FOV
                self.yaw   = (smooth_x - cx_f) / float(w) * self.HORIZONTAL_FOV
                self.pitch = (smooth_y - cy_f) / float(h) * self.VERTICAL_FOV

                # Robot command calculation
                if   self.yaw   >  8: self.command = "▶ TURN RIGHT"
                elif self.yaw   < -8: self.command = "◀ TURN LEFT"
                elif self.pitch >  6: self.command = "▼ LOOK DOWN"
                elif self.pitch < -6: self.command = "▲ LOOK UP"
                else:                 self.command = "● CENTERED"

                box_color = C_KNOWN if self.tracked_name != "Unknown" else C_UNKNOWN

                # ── Draw target HUD on frame ──
                if self.render_hud_overlay:
                    # Target corner brackets
                    corner_brackets(frame,
                                    smooth_x - bw // 2, smooth_y - bh // 2,
                                    smooth_x + bw // 2, smooth_y + bh // 2,
                                    box_color)

                    # Pill label with name & confidence
                    pill_label(frame,
                               f"{self.tracked_name} {int(self.confidence * 100)}%",
                               smooth_x - bw // 2,
                               smooth_y - bh // 2 - 8,
                               box_color)

                    # Motion Trajectory Trail
                    if len(self.trail) > 1:
                        for i in range(1, len(self.trail)):
                            alpha = i / float(len(self.trail))
                            col = tuple(int(c * alpha) for c in C_CYAN)
                            cv2.line(frame, self.trail[i - 1], self.trail[i], col, max(1, int(2 * alpha)), cv2.LINE_AA)
            else:
                self.tracking = False
                status_text   = "LOST"
                status_color  = C_UNKNOWN
                self.log_event(self.tracked_name, "LOST")
                self.tracked_name = "None"
                self.yaw          = 0.0
                self.pitch        = 0.0
                self.command      = "● SEARCHING"
                self.trail.clear()

        # ─────────────────────────────────────────────
        # RENDER FULL SCI-FI HUD ON VIDEO FRAME
        # ─────────────────────────────────────────────
        if self.render_hud_overlay:
            # 1. Header Bar
            hud_panel(frame, 0, 0, w, 32, alpha=0.75)
            cv2.putText(frame, "HUMAN DETECTION ROBOT  //  TACTICAL HUD",
                        (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, C_CYAN, 1, cv2.LINE_AA)
            
            # Mission time
            ts_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            cv2.putText(frame, ts_str,
                        (w - 190, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_WHITE, 1, cv2.LINE_AA)

            # 2. Telemetry Panel (Top-Left)
            hud_panel(frame, 12, 40, 195, 110, alpha=0.65)
            cv2.putText(frame, f"FPS    {self.fps:4d}",
                        (22, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.44, C_WHITE, 1, cv2.LINE_AA)
            
            yaw_color = C_CYAN if abs(self.yaw) < 8 else C_AMBER
            cv2.putText(frame, f"YAW    {self.yaw:+5.1f} deg",
                        (22, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.44, yaw_color, 1, cv2.LINE_AA)

            pitch_color = C_CYAN if abs(self.pitch) < 6 else C_AMBER
            cv2.putText(frame, f"PITCH  {self.pitch:+5.1f} deg",
                        (22, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.44, pitch_color, 1, cv2.LINE_AA)

            cv2.putText(frame, "CONF",
                        (22, 124), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_DIM, 1, cv2.LINE_AA)
            conf_color = C_KNOWN if self.tracked_name != "Unknown" else C_AMBER
            confidence_bar(frame, 68, 117, 125, self.confidence, conf_color)

            # 3. Status Panel (Top-Right)
            hud_panel(frame, w - 175, 40, 163, 40, alpha=0.65)
            status_dot(frame, w - 157, 60, status_color, r=5)
            cv2.putText(frame, status_text,
                        (w - 142, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_WHITE, 1, cv2.LINE_AA)

            # 4. Known Persons Badge
            hud_panel(frame, w - 175, 86, 163, 28, alpha=0.65)
            cv2.putText(frame, f"KNOWN FACES: {len(self.known_names)}",
                        (w - 165, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_DIM, 1, cv2.LINE_AA)

            # 5. Center Reticle & Crosshair
            crosshair(frame, cx_f, cy_f, sz=26, color=C_CYAN)

            # 6. Bottom Command Banner
            if self.tracking:
                cmd_w = 200
                hud_panel(frame, (w - cmd_w) // 2, h - 46, cmd_w, 36, alpha=0.85)
                cv2.putText(frame, self.command,
                            ((w - cmd_w) // 2 + 18, h - 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.58, C_CYAN, 1, cv2.LINE_AA)

        return frame

    def generate_simulated_frame(self):
        """Generates high-tech simulated test footage when no physical webcam is plugged in."""
        w, h = 640, 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        self.sim_angle += 0.04

        # Background grid
        for gy in range(0, h, 40):
            cv2.line(frame, (0, gy), (w, gy), (18, 24, 38), 1)
        for gx in range(0, w, 40):
            cv2.line(frame, (gx, 0), (gx, h), (18, 24, 38), 1)

        # Simulated moving target
        target_cx = int(w / 2 + math.sin(self.sim_angle) * 160)
        target_cy = int(h / 2 + math.cos(self.sim_angle * 0.7) * 90)
        bw, bh = 80, 100

        # Draw simulated human figure / face outline
        cv2.circle(frame, (target_cx, target_cy - 10), 30, (80, 140, 200), 2)
        cv2.ellipse(frame, (target_cx, target_cy + 55), (45, 30), 0, 0, 180, (60, 100, 150), 2)

        # Process through normal pipeline
        self.tracking = True
        self.confidence = 0.94
        self.tracked_name = self.known_names[0] if self.known_names else "Target Alpha"
        self.last_bbox = (target_cx - bw // 2, target_cy - bh // 2, bw, bh)

        self.yaw = (target_cx - w / 2) / float(w) * self.HORIZONTAL_FOV
        self.pitch = (target_cy - h / 2) / float(h) * self.VERTICAL_FOV
        if self.yaw > 8: self.command = "▶ TURN RIGHT"
        elif self.yaw < -8: self.command = "◀ TURN LEFT"
        elif self.pitch > 6: self.command = "▼ LOOK DOWN"
        elif self.pitch < -6: self.command = "▲ LOOK UP"
        else: self.command = "● CENTERED"

        self.trail.append((target_cx, target_cy))

        # Render HUD
        corner_brackets(frame, target_cx - bw // 2, target_cy - bh // 2,
                        target_cx + bw // 2, target_cy + bh // 2, C_KNOWN)
        pill_label(frame, f"{self.tracked_name} {int(self.confidence * 100)}%",
                   target_cx - bw // 2, target_cy - bh // 2 - 8, C_KNOWN)

        if len(self.trail) > 1:
            for i in range(1, len(self.trail)):
                alpha = i / float(len(self.trail))
                col = tuple(int(c * alpha) for c in C_CYAN)
                cv2.line(frame, self.trail[i - 1], self.trail[i], col, max(1, int(2 * alpha)), cv2.LINE_AA)

        # Full HUD
        hud_panel(frame, 0, 0, w, 32, alpha=0.75)
        cv2.putText(frame, "HUMAN DETECTION ROBOT  //  TACTICAL HUD (SIM)",
                    (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, C_CYAN, 1, cv2.LINE_AA)
        ts_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(frame, ts_str, (w - 190, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_WHITE, 1, cv2.LINE_AA)

        hud_panel(frame, 12, 40, 195, 110, alpha=0.65)
        cv2.putText(frame, "FPS    30.0 (SIM)", (22, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.44, C_WHITE, 1, cv2.LINE_AA)
        cv2.putText(frame, f"YAW    {self.yaw:+5.1f} deg", (22, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.44, C_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, f"PITCH  {self.pitch:+5.1f} deg", (22, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.44, C_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, "CONF", (22, 124), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_DIM, 1, cv2.LINE_AA)
        confidence_bar(frame, 68, 117, 125, self.confidence, C_KNOWN)

        hud_panel(frame, w - 175, 40, 163, 40, alpha=0.65)
        status_dot(frame, w - 157, 60, C_KNOWN, r=5)
        cv2.putText(frame, "TRACKING", (w - 142, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_WHITE, 1, cv2.LINE_AA)

        hud_panel(frame, w - 175, 86, 163, 28, alpha=0.65)
        cv2.putText(frame, f"KNOWN FACES: {len(self.known_names)}", (w - 165, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_DIM, 1, cv2.LINE_AA)

        crosshair(frame, w // 2, h // 2, sz=26, color=C_CYAN)

        cmd_w = 200
        hud_panel(frame, (w - cmd_w) // 2, h - 46, cmd_w, 36, alpha=0.85)
        cv2.putText(frame, self.command, ((w - cmd_w) // 2 + 18, h - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.58, C_CYAN, 1, cv2.LINE_AA)

        return frame

    def get_telemetry(self):
        trail_list = list(self.trail)
        bbox_list = list(self.last_bbox) if self.last_bbox is not None else None
        return {
            "fps":             self.fps if self.fps > 0 else 30,
            "yaw":             round(self.yaw, 2),
            "pitch":           round(self.pitch, 2),
            "command":         self.command,
            "tracked_name":    self.tracked_name,
            "confidence":      round(self.confidence, 3),
            "tracking_status": self.tracking,
            "face_count":      len(self.known_names),
            "bbox":            bbox_list,
            "trail":           trail_list,
            "camera_online":   self.camera_online,
            "timestamp":       time.time()
        }

    def get_status(self):
        return {
            "camera_online":     self.camera_online,
            "tracking_active":   self.tracking,
            "known_face_count":  len(self.known_names),
            "serial_connected":  False,
            "uptime_seconds":    int(time.time() - self.start_time),
            "render_hud":        self.render_hud_overlay
        }


engine = FaceDetectionEngine()


# ─────────────────────────────────────────────
# CAMERA & STREAMING THREADS
# ─────────────────────────────────────────────

def video_thread():
    global latest_frame

    # Try DirectShow on Windows for instant camera binding
    cap = None
    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(0)
    except Exception:
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        engine.camera_online = False
        print("[i] No physical camera opened at index 0. Starting simulated tactical HUD generator.")
        while True:
            sim_frame = engine.generate_simulated_frame()
            ret, buffer = cv2.imencode('.jpg', sim_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                with frame_lock:
                    latest_frame = buffer.tobytes()
            time.sleep(0.033)

    engine.camera_online = True
    print("[+] Camera stream started successfully.")

    while True:
        ret, frame = cap.read()
        if not ret:
            engine.camera_online = False
            # Fallback to simulated feed
            sim_frame = engine.generate_simulated_frame()
            ret2, buffer = cv2.imencode('.jpg', sim_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret2:
                with frame_lock:
                    latest_frame = buffer.tobytes()
            time.sleep(0.033)
            continue

        engine.camera_online = True
        annotated = engine.process_frame(frame)
        ret2, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret2:
            with frame_lock:
                latest_frame = buffer.tobytes()

        time.sleep(0.01)

    cap.release()


def telemetry_thread():
    while True:
        socketio.emit('telemetry_update', engine.get_telemetry())
        time.sleep(0.08)  # ~12 Hz telemetry rate


def generate_frames():
    while True:
        with frame_lock:
            if latest_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.033)  # ~30 fps MJPEG stream


# ─────────────────────────────────────────────
# FLASK ROUTES & API
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/faces', methods=['GET'])
def get_faces():
    return jsonify(engine.get_faces())


@app.route('/api/faces', methods=['POST'])
def upload_face():
    if 'image' not in request.files or 'name' not in request.form:
        return jsonify({"success": False, "error": "Missing image or name"}), 400
    file = request.files['image']
    name = request.form['name'].strip()
    success, msg = engine.add_face(name, file.read())
    return jsonify({"success": success, "error": msg})


@app.route('/api/faces/<name>', methods=['DELETE'])
def delete_face(name):
    success = engine.remove_face(name)
    return jsonify({"success": success})


@app.route('/api/events', methods=['GET'])
def get_events():
    return jsonify(list(engine.events))


@app.route('/api/control', methods=['POST'])
def control():
    data = request.json or {}
    cmd = data.get('command', 'S')
    print(f"[*] Manual Robot Command Received: {cmd}")
    return jsonify({"success": True, "command": cmd})


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json or {}
    if 'render_hud' in data:
        engine.render_hud_overlay = bool(data['render_hud'])
    return jsonify({"success": True, "render_hud": engine.render_hud_overlay})


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify(engine.get_status())


if __name__ == '__main__':
    print("[*] Initializing Robot HUD Dashboard System...")
    Thread(target=video_thread,    daemon=True).start()
    Thread(target=telemetry_thread, daemon=True).start()
    print("[*] Dashboard server running at: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)
