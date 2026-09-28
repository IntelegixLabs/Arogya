"""Arogya Prediction Lab.

Real machine-learning models trained at startup on public clinical datasets:

1. Breast cancer   - Breast Cancer Wisconsin (Diagnostic), UCI / scikit-learn build-in
                     (the classic Kaggle benchmark, 569 biopsied tumours)
2. Lung cancer     - Lung Cancer Survey dataset (Hugging Face: nateraw/lung-cancer, 309 records)
3. Cervical cancer - Risk Factors for Cervical Cancer (UCI ML repo, 858 patients, biopsy target)

Each model is a scikit-learn GradientBoostingClassifier with a held-out test split,
reporting accuracy and ROC-AUC, plus feature importances used to explain predictions.
"""
import csv
import os
import threading

import numpy as np
from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")

_LOCK = threading.Lock()
_MODELS = {}   # id -> {meta, clf, scaler-ish info}
_READY = False


# ---------------------------------------------------------------- feature schema helper
def f_num(key, label, mn, mx, default, step=None, unit=""):
    return {"key": key, "label": label, "type": "number", "min": mn, "max": mx,
            "default": default, "step": step or round((mx - mn) / 100, 4), "unit": unit}


def f_bool(key, label, default=0):
    return {"key": key, "label": label, "type": "binary", "default": default}


# ---------------------------------------------------------------- breast cancer (Wisconsin)
BREAST_FEATURES = [
    ("mean radius", f_num("mean radius", "Mean radius", 6.0, 30.0, 14.0, 0.1, "mm")),
    ("mean texture", f_num("mean texture", "Mean texture", 9.0, 40.0, 19.0, 0.1)),
    ("mean perimeter", f_num("mean perimeter", "Mean perimeter", 40.0, 190.0, 92.0, 0.5, "mm")),
    ("mean area", f_num("mean area", "Mean area", 140.0, 2600.0, 655.0, 5, "mm²")),
    ("mean smoothness", f_num("mean smoothness", "Mean smoothness", 0.05, 0.17, 0.096, 0.001)),
    ("mean compactness", f_num("mean compactness", "Mean compactness", 0.02, 0.35, 0.10, 0.001)),
    ("mean concavity", f_num("mean concavity", "Mean concavity", 0.0, 0.45, 0.089, 0.001)),
    ("mean concave points", f_num("mean concave points", "Mean concave points", 0.0, 0.21, 0.048, 0.001)),
    ("worst radius", f_num("worst radius", "Worst radius", 7.0, 37.0, 16.3, 0.1, "mm")),
    ("worst concave points", f_num("worst concave points", "Worst concave points", 0.0, 0.30, 0.114, 0.001)),
]


def _train_breast():
    ds = load_breast_cancer(as_frame=False)
    names = list(ds.feature_names)
    idx = [names.index(k) for k, _ in BREAST_FEATURES]
    X = ds.data[:, idx]
    # target: 0 = malignant, 1 = benign  ->  flip so 1 = malignant (risk)
    y = 1 - ds.target
    return X, y, [schema for _, schema in BREAST_FEATURES]


# ---------------------------------------------------------------- lung cancer (HF survey)
LUNG_FEATURES = [
    f_bool("GENDER", "Male sex"),
    f_num("AGE", "Age", 20, 90, 55, 1, "years"),
    f_bool("SMOKING", "Smoking"),
    f_bool("YELLOW_FINGERS", "Yellow fingers"),
    f_bool("ANXIETY", "Anxiety"),
    f_bool("PEER_PRESSURE", "Peer pressure"),
    f_bool("CHRONIC DISEASE", "Chronic disease"),
    f_bool("FATIGUE", "Fatigue"),
    f_bool("ALLERGY", "Allergy"),
    f_bool("WHEEZING", "Wheezing"),
    f_bool("ALCOHOL CONSUMING", "Alcohol consumption"),
    f_bool("COUGHING", "Coughing"),
    f_bool("SHORTNESS OF BREATH", "Shortness of breath"),
    f_bool("SWALLOWING DIFFICULTY", "Swallowing difficulty"),
    f_bool("CHEST PAIN", "Chest pain"),
]


def _train_lung():
    path = os.path.join(DATASETS_DIR, "lung_cancer_survey.csv")
    rows = list(csv.reader(open(path, encoding="utf-8")))
    header = [h.strip() for h in rows[0]]
    data = rows[1:]
    keymap = {f["key"]: header.index(f["key"].strip() if f["key"].strip() in header
                                     else next(h for h in header if h.strip() == f["key"]))
              for f in LUNG_FEATURES}
    X, y = [], []
    for r in data:
        if len(r) != len(header):
            continue
        feats = []
        for f in LUNG_FEATURES:
            v = r[keymap[f["key"]]].strip()
            if f["key"] == "GENDER":
                feats.append(1.0 if v.upper() == "M" else 0.0)
            elif f["key"] == "AGE":
                feats.append(float(v))
            else:  # survey encodes 1 = no, 2 = yes
                feats.append(1.0 if v == "2" else 0.0)
        X.append(feats)
        y.append(1 if r[header.index("LUNG_CANCER")].strip().upper() == "YES" else 0)
    return np.array(X), np.array(y), LUNG_FEATURES


# ---------------------------------------------------------------- cervical cancer (UCI)
CERVICAL_COLS = [
    ("Age", f_num("Age", "Age", 15, 80, 30, 1, "years")),
    ("Number of sexual partners", f_num("Number of sexual partners", "Sexual partners", 1, 15, 2, 1)),
    ("First sexual intercourse", f_num("First sexual intercourse", "Age at first intercourse", 12, 30, 17, 1, "years")),
    ("Num of pregnancies", f_num("Num of pregnancies", "Pregnancies", 0, 11, 2, 1)),
    ("Smokes", f_bool("Smokes", "Smokes")),
    ("Smokes (years)", f_num("Smokes (years)", "Smoking duration", 0, 40, 0, 1, "years")),
    ("Hormonal Contraceptives", f_bool("Hormonal Contraceptives", "Hormonal contraceptives", 1)),
    ("Hormonal Contraceptives (years)", f_num("Hormonal Contraceptives (years)", "Contraceptive duration", 0, 30, 2, 0.5, "years")),
    ("IUD", f_bool("IUD", "IUD use")),
    ("STDs", f_bool("STDs", "History of STDs")),
    ("STDs (number)", f_num("STDs (number)", "Number of STDs", 0, 4, 0, 1)),
    ("Dx:HPV", f_bool("Dx:HPV", "HPV diagnosis")),
]


def _train_cervical():
    path = os.path.join(DATASETS_DIR, "cervical_cancer_uci.csv")
    rows = list(csv.reader(open(path, encoding="utf-8")))
    header = rows[0]
    data = rows[1:]
    col_idx = [header.index(c) for c, _ in CERVICAL_COLS]
    target_idx = header.index("Biopsy")
    raw = []
    y = []
    for r in data:
        vals = []
        for i in col_idx:
            v = r[i]
            vals.append(np.nan if v == "?" else float(v))
        raw.append(vals)
        y.append(int(float(r[target_idx])))
    X = np.array(raw)
    med = np.nanmedian(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(med, inds[1])
    return X, np.array(y), [schema for _, schema in CERVICAL_COLS]


# ---------------------------------------------------------------- training driver
DATASET_META = {
    "breast": {
        "name": "Breast Cancer",
        "icon": "🎗️",
        "dataset": "Breast Cancer Wisconsin (Diagnostic)",
        "source": "UCI ML Repository / Kaggle classic (via scikit-learn)",
        "n_note": "569 fine-needle-aspirate biopsies, 30 morphometric features",
        "positive_label": "Malignant",
        "negative_label": "Benign",
        "description": "Predicts whether a breast tumour is malignant from cell-nucleus morphometry measured on a digitised fine-needle aspirate.",
        "trainer": _train_breast,
    },
    "lung": {
        "name": "Lung Cancer",
        "icon": "🫁",
        "dataset": "Lung Cancer Survey",
        "source": "Hugging Face: nateraw/lung-cancer",
        "n_note": "309 survey records, symptom + lifestyle factors",
        "positive_label": "High likelihood",
        "negative_label": "Low likelihood",
        "description": "Estimates lung-cancer likelihood from symptoms and lifestyle factors reported in a clinical screening survey.",
        "trainer": _train_lung,
    },
    "cervical": {
        "name": "Cervical Cancer",
        "icon": "🌸",
        "dataset": "Risk Factors for Cervical Cancer",
        "source": "UCI ML Repository (Hospital Universitario de Caracas)",
        "n_note": "858 patients, biopsy-confirmed target",
        "positive_label": "Positive biopsy risk",
        "negative_label": "Low biopsy risk",
        "description": "Predicts biopsy-positive cervical cancer risk from demographic, sexual-health and contraceptive history factors.",
        "trainer": _train_cervical,
    },
}


def _train_all():
    global _READY
    with _LOCK:
        if _READY:
            return
        for mid, meta in DATASET_META.items():
            try:
                X, y, schema = meta["trainer"]()
                Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
                clf = GradientBoostingClassifier(random_state=42)
                clf.fit(Xtr, ytr)
                proba = clf.predict_proba(Xte)[:, 1]
                acc = float(accuracy_score(yte, proba >= 0.5))
                try:
                    auc = float(roc_auc_score(yte, proba))
                except ValueError:
                    auc = None
                importances = sorted(
                    [{"feature": s["label"], "importance": round(float(w), 4)}
                     for s, w in zip(schema, clf.feature_importances_)],
                    key=lambda x: -x["importance"])
                _MODELS[mid] = {
                    "clf": clf, "schema": schema,
                    "meta": {
                        "id": mid, "name": meta["name"], "icon": meta["icon"],
                        "dataset": meta["dataset"], "source": meta["source"],
                        "n_note": meta["n_note"], "description": meta["description"],
                        "positive_label": meta["positive_label"],
                        "negative_label": meta["negative_label"],
                        "n_samples": int(len(y)), "n_positive": int(y.sum()),
                        "accuracy": round(acc, 3),
                        "roc_auc": round(auc, 3) if auc is not None else None,
                        "algorithm": "Gradient Boosting (scikit-learn)",
                        "features": schema,
                        "importances": importances,
                    },
                }
                print(f"[arogya-ml] {meta['name']}: n={len(y)} acc={acc:.3f} auc={auc}")
            except Exception as e:
                print(f"[arogya-ml] FAILED to train {mid}: {e}")
        _READY = True


def ensure_ready():
    if not _READY:
        _train_all()


def list_models() -> list:
    ensure_ready()
    return [m["meta"] for m in _MODELS.values()]


def predict(model_id: str, features: dict) -> dict:
    ensure_ready()
    if model_id not in _MODELS:
        raise KeyError(f"Unknown model '{model_id}'")
    m = _MODELS[model_id]
    x = []
    for s in m["schema"]:
        v = features.get(s["key"], s["default"])
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = float(s["default"])
        x.append(v)
    prob = float(m["clf"].predict_proba(np.array([x]))[0, 1])
    meta = m["meta"]
    band = ("Very high" if prob >= 0.8 else "High" if prob >= 0.6
            else "Moderate" if prob >= 0.35 else "Low" if prob >= 0.15 else "Very low")
    return {
        "model": model_id,
        "probability": round(prob, 4),
        "risk_band": band,
        "label": meta["positive_label"] if prob >= 0.5 else meta["negative_label"],
        "top_factors": meta["importances"][:6],
        "disclaimer": ("Decision-support estimate from a model trained on a public research dataset. "
                       "Not a diagnosis. Always correlate clinically."),
    }
