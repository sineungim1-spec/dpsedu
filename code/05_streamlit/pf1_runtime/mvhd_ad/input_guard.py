from __future__ import annotations
from pathlib import Path
import json
import cv2
import numpy as np
from .artifact_paths import resolve_artifact
from .preprocess import standardize_image, detect_product
from .operating_window import image_proxy_metrics

def _group(window: dict, preferred: str) -> tuple[str, dict]:
    groups = window["groups"]
    if preferred in groups:
        return preferred, groups[preferred]
    if "GENERIC" in groups:
        return "GENERIC", groups["GENERIC"]
    key = next(iter(groups))
    return key, groups[key]

def evaluate_input_guard(image_path: str | Path, artifacts_dir: str | Path,
                         inspection_group: str="GENERIC") -> dict:
    art = Path(artifacts_dir)
    pp = resolve_artifact(art, "preprocess_profile")
    ow = resolve_artifact(art, "operating_window")
    window = json.loads(ow.read_text(encoding="utf-8"))

    standardized = standardize_image(image_path, pp, inspection_group)
    bgr = cv2.cvtColor(standardized.rgb, cv2.COLOR_RGB2BGR)
    mask, _ = detect_product(bgr)
    metrics = image_proxy_metrics(
        standardized.rgb,
        (mask > 0).astype(np.uint8),
        standardized.alignment_score,
    )

    group_name, group_obj = _group(window, standardized.inspection_group)
    violations = []
    severe = 0
    mild = 0

    for name, value in metrics.items():
        spec = group_obj.get("metrics", {}).get(name)
        if not spec:
            continue
        lo, hi = spec.get("lower"), spec.get("upper")
        scale = max(float(spec.get("scale", 1e-6)), 1e-6)
        distance = 0.0
        direction = None
        if lo is not None and value < float(lo):
            distance = (float(lo) - float(value)) / scale
            direction = "LOW"
        elif hi is not None and value > float(hi):
            distance = (float(value) - float(hi)) / scale
            direction = "HIGH"
        if direction:
            severity = "SEVERE" if distance > 1.0 else "MILD"
            severe += severity == "SEVERE"
            mild += severity == "MILD"
            violations.append({
                "metric": name,
                "value": float(value),
                "direction": direction,
                "severity": severity,
                "normalized_distance": float(distance),
                "lower": lo,
                "upper": hi,
            })

    if severe > 0 or len(violations) >= 2:
        status = "REVIEW_INPUT"
    elif mild == 1:
        status = "WARN"
    else:
        status = "OK"

    return {
        "schema_version": 6.5,
        "status": status,
        "inspection_group": group_name,
        "alignment_score": float(standardized.alignment_score),
        "metrics": {k: float(v) for k, v in metrics.items()},
        "violations": violations,
        "policy": {
            "OK": "inside learned TRAIN-GOOD image envelope",
            "WARN": "one mild acquisition deviation; inspect but may continue",
            "REVIEW_INPUT": "multiple/severe acquisition deviations; correct input before trusting defect decision",
        },
    }
