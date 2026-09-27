import os
import csv
import pickle
import logging
import cv2
import threading
import numpy as np

from datetime import datetime
from deepface import DeepFace
from ultralytics import YOLO


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


# =========================
# CONFIG
# =========================
THRESHOLD = 0.50
GAP = 0.03
MIN_FACE_SIZE = 30

# يسجل الحضور بعد 4 مرات تعرف حقيقية على الطالب
CONFIRM_FRAMES = 4

# كم فريم نسمح للتتبع يضل موجود لو التعرف تأخر/فشل مؤقتا
UNKNOWN_GRACE_FRAMES = 12
MAX_TRACK_AGE = 20

# إعدادات ربط الوجوه مع التراكات
IOU_MATCH_THRESHOLD = 0.20
CENTER_MATCH_THRESHOLD = 90

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CAMERA_INDEX = 1
DETECTOR_BACKEND = "opencv"

# =========================
# YOLO11M FACE DETECTION
# =========================
# YOLO is used only to find candidate face areas.
# Recognition remains DeepFace-based like the original code.
YOLO_FACE_MODEL = os.getenv("YOLO_FACE_MODEL", "yolov11m-face.pt")
YOLO_CONF = 0.35
YOLO_IMG_SIZE = 640
YOLO_FACE_MARGIN = 0.55


# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EMB_PATH = os.path.join(
    BASE_DIR,
    "database",
    "embeddings",
    "face_embeddings.pkl"
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "data",
    "live_results"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

ATTENDANCE_CSV = os.path.join(
    OUTPUT_DIR,
    f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
)


# =========================
# LOAD EMBEDDINGS
# =========================
with open(EMB_PATH, "rb") as f:
    db = pickle.load(f)

sample_emb = next(iter(db.values()))[0]
MODEL_NAME = "Facenet" if len(sample_emb) == 128 else "ArcFace"

logger.info(f"Loaded {len(db)} persons | Model: {MODEL_NAME}")


# =========================
# NORMALIZE DATABASE
# =========================
def normalize_embedding(emb):
    emb = np.array(emb, dtype=np.float32)
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 0 else emb


known_embeddings = []
known_names = []

for person, embeddings in db.items():
    for emb in embeddings:
        known_embeddings.append(normalize_embedding(emb))
        known_names.append(person)

known_embeddings = np.array(known_embeddings, dtype=np.float32)
known_names = np.array(known_names)

logger.info(f"Total embeddings loaded: {len(known_embeddings)}")


# =========================
# LOAD YOLO11M FACE DETECTOR
# =========================
if os.path.isabs(YOLO_FACE_MODEL):
    YOLO_FACE_MODEL_PATH = YOLO_FACE_MODEL
else:
    YOLO_FACE_MODEL_PATH = os.path.join(BASE_DIR, YOLO_FACE_MODEL)

logger.info(f"Loading YOLO11m face detector: {YOLO_FACE_MODEL_PATH}")

try:
    yolo_detector = YOLO(YOLO_FACE_MODEL_PATH)
    logger.info("YOLO11m face detector loaded successfully")
except Exception as e:
    raise RuntimeError(
        "Could not load YOLO11m face model. "
        "Make sure the model file exists in model_runner. "
        f"Expected path: {YOLO_FACE_MODEL_PATH}. Original error: {e}"
    )


# =========================
# STATE
# =========================
latest_results = []
latest_batch_id = 0
processed_batch_id = -1
attendance = {}

# العداد صار حسب اسم الطالب، لكن لا يزيد إلا مرة واحدة لكل نتيجة تعرّف جديدة
confirm_counter = {}

# كل وجه له track_id خاص فيه عشان أكثر من وجه يتحركوا لحالهم
tracks = {}
next_track_id = 1

lock = threading.Lock()
processing = False


# =========================
# MATCHING
# =========================
def find_best_match(emb):
    emb = normalize_embedding(emb)

    similarities = np.dot(known_embeddings, emb)
    distances = 1 - similarities

    sorted_idx = np.argsort(distances)

    best_idx = sorted_idx[0]
    best_name = known_names[best_idx]
    best_score = distances[best_idx]

    second_score = 1.0
    for idx in sorted_idx[1:]:
        if known_names[idx] != best_name:
            second_score = distances[idx]
            break

    if best_score < THRESHOLD and (second_score - best_score) > GAP:
        return best_name, best_score

    return "Unknown", best_score


def save_csv():
    with open(ATTENDANCE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "DateTime"])

        for name, dt in attendance.items():
            writer.writerow([name, dt])


# =========================
# TRACKING HELPERS
# =========================
def clamp_bbox(bbox, frame_shape):
    x, y, w, h = [int(v) for v in bbox]
    height, width = frame_shape[:2]

    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))

    return (x, y, w, h)


def bbox_iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter

    return inter / union if union > 0 else 0.0


def center_distance(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    return float(np.hypot(acx - bcx, acy - bcy))


def create_tracker():
    """يحاول إنشاء Tracker قوي. لو OpenCV عندك بدون contrib يرجع None ويشتغل fallback عادي."""
    tracker_factories = [
        lambda: cv2.legacy.TrackerCSRT_create(),
        lambda: cv2.TrackerCSRT_create(),
        lambda: cv2.legacy.TrackerKCF_create(),
        lambda: cv2.TrackerKCF_create(),
        lambda: cv2.legacy.TrackerMOSSE_create(),
    ]

    for factory in tracker_factories:
        try:
            return factory()
        except Exception:
            continue
    return None


def init_tracker(frame, bbox):
    tracker = create_tracker()
    if tracker is None:
        return None

    try:
        tracker.init(frame, tuple(map(float, bbox)))
        return tracker
    except Exception:
        return None


def update_tracks_with_cv_tracker(frame):
    """يحدث مكان كل مربع في كل فريم حتى بين نتائج DeepFace البطيئة."""
    dead_tracks = []

    for track_id, track in list(tracks.items()):
        tracker = track.get("tracker")

        if tracker is None:
            track["age"] += 1
            if track["age"] > MAX_TRACK_AGE:
                dead_tracks.append(track_id)
            continue

        try:
            ok, bbox = tracker.update(frame)
        except Exception:
            ok = False
            bbox = track["bbox"]

        if ok:
            track["bbox"] = clamp_bbox(bbox, frame.shape)
            track["age"] = 0
        else:
            track["age"] += 1
            if track["age"] > MAX_TRACK_AGE:
                dead_tracks.append(track_id)

    for track_id in dead_tracks:
        tracks.pop(track_id, None)


def find_matching_track(bbox, used_track_ids):
    best_track_id = None
    best_score = -1.0

    for track_id, track in tracks.items():
        if track_id in used_track_ids:
            continue

        track_bbox = track["bbox"]
        iou = bbox_iou(bbox, track_bbox)
        dist = center_distance(bbox, track_bbox)

        # score أعلى أفضل: نعطي أولوية للتداخل، ومعه قرب المركز
        score = iou - (dist / 1000.0)

        if (iou >= IOU_MATCH_THRESHOLD or dist <= CENTER_MATCH_THRESHOLD) and score > best_score:
            best_score = score
            best_track_id = track_id

    return best_track_id


def update_name_confirmation(name):
    if name == "Unknown" or name in attendance:
        return

    confirm_counter[name] = confirm_counter.get(name, 0) + 1

    if confirm_counter[name] >= CONFIRM_FRAMES:
        attendance[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"PRESENT: {name}")
        save_csv()


def apply_detections_to_tracks(frame, detections):
    """يربط نتائج DeepFace بالتراكات الموجودة أو ينشئ تراك جديد لكل وجه."""
    global next_track_id

    used_track_ids = set()
    counted_names_this_batch = set()

    for x, y, w, h, name, conf in detections:
        bbox = clamp_bbox((x, y, w, h), frame.shape)
        track_id = find_matching_track(bbox, used_track_ids)

        if track_id is None:
            track_id = next_track_id
            next_track_id += 1
            tracks[track_id] = {
                "bbox": bbox,
                "name": name,
                "conf": conf,
                "age": 0,
                "unknown_age": 0,
                "tracker": None,
            }

        track = tracks[track_id]
        old_name = track.get("name", "Unknown")
        old_conf = track.get("conf", 0.0)

        # لو التعرّف أعطى Unknown مؤقتا، نخلي الاسم القديم لنفس التراك لثبات الليبل
        if name == "Unknown" and old_name != "Unknown" and track.get("unknown_age", 0) < UNKNOWN_GRACE_FRAMES:
            display_name = old_name
            display_conf = old_conf
            track["unknown_age"] = track.get("unknown_age", 0) + 1
        else:
            display_name = name
            display_conf = conf
            track["unknown_age"] = 0 if name != "Unknown" else track.get("unknown_age", 0) + 1

        track.update({
            "bbox": bbox,
            "name": display_name,
            "conf": display_conf,
            "age": 0,
            "tracker": init_tracker(frame, bbox),
        })

        used_track_ids.add(track_id)

        # مهم: العداد يزيد فقط عند تعرّف حقيقي جديد، وليس من الاسم الموروث من التتبع
        if name != "Unknown" and name not in counted_names_this_batch:
            update_name_confirmation(name)
            counted_names_this_batch.add(name)

    # الوجوه غير المحدثة تبقى بالتتبع، ولو اختفت فترة طويلة تنحذف
    for track_id, track in list(tracks.items()):
        if track_id not in used_track_ids:
            track["age"] += 1
            if track["age"] > MAX_TRACK_AGE:
                tracks.pop(track_id, None)


def draw_tracks(frame):
    for track in tracks.values():
        x, y, w, h = track["bbox"]
        name = track.get("name", "Unknown")

        if name in attendance:
            color = (0, 255, 0)
            label = f"PRESENT: {name}"
        elif name != "Unknown":
            color = (0, 165, 255)
            count = confirm_counter.get(name, 0)
            label = f"{name} ({count}/{CONFIRM_FRAMES})"
        else:
            color = (0, 0, 255)
            label = "Unknown"

        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        cv2.putText(
            frame,
            label,
            (x, max(25, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2
        )



# =========================
# YOLO DETECTION + DEEPFACE REFINEMENT
# =========================
def expand_bbox_for_deepface(bbox, frame_shape, margin=YOLO_FACE_MARGIN):
    """
    YOLO boxes can be tight. We expand the box before sending it to DeepFace,
    so DeepFace receives a crop closer to what the original pipeline used.
    """
    x, y, w, h = bbox
    height, width = frame_shape[:2]

    pad_x = int(w * margin)
    pad_y = int(h * margin)

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(width, x + w + pad_x)
    y2 = min(height, y + h + pad_y)

    return clamp_bbox((x1, y1, x2 - x1, y2 - y1), frame_shape)


def detect_faces_yolo(frame):
    """
    YOLO is used for detection only.
    Returns candidate face boxes as: (x, y, w, h)
    """
    detections = []

    predictions = yolo_detector.predict(
        source=frame,
        conf=YOLO_CONF,
        imgsz=YOLO_IMG_SIZE,
        verbose=False
    )

    if not predictions:
        return detections

    result = predictions[0]
    boxes = getattr(result, "boxes", None)

    if boxes is None or boxes.xyxy is None:
        return detections

    class_names = getattr(result, "names", {}) or {}

    for box in boxes:
        cls_id = int(box.cls[0]) if box.cls is not None else -1
        cls_name = str(class_names.get(cls_id, "")).lower()

        # If the model has multiple classes, keep face only.
        # If it is a one-class face model, accept all detections.
        if class_names and len(class_names) > 1 and "face" not in cls_name:
            continue

        x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy()
        x = int(x1)
        y = int(y1)
        w = int(x2 - x1)
        h = int(y2 - y1)

        if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
            continue

        detections.append(clamp_bbox((x, y, w, h), frame.shape))

    return detections


def get_deepface_style_face_crop(frame, yolo_bbox):
    """
    Important part:
    YOLO detects the face location, but DeepFace still refines the face crop
    using the same DETECTOR_BACKEND used in the original code.

    This keeps recognition closer to the old version instead of sending a raw
    tight YOLO crop directly to DeepFace.
    """
    rx, ry, rw, rh = expand_bbox_for_deepface(yolo_bbox, frame.shape)
    roi = frame[ry:ry + rh, rx:rx + rw]

    if roi.size == 0:
        return None, None

    try:
        faces = DeepFace.extract_faces(
            img_path=roi,
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=False
        )
    except Exception:
        faces = []

    best_face_img = None
    best_bbox = None
    best_area_size = 0

    for face in faces:
        area = face.get("facial_area", {})

        fx = int(area.get("x", 0))
        fy = int(area.get("y", 0))
        fw = int(area.get("w", 0))
        fh = int(area.get("h", 0))

        if fw < MIN_FACE_SIZE or fh < MIN_FACE_SIZE:
            continue

        full_bbox = clamp_bbox((rx + fx, ry + fy, fw, fh), frame.shape)
        x, y, w, h = full_bbox
        face_img = frame[y:y + h, x:x + w]

        if face_img.size == 0:
            continue

        area_size = w * h
        if area_size > best_area_size:
            best_area_size = area_size
            best_face_img = face_img
            best_bbox = full_bbox

    # Fallback: if DeepFace cannot refine inside YOLO ROI, use expanded YOLO crop.
    # This keeps the system running, but still gives DeepFace a wider crop.
    if best_face_img is None:
        best_face_img = roi
        best_bbox = yolo_bbox

    best_face_img = cv2.resize(best_face_img, (224, 224))
    return best_face_img, best_bbox

# =========================
# WORKER
# =========================
def worker(frame):
    global latest_results, latest_batch_id, processing

    results = []

    try:
        yolo_boxes = detect_faces_yolo(frame)

        # Safety fallback: if YOLO finds nothing, use the original DeepFace detection.
        # This helps avoid losing faces in difficult frames.
        if not yolo_boxes:
            faces = DeepFace.extract_faces(
                img_path=frame,
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=False
            )

            for face in faces:
                area = face.get("facial_area", {})
                x = int(area.get("x", 0))
                y = int(area.get("y", 0))
                w = int(area.get("w", 0))
                h = int(area.get("h", 0))

                if w >= MIN_FACE_SIZE and h >= MIN_FACE_SIZE:
                    yolo_boxes.append(clamp_bbox((x, y, w, h), frame.shape))

        for yolo_bbox in yolo_boxes:
            face_img, display_bbox = get_deepface_style_face_crop(frame, yolo_bbox)

            if face_img is None or display_bbox is None:
                continue

            x, y, w, h = display_bbox

            name = "Unknown"
            confidence = 0.0

            try:
                # Keep recognition call like the original code.
                # No detector_backend="skip" and no align=False.
                rep = DeepFace.represent(
                    img_path=face_img,
                    model_name=MODEL_NAME,
                    enforce_detection=False
                )

                emb = rep[0]["embedding"]
                name, score = find_best_match(emb)
                confidence = max(0.0, 1.0 - score)

            except Exception as e:
                logger.warning(f"Recognition failed: {e}")

            results.append((x, y, w, h, name, confidence))

    except Exception as e:
        logger.warning(f"YOLO detection failed: {e}")

    with lock:
        latest_results = results
        latest_batch_id += 1

    processing = False

# =========================
# CAMERA
# =========================
cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    raise RuntimeError("Cannot open camera")

logger.info("Camera started — Press Q to exit")


# =========================
# MAIN LOOP
# =========================
try:
    while True:
        ret, frame = cap.read()

        if not ret:
            continue

        # يحدث المربعات بكل فريم حتى لو DeepFace لسه بحلل الفريم السابق
        update_tracks_with_cv_tracker(frame)

        if not processing:
            processing = True
            threading.Thread(
                target=worker,
                args=(frame.copy(),),
                daemon=True
            ).start()

        with lock:
            results = list(latest_results)
            batch_id = latest_batch_id

        # لا تعالج نفس نتائج التعرف مرتين، عشان عداد الأربع مرات يكون صحيح
        if batch_id != processed_batch_id:
            apply_detections_to_tracks(frame, results)
            processed_batch_id = batch_id

        draw_tracks(frame)

        cv2.rectangle(frame, (0, 0), (300, 70), (0, 0, 0), -1)

        cv2.putText(
            frame,
            f"Present: {len(attendance)}/{len(db)}",
            (10, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2
        )

        cv2.imshow("Attendance", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    save_csv()


print("\n" + "=" * 50)
print(f"PRESENT: {len(attendance)}/{len(db)}")

for name, dt in attendance.items():
    print(f"  {name:<25} {dt}")

print(f"Saved: {ATTENDANCE_CSV}")
print("=" * 50)
