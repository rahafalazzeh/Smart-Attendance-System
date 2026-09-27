import os
import pickle
from deepface import DeepFace

# =========================
# تحديد مسار المشروع
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_PATH = os.path.join(
    BASE_DIR, "data", "external_dataset", "prepared_facescrub"
)

EMBEDDINGS_PATH = os.path.join(
    BASE_DIR, "database", "embeddings", "face_embeddings.pkl"
)

MY_NAME = "Jana"   # ✅ اسم الفولدر تبع صورك (حساس للأحرف)

# =========================
# تحميل قاعدة embeddings الحالية
# =========================

with open(EMBEDDINGS_PATH, "rb") as f:
    embeddings_db = pickle.load(f)

print("✅ Loaded existing embeddings")

# =========================
# استخراج embeddings لصور Jana فقط
# =========================

my_folder = os.path.join(DATASET_PATH, MY_NAME)

if not os.path.isdir(my_folder):
    raise FileNotFoundError("❌ Folder 'Jana' not found in prepared_facescrub")

my_embeddings = []

for img in os.listdir(my_folder):
    if not img.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    img_path = os.path.join(my_folder, img)

    try:
        emb = DeepFace.represent(
            img_path=img_path,
            model_name="Facenet",
            enforce_detection=True
        )[0]["embedding"]

        my_embeddings.append(emb)

    except Exception as e:
        print(f"⚠️ Skipped {img}: {e}")

embeddings_db[MY_NAME] = my_embeddings

print(f"✅ Stored {len(my_embeddings)} embeddings for {MY_NAME}")

# =========================
# حفظ قاعدة البيانات المحدّثة
# =========================

with open(EMBEDDINGS_PATH, "wb") as f:
    pickle.dump(embeddings_db, f)

print("🎉 Embeddings updated successfully")