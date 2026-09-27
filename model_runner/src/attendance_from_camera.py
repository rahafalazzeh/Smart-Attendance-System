import os
import pickle
import cv2
import csv
import requests
import numpy as np
from datetime import datetime
from deepface import DeepFace
from scipy.spatial.distance import cosine


# =========================
# Paths
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")
OUT_PATH = os.path.join(BASE_DIR, "database", "attendance.csv")


# =========================
# API Settings
# =========================
API_URL = "http://localhost:5000/api/mark-attendance"
ACTIVE_SESSION_URL = "http://localhost:5000/api/active-session"


def get_active_session_id():
    try:
        response = requests.get(ACTIVE_SESSION_URL, timeout=5)
        result = response.json()

        if response.status_code == 200 and result.get("success"):
            print("Active session found:", result["session_id"])
            return result["session_id"]

        print("No active session found:", result)
        return None

    except Exception as e:
        print("Error getting active session:", e)
        return None


SESSION_ID = get_active_session_id()

if SESSION_ID is None:
    print("Please start an attendance session from the web first.")
    exit()


def send_attendance_to_api(name):
    data = {
        "session_id": SESSION_ID,
        "name": name
    }

    try:
        response = requests.post(API_URL, json=data, timeout=5)

        try:
            result = response.json()
        except Exception:
            result = response.text

        print("API Status:", response.status_code)
        print("API Response:", result)

    except Exception as e:
        print("Error sending attendance to API:", e)


# =========================
# Load embeddings
# =========================
with open(EMB_PATH, "rb") as f:
    db = pickle.load(f)

mean_embeddings = {
    k: np.mean(np.array(v), axis=0)
    for k, v in db.items()
}


# =========================
# Settings
# =========================
THRESHOLD = 0.40
FRAME_SKIP = 5
frame_count = 0

attendance = {}
seen_counter = {}

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Camera not opened")
    exit()

print("Camera opened successfully")


# =========================
# Camera loop
# =========================
while True:
    ret, frame = cap.read()

    if not ret:
        print("Failed to read frame")
        break

    frame_count += 1
    small_frame = cv2.resize(frame, (320, 240))

    # Process only every few frames
    if frame_count % FRAME_SKIP == 0:

        try:
            rep = DeepFace.represent(
                img_path=small_frame,
                model_name="Facenet",
                detector_backend="mtcnn",
                enforce_detection=False
            )

            if rep:
                emb = rep[0]["embedding"]

                best_name = None
                best_dist = 999

                for name, mean in mean_embeddings.items():
                    dist = cosine(emb, mean)

                    if dist < best_dist:
                        best_dist = dist
                        best_name = name

                if best_name is not None and best_dist < THRESHOLD:
                    seen_counter[best_name] = seen_counter.get(best_name, 0) + 1

                    if seen_counter[best_name] >= 3 and best_name not in attendance:
                        attendance[best_name] = datetime.now().strftime("%H:%M:%S")

                        print(f"✅ {best_name} marked present | distance = {best_dist:.4f}")

                        # Send attendance to Flask API
                        send_attendance_to_api(best_name)

                else:
                    print(f"Unknown face | best distance = {best_dist:.4f}")

        except Exception as e:
            print("Recognition error:", e)

    cv2.imshow("Attendance System", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()


# =========================
# Save CSV backup
# =========================
with open(OUT_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Name", "Time"])

    for name, time in attendance.items():
        writer.writerow([name, time])

print("✅ Attendance saved successfully")