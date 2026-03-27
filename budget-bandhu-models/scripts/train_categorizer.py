import pandas as pd
import numpy as np
import joblib
import json
import os
import torch
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sentence_transformers import SentenceTransformer

DATA_PATH = "data/upi_training_data.csv"
MODEL_DIR = "models/phi3_categorizer"
os.makedirs(MODEL_DIR, exist_ok=True)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")
if DEVICE == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

print("Loading training data...")
df = pd.read_csv(DATA_PATH)
print(f"Total samples: {len(df)}")
print(df["category"].value_counts())

print(f"\nLoading sentence transformer on {DEVICE}...")
embedder = SentenceTransformer("all-MiniLM-L6-v2", device=DEVICE)

print("Encoding descriptions (GPU-accelerated)...")
X = embedder.encode(
    df["description"].tolist(),
    batch_size=256,
    show_progress_bar=True,
    device=DEVICE,
    normalize_embeddings=True,
    convert_to_numpy=True,
)
print(f"Embeddings shape: {X.shape}")

le = LabelEncoder()
y  = le.fit_transform(df["category"])

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"\nTrain: {len(X_train)} | Test: {len(X_test)}")

print("Training LogisticRegression classifier...")
clf = LogisticRegression(C=10, max_iter=2000, random_state=42, n_jobs=-1)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
acc    = accuracy_score(y_test, y_pred)
print(f"\nAccuracy: {acc:.4f} ({acc*100:.2f}%)")
print("\nClassification Report:")
print(classification_report(y_test, y_pred, target_names=le.classes_))

assert acc >= 0.88, f"Accuracy {acc:.2f} below 88% threshold — check training data"

# Save model files
joblib.dump(clf, f"{MODEL_DIR}/classifier.joblib")
joblib.dump(le,  f"{MODEL_DIR}/label_encoder.joblib")

metadata = {
    "accuracy":         round(acc, 4),
    "training_samples": len(X_train),
    "test_samples":     len(X_test),
    "categories":       le.classes_.tolist(),
    "embedding_model":  "all-MiniLM-L6-v2",
    "classifier":       "LogisticRegression(C=10)",
    "trained_at":       datetime.utcnow().isoformat(),
    "model_version":    "1.0",
    "trained_on":       DEVICE,
}
with open(f"{MODEL_DIR}/model_metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

print(f"\n✅ Model saved to {MODEL_DIR}/")
print(f"   classifier.joblib      ✅")
print(f"   label_encoder.joblib   ✅")
print(f"   model_metadata.json    ✅")
print(f"\nCategories: {le.classes_.tolist()}")