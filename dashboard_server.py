import cv2
import mediapipe as mp
import face_recognition
import numpy as np
import os
import time
import base64
from datetime import datetime
from collections import deque
from threading import Thread, Lock
from flask import Flask, render_template, Response, request, jsonify
from flask_socketio import SocketIO, emit
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

MODEL_PATH = "blaze_face_short_range.tflite"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Shared variables
frame_lock = Lock()
latest_frame = None


class FaceDetectionEngine:
    def __init__(self):
        self.known_faces_dir = "known_faces"
        os.makedirs(self.known_faces_dir, exist_ok=True)

        self.known_encodings = []
        self.known_names = []
        self.load_known_faces()

        # MediaPipe Tasks API (works with 0.10.x)
        base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.6
        )
        self.face_detector = mp_vision.FaceDetector.create_from_options(options)

        # Kalman filter
        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0],
                                                   [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix  = np.array([[1, 0, 1, 0],
                                                   [0, 1, 0, 1],
                                                   [0, 0, 1, 0],
                                                   [0, 0, 0, 1]], np.float32)
        self.kalman.processNoiseCov   = np.eye(4, dtype=np.float32) * 0.03

        # Camera FOV constants
        self.HORIZONTAL_FOV = 60
        self.VERTICAL_FOV   = 45

        # Tracker state
        self.tracker      = None
        self.tracking     = False
        self.tracked_name = "None"
        self.confidence   = 0.0

        # Telemetry
        self.events        = deque(maxlen=100)
        self.yaw           = 0.0
        self.pitch         = 0.0
        self.command       = "CENTERED"
        self.fps           = 0
        self.start_time    = time.time()
        self.camera_online = False
        self.frame_count   = 0
        self.last_fps_time = time.time()

    def load_known_faces(self):
        self.known_encodings = []
        self.known_names = []
        for file in os.listdir(self.known_faces_dir):
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                path = os.path.join(self.known_faces_dir, file)
                try:
                    image = face_recognition.load_image_file(path)
                    enc   = face_recognition.face_encodings(image)
                    if enc:
                        self.known_encodings.append(enc[0])
                        self.known_names.append(os.path.splitext(file)[0])
                except Exception as e:
                    print(f"Could not load face {file}: {e}")

    def add_face(self, name, image_bytes):
        temp_path = f"temp_{name}.jpg"
        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        try:
            img = face_recognition.load_image_file(temp_path)
            enc = face_recognition.face_encodings(img)
        except Exception as e:
            os.remove(temp_path)
            return False, str(e)

        if not enc:
            os.remove(temp_path)
            return False, "No face detected in image"

        save_path = os.path.join(self.known_faces_dir, f"{name}.jpg")
        cv_img = cv2.imread(temp_path)
        cv_img = cv2.resize(cv_img, (100, 100))
        cv2.imwrite(save_path, cv_img)
        os.remove(temp_path)

        self.known_encodings.append(enc[0])
        self.known_names.append(name)
        socketio.emit('status_update', self.get_status())
        return True, "Success"

    def remove_face(self, name):
        if name in self.known_names:
            idx = self.known_names.index(name)
            self.known_names.pop(idx)
            self.known_encodings.pop(idx)
            for ext in ['.jpg', '.jpeg', '.png']:
                path = os.path.join(self.known_faces_dir, f"{name}{ext}")
                if os.path.exists(path):
                    os.remove(path)
            socketio.emit('status_update', self.get_status())
            return True
        return False

    def get_faces(self):
        faces = []
        for name in self.known_names:
            for ext in ['.jpg', '.jpeg', '.png']:
                p = os.path.join(self.known_faces_dir, f"{name}{ext}")
                if os.path.exists(p):
                    with open(p, "rb") as img_file:
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

    def process_frame(self, frame):
        h, w, _ = frame.shape

        # FPS
        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps           = self.frame_count
            self.frame_count   = 0
            self.last_fps_time = now

        if not self.tracking:
            # --- MediaPipe Tasks API detection ---
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = self.face_detector.detect(mp_image)

            if result.detections:
                det  = result.detections[0]
                bbox = det.bounding_box
                x    = max(0, bbox.origin_x)
                y    = max(0, bbox.origin_y)
                bw   = bbox.width
                bh   = bbox.height

                # Clamp to frame
                x  = min(x,  w - 1)
                y  = min(y,  h - 1)
                bw = min(bw, w - x)
                bh = min(bh, h - y)

                self.confidence = det.categories[0].score if det.categories else 0.5

                # Face recognition
                rgb           = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_loc      = [(y, x + bw, y + bh, x)]
                encs          = face_recognition.face_encodings(rgb, face_loc)
                new_name      = "Unknown"

                if encs and self.known_encodings:
                    distances = face_recognition.face_distance(self.known_encodings, encs[0])
                    best_idx  = int(np.argmin(distances))
                    if distances[best_idx] < 0.6:
                        new_name        = self.known_names[best_idx]
                        self.confidence = float(1.0 - distances[best_idx])

                action = "IDENTIFIED" if new_name != "Unknown" else "SEARCHING"
                self.log_event(new_name, action, self.confidence)
                self.tracked_name = new_name
                self.tracking     = True

                # Init CSRT tracker
                self.tracker = cv2.TrackerCSRT_create()
                self.tracker.init(frame, (x, y, bw, bh))

                # Init Kalman state
                self.kalman.statePre  = np.array([[np.float32(x + bw / 2)],
                                                   [np.float32(y + bh / 2)],
                                                   [0], [0]])
                self.kalman.statePost = self.kalman.statePre.copy()

        else:
            success, bbox = self.tracker.update(frame)
            if success:
                x, y, bw, bh = map(int, bbox)
                cx = x + bw // 2
                cy = y + bh // 2

                meas = np.array([[np.float32(cx)], [np.float32(cy)]])
                self.kalman.correct(meas)
                pred     = self.kalman.predict()
                smooth_x = int(pred[0][0])
                smooth_y = int(pred[1][0])

                # Draw bounding box
                color = (0, 255, 0) if self.tracked_name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame,
                              (smooth_x - bw // 2, smooth_y - bh // 2),
                              (smooth_x + bw // 2, smooth_y + bh // 2),
                              color, 2)
                cv2.putText(frame,
                            f"{self.tracked_name} {int(self.confidence * 100)}%",
                            (smooth_x - bw // 2, smooth_y - bh // 2 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # Angles
                self.yaw   = (smooth_x - w / 2) * (self.HORIZONTAL_FOV / w)
                self.pitch = (smooth_y - h / 2) * (self.VERTICAL_FOV / h)

                cmd = "CENTERED"
                if   self.yaw   >  10: cmd = "TURN RIGHT"
                elif self.yaw   < -10: cmd = "TURN LEFT"
                elif self.pitch >   8: cmd = "LOOK DOWN"
                elif self.pitch <  -8: cmd = "LOOK UP"
                self.command = cmd
            else:
                self.tracking = False
                self.log_event(self.tracked_name, "LOST")
                self.tracked_name = "None"
                self.yaw          = 0.0
                self.pitch        = 0.0
                self.command      = "SEARCHING"

        # Crosshair
        cv2.line(frame, (w // 2 - 15, h // 2), (w // 2 + 15, h // 2), (0, 212, 255), 1)
        cv2.line(frame, (w // 2, h // 2 - 15), (w // 2, h // 2 + 15), (0, 212, 255), 1)
        cv2.circle(frame, (w // 2, h // 2), 5, (0, 212, 255), 1)

        return frame

    def get_telemetry(self):
        return {
            "fps":            self.fps,
            "yaw":            round(self.yaw, 2),
            "pitch":          round(self.pitch, 2),
            "command":        self.command,
            "tracked_name":   self.tracked_name,
            "confidence":     round(self.confidence, 3),
            "tracking_status": self.tracking,
            "face_count":     len(self.known_names)
        }

    def get_status(self):
        return {
            "camera_online":     self.camera_online,
            "tracking_active":   self.tracking,
            "known_face_count":  len(self.known_names),
            "serial_connected":  False,
            "uptime_seconds":    int(time.time() - self.start_time)
        }


engine = FaceDetectionEngine()


def video_thread():
    global latest_frame
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        engine.camera_online = False
        print("Warning: Camera not found. Serving placeholder.")
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "NO CAMERA SIGNAL", (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        ret, jpeg = cv2.imencode('.jpg', blank)
        if ret:
            with frame_lock:
                latest_frame = jpeg.tobytes()
        return

    engine.camera_online = True

    while True:
        ret, frame = cap.read()
        if not ret:
            engine.camera_online = False
            break

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
        time.sleep(0.1)


def generate_frames():
    while True:
        with frame_lock:
            if latest_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.04)  # ~25 fps


# ---- Flask Routes ----

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
    file    = request.files['image']
    name    = request.form['name'].strip()
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
    cmd  = data.get('command', 'S')
    print(f"Manual command received: {cmd}")
    return jsonify({"success": True})


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify(engine.get_status())


if __name__ == '__main__':
    print("Starting background threads...")
    Thread(target=video_thread,    daemon=True).start()
    Thread(target=telemetry_thread, daemon=True).start()
    print("Dashboard running at http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)
