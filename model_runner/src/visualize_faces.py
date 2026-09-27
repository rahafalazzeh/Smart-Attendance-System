import os
import pickle
import cv2
import numpy as np
from deepface import DeepFace
from scipy.spatial.distance import cosine

# =========================
# Paths
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IMAGE_PATH = os.path.join(BASE_DIR, "data", "test_group.jpg")
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "output_result.jpg")

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
# Read image
# =========================
img = cv2.imread(IMAGE_PATH)

print("🔍 Detecting faces...")

# =========================
# Detect faces (MTCNN)
# =========================
faces = DeepFace.extract_faces(
    img_path=img,
    detector_backend="mtcnn",
    enforce_detection=False
)

print(f"✅ Found {len(faces)} faces")

# ✅ القيم النهائية المتوازنة
THRESHOLD = 0.55
GAP = 0.005

# =========================
# Process faces
# =========================
for face in faces:

    area = face["facial_area"]

    x = area["x"]
    y = area["y"]
    w = area["w"]
    h = area["h"]

    # تجهيز الوجه
    face_img = face["face"]
    face_img = (face_img * 255).astype("uint8")
    face_img = cv2.resize(face_img, (224, 224))

    name = "Unknown"

    try:
        rep = DeepFace.represent(
            img_path=face_img,
            model_name="Facenet",
            enforce_detection=False
        )

        emb = rep[0]["embedding"]

        distances = []

        for person, mean in mean_embeddings.items():
            dist = cosine(emb, mean)
            distances.append((person, dist))

        # ترتيب حسب الأقرب
        distances.sort(key=lambda x: x[1])

        best, best_score = distances[0]
        second_best, second_score = distances[1]

        # ✅ القرار الذكي (Balanced)
        if best_score < THRESHOLD and (second_score - best_score) > GAP:
            name = best
        else:
            name = "Unknown"

    except:
        name = "Unknown"

    # =========================
    # Draw rectangle
    # =========================
    cv2.rectangle(
        img,
        (x, y),
        (x + w, y + h),
        (0, 255, 0),
        2
    )

    # =========================
    # Write text inside box
    # =========================
    text_y = y + h - 10

    (text_w, text_h), _ = cv2.getTextSize(
        name,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        2
    )

    # خلفية للنص
    cv2.rectangle(
        img,
        (x, text_y - text_h - 5),
        (x + text_w, text_y + 5),
        (0, 0, 0),
        -1
    )

    # كتابة الاسم
    cv2.putText(
        img,
        name,
        (x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )

# =========================
# Save image (compressed)
# =========================
cv2.imwrite(OUTPUT_PATH, img, [cv2.IMWRITE_JPEG_QUALITY, 80])

print("✅ Output saved as output_result.jpg")