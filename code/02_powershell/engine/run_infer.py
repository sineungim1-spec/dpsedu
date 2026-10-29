from __future__ import annotations
import argparse, json, sys, hashlib, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "runtime"))
from mvhd_ad.line_runtime import run_line_inspection

EXPECTED_MODEL_SHA256 = "736266a37af3c16c0b3445a0505977851592b6fe5103ca4e744d146179ae6bc0"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--actual", default="UNKNOWN")
    ap.add_argument("--output-name", default="latest")
    args = ap.parse_args()

    model_path = ROOT / "model" / "model.ckpt"
    if sha256_file(model_path) != EXPECTED_MODEL_SHA256:
        raise SystemExit("MODEL SHA256 mismatch: Candidate4 E07-S model.ckpt is not intact.")

    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = (ROOT / image_path).resolve()
    out_dir = ROOT / "outputs" / args.output_name

    print("[1/4] Loading Candidate4 E07-S company-style EfficientAD MASTER ...")
    start = time.time()
    result = run_line_inspection(
        ROOT,
        image_path,
        out_dir,
        device="cpu",
        deployment_mode="HUMAN_IN_THE_LOOP",
        audit_log=out_dir / "audit.jsonl",
    )
    elapsed = time.time() - start

    # Keep the original Session-02 console style while exposing the Candidate4 3-zone policy.
    summary = {
        "image": image_path.name,
        "actual": args.actual,
        "score": result.get("score"),
        "review_low": result.get("review_low"),
        "ng_high": result.get("ng_high"),
        "decision": result.get("production_triage"),
        "score_triage": result.get("score_triage"),
        "fusion_reason": result.get("fusion_reason"),
        "input_guard": (result.get("input_guard") or {}).get("status"),
        "line_action": result.get("line_action"),
        "operator_confirmation_required": result.get("operator_confirmation_required"),
        "model": "Candidate4 E07-S / EfficientAD-S",
        "model_sha256": EXPECTED_MODEL_SHA256,
        "elapsed_sec": elapsed,
        "rule": "score < review_low => OK; review_low <= score < ng_high => REVIEW; score >= ng_high => NG",
    }
    (out_dir / "session02_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("[2/4] Applying Input Guard + ROI/alignment + EfficientAD inference ... done")
    print("[3/4] Applying Candidate4 E07-S ScoreFirst OK/REVIEW/NG policy ... done")
    print("[4/4] Saving Original / Heatmap / Overlay / Contour ... done")
    print()
    print("Image      :", image_path.name)
    print("Actual     :", args.actual)
    print(f"Score      : {float(result['score']):.6f}")
    print(f"Review Low : {float(result['review_low']):.6f}")
    print(f"NG High    : {float(result['ng_high']):.6f}")
    print("Decision   :", result.get("production_triage"))
    print("Reason     :", result.get("fusion_reason"))
    print("InputGuard :", (result.get("input_guard") or {}).get("status"))
    print("Line Action:", result.get("line_action"))
    print(f"Elapsed    : {elapsed:.2f} sec")
    print("Outputs    :", out_dir)
    print()
    print("NOTE: Score is not a defect probability.")
    print("NOTE: Candidate4 E07-S uses a 3-zone OK/REVIEW/NG policy, not the old single-threshold demo.")
    print("NOTE: HUMAN_IN_THE_LOOP mode is used; REVIEW/NG require operator confirmation in this training package.")

if __name__ == "__main__":
    main()
