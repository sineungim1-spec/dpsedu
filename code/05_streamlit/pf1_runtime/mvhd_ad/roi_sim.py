from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from .preprocess import _decode_profile

def roi_variants(preprocess_profile: str | Path, inspection_group: str="GENERIC",
                 halo_values=(0, 1, 3, 5, 8)) -> dict[str, np.ndarray]:
    profile = _decode_profile(preprocess_profile)
    groups = profile["groups"]
    if inspection_group not in groups:
        inspection_group = "GENERIC" if "GENERIC" in groups else next(iter(groups))
    surface = (groups[inspection_group]["surface_mask"] > 0).astype(np.uint8)
    out = {"surface_only": surface}
    for halo in halo_values:
        if halo <= 0:
            continue
        k = 2 * int(halo) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        out[f"surface_halo_{halo}px"] = (cv2.dilate(surface, kernel) > 0).astype(np.uint8)
    out["current_master"] = (groups[inspection_group]["master_mask"] > 0).astype(np.uint8)
    return out

def roi_evidence_score(anomaly_map: np.ndarray, roi_mask: np.ndarray, top_fraction: float=.01) -> float:
    a = np.asarray(anomaly_map, dtype=np.float32)
    m = np.asarray(roi_mask) > 0
    vals = a[m]
    if not len(vals):
        return float("nan")
    k = max(1, int(round(len(vals) * float(top_fraction))))
    return float(np.partition(vals, len(vals)-k)[-k:].mean())

def compare_roi_scores(anomaly_map: np.ndarray, variants: dict[str, np.ndarray]) -> dict[str, float]:
    return {name: roi_evidence_score(anomaly_map, mask) for name, mask in variants.items()}
