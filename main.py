import cv2
import face_recognition
import os

known_encodings = []
known_names = []

path = "known_faces"

# Load known faces
for file in os.listdir(path):
    img = face_recognition.load_image_file(f"{path}/{file}")
    enc = face_recognition.face_encodings(img)

    if len(enc) > 0:
        known_encodings.append(enc[0])
        known_names.append(os.path.splitext(file)[0])

# Start webcam
video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

while True:
    ret, frame = video.read()

    # Resize frame for faster processing
    small_frame = cv2.resize(frame, (0,0), fx=0.25, fy=0.25)

    # Convert BGR → RGB
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Detect faces
    faces = face_recognition.face_locations(rgb_small)

    # Encode faces
    encodings = face_recognition.face_encodings(rgb_small, faces)

    for (top, right, bottom, left), face_encoding in zip(faces, encodings):

        matches = face_recognition.compare_faces(known_encodings, face_encoding)

        name = "Unknown"

        if True in matches:
            index = matches.index(True)
            name = known_names[index]

        # Scale face coordinates back
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        cv2.rectangle(frame,(left,top),(right,bottom),(0,255,0),2)
        cv2.putText(frame,name,(left,top-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,255,0),2)

    cv2.imshow("Face Recognition", frame)

    if cv2.waitKey(1) == 27:
        break

video.release()
cv2.destroyAllWindows()