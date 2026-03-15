from pathlib import Path
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

# =========================
# PATH SETUP
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]

FEATURES_CSV = BASE_DIR / "data" / "features" / "features.csv"
MODEL_PATH = BASE_DIR / "data" / "features" / "rf_model.joblib"

# =========================
# LOAD FEATURES
# =========================

print("\nLoading features...")

df = pd.read_csv(FEATURES_CSV)

print(f"Dataset size: {len(df)} samples")

# =========================
# PREPARE DATA
# =========================

X = df.drop(columns=["label", "filename", "filepath"])
y = df["label"]

print(f"Feature count: {X.shape[1]}")

# =========================
# TRAIN / TEST SPLIT
# =========================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

print("\nTrain size:", len(X_train))
print("Test size:", len(X_test))

# =========================
# TRAIN RANDOM FOREST
# =========================

print("\nTraining Random Forest model...")

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=None,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# =========================
# TEST MODEL
# =========================

print("\nEvaluating model...")

y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)

print("\nAccuracy:", accuracy)

print("\nClassification Report:")
print(classification_report(y_test, y_pred))

print("\nConfusion Matrix:")
print(confusion_matrix(y_test, y_pred))

# =========================
# SAVE MODEL
# =========================

joblib.dump(model, MODEL_PATH)

print(f"\nModel saved to: {MODEL_PATH}")
