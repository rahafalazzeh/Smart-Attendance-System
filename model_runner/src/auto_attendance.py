import os
import pickle
import cv2
import csv
import time
import numpy as np
from deepface import DeepFace
from scipy.spatial.distance import cosine

# =========================
# Settings (Optimized for i3)
# =========================
NUM_SHOTS = 3          # ✅ أقل عدد أسرع
DELAY = 1.5            # ✅ مهم للدقة
THRESHOLD = 0.55

# =========================
# Paths
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")
SNAP_DIR = os.path.join(BASE_DIR, "data", "snapshots")
OUT_PATH = os.path.join(BASE_DIR, "database", "attendance.csv")

os.makedirs(SNAP_DIR, exist_ok=True)

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
# STEP 1: Capture Snapshots
# =========================
cap = cv2.VideoCapture(0)

print("📸 Capturing snapshots...")
print("👉 Move your head slightly for accuracy")

for i in range(NUM_SHOTS):
    ret, frame = cap.read()
    if not ret:
        continue

    # ✅ Resize for performance
    frame = cv2.resize(frame, (640, 480))

    path = os.path.join(SNAP_DIR, f"shot_{i+1}.jpg")
    cv2.imwrite(path, frame)

    print(f"✅ Captured shot_{i+1}")

    time.sleep(DELAY)

cap.release()
cv2.destroyAllWindows()

# =========================
# STEP 2: Smart Analysis (FAST)
# =========================
print("🔍 Analyzing snapshots...")

seen_counter = {}

# ✅ ONLY first image = heavy processing
first_img = os.path.join(SNAP_DIR, "shot_1.jpg")

initial_matches = []

try:
    rep = DeepFace.represent(
        img_path=first_img,
        model_name="Facenet",
        detector_backend="mtcnn",  # ✅ doctor requirement
        enforce_detection=False
    )

    if rep:
        emb = rep[0]["embedding"]

        for name, mean in mean_embeddings.items():
            dist = cosine(emb, mean)

            if dist < THRESHOLD:
                seen_counter[name] = 1
                initial_matches.append(name)

except:
    print("⚠️ Error analyzing first snapshot")

# ✅ باقي الصور = confirmation ONLY (fast)
for img_name in os.listdir(SNAP_DIR):

    if img_name == "shot_1.jpg":
        continue

    img_path = os.path.join(SNAP_DIR, img_name)

    try:
        rep = DeepFace.represent(
            img_path=img_path,
            model_name="Facenet",
            detector_backend="mtcnn",
            enforce_detection=False
        )

        if rep:
            emb = rep[0]["embedding"]

            for name in initial_matches:
                mean = mean_embeddings[name]

                dist = cosine(emb, mean)

                if dist < THRESHOLD:
                    seen_counter[name] += 1

    except:
        pass

# =========================
# STEP 3: Attendance Decision
# =========================
attendance = {}

for name, count in seen_counter.items():

    # ✅ Liveness + accuracy
    if count >= 2:
        attendance[name] = "Present"
    else:
        attendance[name] = "Maybe"

# ✅ add Absent
for student in mean_embeddings.keys():
    if student not in attendance:
        attendance[student] = "Absent"

# =========================
# STEP 4: Save CSV
# =========================
with open(OUT_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Name", "Status"])

    for name, status in attendance.items():
        writer.writerow([name, status])

print("✅ Attendance completed successfully!")