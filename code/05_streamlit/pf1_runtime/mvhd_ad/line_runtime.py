from __future__ import annotations
from pathlib import Path
from .infer import infer_image
from .input_guard import evaluate_input_guard
from .production_gate import evaluate_deployment_readiness
from .audit import append_audit, sha256_file
from .config import RUNTIME_VERSION


def run_line_inspection(runtime_root: str | Path, image_path: str | Path, output_dir: str | Path, device: str="cpu", deployment_mode: str="HUMAN_IN_THE_LOOP", audit_log: str | Path | None=None, line_id: str="LINE-01", station_id: str="VISION-01", lot_id: str="", product_id: str="", operator_id: str="", operator_final_decision: str | None=None) -> dict:
    root=Path(runtime_root).resolve(); art=root/"artifacts"; approval=evaluate_deployment_readiness(art)
    guard=evaluate_input_guard(image_path,art); pred=infer_image(root,image_path,output_dir,device=device,actual="UNKNOWN")
    triage=pred["production_triage"]; auto_allowed=bool(approval.get("autonomous_reject_ready",False) and deployment_mode.upper()=="AUTONOMOUS_REJECT")
    if guard["status"]=="REVIEW_INPUT": action="REVIEW_INPUT_BEFORE_DEFECT_DECISION"; operator=True
    elif triage=="OK": action="PASS_CANDIDATE"; operator=not auto_allowed
    elif triage=="REVIEW": action="HOLD_FOR_REVIEW"; operator=True
    else: action="AUTO_REJECT" if auto_allowed else "REJECT_CANDIDATE_OPERATOR_CONFIRM"; operator=not auto_allowed
    result={**pred,"runtime_version":RUNTIME_VERSION,"input_guard":guard,"deployment":approval,"line_action":action,"operator_confirmation_required":operator,"autonomous_reject_allowed":auto_allowed,"truth":{"heatmap_contour":"candidate evidence unless GT localization validation passes","specific_company_deployment":"not asserted by runtime itself"}}
    if audit_log:
        ckpt=root/"model.ckpt"; ckpt=ckpt if ckpt.exists() else root/"model"/"model.ckpt"
        append_audit(audit_log,{"line_id":line_id,"station_id":station_id,"lot_id":lot_id,"product_id":product_id,"camera_view_group":pred.get("camera_view_group"),"model_version":RUNTIME_VERSION,"model_sha256":sha256_file(ckpt) if ckpt.exists() else None,"recipe_id":"V69_PF1_SCORE_FIRST","input_guard_status":guard["status"],"alignment_score":pred.get("alignment_score"),"anomaly_score":pred.get("score"),"review_low":pred.get("review_low"),"ng_high":pred.get("ng_high"),"ai_triage":triage,"line_action":action,"operator_final_decision":operator_final_decision,"operator_id":operator_id,"image_path":str(Path(image_path).resolve()),"heatmap_path":str(Path(output_dir)/"02_heatmap.png"),"contour_path":str(Path(output_dir)/"04_contour.png")})
    return result
