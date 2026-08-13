import cv2
import mediapipe as mp
import face_recognition
import os

# -------------------------
# Load known faces
# -------------------------

known_encodings = []
known_names = []

path = "known_faces"

for file in os.listdir(path):
    img = face_recognition.load_image_file(f"{path}/{file}")
    enc = face_recognition.face_encodings(img)

    if len(enc) > 0:
        known_encodings.append(enc[0])
        known_names.append(os.path.splitext(file)[0])

# -------------------------
# MediaPipe face detector
# -------------------------

mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(
    model_selection=0,
    min_detection_confidence=0.6
)

# -------------------------
# Camera
# -------------------------

video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

previous_area = 0

while True:

    ret, frame = video.read()

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    results = face_detection.process(rgb)

    face_locations = []

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

            face_locations.append((top, right, bottom, left))

    encodings = face_recognition.face_encodings(rgb, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, encodings):

        name = "Unknown"

        matches = face_recognition.compare_faces(known_encodings, face_encoding)

        if True in matches:
            index = matches.index(True)
            name = known_names[index]

        # -------------------------
        # Draw box
        # -------------------------

        cv2.rectangle(frame,(left,top),(right,bottom),(0,255,0),2)
        cv2.putText(frame,name,(left,top-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,0),2)

        # -------------------------
        # Movement detection
        # -------------------------

        frame_h, frame_w, _ = frame.shape

        frame_center_x = frame_w // 2
        face_center_x = (left + right) // 2

        threshold = 80

        direction = "CENTERED"

        if face_center_x < frame_center_x - threshold:
            direction = "MOVE LEFT"

        elif face_center_x > frame_center_x + threshold:
            direction = "MOVE RIGHT"

        # -------------------------
        # Forward / backward
        # -------------------------

        area = (right-left) * (bottom-top)

        if previous_area != 0:

            if area > previous_area + 3000:
                direction = "MOVE FORWARD"

            elif area < previous_area - 3000:
                direction = "MOVE BACKWARD"

        previous_area = area

        cv2.putText(frame,direction,(20,40),
                    cv2.FONT_HERSHEY_SIMPLEX,1,(0,255,255),3)

    cv2.imshow("Face Tracking System", frame)

    if cv2.waitKey(1) == 27:
        break

video.release()
cv2.destroyAllWindows()