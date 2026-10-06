import os
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator

# ==========================
# Dataset Path
# ==========================
DATASET_DIR = "MRL_Eye_2K"

# Image Settings
IMG_SIZE = (224, 224)
BATCH_SIZE = 32

# ==========================
# Data Augmentation
# ==========================
train_datagen = ImageDataGenerator(
    rescale=1./255,
    validation_split=0.2,
    rotation_range=15,
    zoom_range=0.15,
    width_shift_range=0.1,
    height_shift_range=0.1,
    horizontal_flip=True,
    fill_mode="nearest"
)

# ==========================
# Training Dataset
# ==========================
train_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode="binary",
    subset="training",
    shuffle=True
)

# ==========================
# Validation Dataset
# ==========================
validation_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode="binary",
    subset="validation",
    shuffle=False
)

# ==========================
# Display Dataset Information
# ==========================
print("=" * 50)
print("Class Labels:", train_generator.class_indices)
print("Training Images :", train_generator.samples)
print("Validation Images :", validation_generator.samples)
print("=" * 50)

from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import GlobalAveragePooling2D, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tensorflow.keras.optimizers import Adam

# ==========================
# Build EfficientNetB0 Model
# ==========================

base_model = EfficientNetB0(
    weights="imagenet",
    include_top=False,
    input_shape=(224, 224, 3)
)

# Freeze pretrained layers
base_model.trainable = False

# Create Model
model = Sequential([
    base_model,
    GlobalAveragePooling2D(),

    Dense(256, activation='relu'),
    Dropout(0.4),

    Dense(128, activation='relu'),
    Dropout(0.3),

    Dense(1, activation='sigmoid')
])

# ==========================
# Compile Model
# ==========================

model.compile(
    optimizer=Adam(learning_rate=0.0001),
    loss='binary_crossentropy',
    metrics=['accuracy']
)

# ==========================
# Callbacks
# ==========================

checkpoint = ModelCheckpoint(
    "best_eye_model.keras",
    monitor="val_accuracy",
    save_best_only=True,
    verbose=1
)

early_stop = EarlyStopping(
    monitor="val_loss",
    patience=5,
    restore_best_weights=True
)

reduce_lr = ReduceLROnPlateau(
    monitor="val_loss",
    factor=0.2,
    patience=3,
    verbose=1
)

# ==========================
# Model Summary
# ==========================

model.summary()

# ==========================
# Train Model
# ==========================

EPOCHS = 15

history = model.fit(
    train_generator,
    validation_data=validation_generator,
    epochs=EPOCHS,
    callbacks=[
        checkpoint,
        early_stop,
        reduce_lr
    ]
)

import matplotlib.pyplot as plt
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image

# ==========================
# Evaluate Model
# ==========================

loss, accuracy = model.evaluate(validation_generator)

print("\n" + "=" * 50)
print(f"Validation Accuracy : {accuracy * 100:.2f}%")
print(f"Validation Loss     : {loss:.4f}")
print("=" * 50)

# ==========================
# Save Final Model
# ==========================

model.save("eye_model.keras")

print("\nModel saved successfully as eye_model.keras")

# ==========================
# Save Labels
# ==========================

with open("labels.txt", "w") as f:
    f.write("0 Closed\n")
    f.write("1 Open\n")

print("labels.txt created successfully")

# ==========================
# Plot Accuracy
# ==========================

plt.figure(figsize=(8,5))
plt.plot(history.history['accuracy'], label='Training Accuracy')
plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
plt.xlabel("Epoch")
plt.ylabel("Accuracy")
plt.title("Model Accuracy")
plt.legend()
plt.grid(True)
plt.savefig("accuracy.png")
plt.show()

# ==========================
# Plot Loss
# ==========================

plt.figure(figsize=(8,5))
plt.plot(history.history['loss'], label='Training Loss')
plt.plot(history.history['val_loss'], label='Validation Loss')
plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("Model Loss")
plt.legend()
plt.grid(True)
plt.savefig("loss.png")
plt.show()

# ==========================
# Test Prediction
# ==========================

MODEL_PATH = "eye_model.keras"
TEST_IMAGE = "test.jpg"   # Replace with your image

if os.path.exists(TEST_IMAGE):

    model = load_model(MODEL_PATH)

    img = image.load_img(TEST_IMAGE, target_size=(224,224))
    img = image.img_to_array(img)
    img = np.expand_dims(img, axis=0)
    img = img / 255.0

    prediction = model.predict(img)[0][0]

    if prediction > 0.5:
        print("\nPrediction : OPEN EYE")
        print(f"Confidence : {prediction*100:.2f}%")
    else:
        print("\nPrediction : CLOSED EYE")
        print(f"Confidence : {(1-prediction)*100:.2f}%")

else:
    print("\nPlace a test image named 'test.jpg' in this folder to test the model.")