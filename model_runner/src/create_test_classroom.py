import cv2
import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INPUT_DIR = os.path.join(BASE_DIR, "data", "team_test_faces")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "test_group.jpg")

images = []

# قراءة الصور
for img_name in os.listdir(INPUT_DIR):
    path = os.path.join(INPUT_DIR, img_name)
    img = cv2.imread(path)

    if img is None:
        continue

    img = cv2.resize(img, (300, 300))
    images.append(img)

# ترتيبهم Grid
rows = []
row_size = 5

for i in range(0, len(images), row_size):
    row = images[i:i+row_size]

    if len(row) < row_size:
        break

    row_img = np.hstack(row)
    rows.append(row_img)

final_image = np.vstack(rows)

cv2.imwrite(OUTPUT_FILE, final_image)

print("✅ Classroom test image created!")