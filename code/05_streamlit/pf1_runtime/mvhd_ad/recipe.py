from __future__ import annotations
from pathlib import Path
import json
from .artifact_paths import resolve_artifact

def build_inspection_recipe(artifacts_dir: str | Path) -> dict:
    art = Path(artifacts_dir)
    threshold = json.loads(resolve_artifact(art, "threshold").read_text(encoding="utf-8"))
    return {
        "schema_version": 6.7,
        "recipe_id": "AUTO_FROM_CALIBRATED_BUNDLE",
        "pipeline": [
            "input/acquisition guard",
            "alignment",
            "surface ROI + boundary halo",
            "EfficientAD anomaly score",
            "calibration-only decision head",
            "calibrated raw OK/REVIEW/NG triage",
            "visible/safety evidence gate",
            "heatmap/overlay/contour",
            "operator confirmation when required",
            "audit logging",
        ],
        "roi": {
            "preprocess_profile": resolve_artifact(art, "preprocess_profile").name,
            "localization_profile": resolve_artifact(art, "localization_profile").name,
            "policy": "stable GOOD surface + narrow boundary halo; far background/stable openings excluded",
        },
        "decision": {
            "review_low": float(threshold["review_low"]),
            "ng_high": float(threshold["ng_high"]),
            "binary_threshold": float(threshold.get("threshold", threshold["review_low"])),
            "final_test_not_used_for_threshold": True,
        },
        "input_guard": {
            "operating_window": resolve_artifact(art, "operating_window").name,
            "statuses": ["OK", "WARN", "REVIEW_INPUT"],
        },
        "visuals": ["Original", "Heatmap", "Overlay", "Contour", "CandidateMap"],
        "localization_wording": "defect candidate unless GT-mask validation passes",
    }

def save_inspection_recipe(path: str | Path, artifacts_dir: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(build_inspection_recipe(artifacts_dir), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
