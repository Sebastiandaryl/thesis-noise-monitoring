import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib

FEATURES_CSV = Path.home() / "thesis" / "data" / "features" / "features.csv"
MODEL_OUT = Path.home() / "thesis" / "data" / "features" / "rf_model.joblib"

def main():
    df = pd.read_csv(FEATURES_CSV)

    # Drop non-feature columns
    X = df.drop(columns=["filepath", "label"])
    y = df["label"]

    # Stratified split keeps class balance
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)

    print("\n Accuracy:", accuracy_score(y_test, y_pred))
    print("\nConfusion Matrix:\n", confusion_matrix(y_test, y_pred))
    print("\nClassification Report:\n", classification_report(y_test, y_pred))

    joblib.dump(clf, MODEL_OUT)
    print(f"\n Saved model to: {MODEL_OUT}")

if __name__ == "__main__":
    main()