import os
import pickle
from deepface import DeepFace
import numpy as np

# =========================
# Paths
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_PATH = os.path.join(
    BASE_DIR, "data", "external_dataset", "prepared_facescrub"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "database", "embeddings"
)

OUTPUT_FILE = os.path.join(OUTPUT_PATH, "face_embeddings.pkl")

os.makedirs(OUTPUT_PATH, exist_ok=True)

# =========================
# Storage
# =========================

embeddings_db = {}

# =========================
# Processing
# =========================

print("📂 Reading dataset from:", DATASET_PATH)

for person_name in os.listdir(DATASET_PATH):
    person_dir = os.path.join(DATASET_PATH, person_name)

    if not os.path.isdir(person_dir):
        continue

    print(f"\n👤 Processing {person_name}")

    person_embeddings = []

    for image_name in os.listdir(person_dir):
        image_path = os.path.join(person_dir, image_name)

        try:
            embedding = DeepFace.represent(
                img_path=image_path,
                model_name="Facenet",
                enforce_detection=True
            )[0]["embedding"]

            person_embeddings.append(embedding)

        except Exception as e:
            print(f"⚠️ Skipped {image_name}: {e}")

    if person_embeddings:
        embeddings_db[person_name] = person_embeddings
        print(f"✅ Stored {len(person_embeddings)} embeddings")

# =========================
# Save to file
# =========================

with open(OUTPUT_FILE, "wb") as f:
    pickle.dump(embeddings_db, f)

print("\n🎉 EMBEDDING EXTRACTION COMPLETED")
print(f"✅ Total identities stored: {len(embeddings_db)}")
print(f"💾 Saved to: {OUTPUT_FILE}")