import os
import pickle
from deepface import DeepFace

# =========================
# Paths
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_PATH = os.path.join(BASE_DIR, "data", "external_dataset", "prepared_facescrub")
EMB_PATH = os.path.join(BASE_DIR, "database", "embeddings", "face_embeddings.pkl")

# =========================
# Load existing embeddings
# =========================
with open(EMB_PATH, "rb") as f:
    db = pickle.load(f)

print("Loaded existing embeddings.\n")

# =========================
# New People (ADD HERE)
# =========================
NEW_PEOPLE = ["ayah", "leen", "sara", "rama", "rahaf", "tabark", "ghaida", "adam"]

# =========================
# Process each new person
# =========================
for person in NEW_PEOPLE:

    person_path = os.path.join(DATASET_PATH, person)

    if not os.path.isdir(person_path):
        print(f"{person} folder not found, skipping.")
        continue

    embeddings = []

    print(f"Processing {person}...")

    for img_name in os.listdir(person_path):

        img_path = os.path.join(person_path, img_name)

        try:
            rep = DeepFace.represent(
                img_path=img_path,
                model_name="Facenet",
                enforce_detection=False
            )

            embeddings.append(rep[0]["embedding"])

        except:
            continue

    if len(embeddings) > 0:
        db[person] = embeddings
        print(f"{person} added successfully.\n")
    else:
        print(f"No valid embeddings for {person}\n")

# =========================
# Save updated embeddings
# =========================
with open(EMB_PATH, "wb") as f:
    pickle.dump(db, f)

print("✅ New people added successfully to embeddings.")