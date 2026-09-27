import os
import pickle
import cv2
import csv
import numpy as np
from datetime import datetime
from deepface import DeepFace
from scipy.spatial.distance import cosine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")
OUT_PATH = os.path.join(BASE_DIR, "database", "attendance.csv")

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

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    small_frame = cv2.resize(frame, (320, 240))

    # ✅ نحسب فقط كل 몇 فريم
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
                else:
                    print(f"Unknown face | best distance = {best_dist:.4f}")

        except:
            pass

    cv2.imshow("Attendance System", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

# =========================
# Save CSV
# =========================
with open(OUT_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Name", "Time"])
    for name, time in attendance.items():
        writer.writerow([name, time])

print("✅ Attendance saved successfully")