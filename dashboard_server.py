import os
# Suppress TensorFlow and MediaPipe Clearcut log noise
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'
os.environ['MEDIAPIPE_DISABLE_GPU'] = '1'

import cv2
import numpy as np
import time
import base64
import math
from datetime import datetime
from collections import deque
from threading import Thread, Lock, Condition
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

# ─────────────────────────────────────────────
# REAL-TIME BROADCAST ENGINE (ZERO-LATENCY)
# ─────────────────────────────────────────────
class FrameBroadcaster:
    def __init__(self):
        self.condition = Condition()
        self.frame_bytes = None
        self.frame_id = 0

    def update(self, frame_bytes):
        with self.condition:
            self.frame_bytes = frame_bytes
            self.frame_id += 1
            self.condition.notify_all()

    def get_latest(self, last_seen_id=0, timeout=0.04):
        with self.condition:
            if self.frame_id == last_seen_id:
                self.condition.wait(timeout=timeout)
            return self.frame_bytes, self.frame_id


broadcaster = FrameBroadcaster()

# Colors (BGR for OpenCV)
C_KNOWN   = (0, 255, 136)      # Neon Green
C_UNKNOWN = (51, 51, 255)      # Red
C_CYAN    = (255, 212, 0)      # Cyan
C_WHITE   = (255, 255, 255)
C_AMBER   = (0, 170, 255)      # Amber
C_DIM     = (140, 140, 140)
C_DARK    = (15, 15, 25)


# ─────────────────────────────────────────────
# ULTRA-FAST HUD DRAWING HELPERS (IN-PLACE ROI)
# ─────────────────────────────────────────────

def hud_panel(frame, x, y, w, h, alpha=0.60, color=C_DARK):
    """Draw a semi-transparent HUD background panel with zero full-frame copying."""
    h_f, w_f, _ = frame.shape
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(w_f, int(x + w)), min(h_f, int(y + h))
    if x2 <= x1 or y2 <= y1:
        return
    sub = frame[y1:y2, x1:x2]
    rect = np.full_like(sub, color, dtype=np.uint8)
    cv2.addWeighted(rect, alpha, sub, 1.0 - alpha, 0, sub)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 70, 90), 1)


def corner_brackets(frame, x1, y1, x2, y2, color, t=2, seg=16):
    """Draw tactical corner-bracket bounding box."""
    h_f, w_f, _ = frame.shape
    x1, y1 = max(2, int(x1)), max(2, int(y1))
    x2, y2 = min(w_f - 3, int(x2)), min(h_f - 3, int(y2))
    if x2 <= x1 or y2 <= y1:
        return

    # Sharp tactile corners
    for px, py, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1),
                           (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(frame, (px, py), (px + dx * seg, py), color, t, cv2.LINE_AA)
        cv2.line(frame, (px, py), (px, py + dy * seg), color, t, cv2.LINE_AA)


def crosshair(frame, cx, cy, sz=22, color=C_CYAN):
    """Draw tactical center reticle."""
    cx, cy = int(cx), int(cy)
    cv2.line(frame, (cx - sz, cy), (cx - 6, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx + 6, cy), (cx + sz, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - sz), (cx, cy - 6), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy + 6), (cx, cy + sz), color, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), sz // 2, color, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 2, color, -1)


def pill_label(frame, text, x, y, bg_color, font_scale=0.48):
    """Draw a pill label above detected targets without full frame copy."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, 1)
    px, py = 6, 3
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
    x, y, w = int(x), int(y), int(w)
    val = max(0.0, min(1.0, float(val)))
    cv2.rectangle(frame, (x, y), (x + w, y + 6), (35, 40, 50), -1)
    fill_w = int(w * val)
    if fill_w > 0:
        cv2.rectangle(frame, (x, y), (x + fill_w, y + 6), color, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + 6), C_DIM, 1)


def status_dot(frame, x, y, color, r=5):
    x, y = int(x), int(y)
    cv2.circle(frame, (x, y), r + 2, (0, 0, 0), -1)
    cv2.circle(frame, (x, y), r, color, -1)


# ─────────────────────────────────────────────
# THREADED HARDWARE CAMERA CAPTURE (LOW LATENCY)
# ─────────────────────────────────────────────

class ThreadedCamera:
    """Ultra-low latency grabber providing latest frame with zero queue buildup."""
    def __init__(self, src=0):
        self.src = src
        self.cap = None
        self.running = False
        self.frame = None
        self.lock = Lock()
        self.is_opened = False
        self.frame_id = 0
        self.start()

    def start(self):
        try:
            self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap.release()
                self.cap = cv2.VideoCapture(self.src)
        except Exception:
            self.cap = cv2.VideoCapture(self.src)

        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 20)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.is_opened = True
            self.running = True
            Thread(target=self._update, daemon=True).start()
            print("[+] ThreadedCamera capture initialized.")
        else:
            self.is_opened = False

    def _update(self):
        while self.running:
            if self.cap is not None and self.cap.isOpened():
                grabbed = self.cap.grab()
                if grabbed:
                    ret, frame = self.cap.retrieve()
                    if ret and frame is not None:
                        with self.lock:
                            self.frame = frame
                            self.frame_id += 1
                else:
                    time.sleep(0.005)
            else:
                break
            time.sleep(0.001)

    def read(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None, self.frame_id

    def release(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()


# ─────────────────────────────────────────────
# FACE DETECTION & RECOGNITION ENGINE
# ─────────────────────────────────────────────

class FaceDetectionEngine:
    def __init__(self):
        self.known_faces_dir = KNOWN_FACES_DIR
        os.makedirs(self.known_faces_dir, exist_ok=True)

        self.known_encodings = []
        self.known_names = []
        self.unique_names = set()
        self.load_known_faces()

        # Detector Setup
        self.face_detector = None
        self.cascade_detector = None
        self.init_detectors()

        # Kalman filter
        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0],
                                                  [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix  = np.array([[1, 0, 1, 0],
                                                  [0, 1, 0, 1],
                                                  [0, 0, 1, 0],
                                                  [0, 0, 0, 1]], np.float32)
        self.kalman.processNoiseCov   = np.eye(4, dtype=np.float32) * 0.05
        self.kalman_initialized = False

        # Camera FOV constants
        self.HORIZONTAL_FOV = 60
        self.VERTICAL_FOV   = 45

        # Tracker state
        self.tracking     = False
        self.tracked_name = "Unknown"
        self.confidence   = 0.0
        self.last_bbox    = None
        self.trail        = deque(maxlen=24)

        # Recognition worker state
        self.is_recognizing = False
        self.recognition_lock = Lock()
        self.last_recognition_time = 0.0

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

        # Simulation
        self.sim_angle = 0.0

    def init_detectors(self):
        if MEDIAPIPE_AVAILABLE and os.path.exists(MODEL_PATH):
            try:
                base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
                options = mp_vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.45
                )
                self.face_detector = mp_vision.FaceDetector.create_from_options(options)
                print("[+] MediaPipe BlazeFace Detector initialized.")
            except Exception as e:
                print(f"MediaPipe initialization note: {e}")

        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(cascade_path):
                self.cascade_detector = cv2.CascadeClassifier(cascade_path)
        except Exception:
            pass

    def load_known_faces(self):
        self.known_encodings = []
        self.known_names = []
        self.unique_names = set()
        if not FACE_REC_AVAILABLE:
            return

        print("\n=== Loading Known Faces for Robot HUD ===")
        # Subdirectories
        for entry in os.scandir(self.known_faces_dir):
            if entry.is_dir():
                person_name = entry.name
                p_count = 0
                for img_file in os.scandir(entry.path):
                    if img_file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                        try:
                            img = face_recognition.load_image_file(img_file.path)
                            encs = face_recognition.face_encodings(img)
                            if encs:
                                self.known_encodings.append(encs[0])
                                self.known_names.append(person_name)
                                self.unique_names.add(person_name)
                                p_count += 1
                        except Exception as e:
                            print(f"  [!] Skipped {img_file.path}: {e}")
                if p_count > 0:
                    print(f"  [+] {person_name}: trained on {p_count} photo(s)")

        # Flat files
        for img_file in os.scandir(self.known_faces_dir):
            if img_file.is_file() and img_file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                person_name = os.path.splitext(img_file.name)[0]
                if person_name in self.unique_names:
                    continue
                try:
                    img = face_recognition.load_image_file(img_file.path)
                    encs = face_recognition.face_encodings(img)
                    if encs:
                        self.known_encodings.append(encs[0])
                        self.known_names.append(person_name)
                        self.unique_names.add(person_name)
                        print(f"  [+] {person_name}: trained on 1 flat photo")
                except Exception as e:
                    print(f"  [!] Skipped {img_file.path}: {e}")

        print(f"Total training vectors: {len(self.known_encodings)} across {len(self.unique_names)} persons\n")

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

        target_dir = os.path.join(self.known_faces_dir, name)
        os.makedirs(target_dir, exist_ok=True)
        idx = len(os.listdir(target_dir)) + 1
        save_path = os.path.join(target_dir, f"{idx:03d}.jpg")
        cv_img = cv2.imread(temp_path)
        cv2.imwrite(save_path, cv_img)
        if os.path.exists(temp_path): os.remove(temp_path)

        self.load_known_faces()
        socketio.emit('status_update', self.get_status())
        return True, "Success"

    def remove_face(self, name):
        removed = False
        dir_path = os.path.join(self.known_faces_dir, name)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            import shutil
            shutil.rmtree(dir_path, ignore_errors=True)
            removed = True

        for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            path = os.path.join(self.known_faces_dir, f"{name}{ext}")
            if os.path.exists(path):
                os.remove(path)
                removed = True

        self.load_known_faces()
        socketio.emit('status_update', self.get_status())
        return removed

    def get_faces(self):
        faces = []
        for name in sorted(list(self.unique_names)):
            found = False
            dir_p = os.path.join(self.known_faces_dir, name)
            if os.path.exists(dir_p) and os.path.isdir(dir_p):
                for f in sorted(os.listdir(dir_p)):
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                        with open(os.path.join(dir_p, f), "rb") as img_file:
                            b64 = base64.b64encode(img_file.read()).decode('utf-8')
                            faces.append({"name": name, "thumbnail": b64})
                            found = True
                        break
            if not found:
                for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                    p = os.path.join(self.known_faces_dir, f"{name}{ext}")
                    if os.path.exists(p):
                        with open(p, "rb") as img_file:
                            b64 = base64.b64encode(img_file.read()).decode('utf-8')
                            faces.append({"name": name, "thumbnail": b64})
                        break
        return faces

    def log_event(self, name, action, confidence=None):
        evt = {
            "timestamp":  float(time.time()),
            "name":       str(name),
            "action":     str(action),
            "confidence": float(confidence) if confidence is not None else None
        }
        self.events.append(evt)
        socketio.emit('detection_event', evt)

    def _async_recognize_face(self, rgb_frame, top, right, bottom, left):
        """Runs fast scaled face encoding asynchronously with exact face coordinates."""
        try:
            scale = 0.5
            rgb_small = cv2.resize(rgb_frame, (0, 0), fx=scale, fy=scale)
            loc_small = [(int(top * scale), int(right * scale), int(bottom * scale), int(left * scale))]
            encs = face_recognition.face_encodings(rgb_small, loc_small)
            if encs and self.known_encodings:
                distances = face_recognition.face_distance(self.known_encodings, encs[0])
                best_idx = int(np.argmin(distances))
                min_dist = distances[best_idx]
                if min_dist < 0.58:
                    matched_name = self.known_names[best_idx]
                    conf = float(1.0 - min_dist)
                    if matched_name != self.tracked_name:
                        self.log_event(matched_name, "IDENTIFIED", conf)
                    self.tracked_name = matched_name
                    self.confidence = conf
                else:
                    self.tracked_name = "Unknown"
        except Exception:
            pass
        finally:
            with self.recognition_lock:
                self.is_recognizing = False

    def detect_face_fast(self, frame, rgb):
        """Blazing fast face detection on downscaled 320x240 buffer (~2.5ms)."""
        h, w, _ = frame.shape
        boxes = []

        if self.face_detector is not None:
            try:
                rgb_small = cv2.resize(rgb, (320, 240))
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_small)
                result = self.face_detector.detect(mp_image)
                if result.detections:
                    scale_x = w / 320.0
                    scale_y = h / 240.0
                    for det in result.detections:
                        bb = det.bounding_box
                        bx = int(max(0, bb.origin_x) * scale_x)
                        by = int(max(0, bb.origin_y) * scale_y)
                        bw = int(bb.width * scale_x)
                        bh = int(bb.height * scale_y)
                        bx = min(w - 1, bx)
                        by = min(h - 1, by)
                        bw = min(w - bx, bw)
                        bh = min(h - by, bh)
                        score = det.categories[0].score if det.categories else 0.85
                        boxes.append((bx, by, bw, bh, score))
                    return boxes
            except Exception:
                pass

        if self.cascade_detector is not None:
            small_gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 240))
            faces = self.cascade_detector.detectMultiScale(small_gray, 1.2, 3, minSize=(25, 25))
            for (sx, sy, sbw, sbh) in faces:
                boxes.append((sx * 2, sy * 2, sbw * 2, sbh * 2, 0.75))

        return boxes

    def process_frame(self, frame):
        h, w, _ = frame.shape
        cx_f, cy_f = w // 2, h // 2

        # FPS calculation
        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 0.5:
            self.fps = int(self.frame_count / (now - self.last_fps_time))
            self.frame_count = 0
            self.last_fps_time = now

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        status_text = "SEARCHING"
        status_color = C_AMBER

        # Run face detection on alternate frames (interleaved 60 FPS Kalman prediction)
        detected_boxes = []
        if self.frame_count % 2 == 0 or not self.tracking:
            detected_boxes = self.detect_face_fast(frame, rgb)

        if detected_boxes:
            best = max(detected_boxes, key=lambda b: b[2] * b[3])
            bx, by, bw, bh = best[0], best[1], best[2], best[3]
            det_score = best[4] if len(best) > 4 else 0.80

            meas_x = float(bx + bw / 2)
            meas_y = float(by + bh / 2)

            if not self.kalman_initialized:
                self.kalman.statePre  = np.array([[meas_x], [meas_y], [0.], [0.]], np.float32)
                self.kalman.statePost = np.array([[meas_x], [meas_y], [0.], [0.]], np.float32)
                self.kalman_initialized = True
            else:
                self.kalman.correct(np.array([[np.float32(meas_x)], [np.float32(meas_y)]]))

            pred = self.kalman.predict()
            smooth_x = int(pred[0][0])
            smooth_y = int(pred[1][0])

            self.tracking = True
            self.confidence = max(self.confidence, det_score)
            self.last_bbox = (bx, by, bw, bh)
            self.trail.append((smooth_x, smooth_y))

            status_text = "TRACKING"
            status_color = C_KNOWN

            # Throttled asynchronous face recognition
            now_time = time.time()
            need_rec = (self.tracked_name == "Unknown" or self.tracked_name == "None" or (now_time - self.last_recognition_time > 1.5))
            if FACE_REC_AVAILABLE and self.known_encodings and not self.is_recognizing and need_rec:
                with self.recognition_lock:
                    self.is_recognizing = True
                self.last_recognition_time = now_time
                top = max(0, by)
                right = min(w, bx + bw)
                bottom = min(h, by + bh)
                left = max(0, bx)
                Thread(target=self._async_recognize_face,
                       args=(rgb.copy(), top, right, bottom, left),
                       daemon=True).start()

        elif self.tracking and self.kalman_initialized:
            # Predict Kalman smoothly on intervening frame (<0.05ms)
            pred = self.kalman.predict()
            smooth_x = int(pred[0][0])
            smooth_y = int(pred[1][0])
            self.trail.append((smooth_x, smooth_y))
            status_text = "TRACKING"
            status_color = C_KNOWN
            bx, by, bw, bh = self.last_bbox

        else:
            if self.tracking:
                self.tracking = False
                status_text = "LOST"
                status_color = C_UNKNOWN
                self.log_event(self.tracked_name, "LOST")
                self.tracked_name = "None"
                self.yaw = 0.0
                self.pitch = 0.0
                self.command = "● SEARCHING"
                self.trail.clear()
                self.kalman_initialized = False

        # If currently tracking, calculate angles and draw target overlays
        if self.tracking:
            self.yaw   = (smooth_x - cx_f) / float(w) * self.HORIZONTAL_FOV
            self.pitch = (smooth_y - cy_f) / float(h) * self.VERTICAL_FOV

            if   self.yaw   >  8: self.command = "▶ TURN RIGHT"
            elif self.yaw   < -8: self.command = "◀ TURN LEFT"
            elif self.pitch >  6: self.command = "▼ LOOK DOWN"
            elif self.pitch < -6: self.command = "▲ LOOK UP"
            else:                 self.command = "● CENTERED"

            if self.render_hud_overlay:
                box_color = C_KNOWN if (self.tracked_name != "Unknown" and self.tracked_name != "None") else C_UNKNOWN
                corner_brackets(frame,
                                smooth_x - bw // 2, smooth_y - bh // 2,
                                smooth_x + bw // 2, smooth_y + bh // 2,
                                box_color)

                pill_label(frame,
                           f"{self.tracked_name} {int(self.confidence * 100)}%",
                           smooth_x - bw // 2,
                           smooth_y - bh // 2 - 8,
                           box_color)

                if len(self.trail) > 1:
                    for i in range(1, len(self.trail)):
                        alpha = i / float(len(self.trail))
                        col = tuple(int(c * alpha) for c in C_CYAN)
                        cv2.line(frame, self.trail[i - 1], self.trail[i], col, max(1, int(2 * alpha)), cv2.LINE_AA)

        # ─────────────────────────────────────────────
        # RENDER FULL SCI-FI HUD ON VIDEO FRAME
        # ─────────────────────────────────────────────
        if self.render_hud_overlay:
            # 1. Top HUD Header
            hud_panel(frame, 0, 0, w, 30, alpha=0.75)
            cv2.putText(frame, "HUMAN DETECTION ROBOT  //  TACTICAL HUD",
                        (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, C_CYAN, 1, cv2.LINE_AA)
            
            ts_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            cv2.putText(frame, ts_str,
                        (w - 185, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_WHITE, 1, cv2.LINE_AA)

            # 2. Telemetry Panel (Top-Left)
            hud_panel(frame, 10, 36, 185, 105, alpha=0.65)
            cv2.putText(frame, f"FPS    {self.fps:4d}",
                        (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_WHITE, 1, cv2.LINE_AA)
            
            yaw_col = C_CYAN if abs(self.yaw) < 8 else C_AMBER
            cv2.putText(frame, f"YAW    {self.yaw:+5.1f} deg",
                        (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.42, yaw_col, 1, cv2.LINE_AA)

            pitch_col = C_CYAN if abs(self.pitch) < 6 else C_AMBER
            cv2.putText(frame, f"PITCH  {self.pitch:+5.1f} deg",
                        (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.42, pitch_col, 1, cv2.LINE_AA)

            cv2.putText(frame, "CONF",
                        (20, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_DIM, 1, cv2.LINE_AA)
            conf_color = C_KNOWN if self.tracked_name != "Unknown" else C_AMBER
            confidence_bar(frame, 62, 112, 120, self.confidence, conf_color)

            # 3. Status Panel (Top-Right)
            hud_panel(frame, w - 165, 36, 155, 38, alpha=0.65)
            status_dot(frame, w - 148, 55, status_color, r=5)
            cv2.putText(frame, status_text,
                        (w - 134, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_WHITE, 1, cv2.LINE_AA)

            # 4. Known Persons Badge
            hud_panel(frame, w - 165, 80, 155, 26, alpha=0.65)
            cv2.putText(frame, f"ROSTER: {len(self.known_names)} PERSONS",
                        (w - 155, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_DIM, 1, cv2.LINE_AA)

            # 5. Center Reticle & Crosshair
            crosshair(frame, cx_f, cy_f, sz=22, color=C_CYAN)

            # 6. Bottom Command Banner
            if self.tracking:
                cmd_w = 190
                hud_panel(frame, (w - cmd_w) // 2, h - 42, cmd_w, 32, alpha=0.85)
                cv2.putText(frame, self.command,
                            ((w - cmd_w) // 2 + 16, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_CYAN, 1, cv2.LINE_AA)

        return frame

    def generate_simulated_frame(self):
        """Generates high-speed 60 FPS simulated HUD feed when no physical camera is attached."""
        w, h = 640, 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        self.sim_angle += 0.05

        # Background grid
        for gy in range(0, h, 40):
            cv2.line(frame, (0, gy), (w, gy), (18, 24, 38), 1)
        for gx in range(0, w, 40):
            cv2.line(frame, (gx, 0), (gx, h), (18, 24, 38), 1)

        target_cx = int(w / 2 + math.sin(self.sim_angle) * 160)
        target_cy = int(h / 2 + math.cos(self.sim_angle * 0.7) * 90)
        bw, bh = 80, 100

        cv2.circle(frame, (target_cx, target_cy - 10), 30, (80, 140, 200), 2)
        cv2.ellipse(frame, (target_cx, target_cy + 55), (45, 30), 0, 0, 180, (60, 100, 150), 2)

        self.tracking = True
        self.confidence = 0.96
        self.tracked_name = "piyush"
        self.last_bbox = (target_cx - bw // 2, target_cy - bh // 2, bw, bh)
        self.fps = 20

        self.yaw = (target_cx - w / 2) / float(w) * self.HORIZONTAL_FOV
        self.pitch = (target_cy - h / 2) / float(h) * self.VERTICAL_FOV
        if self.yaw > 8: self.command = "▶ TURN RIGHT"
        elif self.yaw < -8: self.command = "◀ TURN LEFT"
        elif self.pitch > 6: self.command = "▼ LOOK DOWN"
        elif self.pitch < -6: self.command = "▲ LOOK UP"
        else: self.command = "● CENTERED"

        self.trail.append((target_cx, target_cy))

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
        hud_panel(frame, 0, 0, w, 30, alpha=0.75)
        cv2.putText(frame, "HUMAN DETECTION ROBOT  //  TACTICAL HUD (SIM 20FPS)",
                    (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, C_CYAN, 1, cv2.LINE_AA)
        ts_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(frame, ts_str, (w - 185, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_WHITE, 1, cv2.LINE_AA)

        hud_panel(frame, 10, 36, 185, 105, alpha=0.65)
        cv2.putText(frame, "FPS    20.0 (SIM)", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_WHITE, 1, cv2.LINE_AA)
        cv2.putText(frame, f"YAW    {self.yaw:+5.1f} deg", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, f"PITCH  {self.pitch:+5.1f} deg", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, "CONF", (20, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_DIM, 1, cv2.LINE_AA)
        confidence_bar(frame, 62, 112, 120, self.confidence, C_KNOWN)

        hud_panel(frame, w - 165, 36, 155, 38, alpha=0.65)
        status_dot(frame, w - 148, 55, C_KNOWN, r=5)
        cv2.putText(frame, "TRACKING", (w - 134, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_WHITE, 1, cv2.LINE_AA)

        hud_panel(frame, w - 165, 80, 155, 26, alpha=0.65)
        cv2.putText(frame, f"ROSTER: {len(self.known_names)} PERSONS", (w - 155, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_DIM, 1, cv2.LINE_AA)

        crosshair(frame, w // 2, h // 2, sz=22, color=C_CYAN)

        cmd_w = 190
        hud_panel(frame, (w - cmd_w) // 2, h - 42, cmd_w, 32, alpha=0.85)
        cv2.putText(frame, self.command, ((w - cmd_w) // 2 + 16, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_CYAN, 1, cv2.LINE_AA)

        return frame

    def get_telemetry(self):
        trail_list = [[int(pt[0]), int(pt[1])] for pt in self.trail]
        bbox_list = [int(v) for v in self.last_bbox] if self.last_bbox is not None else None
        return {
            "fps":             int(self.fps if self.fps > 0 else 20),
            "yaw":             float(round(float(self.yaw), 2)),
            "pitch":           float(round(float(self.pitch), 2)),
            "command":         str(self.command),
            "tracked_name":    str(self.tracked_name),
            "confidence":      float(round(float(self.confidence), 3)),
            "tracking_status": bool(self.tracking),
            "face_count":      int(len(self.unique_names)),
            "bbox":            bbox_list,
            "trail":           trail_list,
            "camera_online":   bool(self.camera_online),
            "timestamp":       float(time.time())
        }

    def get_status(self):
        return {
            "camera_online":     bool(self.camera_online),
            "tracking_active":   bool(self.tracking),
            "known_face_count":  int(len(self.unique_names)),
            "serial_connected":  False,
            "uptime_seconds":    int(time.time() - self.start_time),
            "render_hud":        bool(self.render_hud_overlay)
        }


engine = FaceDetectionEngine()


# ─────────────────────────────────────────────
# HIGH-PERFORMANCE VIDEO & STREAMING THREADS
# ─────────────────────────────────────────────

def video_processing_thread():
    threaded_cam = ThreadedCamera(src=0)
    last_processed_id = -1

    if not threaded_cam.is_opened:
        engine.camera_online = False
        print("[i] Physical camera not connected. Running 20 FPS simulated HUD stream.")
        while True:
            sim_frame = engine.generate_simulated_frame()
            ret, buffer = cv2.imencode('.jpg', sim_frame, [cv2.IMWRITE_JPEG_QUALITY, 65, cv2.IMWRITE_JPEG_OPTIMIZE, 0])
            if ret:
                broadcaster.update(buffer.tobytes())
            time.sleep(0.05)  # 20 FPS simulation

    engine.camera_online = True

    while True:
        frame, frame_id = threaded_cam.read()
        if frame is None or frame_id == last_processed_id:
            time.sleep(0.005)
            continue

        last_processed_id = frame_id
        annotated = engine.process_frame(frame)
        ret, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 65, cv2.IMWRITE_JPEG_OPTIMIZE, 0])
        if ret:
            broadcaster.update(buffer.tobytes())

        # Frame rate regulation for steady 20 FPS optical flow
        time.sleep(0.01)


def telemetry_thread():
    while True:
        socketio.emit('telemetry_update', engine.get_telemetry())
        time.sleep(0.05)  # 20 Hz real-time telemetry synchronization


def generate_frames():
    """Event-synchronized MJPEG stream generator delivering continuous 20 FPS with zero duplicate buffering."""
    last_sent_id = 0
    while True:
        frame_bytes, last_sent_id = broadcaster.get_latest(last_sent_id, timeout=0.06)
        if frame_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/video_feed')
def video_feed():
    res = Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    res.headers['X-Accel-Buffering'] = 'no'
    return res


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
    print("[*] Initializing Ultra-Smooth Robot HUD Dashboard...")
    Thread(target=video_processing_thread, daemon=True).start()
    Thread(target=telemetry_thread,        daemon=True).start()
    print("[*] Dashboard server running at: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)
