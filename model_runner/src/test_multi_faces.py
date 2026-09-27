import os
import pickle
import cv2
import numpy as np
from deepface import DeepFace
from scipy.spatial.distance import cosine
from sklearn.metrics import accuracy_score, recall_score, f1_score

# =========================
# CONFIG (FINAL FIX)
# =========================
THRESHOLD = 0.5
GAP = 0.01

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_PATH = os.path.join(BASE_DIR, "data", "test_group.jpg")
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")

# =========================
# LOAD EMBEDDINGS
# =========================
with open(EMB_PATH, "rb") as f:
    db = pickle.load(f)

mean_embeddings = {
    person: np.mean(np.array(embeddings), axis=0)
    for person, embeddings in db.items()
}

# =========================
# LOAD IMAGE
# =========================
img = cv2.imread(IMAGE_PATH)

faces = DeepFace.extract_faces(
    img_path=img,
    detector_backend="mtcnn",
    enforce_detection=False
)

print(f"\n✅ Found {len(faces)} faces\n")

y_true = []
y_pred = []

# =========================
# PROCESS
# =========================
for i, face in enumerate(faces):

    face_img = face["face"]
    face_img = (face_img * 255).astype("uint8")
    face_img = cv2.resize(face_img, (224, 224))

    predicted = "Unknown"

    try:
        rep = DeepFace.represent(
            img_path=face_img,
            model_name="Facenet",
            enforce_detection=False
        )

        emb = rep[0]["embedding"]

        distances = [
            (name, cosine(emb, mean))
            for name, mean in mean_embeddings.items()
        ]

        distances.sort(key=lambda x: x[1])

        best, best_score = distances[0]
        second_score = distances[1][1]

        # ✅ FIXED DECISION
        if best_score < THRESHOLD and (second_score - best_score) > GAP:
            predicted = best
        else:
            predicted = "Unknown"

    except:
        predicted = "Unknown"

    # ✅ TRUE LABELS (نفسك)
    if i == 2:
        true = "Jana"
    elif i == 3:
        true = "Leonardo_DiCaprio"
    elif i == 13:
        true = "Selena_Gomez"
    elif i >= 10:
        true = "Unknown"
    else:
        true = "Known"

    y_true.append(true)
    y_pred.append(predicted)

    print(f"[{i+1}] Predicted: {predicted:<25} | True: {true}")

# =========================
# METRICS
# =========================
y_true_bin = [0 if x == "Unknown" else 1 for x in y_true]
y_pred_bin = [0 if x == "Unknown" else 1 for x in y_pred]

accuracy = accuracy_score(y_true_bin, y_pred_bin)
recall = recall_score(y_true_bin, y_pred_bin)
f1 = f1_score(y_true_bin, y_pred_bin)

print("\n📊 FINAL METRICS:")
print(f"✅ Accuracy : {accuracy:.2f}")
print(f"✅ Recall   : {recall:.2f}")
print(f"✅ F1 Score : {f1:.2f}")