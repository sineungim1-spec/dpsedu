from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json

@dataclass
class DecisionResult:
    score: float
    triage: str
    binary_decision: str
    line_action: str
    operator_confirmation_required: bool
    autonomous_reject_allowed: bool

def triage_score(score: float, threshold_obj: dict) -> str:
    low = float(threshold_obj["review_low"])
    high = float(threshold_obj["ng_high"])
    if score < low:
        return "OK"
    if score < high:
        return "REVIEW"
    return "NG"

def decide(score: float, threshold_obj: dict, deployment_approval: dict | None=None,
           deployment_mode: str="HUMAN_IN_THE_LOOP") -> DecisionResult:
    triage = triage_score(float(score), threshold_obj)
    binary_threshold = float(threshold_obj.get("threshold", threshold_obj["review_low"]))
    binary = "NG" if float(score) >= binary_threshold else "OK"

    autonomous_ready = bool((deployment_approval or {}).get("autonomous_reject_ready", False))
    autonomous_requested = deployment_mode.upper() == "AUTONOMOUS_REJECT"
    autonomous_allowed = autonomous_ready and autonomous_requested

    if triage == "OK":
        action = "PASS_CANDIDATE"
        operator_required = not autonomous_allowed
    elif triage == "REVIEW":
        action = "HOLD_FOR_REVIEW"
        operator_required = True
    else:
        action = "AUTO_REJECT" if autonomous_allowed else "REJECT_CANDIDATE_OPERATOR_CONFIRM"
        operator_required = not autonomous_allowed

    return DecisionResult(
        score=float(score),
        triage=triage,
        binary_decision=binary,
        line_action=action,
        operator_confirmation_required=operator_required,
        autonomous_reject_allowed=autonomous_allowed,
    )

def save_decision_policy(path: str | Path, threshold_obj: dict) -> Path:
    p = Path(path)
    obj = {
        "schema_version": 6.7,
        "policy": "three_zone_company_line_triage",
        "review_low": float(threshold_obj["review_low"]),
        "ng_high": float(threshold_obj["ng_high"]),
        "binary_threshold": float(threshold_obj.get("threshold", threshold_obj["review_low"])),
        "zones": {
            "OK": "score < review_low",
            "REVIEW": "review_low <= score < ng_high",
            "NG": "score >= ng_high",
        },
        "deployment_rule": {
            "HUMAN_IN_THE_LOOP": "OK/REVIEW/NG are AI candidates; operator confirms REVIEW and NG.",
            "AUTONOMOUS_REJECT": "Allowed only when autonomous_reject_ready=true in deployment_validation.json.",
        },
        "final_test_not_used_for_threshold": bool(threshold_obj.get("final_test_not_used_for_threshold", True)),
    }
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
