import tensorflow as tf
import os

from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications.efficientnet import preprocess_input

# ==============================
# Dataset Path
# ==============================

DATASET_DIR = "train"

IMG_SIZE = (224, 224)
BATCH_SIZE = 32

# ==============================
# Data Generator
# ==============================

train_datagen = ImageDataGenerator(
    preprocessing_function=preprocess_input,
    validation_split=0.2,
    rotation_range=15,
    zoom_range=0.15,
    width_shift_range=0.1,
    height_shift_range=0.1,
    horizontal_flip=True
)

# ==============================
# Training Dataset
# ==============================

train_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode="binary",
    subset="training",
    shuffle=True
)

# ==============================
# Validation Dataset
# ==============================

validation_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode="binary",
    subset="validation",
    shuffle=False
)

# ==============================
# Information
# ==============================

print("=" * 60)
print("Classes :", train_generator.class_indices)
print("Training Images :", train_generator.samples)
print("Validation Images :", validation_generator.samples)
print("=" * 60)

from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.layers import (
    GlobalAveragePooling2D,
    Dense,
    Dropout,
    BatchNormalization
)
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam

# ====================================
# Load EfficientNetB0
# ====================================

base_model = EfficientNetB0(
    weights="imagenet",
    include_top=False,
    input_shape=(224,224,3)
)

# ====================================
# Fine-Tuning
# Freeze all except last 20 layers
# ====================================

base_model.trainable = True

for layer in base_model.layers[:-20]:
    layer.trainable = False

# ====================================
# Custom Classification Head
# ====================================

x = base_model.output

x = GlobalAveragePooling2D()(x)

x = BatchNormalization()(x)

x = Dense(
    256,
    activation="relu"
)(x)

x = Dropout(0.5)(x)

x = Dense(
    128,
    activation="relu"
)(x)

x = Dropout(0.3)(x)

output = Dense(
    1,
    activation="sigmoid"
)(x)

# ====================================
# Final Model
# ====================================

model = Model(
    inputs=base_model.input,
    outputs=output
)

# ====================================
# Compile
# ====================================

model.compile(
    optimizer=Adam(learning_rate=1e-4),
    loss="binary_crossentropy",
    metrics=[
        "accuracy",
        tf.keras.metrics.Precision(name="precision"),
        tf.keras.metrics.Recall(name="recall")
    ]
)

# ====================================
# Model Summary
# ====================================

model.summary()


from tensorflow.keras.callbacks import (
    EarlyStopping,
    ModelCheckpoint,
    ReduceLROnPlateau,
    CSVLogger
)

# ===========================================
# Callbacks
# ===========================================

checkpoint = ModelCheckpoint(
    filepath="best_eye_model.keras",
    monitor="val_accuracy",
    save_best_only=True,
    verbose=1
)

early_stop = EarlyStopping(
    monitor="val_loss",
    patience=6,
    restore_best_weights=True,
    verbose=1
)

reduce_lr = ReduceLROnPlateau(
    monitor="val_loss",
    factor=0.2,
    patience=3,
    min_lr=1e-7,
    verbose=1
)

csv_logger = CSVLogger("training_log.csv")

# ===========================================
# Train Model
# ===========================================

EPOCHS = 30

history = model.fit(
    train_generator,
    validation_data=validation_generator,
    epochs=EPOCHS,
    callbacks=[
        checkpoint,
        early_stop,
        reduce_lr,
        csv_logger
    ],
    verbose=1
)

print("\nTraining Completed Successfully!")


import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# Evaluate Model
# ==========================================

results = model.evaluate(validation_generator, verbose=1)

print("\n" + "="*60)
print(f"Validation Loss      : {results[0]:.4f}")
print(f"Validation Accuracy  : {results[1]*100:.2f}%")
print(f"Validation Precision : {results[2]*100:.2f}%")
print(f"Validation Recall    : {results[3]*100:.2f}%")
print("="*60)

# ==========================================
# Save Final Model
# ==========================================

model.save("eye_model.keras")

print("\nModel saved successfully!")

# ==========================================
# Save Labels
# ==========================================

labels = train_generator.class_indices

with open("labels.txt", "w") as f:
    for name, idx in labels.items():
        f.write(f"{idx} {name}\n")

print("labels.txt saved!")

# ==========================================
# Accuracy Graph
# ==========================================

plt.figure(figsize=(10,5))

plt.plot(history.history["accuracy"], label="Train Accuracy")
plt.plot(history.history["val_accuracy"], label="Validation Accuracy")

plt.xlabel("Epoch")
plt.ylabel("Accuracy")
plt.title("Training vs Validation Accuracy")

plt.legend()
plt.grid(True)

plt.savefig("accuracy_graph.png")
plt.show()

# ==========================================
# Loss Graph
# ==========================================

plt.figure(figsize=(10,5))

plt.plot(history.history["loss"], label="Train Loss")
plt.plot(history.history["val_loss"], label="Validation Loss")

plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("Training vs Validation Loss")

plt.legend()
plt.grid(True)

plt.savefig("loss_graph.png")
plt.show()

print("\nGraphs saved successfully!")

import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.applications.efficientnet import preprocess_input

# ==========================================
# Load Model
# ==========================================

model = load_model("eye_model.keras")

# ==========================================
# Class Labels
# ==========================================

classes = ["Closed_Eyes", "Open_Eyes"]

# ==========================================
# Test Image Path
# ==========================================

IMAGE_PATH = "test.jpg"

# ==========================================
# Read Image
# ==========================================

image = cv2.imread(IMAGE_PATH)

if image is None:
    print("Image not found!")
    exit()

original = image.copy()

# ==========================================
# Preprocess
# ==========================================

image = cv2.resize(image, (224, 224))
image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

image = np.array(image, dtype=np.float32)

image = preprocess_input(image)

image = np.expand_dims(image, axis=0)

# ==========================================
# Prediction
# ==========================================

prediction = model.predict(image)

confidence = float(prediction[0][0])

if confidence >= 0.5:
    label = classes[1]
    score = confidence
else:
    label = classes[0]
    score = 1 - confidence

print("=" * 60)
print("Prediction :", label)
print(f"Confidence : {score*100:.2f}%")
print("=" * 60)

# ==========================================
# Display
# ==========================================

cv2.putText(
    original,
    f"{label} ({score*100:.2f}%)",
    (20,40),
    cv2.FONT_HERSHEY_SIMPLEX,
    1,
    (0,255,0),
    2
)

cv2.imshow("Prediction", original)

cv2.waitKey(0)
cv2.destroyAllWindows()