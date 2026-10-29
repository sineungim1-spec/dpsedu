from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib

AUDIT_FIELDS = [
    "timestamp", "line_id", "station_id", "lot_id", "product_id",
    "camera_view_group", "model_version", "model_sha256", "recipe_id",
    "input_guard_status", "alignment_score", "anomaly_score",
    "review_low", "ng_high", "ai_triage", "line_action",
    "operator_final_decision", "operator_id", "image_path",
    "heatmap_path", "contour_path",
]

def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def append_audit(log_path: str | Path, record: dict) -> Path:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = {k: record.get(k) for k in AUDIT_FIELDS}
    obj["timestamp"] = obj["timestamp"] or datetime.now(timezone.utc).isoformat()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return p

def save_audit_schema(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps({
        "schema_version": 6.5,
        "format": "JSONL",
        "required_fields": AUDIT_FIELDS,
        "purpose": ["traceability", "FP/FN review", "drift monitoring", "rollback", "lot/shift comparison"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
