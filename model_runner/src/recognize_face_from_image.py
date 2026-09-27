import os
import pickle
import cv2
import numpy as np
from deepface import DeepFace
from scipy.spatial.distance import cosine

# =========================
# تحديد مسار المشروع
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")

EMBEDDINGS_PATH = os.path.join(
    BASE_DIR, "database", "embeddings", "face_embeddings.pkl"
)

# =========================
# تحميل قاعدة البيانات
# =========================

with open(EMBEDDINGS_PATH, "rb") as f:
    embeddings_db = pickle.load(f)

print("✅ Embeddings loaded")
print(f"✅ Total identities stored: {len(embeddings_db)}")

# =========================
# إيجاد صورة الاختبار تلقائيًا
# =========================

image_files = [
    f for f in os.listdir(DATA_DIR)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
]

if not image_files:
    raise FileNotFoundError("❌ No image found in data/ folder")

TEST_IMAGE_PATH = os.path.join(DATA_DIR, image_files[0])
print("📸 Using test image:", image_files[0])

# =========================
# تحميل الصورة
# =========================

image = cv2.imread(TEST_IMAGE_PATH)

if image is None:
    raise ValueError("❌ Failed to load the image")

# =========================
# استخراج embedding للصورة
# =========================

test_embedding = DeepFace.represent(
    img_path=image,
    model_name="Facenet",
    enforce_detection=True
)[0]["embedding"]

# =========================
# المقارنة مع قاعدة البيانات
# =========================

best_match = None
best_score = float("inf")

for person_name, person_embeddings in embeddings_db.items():
    for emb in person_embeddings:
        distance = cosine(test_embedding, emb)
        if distance < best_score:
            best_score = distance
            best_match = person_name

# =========================
# القرار النهائي
# =========================

THRESHOLD = 0.4

if best_score < THRESHOLD:
    print(f"\n✅ MATCH FOUND: {best_match}")
    print(f"Distance: {best_score:.4f}")
else:
    print("\n❌ UNKNOWN PERSON")
    print(f"Distance: {best_score:.4f}")