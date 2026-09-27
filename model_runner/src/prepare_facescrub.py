import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FACESCRUB_PATH = os.path.join(
    BASE_DIR, "data", "external_dataset", "facescrub_full"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "external_dataset", "prepared_facescrub"
)

IMAGES_PER_PERSON = 15

print("📂 Reading from:", FACESCRUB_PATH)

os.makedirs(OUTPUT_PATH, exist_ok=True)

total_persons = 0

for person_name in os.listdir(FACESCRUB_PATH):
    person_dir = os.path.join(FACESCRUB_PATH, person_name)

    if not os.path.isdir(person_dir):
        continue

    images = [
        img for img in os.listdir(person_dir)
        if img.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if len(images) < IMAGES_PER_PERSON:
        continue

    target_dir = os.path.join(OUTPUT_PATH, person_name)
    os.makedirs(target_dir, exist_ok=True)

    for i, img in enumerate(images[:IMAGES_PER_PERSON], start=1):
        src = os.path.join(person_dir, img)
        dst = os.path.join(target_dir, f"{i}.jpg")
        shutil.copy(src, dst)

    total_persons += 1
    print(f"✅ Prepared {person_name}")

print("\n🎉 DONE")
print(f"✅ Total persons prepared: {total_persons}")
print(f"✅ Images per person: {IMAGES_PER_PERSON}")