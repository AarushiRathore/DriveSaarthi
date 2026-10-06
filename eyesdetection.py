import os
import random
import shutil

# -----------------------------
# Source folders
# -----------------------------
SOURCE_DIR = "MRL_Eye"

OPEN_DIR = os.path.join(SOURCE_DIR, "Open-Eyes")
CLOSED_DIR = os.path.join(SOURCE_DIR, "Close-Eyes")

# -----------------------------
# Destination folders
# -----------------------------
DEST_DIR = "MRL_Eye_2K"

DEST_OPEN = os.path.join(DEST_DIR, "Open-Eyes")
DEST_CLOSED = os.path.join(DEST_DIR, "Close-Eyes")

OPEN_COUNT = 2000
CLOSED_COUNT = 2000

# -----------------------------
# Create destination folders
# -----------------------------
os.makedirs(DEST_OPEN, exist_ok=True)
os.makedirs(DEST_CLOSED, exist_ok=True)

# -----------------------------
# Function
# -----------------------------
def copy_images(src, dst, count):

    files = [f for f in os.listdir(src)
             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]

    print(f"Found {len(files)} images in {src}")

    if len(files) < count:
        count = len(files)

    selected = random.sample(files, count)

    for file in selected:
        shutil.copy2(
            os.path.join(src, file),
            os.path.join(dst, file)
        )

    print(f"Copied {count} images.")

# -----------------------------
# Run
# -----------------------------
copy_images(OPEN_DIR, DEST_OPEN, OPEN_COUNT)
copy_images(CLOSED_DIR, DEST_CLOSED, CLOSED_COUNT)

print("\nDataset Created Successfully!")
print("Location:", DEST_DIR)