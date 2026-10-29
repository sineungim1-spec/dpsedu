from __future__ import annotations
from pathlib import Path
import json
from .artifact_paths import resolve_artifact
from .config import SCHEMA_VERSION

def evaluate_deployment_readiness(artifacts_dir: str | Path) -> dict:
    art = Path(artifacts_dir)
    prod = json.loads(resolve_artifact(art, "production_validation").read_text(encoding="utf-8"))
    metrics = json.loads(resolve_artifact(art, "metrics").read_text(encoding="utf-8"))
    dataset = json.loads(resolve_artifact(art, "dataset").read_text(encoding="utf-8"))

    required = [
        "threshold.json",
        "metrics.json",
        "dataset.json",
        "production_validation.json",
    ]
    required_keys = ["preprocess_profile", "localization_profile", "operating_window", "score_recipe", "line_policy_validation", "decision_model"]

    files_ok = all((art / x).exists() for x in required) and all(
        resolve_artifact(art, k, required=False) is not None for k in required_keys
    )

    data_gate = prod.get("data_gate", {})
    data_ok = bool(data_gate) and all(bool(v) for v in data_gate.values())
    final_metrics = prod.get("final_test_metrics") or metrics.get("final_test", {})
    loc = prod.get("localization_validation", {})

    line_assist_ready = bool(files_ok and data_ok and final_metrics)
    autonomous_reject_ready = bool(prod.get("production_ready", False))
    localization_claim_ready = bool(
        (loc.get("labeled_bad_images") or 0) >= 20
        and loc.get("pixel_recall") is not None
        and loc.get("pixel_f1") is not None
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "line_assist_ready": line_assist_ready,
        "autonomous_reject_ready": autonomous_reject_ready,
        "localization_claim_ready": localization_claim_ready,
        "recommended_mode": "AUTONOMOUS_REJECT" if autonomous_reject_ready else "HUMAN_IN_THE_LOOP",
        "line_policy_target_met": bool((prod.get("line_policy_gate") or {}).get("final_bad_auto_pass_le_1",False) and (prod.get("line_policy_gate") or {}).get("final_good_auto_reject_le_1",False)),
        "final_test": final_metrics,
        "line_policy_gate": prod.get("line_policy_gate", {}),
        "line_policy_final_test": (prod.get("line_policy_validation") or {}).get("final_test"),
        "data_gate": data_gate,
        "localization_status": loc.get("status"),
        "rules": {
            "line_assist_ready": "artifacts complete + leakage/data gate passed + final-test metrics exist",
            "autonomous_reject_ready": "strict production_validation gate passed",
            "localization_claim_ready": "sufficient human GT masks and pixel metrics exist",
        },
        "truthfulness": "Runtime architecture can be production-line oriented; actual deployment/use by a specific company requires external evidence.",
    }

def save_deployment_readiness(path: str | Path, artifacts_dir: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(evaluate_deployment_readiness(artifacts_dir), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
