import os
import pickle
import shutil
import tempfile
from deepface import DeepFace
from utils_logger import write_log

# =========================
# Paths
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(
    BASE_DIR,
    "data",
    "external_dataset",
    "prepared_facescrub"
)

OUTPUT_EMB_PATH = os.path.join(
    BASE_DIR,
    "database",
    "embeddings",
    "face_embeddings_IT_students.pkl"
)

# Temporary English-only path for DeepFace
TEMP_DIR = os.path.join(tempfile.gettempdir(), "deepface_temp_images")
os.makedirs(TEMP_DIR, exist_ok=True)

# =========================
# Settings
# =========================

VALID_EXTENSIONS = (".jpg", ".jpeg", ".png")


# =========================
# Helpers
# =========================

def make_safe_temp_copy(img_path, person_label, counter):
    extension = os.path.splitext(img_path)[1].lower()

    safe_filename = f"{person_label}_{counter}{extension}"
    safe_path = os.path.join(TEMP_DIR, safe_filename)

    shutil.copy2(img_path, safe_path)

    return safe_path


# =========================
# Build embeddings
# =========================

def build_embeddings():
    if not os.path.exists(DATASET_PATH):
        print("Dataset folder not found:", DATASET_PATH)
        return

    db = {}

    people_folders = [
        folder for folder in os.listdir(DATASET_PATH)
        if os.path.isdir(os.path.join(DATASET_PATH, folder))
    ]

    if not people_folders:
        print("No student folders found.")
        return

    print("Found students:", len(people_folders))
    print("-" * 50)

    write_log("INFO", f"Building embeddings from dataset: {DATASET_PATH}")

    for person in people_folders:
        person_label = person.strip().lower().replace(" ", "_")
        person_path = os.path.join(DATASET_PATH, person)

        print(f"Processing: {person_label}")
        write_log("INFO", f"Processing student folder: {person_label}")

        embeddings = []
        processed_images = 0
        failed_images = 0
        image_counter = 1

        for img_name in os.listdir(person_path):
            img_path = os.path.join(person_path, img_name)

            if not os.path.isfile(img_path):
                continue

            if not img_name.lower().endswith(VALID_EXTENSIONS):
                continue

            safe_img_path = None

            try:
                safe_img_path = make_safe_temp_copy(
                    img_path,
                    person_label,
                    image_counter
                )

                rep = DeepFace.represent(
                    img_path=safe_img_path,
                    model_name="Facenet",
                    enforce_detection=False
                )

                embeddings.append(rep[0]["embedding"])
                processed_images += 1
                image_counter += 1

            except Exception as e:
                failed_images += 1
                write_log(
                    "ERROR",
                    f"Failed image for {person_label}: {img_name} | {str(e)}"
                )

            finally:
                if safe_img_path and os.path.exists(safe_img_path):
                    try:
                        os.remove(safe_img_path)
                    except:
                        pass

        if embeddings:
            db[person_label] = embeddings

            print(f"  Added: {person_label}")
            print(f"  Valid embeddings: {len(embeddings)}")
            print(f"  Failed images: {failed_images}")
            print()

            write_log(
                "SUCCESS",
                f"Added embeddings for {person_label} | valid: {len(embeddings)} | failed: {failed_images}"
            )

        else:
            print(f"  No valid embeddings for: {person_label}")
            print()

            write_log("ERROR", f"No valid embeddings generated for {person_label}")

    if not db:
        print("No embeddings were generated.")
        write_log("ERROR", "No embeddings were generated from dataset.")
        return

    with open(OUTPUT_EMB_PATH, "wb") as f:
        pickle.dump(db, f)

    print("-" * 50)
    print("Embeddings file created successfully:")
    print(OUTPUT_EMB_PATH)
    print("Total labels:", len(db))

    write_log("SUCCESS", f"Embeddings file created: {OUTPUT_EMB_PATH}")
    write_log("SUCCESS", f"Total labels generated: {len(db)}")


if __name__ == "__main__":
    build_embeddings()