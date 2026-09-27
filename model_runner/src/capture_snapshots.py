import cv2
import os
import time

# =========================
# Settings
# =========================

NUM_SHOTS = 5        # عدد الصور
DELAY = 1.5          # وقت بين كل صورة (مهم للدقة)
RESIZE = (640, 480)  # حجم مناسب (خفيف ومتوسط الجودة)

# =========================
# Paths
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "data", "snapshots")

os.makedirs(SAVE_DIR, exist_ok=True)

# =========================
# Open Camera
# =========================

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise RuntimeError("❌ Cannot open camera")

print("📸 Starting snapshot capture...")
print("👉 Please look at the camera and slightly move your head")

count = 0

while count < NUM_SHOTS:

    ret, frame = cap.read()

    if not ret:
        continue

    # ✅ تحسين الأداء (resize)
    frame = cv2.resize(frame, RESIZE)

    filename = f"snapshot_{count+1}.jpg"
    filepath = os.path.join(SAVE_DIR, filename)

    cv2.imwrite(filepath, frame)
    print(f"✅ Saved {filename}")

    count += 1

    # ✅ مهم: يعطي وقت للحركة -> يزيد الدقة
    time.sleep(DELAY)

cap.release()
cv2.destroyAllWindows()

print("🎉 Snapshot capture completed successfully")