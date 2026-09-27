import os
import time
import pickle
import shutil
import cv2
import tempfile
from flask import Flask, request, jsonify
from deepface import DeepFace
from utils_logger import write_log

app = Flask(__name__)

# =========================
# Settings
# =========================

CAMERA_INDEX = 1       # 1 = phone camera, 0 = laptop camera
NUM_SHOTS = 5
DELAY = 1.5
RESIZE = (640, 480)

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

EMB_PATH = os.path.join(
    BASE_DIR,
    "database",
    "embeddings",
    "face_embeddings.pkl"
)

os.makedirs(DATASET_PATH, exist_ok=True)

TEMP_DIR = os.path.join(tempfile.gettempdir(), "deepface_registration_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# =========================
# Helpers
# =========================

def clean_face_label(face_label):
    face_label = face_label.strip().lower()
    face_label = face_label.replace(" ", "_")
    return face_label


def capture_student_images(face_label):
    person_path = os.path.join(DATASET_PATH, face_label)
    os.makedirs(person_path, exist_ok=True)

    write_log("INFO", f"Images folder ready for {face_label}: {person_path}")

    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
       write_log("ERROR", f"Cannot open camera. Camera index: {CAMERA_INDEX}")
       raise RuntimeError("Cannot open camera")

    write_log("INFO", f"Camera opened successfully. Camera index: {CAMERA_INDEX}")
    print(f"Starting face capture for: {face_label}")
    print("Please look at the camera and slightly move your head.")
    print("Press q to stop early.")

    count = 0

    while count < NUM_SHOTS:
        ret, frame = cap.read()

        if not ret:
            continue

        frame = cv2.resize(frame, RESIZE)

        cv2.imshow("Face Registration", frame)
        filename = f"{face_label}_{count + 1}.jpg"
        filepath = os.path.join(person_path, filename)

        success, encoded_image = cv2.imencode(".jpg", frame)

        if success:
           encoded_image.tofile(filepath)
           write_log("INFO", f"Saved image: {filename}")
           count += 1
        else:
           write_log("ERROR", f"Failed to save image: {filename}")
           continue
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(DELAY)

    cap.release()
    cv2.destroyAllWindows()

    if count == 0:
        raise RuntimeError("No images captured")

    return person_path

def make_safe_temp_copy(img_path, face_label, counter):
    extension = os.path.splitext(img_path)[1].lower()
    safe_filename = f"{face_label}_{counter}{extension}"
    safe_path = os.path.join(TEMP_DIR, safe_filename)

    shutil.copy2(img_path, safe_path)

    return safe_path


def update_embeddings(face_label, person_path):
    if not os.path.exists(EMB_PATH):
        write_log("ERROR", f"Embeddings file not found: {EMB_PATH}")
        raise RuntimeError("Embeddings file not found")

    write_log("INFO", f"Loading embeddings file: {EMB_PATH}")

    backup_path = EMB_PATH.replace(".pkl", "_before_registration_backup.pkl")
    shutil.copy2(EMB_PATH, backup_path)

    write_log("INFO", f"Embeddings backup created: {backup_path}")

    with open(EMB_PATH, "rb") as f:
        db = pickle.load(f)

    embeddings = []
    image_counter = 1

    for img_name in os.listdir(person_path):
        img_path = os.path.join(person_path, img_name)

        if not os.path.isfile(img_path):
            continue

        safe_img_path = None

        try:
            safe_img_path = make_safe_temp_copy(
                img_path,
                face_label,
                image_counter
            )

            rep = DeepFace.represent(
                img_path=safe_img_path,
                model_name="Facenet",
                enforce_detection=False
            )

            embeddings.append(rep[0]["embedding"])
            image_counter += 1

        except Exception as e:
            write_log("ERROR", f"Could not process image {img_name}: {str(e)}")

        finally:
            if safe_img_path and os.path.exists(safe_img_path):
                try:
                    os.remove(safe_img_path)
                except:
                    pass

    if len(embeddings) == 0:
        raise RuntimeError("No valid embeddings generated")

    db[face_label] = embeddings

    with open(EMB_PATH, "wb") as f:
        pickle.dump(db, f)

    write_log("SUCCESS", f"Embeddings saved successfully for label: {face_label}")

    return len(embeddings)
# =========================
# Routes
# =========================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "message": "Face registration service is running"
    }), 200


@app.route("/register-face", methods=["POST"])
def register_face():
    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "No JSON data received"
        }), 400

    face_label = data.get("face_label", "")

    face_label = clean_face_label(face_label)

    if not face_label:
        write_log("ERROR", "Face registration failed: face_label is required")

        return jsonify({
           "success": False,
           "message": "face_label is required"
        }), 400

    write_log("INFO", f"Face registration request received for label: {face_label}")

    try:
       write_log("INFO", f"Starting face registration process for: {face_label}")

       person_path = capture_student_images(face_label)
       write_log("SUCCESS", f"Images captured successfully for: {face_label}")

       embeddings_count = update_embeddings(face_label, person_path)
       write_log("SUCCESS", f"Embeddings updated for: {face_label} | Count: {embeddings_count}")

       return jsonify({
           "success": True,
           "message": "Face registered successfully",
           "face_label": face_label,
           "images_path": person_path,
           "embeddings_count": embeddings_count
    }), 200

    except Exception as e:
       write_log("ERROR", f"Face registration failed for {face_label}: {str(e)}")

       return jsonify({
           "success": False,
           "message": str(e)
    }), 500


# =========================
# Run
# =========================

if __name__ == "__main__":
    write_log("INFO", "Face Registration Service Started")
    write_log("INFO", "Running on http://localhost:6000")
    app.run(host="127.0.0.1", port=6000, debug=False)