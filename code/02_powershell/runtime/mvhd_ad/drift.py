from __future__ import annotations
from pathlib import Path
import json
import numpy as np

def build_score_baseline(train_good_scores: list[float], calibration_good_scores: list[float] | None=None) -> dict:
    def summary(vals):
        a = np.asarray(vals, dtype=float)
        return {
            "n": int(len(a)),
            "median": float(np.median(a)),
            "q90": float(np.quantile(a, .90)),
            "q95": float(np.quantile(a, .95)),
            "q99": float(np.quantile(a, .99)),
            "mad": float(np.median(np.abs(a - np.median(a)))),
        }
    return {
        "schema_version": 6.5,
        "train_good": summary(train_good_scores),
        "calibration_good": summary(calibration_good_scores or []),
        "use": "production score-drift baseline; never used to rewrite Final-Test metrics",
    }

def read_audit_scores(log_path: str | Path, last_n: int=200) -> list[float]:
    vals = []
    p = Path(log_path)
    if not p.exists():
        return vals
    for line in p.read_text(encoding="utf-8").splitlines()[-last_n:]:
        try:
            x = json.loads(line).get("anomaly_score")
            if x is not None:
                vals.append(float(x))
        except Exception:
            pass
    return vals

def score_drift_status(baseline: dict, recent_scores: list[float]) -> dict:
    if len(recent_scores) < 20:
        return {"status": "INSUFFICIENT_DATA", "n": len(recent_scores)}
    a = np.asarray(recent_scores, dtype=float)
    b = baseline["train_good"]
    recent_median = float(np.median(a))
    recent_q95 = float(np.quantile(a, .95))
    scale = max(float(b.get("mad", 0.0)) * 1.4826, 1e-6)
    z = abs(recent_median - float(b["median"])) / scale
    q95_ratio = recent_q95 / max(float(b["q95"]), 1e-6)
    status = "DRIFT_ALERT" if z > 3.0 or q95_ratio > 1.5 else ("WATCH" if z > 2.0 or q95_ratio > 1.25 else "STABLE")
    return {
        "status": status,
        "n": int(len(a)),
        "recent_median": recent_median,
        "recent_q95": recent_q95,
        "median_robust_z": float(z),
        "q95_ratio": float(q95_ratio),
    }
