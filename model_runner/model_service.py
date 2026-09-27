import os
import csv
import pickle
import logging
import cv2
import threading
import numpy as np
import requests
import json
import hashlib
import time
from datetime import datetime
from deepface import DeepFace
from ultralytics import YOLO


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "model_service.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

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
UNKNOWN_GRACE_FRAMES = 8
MAX_TRACK_AGE = 35

# بعد ما الطالب يتأكد وينسجل حضور، لا نرجع نعرض Unknown له
# مناسب للعدد الكبير: ما بنورّث الهوية من الذاكرة إلا بعد تسجيل الحضور
LOCK_IDENTITY_AFTER_CONFIRMATION = True
KEEP_LAST_KNOWN_NAME = True

# إعدادات ربط الوجوه مع التراكات
IOU_MATCH_THRESHOLD = 0.20
CENTER_MATCH_THRESHOLD = 90

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CAMERA_INDEX = 0
DETECTOR_BACKEND = "opencv"

# =========================
# WEB API CONFIG
# =========================
WEB_API_BASE_URL = "http://127.0.0.1:5000"

ACTIVE_SESSION_URL = f"{WEB_API_BASE_URL}/api/active-session"
MARK_ATTENDANCE_URL = f"{WEB_API_BASE_URL}/api/mark-attendance"

# =========================
# SERVICE CONFIG
# =========================
SERVICE_POLL_SECONDS = 10
FINISHED_SESSIONS = set()

# =========================
# SNAPSHOT / AUTO CLOSE CONFIG
# =========================
# يبدأ فحص الإغلاق التلقائي بعد 25 ثانية. عدليها إلى 20 أو 30 حسب الحاجة.
AUTO_CHECK_START_SECONDS = 20

# لازم يضل الوضع صالح/ثابت لمدة 3 ثواني قبل حفظ اللقطة وإغلاق الكاميرا.
AUTO_STABLE_SECONDS = 4

# مناسب للتجربة على شخص واحد. للصف الكبير ارفعي الأرقام حسب عدد الطلاب المتوقع ظهوره.
MIN_TRACKS_FOR_AUTO_CLOSE = 1
MIN_ATTENDANCE_FOR_AUTO_CLOSE = 1

# الإغلاق مسموح إذا كل المربعات صارت نهائية:
# أخضر PRESENT أو أحمر Unknown.
# غير مسموح الإغلاق إذا في مربع برتقالي، يعني اسم طالب لسه غير مؤكد.
MAX_PENDING_COUNT_FOR_AUTO_CLOSE = 0

# تخفيف شرط الثبات لأن مربعات الوجه ممكن تهتز طبيعيًا.
STABLE_MAX_AVG_CENTER_MOVEMENT = 55
STABLE_MAX_COUNT_CHANGE = 1

# تحمل اختفاء التراك للحظات بدون تصفير العداد مباشرة.
AUTO_MISSING_TRACK_GRACE_SECONDS = 2.5
AUTO_REQUIRE_RECENT_VALID_SCENE_SECONDS = 4.0
AUTO_STATUS_LOG_INTERVAL_SECONDS = 2.0

# إذا ظهر أي طالب برتقالي/مشكوك فيه، نعيد فتح نافذة تأكيد جديدة قبل السماح بالتصوير.
# بعد اختفاء البرتقالي، لازم يمر هذا الوقت بدون شك جديد، ثم يبدأ عداد الثبات AUTO_STABLE_SECONDS.
AUTO_RECHECK_AFTER_PENDING_SECONDS = 5


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
# Project structure:
# graduation-test
# ├── model_runner
# └── web_app

PROJECT_DIR = os.path.dirname(BASE_DIR)
WEB_APP_DIR = os.path.join(PROJECT_DIR, "web_app")

SNAPSHOT_OUTPUT_DIR = os.path.join(
    WEB_APP_DIR,
    "private_uploads",
    "live-result"
)

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
# WEB SESSION STATE
# =========================
active_session = None
allowed_face_labels = set()
label_to_student = {}

# =========================
# SNAPSHOT / AUTO CLOSE STATE
# =========================
program_start_time = datetime.now()
last_present_update_time = datetime.now()
snapshot_saved = False
auto_stable_start_time = None
last_valid_scene_time = None
last_valid_snapshot_frame = None
last_track_centers = None
last_scene_signature = None
last_auto_status_log_time = None
last_auto_status_text = "Auto: waiting"
last_pending_seen_time = None
final_snapshot_image_path = None
final_snapshot_json_path = None

# ذاكرة محافظة للهويات المؤكدة فقط.
# الهدف: إذا الطالب صار PRESENT وبعدها تحرك/انكسر التراك، ما يرجع يظهر Unknown.
# مهم للعدد الكبير: لا نخزن ولا نورّث اسم أي طالب قبل ما ينثبت حضوره.
identity_memory = {}
IDENTITY_MEMORY_MAX_AGE = 35
IDENTITY_MEMORY_CENTER_THRESHOLD = 80
IDENTITY_MEMORY_IOU_THRESHOLD = 0.12


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

      # Only accept students registered in the active section
      if allowed_face_labels and best_name not in allowed_face_labels:
          return "Unknown", best_score

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


def remember_confirmed_identity(name, bbox, conf=0.0):
    """يحفظ آخر مكان معروف فقط للطلاب الذين تم تسجيل حضورهم فعليًا."""
    if not name or name == "Unknown" or name not in attendance or bbox is None:
        return

    identity_memory[name] = {
        "bbox": bbox,
        "conf": float(conf or 0.0),
        "seen_at_batch": latest_batch_id,
    }


def forget_old_confirmed_identities():
    """ينظف الذاكرة القديمة حتى لا ينتقل اسم طالب لشخص آخر بعد فترة."""
    for name, item in list(identity_memory.items()):
        if latest_batch_id - item.get("seen_at_batch", 0) > IDENTITY_MEMORY_MAX_AGE:
            identity_memory.pop(name, None)


def find_confirmed_identity_from_memory(bbox):
    """
    يرجع اسم طالب مؤكد فقط إذا كان المربع الجديد قريب جدًا من آخر مكان معروف له.
    هذا يمنع رجوع الطالب Unknown بعد التسجيل، مع تقليل خلط الأسماء عند العدد الكبير.
    """
    forget_old_confirmed_identities()

    best_name = None
    best_conf = 0.0
    best_score = -999.0

    for name, item in identity_memory.items():
        if name not in attendance:
            continue

        old_bbox = item.get("bbox")
        if old_bbox is None:
            continue

        iou = bbox_iou(bbox, old_bbox)
        dist = center_distance(bbox, old_bbox)

        if iou >= IDENTITY_MEMORY_IOU_THRESHOLD or dist <= IDENTITY_MEMORY_CENTER_THRESHOLD:
            score = (iou * 3.0) - (dist / 1000.0)
            if score > best_score:
                best_score = score
                best_name = name
                best_conf = item.get("conf", 0.0)

    return best_name, best_conf


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
    global last_present_update_time

    if name == "Unknown" or name in attendance:
        return

    confirm_counter[name] = confirm_counter.get(name, 0) + 1

    if confirm_counter[name] >= CONFIRM_FRAMES:
        attendance[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"PRESENT: {name}")

        save_csv()

        api_success = mark_attendance_on_web(name)

        if api_success:
            logger.info(f"Attendance saved in web database for: {name}")
        else:
            logger.warning(f"Attendance was saved locally only for: {name}")

        last_present_update_time = datetime.now()

def apply_detections_to_tracks(frame, detections):
    """
    يربط نتائج التعرف بالتراكات.

    النسخة النهائية المحافظة للعدد الكبير:
    - لا نثبت الهوية من أول تعرّف، حتى لا تختلط أسماء الطلاب.
    - العدّاد يزيد فقط من نتائج تعرف حقيقية من DeepFace.
    - بعد ما الطالب يصير PRESENT، نحفظ هويته في ذاكرة مؤكدة.
    - إذا تحرك الطالب أو انكسر track_id بعد التسجيل، نورّث الاسم من الذاكرة المؤكدة بدل Unknown.
    """
    global next_track_id

    used_track_ids = set()
    counted_names_this_batch = set()

    for x, y, w, h, raw_name, raw_conf in detections:
        bbox = clamp_bbox((x, y, w, h), frame.shape)

        # الاسم الخام من DeepFace. هذا فقط الذي يسمح بزيادة عداد الحضور.
        recognized_name = raw_name
        recognized_conf = raw_conf

        # للعرض فقط: إذا DeepFace رجع Unknown، جرب ذاكرة الطلاب المؤكدين فقط.
        display_candidate_name = recognized_name
        display_candidate_conf = recognized_conf
        if recognized_name == "Unknown":
            memory_name, memory_conf = find_confirmed_identity_from_memory(bbox)
            if memory_name and memory_name in attendance:
                display_candidate_name = memory_name
                display_candidate_conf = memory_conf

        track_id = find_matching_track(bbox, used_track_ids)

        if track_id is None:
            track_id = next_track_id
            next_track_id += 1
            tracks[track_id] = {
                "bbox": bbox,
                "name": display_candidate_name,
                "conf": display_candidate_conf,
                "age": 0,
                "unknown_age": 0,
                "tracker": None,
                "locked_name": None,
                "locked_conf": 0.0,
                "last_known_name": None,
                "last_known_conf": 0.0,
            }

        track = tracks[track_id]
        old_name = track.get("name", "Unknown")
        old_conf = track.get("conf", 0.0)
        locked_name = track.get("locked_name")
        last_known_name = track.get("last_known_name")
        last_known_conf = track.get("last_known_conf", 0.0)

        # إذا الطالب مثبت حضور، الهوية المقفلة لها الأولوية.
        if locked_name and locked_name in attendance:
            display_name = locked_name
            display_conf = track.get("locked_conf", old_conf)
            track["unknown_age"] = 0

        else:
            # إذا وصلنا اسم حقيقي من DeepFace، نعرضه ونحتفظ به داخل نفس التراك فقط.
            # هذا لا يسجل حضور إلا عبر العداد بالأسفل.
            if display_candidate_name != "Unknown":
                display_name = display_candidate_name
                display_conf = display_candidate_conf
                track["last_known_name"] = display_name
                track["last_known_conf"] = display_conf
                track["unknown_age"] = 0

            # لو DeepFace رجع Unknown والتراك نفسه كان عارف اسم قبل قليل، خليه ظاهر بدل الوميض.
            elif KEEP_LAST_KNOWN_NAME and last_known_name:
                display_name = last_known_name
                display_conf = last_known_conf
                track["unknown_age"] = track.get("unknown_age", 0) + 1

            elif KEEP_LAST_KNOWN_NAME and old_name != "Unknown":
                display_name = old_name
                display_conf = old_conf
                track["unknown_age"] = track.get("unknown_age", 0) + 1

            else:
                display_name = "Unknown"
                display_conf = display_candidate_conf
                track["unknown_age"] = track.get("unknown_age", 0) + 1

        track.update({
            "bbox": bbox,
            "name": display_name,
            "conf": display_conf,
            "age": 0,
            "tracker": init_tracker(frame, bbox),
        })

        used_track_ids.add(track_id)

        # مهم جدًا: عداد الحضور يزيد فقط من التعرف الحقيقي، وليس من الاسم الموروث من الذاكرة أو التتبع.
        if recognized_name != "Unknown" and recognized_name not in counted_names_this_batch:
            update_name_confirmation(recognized_name)
            counted_names_this_batch.add(recognized_name)

            # بعد التأكيد، ثبت الاسم على هذا التراك واحفظه في الذاكرة المؤكدة.
            if LOCK_IDENTITY_AFTER_CONFIRMATION and recognized_name in attendance:
                track["locked_name"] = recognized_name
                track["locked_conf"] = recognized_conf
                track["last_known_name"] = recognized_name
                track["last_known_conf"] = recognized_conf
                track["name"] = recognized_name
                track["conf"] = recognized_conf
                remember_confirmed_identity(recognized_name, bbox, recognized_conf)

        # حدّث ذاكرة الطلاب المؤكدين فقط عند كل ظهور.
        confirmed_name = track.get("locked_name") or track.get("name")
        if confirmed_name in attendance:
            remember_confirmed_identity(confirmed_name, bbox, track.get("conf", 0.0))

    # الوجوه غير المحدثة تبقى بالتتبع، ولو اختفت فترة طويلة تنحذف.
    for track_id, track in list(tracks.items()):
        if track_id not in used_track_ids:
            track["age"] += 1

            confirmed_name = track.get("locked_name") or track.get("name")
            if confirmed_name in attendance:
                remember_confirmed_identity(confirmed_name, track.get("bbox"), track.get("conf", 0.0))

            if track["age"] > MAX_TRACK_AGE:
                tracks.pop(track_id, None)

def draw_tracks(frame):
    for track in tracks.values():
        x, y, w, h = track["bbox"]
        name = track.get("locked_name") or track.get("name", "Unknown")

        # إذا صار الطالب PRESENT وانكسر التعرف أثناء الحركة، استخدم الذاكرة المؤكدة فقط.
        if name == "Unknown":
            memory_name, memory_conf = find_confirmed_identity_from_memory(track["bbox"])
            if memory_name and memory_name in attendance:
                name = memory_name
                track["name"] = memory_name
                track["locked_name"] = memory_name
                track["locked_conf"] = memory_conf
                track["conf"] = memory_conf

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
# WEB API HELPERS
# =========================
def fetch_active_session_from_web():
    try:
        response = requests.get(ACTIVE_SESSION_URL, timeout=5)

        if response.status_code != 200:
            logger.info("No active session found from web.")
            return None

        data = response.json()

        if not data.get("success"):
            logger.info("Active session API returned success=False.")
            return None

        return data

    except Exception as e:
        logger.warning(f"Failed to connect to active session API: {e}")
        return None


def setup_active_session():
    global active_session, allowed_face_labels, label_to_student

    active_session = fetch_active_session_from_web()

    if active_session is None:
        return False

    allowed_face_labels = set(active_session.get("allowed_face_labels", []))

    label_to_student = {}

    for student in active_session.get("students", []):
        face_label = student.get("face_label")

        if face_label:
            label_to_student[face_label] = {
                "student_id": student.get("student_id"),
                "full_name": student.get("full_name")
            }

    logger.info(f"Active session found: {active_session.get('session_id')}")
    logger.info(f"Allowed labels: {allowed_face_labels}")

    return True


def mark_attendance_on_web(face_label):
    if active_session is None:
        logger.warning("Cannot mark attendance because there is no active session.")
        return False

    student = label_to_student.get(face_label)

    if not student:
        logger.warning(f"Face label not found in current session students: {face_label}")
        return False

    payload = {
        "session_id": active_session["session_id"],
        "student_id": student["student_id"],
        "name": face_label
    }

    try:
        response = requests.post(
            MARK_ATTENDANCE_URL,
            json=payload,
            timeout=5
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        logger.info(f"Attendance API Status: {response.status_code}")
        logger.info(f"Attendance API Response: {data}")

        return response.status_code in [200, 201] and data.get("success", False)

    except Exception as e:
        logger.warning(f"Failed to send attendance to web API: {e}")
        return False

# =========================
# SNAPSHOT HELPERS
# =========================
def safe_text(text):
    text = str(text).strip()
    text = text.replace(" ", "_")
    text = text.replace("/", "-")
    text = text.replace("\\", "-")
    text = text.replace(":", "-")
    return text


def calculate_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()

def get_snapshot_folder():
    """
    Creates nested folders in this order:
    live-result / Course_ID_Name / Section_ID / Date / Session_ID
    """
    if active_session is None:
        os.makedirs(SNAPSHOT_OUTPUT_DIR, exist_ok=True)
        return SNAPSHOT_OUTPUT_DIR

    course_id = active_session.get("course_id", "unknown_course")
    course_name = active_session.get("course_name", "UnknownCourse")
    section_id = active_session.get("section_id", "unknown_section")
    session_id = active_session.get("session_id", "unknown_session")
    date_text = datetime.now().strftime("%Y-%m-%d")

    course_folder = safe_text(f"Course_{course_id}_{course_name}")
    section_folder = safe_text(f"Section_{section_id}")
    session_folder = safe_text(f"Session_{session_id}")

    folder = os.path.join(
        SNAPSHOT_OUTPUT_DIR,
        course_folder,
        section_folder,
        date_text,
        session_folder
    )

    os.makedirs(folder, exist_ok=True)

    return folder

def save_classroom_snapshot(frame):
    """
    يحفظ صورة نهائية + ملف JSON metadata ويرجع المسارات.

    ملاحظة مهمة:
    - الصورة نفسها لا تحتوي صندوق معلومات أعلى الصورة.
    - معلومات الكورس/السيكشن/الحضور/الغياب محفوظة فقط في ملف JSON جانبي.
    - اسم الصورة مربوط بالتاريخ والوقت فقط حتى تكون مناسبة للويب وواضحة بدون كشف البيانات داخل الصورة.
    """
    if active_session is None:
        return None, None

    now = datetime.now()
    snapshot_folder = get_snapshot_folder()

    present_names = sorted(list(attendance.keys()))
    all_names = sorted(list(allowed_face_labels))
    absent_names = sorted([
        name for name in all_names
        if name not in attendance
    ])

    # مهم: نحفظ اللقطة من الفريم الأصلي فقط بدون مربعات الوجوه أو الأسماء.
    # العرض المباشر على الكاميرا يبقى فيه draw_tracks، لكن الصورة المحفوظة تكون نظيفة.
    snapshot_frame = frame.copy()

    # اسم الملف مربوط باليوم والتاريخ والوقت فقط.
    date_text = now.strftime("%Y%m%d")
    time_text = now.strftime("%H%M%S")

    course_id = active_session.get("course_id", "unknown_course")
    course_name = safe_text(active_session.get("course_name", "UnknownCourse"))
    section_id = active_session.get("section_id", "unknown_section")
    session_id = active_session.get("session_id", "unknown_session")

    image_filename = (
      f"snapshot_course_{course_id}_{course_name}"
      f"_section_{section_id}"
      f"_session_{session_id}"
      f"_{date_text}_{time_text}.jpg"
    )

    json_filename = (
      f"snapshot_course_{course_id}_{course_name}"
      f"_section_{section_id}"
      f"_session_{session_id}"
      f"_{date_text}_{time_text}.json"
    )

    image_path = os.path.join(snapshot_folder, image_filename)
    json_path = os.path.join(snapshot_folder, json_filename)

    ok = cv2.imwrite(image_path, snapshot_frame)
    if not ok:
        logger.warning(f"Failed to write classroom snapshot: {image_path}")
        return None, None

    image_hash = calculate_file_hash(image_path)

    # كل المعلومات الإضافية محفوظة بعيدًا عن الصورة في ملف JSON جانبي.
    metadata = {
        "course_id": active_session.get("course_id"),
        "course_name": active_session.get("course_name"),
        "section_id": active_session.get("section_id"),
        "session_id": active_session.get("session_id"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "image_file": image_filename,
        "image_path": image_path,
        "image_sha256": image_hash,
        "total_students": len(all_names),
        "present_count": len(present_names),
        "absent_count": len(absent_names),
        "present_students": present_names,
        "absent_students": absent_names
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)

    logger.info(f"Classroom snapshot saved without info overlay: {image_path}")
    logger.info(f"Snapshot metadata saved separately: {json_path}")

    return image_path, json_path

def get_track_display_name(track):
    name = track.get("locked_name") or track.get("name", "Unknown")

    if name == "Unknown":
        memory_name, memory_conf = find_confirmed_identity_from_memory(track.get("bbox"))
        if memory_name and memory_name in attendance:
            name = memory_name
            track["name"] = memory_name
            track["locked_name"] = memory_name
            track["locked_conf"] = memory_conf
            track["conf"] = memory_conf

    return name


def get_current_scene_status():
    """
    يقيس هل المشهد صالح للإغلاق:
    - لازم يوجد عدد كافٍ من التراكات الظاهرة.
    - المربع الأخضر PRESENT مقبول.
    - المربع الأحمر Unknown مقبول إذا ظل ثابت.
    - المربع البرتقالي، أي طالب متعرف عليه جزئيًا ولسه غير مؤكد، غير مقبول للإغلاق.
    """
    visible_tracks = [
        track for track in tracks.values()
        if track.get("bbox") is not None and track.get("age", 0) <= UNKNOWN_GRACE_FRAMES
    ]

    total_visible = len(visible_tracks)
    green_count = 0
    unknown_count = 0
    pending_count = 0
    centers = []
    labels = []

    for track in visible_tracks:
        bbox = track.get("bbox")
        x, y, w, h = bbox
        centers.append((x + w / 2.0, y + h / 2.0))

        name = get_track_display_name(track)

        if name in attendance:
            green_count += 1
            labels.append(f"PRESENT:{name}")
        elif name == "Unknown":
            unknown_count += 1
            labels.append("UNKNOWN")
        else:
            # هذا هو البرتقالي: النظام شاكك إنه طالب معيّن لكنه لم يؤكده بعد.
            pending_count += 1
            labels.append(f"PENDING:{name}")

    final_count = green_count + unknown_count
    final_ratio = (final_count / total_visible) if total_visible > 0 else 0.0
    green_ratio = (green_count / total_visible) if total_visible > 0 else 0.0

    # نستخدمها لتثبيت نفس النتيجة 3 ثواني: نفس عدد الأخضر/الأحمر/البرتقالي ونفس أسماء الحاضرين.
    scene_signature = tuple(sorted(labels))

    return {
        "total_visible": total_visible,
        "green_count": green_count,
        "unknown_count": unknown_count,
        "pending_count": pending_count,
        "suspicious_count": pending_count,
        "green_ratio": green_ratio,
        "final_ratio": final_ratio,
        "centers": centers,
        "scene_signature": scene_signature,
    }


def scene_is_stable(current_centers):
    """ثبات محافظ لكن متسامح مع اهتزاز بسيط بمربعات الوجه."""
    global last_track_centers

    if last_track_centers is None:
        last_track_centers = list(current_centers)
        return False

    if abs(len(current_centers) - len(last_track_centers)) > STABLE_MAX_COUNT_CHANGE:
        last_track_centers = list(current_centers)
        return False

    if not current_centers or not last_track_centers:
        last_track_centers = list(current_centers)
        return False

    # نقارن أقرب مراكز، وليس نفس الترتيب بالضرورة.
    distances = []
    used_old = set()

    for cx, cy in current_centers:
        best_idx = None
        best_dist = None

        for idx, (ox, oy) in enumerate(last_track_centers):
            if idx in used_old:
                continue

            dist = float(np.hypot(cx - ox, cy - oy))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx is not None and best_dist is not None:
            used_old.add(best_idx)
            distances.append(best_dist)

    last_track_centers = list(current_centers)

    if not distances:
        return False

    avg_movement = sum(distances) / len(distances)
    return avg_movement <= STABLE_MAX_AVG_CENTER_MOVEMENT


def update_auto_snapshot_and_close(frame):
    """
    بعد مرور AUTO_CHECK_START_SECONDS:
    إذا المشهد النهائي صالح ومستقر 3 ثواني، يحفظ لقطة في مجلد الويب ثم يرجع True لإغلاق الكاميرا.
    النهائي يعني: كل مربع أخضر PRESENT أو أحمر Unknown. البرتقالي غير مسموح حتى يتحول لأخضر أو Unknown.
    يتحمل اختفاء التراك المؤقت باستخدام آخر فريم صالح.
    """
    global snapshot_saved
    global auto_stable_start_time
    global last_valid_scene_time
    global last_valid_snapshot_frame
    global last_scene_signature
    global last_auto_status_log_time
    global last_auto_status_text
    global last_pending_seen_time
    global final_snapshot_image_path
    global final_snapshot_json_path

    if snapshot_saved:
        last_auto_status_text = "Auto: snapshot already saved"
        return False

    if active_session is None:
        last_auto_status_text = "Auto: no active session"
        return False

    now = datetime.now()
    seconds_from_start = (now - program_start_time).total_seconds()

    status = get_current_scene_status()
    total_visible = status["total_visible"]
    green_count = status["green_count"]
    unknown_count = status["unknown_count"]
    pending_count = status["pending_count"]
    green_ratio = status["green_ratio"]
    final_ratio = status["final_ratio"]
    centers = status["centers"]
    scene_signature = status["scene_signature"]

    reason = ""

    if pending_count > MAX_PENDING_COUNT_FOR_AUTO_CLOSE:
        # لا نغلق إذا في طالب برتقالي: لازم يتأكد ويصير أخضر، أو يفشل التعرف بثبات ويصير Unknown أحمر.
        # والأهم: كل مرة يظهر فيها برتقالي نعيد عداد التحقق 20 ثانية من جديد.
        last_pending_seen_time = now
        reason = (
            f"Pending/orange boxes {pending_count}/{MAX_PENDING_COUNT_FOR_AUTO_CLOSE} | "
            f"resetting recheck timer {AUTO_RECHECK_AFTER_PENDING_SECONDS}s"
        )
        auto_stable_start_time = None
        last_scene_signature = None
    elif last_pending_seen_time is not None:
        seconds_since_pending = (now - last_pending_seen_time).total_seconds()

        if seconds_since_pending < AUTO_RECHECK_AFTER_PENDING_SECONDS:
            # بعد اختفاء البرتقالي، نعطي النظام 20 ثانية جديدة ليتأكد قبل أن يبدأ عداد الـ 4 ثواني.
            reason = (
                f"Rechecking after pending "
                f"{seconds_since_pending:.1f}/{AUTO_RECHECK_AFTER_PENDING_SECONDS}s"
            )
            auto_stable_start_time = None
            last_scene_signature = None
        else:
            # انتهت نافذة إعادة التحقق، الآن مسموح نكمل شروط الإغلاق العادية.
            last_pending_seen_time = None

    if not reason and seconds_from_start < AUTO_CHECK_START_SECONDS:
        reason = f"Waiting time {seconds_from_start:.1f}/{AUTO_CHECK_START_SECONDS}s"
        auto_stable_start_time = None
        last_scene_signature = None
    elif not reason and len(attendance) < MIN_ATTENDANCE_FOR_AUTO_CLOSE:
        reason = f"Attendance low {len(attendance)}/{MIN_ATTENDANCE_FOR_AUTO_CLOSE}"
        auto_stable_start_time = None
        last_scene_signature = None
    elif not reason and total_visible < MIN_TRACKS_FOR_AUTO_CLOSE:
        # لا نصفر العداد مباشرة إذا كان عندنا مشهد صالح قريبًا.
        if last_valid_scene_time is not None:
            missing_seconds = (now - last_valid_scene_time).total_seconds()
            if missing_seconds <= AUTO_MISSING_TRACK_GRACE_SECONDS:
                reason = f"Using recent valid scene {missing_seconds:.1f}/{AUTO_MISSING_TRACK_GRACE_SECONDS}s"
            else:
                reason = f"Visible tracks low {total_visible}/{MIN_TRACKS_FOR_AUTO_CLOSE}"
                auto_stable_start_time = None
                last_scene_signature = None
        else:
            reason = f"Visible tracks low {total_visible}/{MIN_TRACKS_FOR_AUTO_CLOSE}"
            auto_stable_start_time = None
            last_scene_signature = None
    elif not reason and final_ratio < 1.0:
        # احتياط: كل المربعات لازم تكون نهائية، أخضر أو Unknown.
        reason = f"Final result ratio low {final_ratio:.2f}/1.00"
        auto_stable_start_time = None
        last_scene_signature = None
    elif not reason and not scene_is_stable(centers):
        reason = "Scene not stable yet"
        auto_stable_start_time = None
        last_scene_signature = None
        last_valid_scene_time = now
        last_valid_snapshot_frame = frame.copy()
    elif not reason:
        # مشهد صالح وثابت: كل الوجوه أخضر أو Unknown، ولا يوجد برتقالي.
        last_valid_scene_time = now
        last_valid_snapshot_frame = frame.copy()

        # لازم نفس نتيجة التصنيف تظل ثابتة 3 ثواني، وليس فقط نفس المكان.
        if last_scene_signature != scene_signature:
            last_scene_signature = scene_signature
            auto_stable_start_time = now

        if auto_stable_start_time is None:
            auto_stable_start_time = now

        stable_seconds = (now - auto_stable_start_time).total_seconds()
        reason = f"Stable final result {stable_seconds:.1f}/{AUTO_STABLE_SECONDS}s"

        if stable_seconds >= AUTO_STABLE_SECONDS:
            snapshot_frame = last_valid_snapshot_frame if last_valid_snapshot_frame is not None else frame
            image_path, json_path = save_classroom_snapshot(snapshot_frame)

            if image_path:
                snapshot_saved = True
                final_snapshot_image_path = image_path
                final_snapshot_json_path = json_path
                last_auto_status_text = "Auto: snapshot saved, closing camera"
                logger.info("Final snapshot saved and camera will close.")
                return True
            else:
                reason = "Failed to save snapshot"
                auto_stable_start_time = None

    # إذا صار فيه مشهد صالح مؤخرًا لكن التراك اختفى لحظة، نكمل العداد بشكل متسامح.
    if (
        reason.startswith("Using recent valid scene")
        and last_valid_snapshot_frame is not None
        and last_valid_scene_time is not None
    ):
        recent_valid_age = (now - last_valid_scene_time).total_seconds()
        if recent_valid_age <= AUTO_REQUIRE_RECENT_VALID_SCENE_SECONDS:
            if auto_stable_start_time is None:
                auto_stable_start_time = now

            stable_seconds = (now - auto_stable_start_time).total_seconds()
            reason = f"Stable by recent valid scene {stable_seconds:.1f}/{AUTO_STABLE_SECONDS}s"

            if stable_seconds >= AUTO_STABLE_SECONDS:
                image_path, json_path = save_classroom_snapshot(last_valid_snapshot_frame)
                if image_path:
                    snapshot_saved = True
                    final_snapshot_image_path = image_path
                    final_snapshot_json_path = json_path
                    last_auto_status_text = "Auto: snapshot saved, closing camera"
                    logger.info("Final snapshot saved and camera will close.")
                    return True

    last_auto_status_text = reason

    should_log = False
    if last_auto_status_log_time is None:
        should_log = True
    elif (now - last_auto_status_log_time).total_seconds() >= AUTO_STATUS_LOG_INTERVAL_SECONDS:
        should_log = True

    if should_log:
        logger.info(
            "Auto close status | "
            f"{reason} | "
            f"green={green_count}/{total_visible} | "
            f"unknown={unknown_count} | "
            f"pending={pending_count} | "
            f"present={len(attendance)}/{len(allowed_face_labels)}"
        )
        last_auto_status_log_time = now

    return False


def draw_auto_status(frame):
    """يعرض حالة الإغلاق التلقائي أسفل الشاشة حتى نعرف سبب الانتظار."""
    text = last_auto_status_text or "Auto: waiting"
    h, w = frame.shape[:2]

    cv2.rectangle(frame, (0, h - 45), (w, h), (0, 0, 0), -1)
    cv2.putText(
        frame,
        text[:95],
        (10, h - 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2
    )


def reset_runtime_state():
    global latest_results, latest_batch_id, processed_batch_id
    global attendance, confirm_counter, tracks, next_track_id
    global processing
    global program_start_time, last_present_update_time
    global snapshot_saved, auto_stable_start_time
    global last_valid_scene_time, last_valid_snapshot_frame
    global last_track_centers, last_scene_signature
    global last_auto_status_log_time, last_auto_status_text
    global last_pending_seen_time
    global final_snapshot_image_path, final_snapshot_json_path
    global identity_memory

    latest_results = []
    latest_batch_id = 0
    processed_batch_id = -1

    attendance = {}
    confirm_counter = {}

    tracks = {}
    next_track_id = 1

    processing = False

    program_start_time = datetime.now()
    last_present_update_time = datetime.now()

    snapshot_saved = False
    auto_stable_start_time = None
    last_valid_scene_time = None
    last_valid_snapshot_frame = None
    last_track_centers = None
    last_scene_signature = None
    last_auto_status_log_time = None
    last_auto_status_text = "Auto: waiting"
    last_pending_seen_time = None

    final_snapshot_image_path = None
    final_snapshot_json_path = None

    identity_memory = {}
def run_attendance_for_current_session():
    global processing
    global processed_batch_id
    global final_snapshot_image_path
    global final_snapshot_json_path

    reset_runtime_state()

    session_id = active_session.get("session_id")
    logger.info(f"Starting attendance service for session: {session_id}")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        logger.warning("Cannot open camera.")
        return False

    logger.info("Camera started — Press Q to stop current session camera")

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                continue

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

            if batch_id != processed_batch_id:
                apply_detections_to_tracks(frame, results)
                processed_batch_id = batch_id

            should_close_camera = update_auto_snapshot_and_close(frame)

            draw_tracks(frame)
            draw_auto_status(frame)

            cv2.rectangle(frame, (0, 0), (300, 70), (0, 0, 0), -1)

            cv2.putText(
                frame,
                f"Present: {len(attendance)}/{len(allowed_face_labels)}",
                (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2
            )

            cv2.imshow("Attendance", frame)

            if should_close_camera:
                logger.info("Snapshot saved. Closing camera for this session.")
                break

            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Camera stopped manually by user.")
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        save_csv()

    print("\n" + "=" * 50)
    print(f"SESSION: {session_id}")
    print(f"PRESENT: {len(attendance)}/{len(allowed_face_labels)}")

    for name, dt in attendance.items():
        print(f"  {name:<25} {dt}")

    print(f"Saved CSV: {ATTENDANCE_CSV}")

    if final_snapshot_image_path:
        print(f"Snapshot image: {final_snapshot_image_path}")

    if final_snapshot_json_path:
        print(f"Snapshot JSON: {final_snapshot_json_path}")

    print("=" * 50)

    return True


# =========================
# SERVICE LOOP
# =========================
logger.info("Model service started.")
logger.info("Waiting for active sessions from the web...")

while True:
    try:
        if setup_active_session():
            current_session_id = active_session.get("session_id")

            if current_session_id in FINISHED_SESSIONS:
                logger.info(
                    f"Session {current_session_id} already processed. Waiting for a new session..."
                )
                time.sleep(SERVICE_POLL_SECONDS)
                continue

            run_attendance_for_current_session()

            FINISHED_SESSIONS.add(current_session_id)

            logger.info(
                f"Finished session {current_session_id}. Waiting for next active session..."
            )

        else:
            logger.info("No active session found. Waiting...")

        time.sleep(SERVICE_POLL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Model service stopped by user.")
        break

    except Exception as e:
        logger.warning(f"Service error: {e}")
        time.sleep(SERVICE_POLL_SECONDS)