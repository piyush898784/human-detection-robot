import cv2
import mediapipe as mp
import face_recognition
import os
import numpy as np

# --------------------------
# Load known faces
# --------------------------

known_encodings = []
known_names = []

path = "known_faces"

for file in os.listdir(path):
    img = face_recognition.load_image_file(f"{path}/{file}")
    enc = face_recognition.face_encodings(img)

    if len(enc) > 0:
        known_encodings.append(enc[0])
        known_names.append(os.path.splitext(file)[0])

# --------------------------
# MediaPipe face detection
# --------------------------

mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(0, 0.6)

# --------------------------
# Kalman Filter Setup
# --------------------------

kalman = cv2.KalmanFilter(4,2)

kalman.measurementMatrix = np.array([[1,0,0,0],
                                     [0,1,0,0]], np.float32)

kalman.transitionMatrix = np.array([[1,0,1,0],
                                    [0,1,0,1],
                                    [0,0,1,0],
                                    [0,0,0,1]], np.float32)

kalman.processNoiseCov = np.eye(4, dtype=np.float32) * 0.03

# --------------------------
# Camera
# --------------------------

video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

HORIZONTAL_FOV = 60
VERTICAL_FOV = 45

while True:

    ret, frame = video.read()

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    results = face_detection.process(rgb)

    if results.detections:

        h, w, _ = frame.shape

        for detection in results.detections:

            bbox = detection.location_data.relative_bounding_box

            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)

            top = y
            right = x + width
            bottom = y + height
            left = x

            face_locations = [(top,right,bottom,left)]

            encodings = face_recognition.face_encodings(rgb, face_locations)

            for face_encoding in encodings:

                name = "Unknown"

                matches = face_recognition.compare_faces(known_encodings,
                                                         face_encoding)

                if True in matches:
                    index = matches.index(True)
                    name = known_names[index]

                # Face center
                face_center_x = (left + right) / 2
                face_center_y = (top + bottom) / 2

                measurement = np.array([[np.float32(face_center_x)],
                                        [np.float32(face_center_y)]])

                kalman.correct(measurement)

                prediction = kalman.predict()

                smooth_x = prediction[0][0]
                smooth_y = prediction[1][0]

                # Draw predicted position
                cv2.circle(frame,
                           (int(smooth_x),int(smooth_y)),
                           8,
                           (0,0,255),
                           -1)

                # ----------------------
                # Angle calculation
                # ----------------------

                frame_center_x = w/2
                frame_center_y = h/2

                pixel_offset_x = smooth_x - frame_center_x
                pixel_offset_y = smooth_y - frame_center_y

                angle_per_pixel_x = HORIZONTAL_FOV / w
                angle_per_pixel_y = VERTICAL_FOV / h

                yaw = pixel_offset_x * angle_per_pixel_x
                pitch = pixel_offset_y * angle_per_pixel_y

                # ----------------------
                # Commands
                # ----------------------

                command = "CENTER"

                if yaw > 10:
                    command = "TURN RIGHT"
                elif yaw < -10:
                    command = "TURN LEFT"

                # ----------------------
                # Display
                # ----------------------

                cv2.rectangle(frame,(left,top),(right,bottom),(0,255,0),2)

                cv2.putText(frame,name,
                            (left,top-10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0,255,0),
                            2)

                cv2.putText(frame,
                            f"Yaw: {yaw:.2f}",
                            (20,40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (255,255,0),
                            2)

                cv2.putText(frame,
                            f"Pitch: {pitch:.2f}",
                            (20,70),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (255,255,0),
                            2)

                cv2.putText(frame,
                            command,
                            (20,110),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0,255,255),
                            3)

    cv2.imshow("Kalman Face Tracking", frame)

    if cv2.waitKey(1) == 27:
        break

video.release()
cv2.destroyAllWindows()