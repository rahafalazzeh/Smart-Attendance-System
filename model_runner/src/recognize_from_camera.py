import os
import pickle
import cv2
import numpy as np
from collections import deque
from deepface import DeepFace
from scipy.spatial.distance import cosine

# =========================
# Paths
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")

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
THRESHOLD = 0.55
FRAME_SKIP = 5
frame_count = 0
BUFFER = deque(maxlen=7)
prediction = "Unknown"


# =========================
# Camera
# =========================
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    # ✅ Resize (سرعة)
    small_frame = cv2.resize(frame, (320, 240))

    # ✅ Frame skipping
    if frame_count % FRAME_SKIP == 0:

        try:
            rep = DeepFace.represent(
                img_path=small_frame,
                model_name="Facenet",
                detector_backend="mtcnn",   # ✅ تعديل الدكتور
                enforce_detection=False
            )

            if rep:
                emb = rep[0]["embedding"]

                best = None
                best_score = float("inf")

                for name, mean in mean_embeddings.items():
                    dist = cosine(emb, mean)
                    if dist < best_score:
                        best_score = dist
                        best = name

                if best_score < THRESHOLD:
                    prediction = best

        except:
            prediction = "Unknown"

    # ✅ smoothing
    if frame_count % FRAME_SKIP == 0:
        BUFFER.append(prediction)

    if BUFFER:
        final = max(set(BUFFER), key=BUFFER.count)
    else:
        final = prediction

    cv2.putText(frame, f"Name: {final}",
                (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1, (0, 255, 0), 2)

    cv2.imshow("Face Recognition", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()