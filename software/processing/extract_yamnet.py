"""YAMNet embeddings for every clip (pretrained AudioSet CNN, transfer learning).

data/dataset/<class>/*.wav -> data/features/features_yamnet.csv
"""
from multiprocessing import Pool
from pathlib import Path
import warnings

import librosa
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[2]   # ~/thesis
DATASET_DIR = BASE_DIR / "data" / "dataset"
OUTPUT_CSV = BASE_DIR / "data" / "features" / "features_yamnet.csv"
YAMNET_MODEL = BASE_DIR / "models" / "yamnet.tflite"

YAMNET_SR = 16000   # YAMNet expects 16 kHz mono in [-1, 1]

_interpreter = None


def yamnet_features(file_path):
    global _interpreter
    if _interpreter is None:
        from ai_edge_litert.interpreter import Interpreter
        _interpreter = Interpreter(model_path=str(YAMNET_MODEL))

    y, _ = librosa.load(file_path, sr=YAMNET_SR, mono=True)
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak
    y = y.astype(np.float32)

    inp = _interpreter.get_input_details()[0]
    _interpreter.resize_tensor_input(inp["index"], [len(y)], strict=False)
    _interpreter.allocate_tensors()
    _interpreter.set_tensor(inp["index"], y)
    _interpreter.invoke()
    out = {d["name"]: _interpreter.get_tensor(d["index"]) for d in _interpreter.get_output_details()}
    scores, embeddings = out["Identity"], out["Identity_1"]   # per 0.48 s frame

    features = {}
    features.update({f"emb_mean_{i}": float(v) for i, v in enumerate(embeddings.mean(0))})
    features.update({f"emb_max_{i}": float(v) for i, v in enumerate(embeddings.max(0))})
    features.update({f"score_{i}": float(v) for i, v in enumerate(scores.mean(0))})
    return features


def _row(file_path):
    feat = yamnet_features(file_path)
    feat["label"] = file_path.relative_to(DATASET_DIR).parts[0]
    feat["filename"] = file_path.name
    return feat


def main():
    files = sorted(DATASET_DIR.rglob("*.wav"))
    print(f"Extracting YAMNet features for {len(files)} files (do not edit the dataset meanwhile)...")
    with Pool(4) as pool:
        rows = pool.map(_row, files, chunksize=16)
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
