from __future__ import annotations
from pathlib import Path
import json

def deployment_profiles() -> dict:
    return {
        "schema_version": 6.5,
        "profiles": {
            "COMPANY_REFERENCE": {
                "image_size": 256,
                "batch_size": 1,
                "visualizer": False,
                "decision": "raw OK/REVIEW/NG + ACTION/SAFETY fused production triage",
                "input_guard": True,
                "audit": True,
                "purpose": "line-quality-assist reference",
            },
            "EDU_LIGHT": {
                "image_size": 256,
                "training_epochs_recommended": 2,
                "batch_size": 1,
                "visualizer": False,
                "purpose": "teacher training / reproducible educational model building",
            },
            "EDGE_PREP": {
                "image_size": 256,
                "batch_size": 1,
                "visualizer": False,
                "recommended_targets": ["ONNX", "OpenVINO"],
                "note": "Actual graph export is performed only when the installed Anomalib/torch backend supports the target; numerical parity must be validated before deployment.",
            },
        },
    }

def save_deployment_profiles(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(deployment_profiles(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
