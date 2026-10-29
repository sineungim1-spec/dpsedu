from __future__ import annotations
from pathlib import Path
import hashlib, json, shutil, zipfile, tempfile
from .config import SCHEMA_VERSION, RUNTIME_VERSION
from .artifact_paths import resolve_artifact
from .production_gate import evaluate_deployment_readiness

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

def _write(p: Path, obj) -> None:
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def package_company_master_bundle(ckpt_path: str | Path, artifacts_dir: str | Path,
                                  output_zip: str | Path,
                                  package_name: str="car_EfficientAD_CompanyLine_Master") -> Path:
    ckpt = Path(ckpt_path).resolve()
    art = Path(artifacts_dir).resolve()
    out = Path(output_zip).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    approval = evaluate_deployment_readiness(art)
    threshold = json.loads(resolve_artifact(art, "threshold").read_text(encoding="utf-8"))
    dataset = json.loads(resolve_artifact(art, "dataset").read_text(encoding="utf-8"))
    metrics = json.loads(resolve_artifact(art, "metrics").read_text(encoding="utf-8"))
    score_recipe = json.loads(resolve_artifact(art, "score_recipe").read_text(encoding="utf-8"))
    line_policy = json.loads(resolve_artifact(art, "line_policy_validation").read_text(encoding="utf-8"))
    cfg = json.loads((art/"config.json").read_text(encoding="utf-8"))
    model_hash = _sha256(ckpt)

    with tempfile.TemporaryDirectory(prefix="company_line_") as td:
        root = Path(td) / package_name
        root.mkdir(parents=True)
        shutil.copy2(ckpt, root/"model.ckpt")
        shutil.copytree(art, root/"artifacts")

        info = {
            "bundle_schema_version": SCHEMA_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "bundle_role": "COMPANY_LINE_MASTER_REFERENCE",
            "model": "EfficientAD-S",
            "model_sha256": model_hash,
            "image_size": 256,
            "epochs": (cfg.get("train_config") or {}).get("max_epochs"),
            "counts": dataset.get("counts"),
            "review_low": threshold["review_low"],
            "ng_high": threshold["ng_high"],
            "line_assist_ready": approval["line_assist_ready"],
            "autonomous_reject_ready": approval["autonomous_reject_ready"],
            "recommended_mode": approval["recommended_mode"],
            "final_test": metrics.get("final_test"),
            "score_recipe": score_recipe.get("selected_recipe"),
            "line_policy_final_test": line_policy.get("final_test"),
            "truthfulness": "Package architecture is company-line oriented. Actual use by a named company is an external fact and is not asserted by this file.",
        }
        _write(root/"model_info.json", info)

        _write(root/"MODEL_CARD.md", f"""# V6.7 Company-Line DecisionFusion Model Card

Runtime: {RUNTIME_VERSION}
Model: EfficientAD-S
SHA256: {model_hash}

## Operating concept
Input Guard -> Alignment -> Surface ROI + Boundary Halo -> EfficientAD ->
Calibration-only Decision Head -> constrained OK/REVIEW/NG band -> visible/safety evidence gate -> Operator confirmation as required -> Audit Log.

## Deployment status
- Line assist ready: {approval['line_assist_ready']}
- Autonomous reject ready: {approval['autonomous_reject_ready']}
- Recommended mode: {approval['recommended_mode']}

Final Test is not used to choose the threshold.

Heatmap/Contour is defect-candidate evidence unless GT-mask localization validation has passed.
""")

        _write(root/"LINE_OPERATION_SOP.md", """# Line Operation SOP

1. Verify model hash / recipe / camera condition.
2. Run Input Guard first.
3. If REVIEW_INPUT: correct acquisition before trusting defect decision.
4. Run OK/REVIEW/NG triage.
5. REVIEW is always held for operator review.
6. NG is automatic reject only when deployment_validation says autonomous_reject_ready=true.
7. Save audit log.
8. Do not change model.ckpt / threshold / ROI profiles independently.
9. New version => new model hash + recipe + validation.
10. Final Test must never be used for threshold tuning.
""")

        _write(root/"DEPLOYMENT_STATUS.json", approval)

        files=[]
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files.append({"path":str(p.relative_to(root)),"bytes":p.stat().st_size,"sha256":_sha256(p)})
        _write(root/"build_manifest.json", {"schema_version":SCHEMA_VERSION,"runtime_version":RUNTIME_VERSION,"files":files})

        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob("*"):
                if p.is_file():
                    z.write(p, Path(root.name)/p.relative_to(root))
    return out

# Backward-compatible API. It now creates the company-line master structure.
def package_model_bundle(ckpt_path: str | Path, artifacts_dir: str | Path, output_zip: str | Path) -> Path:
    return package_company_master_bundle(ckpt_path, artifacts_dir, output_zip)
