import cv2
import face_recognition
import mediapipe as mp
import os

# Load known faces
known_encodings = []
known_names = []

path = "known_faces"

for file in os.listdir(path):
    img = face_recognition.load_image_file(f"{path}/{file}")
    enc = face_recognition.face_encodings(img)

    if len(enc) > 0:
        known_encodings.append(enc[0])
        known_names.append(os.path.splitext(file)[0])

# MediaPipe detector
mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.6)

video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

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

    # Encode faces from full image
    encodings = face_recognition.face_encodings(rgb, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, encodings):

        matches = face_recognition.compare_faces(known_encodings, face_encoding)

        name = "Unknown"

        if True in matches:
            index = matches.index(True)
            name = known_names[index]

        cv2.rectangle(frame, (left, top), (right, bottom), (0,255,0), 2)
        cv2.putText(frame, name, (left, top-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)

    cv2.imshow("Fast Face Recognition", frame)

    if cv2.waitKey(1) == 27:
        break

video.release()
cv2.destroyAllWindows()