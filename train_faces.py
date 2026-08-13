"""
Face Training Helper — Human Detection Robot
============================================
Run this script to interactively capture training photos from your webcam.
Each photo is saved to  known_faces/<YourName>/  as a numbered image.
The more photos you take (different angles, lighting), the better the accuracy.

Usage:
    python train_faces.py

Controls (while webcam window is open):
    SPACE  — capture current frame as a training photo
    ESC    — finish and exit
"""

import cv2
import os
import time

KNOWN_FACES_DIR = "known_faces"
MIN_PHOTOS = 5
RECOMMENDED_PHOTOS = 10


def capture_training_photos(name: str):
    person_dir = os.path.join(KNOWN_FACES_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    # Find the next available photo number
    existing = [f for f in os.listdir(person_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    photo_idx = len(existing) + 1

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open webcam.")
        return

    win = f"Training — {name}  |  SPACE=capture  ESC=done"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 800, 520)

    captured = 0
    flash    = 0  # countdown for flash effect

    print(f"\n📸 Capturing photos for: {name}")
    print(f"   Aim: ≥{RECOMMENDED_PHOTOS} photos from different angles and distances")
    print(f"   SPACE → capture   ESC → finish\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        H, W, _ = display.shape

        # Flash feedback
        if flash > 0:
            overlay = display.copy()
            cv2.rectangle(overlay, (0,0), (W,H), (255,255,255), -1)
            cv2.addWeighted(overlay, flash / 10, display, 1 - flash / 10, 0, display)
            flash = max(0, flash - 1)

        # Instructions overlay
        cv2.rectangle(display, (0, H-80), (W, H), (15,15,25), -1)
        cv2.putText(display, f"Person: {name}",
                    (10, H-55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,136), 1, cv2.LINE_AA)
        cv2.putText(display, f"Captured: {captured} photo(s)   (aim for {RECOMMENDED_PHOTOS}+)",
                    (10, H-30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,200,0), 1, cv2.LINE_AA)
        cv2.putText(display, "SPACE = capture    ESC = done",
                    (10, H-8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150,150,150), 1, cv2.LINE_AA)

        # Crosshair guide
        cx, cy = W//2, H//2
        cv2.line(display, (cx-40,cy), (cx+40,cy), (0,200,255), 1)
        cv2.line(display, (cx,cy-40), (cx,cy+40), (0,200,255), 1)
        cv2.circle(display, (cx,cy), 60, (0,200,255), 1)

        # Progress dots
        for i in range(RECOMMENDED_PHOTOS):
            dot_color = (0,255,136) if i < captured else (60,60,60)
            cv2.circle(display, (W - 30, 30 + i*22), 8, dot_color, -1)

        cv2.imshow(win, display)
        key = cv2.waitKey(1) & 0xFF

        if key == 27:   # ESC — done
            break

        if key == 32:   # SPACE — capture
            save_path = os.path.join(person_dir, f"{photo_idx:03d}.jpg")
            cv2.imwrite(save_path, frame)
            print(f"  ✔ Saved: {save_path}")
            photo_idx += 1
            captured  += 1
            flash      = 8

            if captured == MIN_PHOTOS:
                print(f"  ℹ Minimum reached ({MIN_PHOTOS}). Keep going for better accuracy!")
            if captured == RECOMMENDED_PHOTOS:
                print(f"  🎯 Recommended count reached! You can press ESC or take more.")

    cap.release()
    cv2.destroyAllWindows()

    total_photos = len(os.listdir(person_dir))
    print(f"\n✅ Done! {name} now has {total_photos} training photo(s) in {person_dir}")
    if total_photos < MIN_PHOTOS:
        print(f"⚠  Warning: fewer than {MIN_PHOTOS} photos may reduce accuracy.")


def show_current_faces():
    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
    print("\n━━━ Current known faces ━━━")
    found = False

    # Subfolders
    for entry in os.scandir(KNOWN_FACES_DIR):
        if entry.is_dir():
            n = len([f for f in os.scandir(entry.path)
                     if f.name.lower().endswith(('.jpg','.jpeg','.png'))])
            status = "✔" if n >= MIN_PHOTOS else f"⚠ only {n} photo(s)"
            print(f"  {entry.name:<20} {status}")
            found = True

    # Flat files
    for entry in os.scandir(KNOWN_FACES_DIR):
        if entry.is_file() and entry.name.lower().endswith(('.jpg','.jpeg','.png')):
            name = os.path.splitext(entry.name)[0]
            print(f"  {name:<20} 1 photo (add more by creating known_faces/{name}/ folder)")
            found = True

    if not found:
        print("  (none yet)")
    print()


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Face Training — Human Detection Robot")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    show_current_faces()

    while True:
        print("Options:")
        print("  1 — Add / update a person (capture from webcam)")
        print("  2 — Show current known faces")
        print("  3 — Exit")
        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            name = input("Enter person's name (no spaces, e.g. Alice): ").strip()
            if name:
                capture_training_photos(name)
        elif choice == "2":
            show_current_faces()
        elif choice == "3":
            print("Done! Run  python final.py  to start the robot.")
            break
        else:
            print("Invalid choice, try again.\n")
