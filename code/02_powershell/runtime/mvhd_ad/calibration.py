from __future__ import annotations
import numpy as np
from .metrics import binary_metrics
from .config import SCHEMA_VERSION


def _candidate_thresholds(scores) -> list[float]:
    s=np.asarray(scores,dtype=float); u=np.unique(s[np.isfinite(s)])
    if not len(u): return [0.0]
    eps=max(1e-9,float(np.ptp(u))*1e-9)
    return [float(u[0]-eps), *map(float,u), float(u[-1]+eps)]


def choose_thresholds(labels, scores, target_recall: float=0.98, target_specificity: float=0.95) -> dict:
    """Calibration-only thresholding.

    V6.7 deliberately removes the old absolute FN=0-first rule. With 64 BAD calibration
    images, recall >= .98 allows at most one miss and lets the threshold move upward when
    that materially reduces GOOD false alarms. Final Test is never touched here.
    """
    labels=np.asarray(labels,dtype=np.int8); scores=np.asarray(scores,dtype=float)
    cands=[]
    for t in _candidate_thresholds(scores):
        m=binary_metrics(labels,scores,t); cands.append((t,m))

    safe=[x for x in cands if x[1]["recall"]>=target_recall]
    if safe:
        low=max(safe,key=lambda x:(x[1]["specificity"],x[1]["f1"],x[1]["recall"],x[0]))
        method="recall_ge_0.98_then_max_specificity_on_calibration_only"
    else:
        low=max(cands,key=lambda x:(x[1]["recall"],x[1]["specificity"],x[1]["f1"],x[0]))
        method="max_recall_then_specificity_on_calibration_only"

    high=[x for x in cands if x[1]["specificity"]>=target_specificity]
    if high:
        high_pick=max(high,key=lambda x:(x[1]["recall"],x[1]["f1"],x[1]["precision"],x[0]))
        high_method="specificity_ge_0.95_then_max_recall"
    else:
        high_pick=max(cands,key=lambda x:(x[1]["specificity"],x[1]["recall"],x[1]["f1"],x[0]))
        high_method="max_specificity_then_recall"

    review_low=float(low[0]); ng_high=float(max(review_low,high_pick[0]))
    high_metrics=binary_metrics(labels,scores,ng_high)
    return {
        "schema_version":SCHEMA_VERSION,
        "threshold":review_low,
        "rule":"score >= threshold => NG (legacy binary view only; company line uses fused OK/REVIEW/NG)",
        "method":method,
        "target_recall":float(target_recall),
        "review_low":review_low,
        "ng_high":ng_high,
        "ng_high_method":high_method,
        "target_specificity_high":float(target_specificity),
        "calibration_binary":binary_metrics(labels,scores,review_low),
        "calibration_high_confidence":high_metrics,
        "production_triage":"score < review_low => raw OK; review_low <= score < ng_high => raw REVIEW; score >= ng_high => raw NG; V6.7 fusion may promote/downgrade to REVIEW using localized evidence",
        "final_test_not_used_for_threshold":True,
        "score_definition":"V6.7 calibration-selected spatial evidence recipe",
    }


def triage(score: float, threshold_obj: dict) -> str:
    if score < float(threshold_obj["review_low"]): return "OK"
    if score < float(threshold_obj["ng_high"]): return "REVIEW"
    return "NG"
