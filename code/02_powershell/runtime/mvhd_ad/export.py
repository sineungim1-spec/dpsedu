from __future__ import annotations
from pathlib import Path
import json, shutil, math
import numpy as np
from .config import InferConfig, DatasetSpec, SCHEMA_VERSION, RUNTIME_VERSION
from .protocol import build_protocol, save_protocol, load_protocol
from .preprocess import build_preprocess_profile, prepare_standardized_dataset, _decode_profile
from .runners.anomalib_runner import predict_many_with_anomalib
from .localization import build_localization_profile, calibrate_localization_dual, validate_localization, validate_visible_localization, save_localization_profile
from .calibration import choose_thresholds
from .metrics import full_metrics, ranking_metrics
from .operating_window import build_operating_window, save_operating_window
from .decision_policy import save_decision_policy
from .recipe import save_inspection_recipe
from .audit import save_audit_schema
from .production_gate import save_deployment_readiness
from .deployment import save_deployment_profiles
from .drift import build_score_baseline
from .decision_engine import fit_decision_model, score_record as decision_score_record, save_decision_model
from .fusion_policy import policy_metrics, calibrate_fusion_policy


def _write(path: Path,obj: dict) -> Path:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8"); return path


def _locate_run_root(ckpt: Path, train_config_path: str|Path|None) -> Path:
    cands=[]
    if train_config_path: cands.append(Path(train_config_path).expanduser().resolve().parent)
    cands.extend([ckpt.parent,ckpt.parent.parent])
    for c in cands:
        if (c/"protocol_v6.json").exists() or (c/"preprocess_profile_v6.json").exists(): return c
    return ckpt.parent


def _ensure_prepared(run_root: Path,data_root: Path,image_size: int,train_config_path: str|Path|None) -> tuple[dict,Path]:
    prot_path=run_root/"protocol_v6.json"; pp=run_root/"preprocess_profile_v6.json"
    if prot_path.exists(): protocol=load_protocol(prot_path)
    else:
        default_view=None
        if train_config_path and Path(train_config_path).exists():
            try: default_view=json.loads(Path(train_config_path).read_text(encoding="utf-8")).get("dataset",{}).get("default_view")
            except Exception: pass
        protocol=build_protocol(DatasetSpec(root=data_root,default_view=default_view),seed=42); save_protocol(protocol,prot_path)
    # Repair stale absolute raw paths after a fresh Colab session by using relative_path.
    for r in protocol["records"]:
        if not Path(r.get("path", "")).exists():
            candidate=data_root/r["relative_path"]
            if candidate.exists(): r["path"]=str(candidate.resolve())
        if r.get("prepared_relative_path"):
            candidate=run_root/r["prepared_relative_path"]
            if candidate.exists(): r["prepared_path"]=str(candidate.resolve())
    save_protocol(protocol,prot_path)
    if not pp.exists():
        build_preprocess_profile(protocol,pp,image_size,halo_px=3)
    else:
        # V6.3 sometimes serialized `count: 0` although the actual reference arrays were
        # built from TRAIN GOOD. Repair metadata without changing those arrays, so an old
        # checkpoint is not paired with a newly generated geometric reference by accident.
        try:
            pobj=json.loads(pp.read_text(encoding="utf-8"))
            if float(pobj.get("schema_version",0)) < 6.4:
                group_counts={}
                for r in protocol["records"]:
                    if r["split"]=="train" and r["label"]=="good":
                        group_counts[r["inspection_group"]]=group_counts.get(r["inspection_group"],0)+1
                total=sum(group_counts.values())
                for name,g in pobj.get("groups",{}).items():
                    if int(g.get("count",0))<=0:
                        g["count"]=int(group_counts.get(name,total if name=="GENERIC" else 0))
                        g["metadata_count_repaired_v64"]=True
                pobj["schema_version"]=SCHEMA_VERSION
                pp.write_text(json.dumps(pobj,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception:
            pass
    missing=any(not r.get("prepared_path") or not Path(r.get("prepared_path","")).exists() for r in protocol["records"])
    if missing:
        protocol=prepare_standardized_dataset(protocol,pp,run_root); save_protocol(protocol,prot_path)
    return protocol,pp


def _records(ckpt: Path, source: list[dict], pp: Path, image_size: int, device: str, imagenet_dir: str|Path|None=None) -> list[dict]:
    paths=[Path(r["prepared_path"]) for r in source]; cfg=InferConfig(model="efficientad",checkpoint_path=ckpt,image_size=image_size,device=device)
    preds=predict_many_with_anomalib(cfg,paths,preprocess_profile_path=pp,metadata=source,paths_are_prepared=True,imagenet_dir=imagenet_dir)
    out=[]
    for src,pred in zip(source,preds):
        if pred.get("anomaly_map") is None: raise RuntimeError(f"No anomaly_map returned: {src['relative_path']}")
        out.append({**src,**pred,"prepared_path":src["prepared_path"],"inspection_group_used":pred.get("inspection_group_used") or src.get("inspection_group","GENERIC")})
    return out


def _threshold_by_group(cal: list[dict], global_obj: dict) -> dict:
    by={}
    for g in sorted({r["inspection_group_used"] for r in cal}):
        rr=[r for r in cal if r["inspection_group_used"]==g]; labels=[1 if r["label"]=="bad" else 0 for r in rr]
        if sum(labels)>=5 and len(labels)-sum(labels)>=5:
            t=choose_thresholds(labels,[r["score"] for r in rr]); by[g]={"threshold":t["threshold"],"review_low":t["review_low"],"ng_high":t["ng_high"],"calibration_binary":t["calibration_binary"],"calibration_high_confidence":t["calibration_high_confidence"],"good_n":len(labels)-sum(labels),"bad_n":sum(labels)}
    global_obj["by_group"]=by
    return global_obj


def _triage_counts(records:list[dict],th:dict)->dict:
    c={"OK":0,"REVIEW":0,"NG":0}
    for r in records:
        s=float(r["score"]); status="OK" if s<th["review_low"] else ("REVIEW" if s<th["ng_high"] else "NG");c[status]+=1
    c["n"]=len(records);return c


def _company_alignment(protocol:dict)->dict:
    views=sorted(set(protocol["coverage"]["train"]["views"]+protocol["coverage"]["calibration"]["views"]+protocol["coverage"]["final_test"]["views"])); cams=sorted(set(protocol["coverage"]["train"]["cameras"]+protocol["coverage"]["calibration"]["cameras"]+protocol["coverage"]["final_test"]["cameras"]))
    not_claimed=["Physical lux/mm/angle operating limits are not inferred from images; they require on-line sweep commissioning.","Pixel-level defect correctness is not claimed without human GT defect masks.","OpenVINO/ONNX export is a deployment extension; the Colab teaching bundle remains checkpoint-compatible."]
    if views==["UNKNOWN"]: not_claimed.insert(0,"No view labels were recoverable from the supplied filenames/metadata; missing views are not fabricated.")
    if cams==["GENERIC"]: not_claimed.insert(0,"No camera labels were recoverable from the supplied filenames/metadata; CAM identities are not fabricated.")
    return {"schema_version":SCHEMA_VERSION,"implemented":["CAM/View-aware naming and ROI architecture when metadata is present","remove unnecessary illuminated background while preserving crop buffer","EfficientAD normal-pattern training and ImageNet/Imagenette auxiliary path via Anomalib","optional human defect masks for true pixel/lesion localization validation","boundary inspection halo for burr/edge defects","separate image decision score and pixel/localization thresholds","fixed-scale Original/Heatmap/Overlay/Contour semantics","capture-group leakage-free TRAIN/CALIBRATION/FINAL TEST protocol","V6.4 inference checkpoint callback conflict fix and ImageVisualizer OFF","V6.7 calibration-selected score recipe","V6.7 ACTION/SAFETY localization fusion"],"observed_cameras":cams,"observed_views":views,"not_claimed":not_claimed,"company_reference_metrics_note":"Company reference metrics are never copied; only measured V6.7 STEP8 results are reported."}


def export_artifacts_from_ckpt(ckpt_path: str|Path,data_root: str|Path,image_size: int=256,device: str="cuda",train_config_path: str|Path|None=None) -> Path:
    ckpt=Path(ckpt_path).expanduser().resolve(); data_root=Path(data_root).expanduser().resolve()
    if not ckpt.exists(): raise FileNotFoundError(str(ckpt))
    run_root=_locate_run_root(ckpt,train_config_path); art=run_root/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    protocol,pp=_ensure_prepared(run_root,data_root,image_size,train_config_path)
    train_src=[r for r in protocol["records"] if r["split"]=="train"]; cal_src=[r for r in protocol["records"] if r["split"]=="calibration"]; final_src=[r for r in protocol["records"] if r["split"]=="final_test"]
    imagenet_dir=None; train_cfg={}
    if train_config_path and Path(train_config_path).exists():
        train_cfg=json.loads(Path(train_config_path).read_text(encoding="utf-8")); imagenet_dir=train_cfg.get("efficientad_imagenet_dir")
    print("[V6.9-PF1 STEP8] Bulk predict with visualizer OFF and checkpointing-compatible Engine ...")
    train=_records(ckpt,train_src,pp,image_size,device,imagenet_dir); cal=_records(ckpt,cal_src,pp,image_size,device,imagenet_dir); final=_records(ckpt,final_src,pp,image_size,device,imagenet_dir)
    print("[V6.9-PF1] Building GOOD spatial baseline ...")
    loc=build_localization_profile(train,pp)
    print("[V6.9-PF1] Fitting calibration-only decision head with 5-fold OOF model selection ...")
    decision_model=fit_decision_model(cal,loc)
    for r in train+cal+final:
        r["score"]=decision_score_record(r,loc,decision_model)
    cal_labels=[1 if r["label"]=="bad" else 0 for r in cal]; final_labels=[1 if r["label"]=="bad" else 0 for r in final]
    band=decision_model["calibration_operating_band"]
    threshold={"schema_version":SCHEMA_VERSION,"threshold":float(band["review_low"]),"review_low":float(band["review_low"]),"ng_high":float(band["ng_high"]),
               "method":"V6.8 calibration score band: minimize REVIEW subject to BAD->OK<=1 and GOOD->NG<=1",
               "calibration_policy":band,"final_test_not_used_for_threshold":True,"decision_model":"decision_model.json",
               "score_definition":"V6.9-PF1 calibration-supervised decision score (EfficientAD spatial features)",
               "production_triage":"score < review_low => OK; review_low <= score < ng_high => REVIEW; score >= ng_high => NG. Localization explains the decision; PF1 safety may only hold a calibrated borderline OK for REVIEW and never downgrades NG."}

    print("[V6.9-PF1] Calibrating dual ACTION/SAFETY localization on CALIBRATION only ...")
    action_th,safety_th,cal_diag=calibrate_localization_dual(cal,loc)
    display_cfg=cal_diag["display_fallback"]
    loc["thresholds_global"]=action_th; loc["thresholds_action"]=action_th; loc["thresholds_safety"]=safety_th; loc["display_fallback"]=display_cfg
    locval=validate_localization(final,loc,action_th); cal_locval=validate_localization(cal,loc,action_th)
    visible_final=validate_visible_localization(final,loc,action_th,display_cfg); visible_cal=validate_visible_localization(cal,loc,action_th,display_cfg)
    safety_final=validate_localization(final,loc,safety_th); safety_cal=validate_localization(cal,loc,safety_th)
    locval["ground_truth_masks_found_calibration"]=cal_locval["labeled_bad_images"]; locval["ground_truth_masks_found_final_test"]=locval["labeled_bad_images"]
    locval["calibration_diagnostics"]={"action_thresholds":action_th,"safety_thresholds":safety_th,"display_fallback":display_cfg,"action_calibration":cal_locval,"visible_calibration":visible_cal,"safety_calibration":safety_cal,"grid_diagnostics":cal_diag}
    locval["visible_candidate_final_test"]=visible_final
    locval["safety_candidate_final_test"]={k:v for k,v in safety_final.items() if k not in {"pixel_precision","pixel_recall","pixel_f1","pixel_iou"}}
    loc["validation"]=locval

    print("[V6.9-PF1] Calibrating score-first monotonic line policy on CALIBRATION only ...")
    fusion_cfg=calibrate_fusion_policy(
        cal,loc,action_th,safety_th,display_cfg,threshold=threshold,
        max_bad_ok=1,max_good_ng=1
    )

    cal_metrics=full_metrics(cal_labels,[r["score"] for r in cal],threshold["threshold"]); final_metrics=full_metrics(final_labels,[r["score"] for r in final],threshold["threshold"])
    cal_metrics["triage_counts"]=_triage_counts(cal,threshold); final_metrics["triage_counts"]=_triage_counts(final,threshold)
    final_high=full_metrics(final_labels,[r["score"] for r in final],threshold["ng_high"])
    cal_policy=policy_metrics(cal,loc,threshold,action_th,safety_th,display_cfg,fusion_cfg); final_policy=policy_metrics(final,loc,threshold,action_th,safety_th,display_cfg,fusion_cfg)
    line_policy={"schema_version":SCHEMA_VERSION,"calibration":cal_policy,"final_test":final_policy,"final_test_not_used_for_policy_selection":True}
    metrics={"schema_version":SCHEMA_VERSION,"score_definition":threshold["score_definition"],"score_recipe":"V69_PF1_DECISION_HEAD","calibration":cal_metrics,"final_test":final_metrics,"final_test_high_confidence_ng":final_high,"line_policy_final_test":final_policy,"localization_validation":locval,"production_ready":False}
    dataset={"schema_version":SCHEMA_VERSION,"counts":protocol["counts"],"coverage":protocol["coverage"],"leakage_check":protocol["leakage_check"],"ground_truth_masks_calibration":cal_locval["labeled_bad_images"],"ground_truth_masks_final_test":locval["labeled_bad_images"]}
    op=build_operating_window(train)
    image_gate={"final_test_fn_zero":final_metrics["fn"]==0,"final_test_bad_recall_ge_0_98":final_metrics["recall"]>=.98,"final_test_good_specificity_ge_0_90":final_metrics["specificity"]>=.90,"final_test_auroc_ge_0_95":final_metrics["image_AUROC"] is not None and final_metrics["image_AUROC"]>=.95}
    data_gate={"capture_group_leakage_zero":protocol["leakage_check"]["capture_group_leakage_count"]==0,"mixed_view_label_groups_isolated_from_train":protocol["leakage_check"]["mixed_view_label_groups_isolated_from_train"],"final_test_good_ge_20":protocol["counts"]["final_test_good"]>=20,"final_test_bad_ge_20":protocol["counts"]["final_test_bad"]>=20}
    localization_gate={"final_test_gt_masks_ge_20":locval["labeled_bad_images"]>=20,"good_visible_red_fp_le_1":visible_final["good_visible_fp"]<=1,"lesion_hit_recall_ge_0_98":locval["lesion_hit_recall"] is not None and locval["lesion_hit_recall"]>=.98,"pixel_recall_ge_0_90":locval["pixel_recall"] is not None and locval["pixel_recall"]>=.90,"pixel_f1_ge_0_50":locval["pixel_f1"] is not None and locval["pixel_f1"]>=.50}
    line_policy_gate={"final_bad_auto_pass_le_1":final_policy["bad_auto_pass_escape"]<=1,"final_good_auto_reject_le_1":final_policy["good_auto_reject"]<=1,"final_review_rate_le_0_40":final_policy["review_rate"]<=.40}
    production_ready=all(image_gate.values()) and all(data_gate.values()) and all(localization_gate.values()) and all(line_policy_gate.values())
    metrics["production_ready"]=production_ready
    prod={"schema_version":SCHEMA_VERSION,"runtime_version":RUNTIME_VERSION,"production_ready":production_ready,"image_gate":image_gate,"line_policy_gate":line_policy_gate,"data_gate":data_gate,"localization_gate":localization_gate,"decision_model":decision_model,"fusion_policy":fusion_cfg,"final_test_metrics":final_metrics,"final_test_high_confidence_ng":final_high,"line_policy_validation":line_policy,"localization_validation":locval,"note":"Decision-head hyperparameters and score operating band were selected on Calibration only. PF1 keeps score as the primary monotonic triage; localization is explanatory and safety is a limited OK-to-REVIEW fail-safe. Final Test remained locked."}
    # write artifacts
    shutil.copy2(run_root/"protocol_v6.json",art/"protocol_v6.json"); shutil.copy2(pp,art/"preprocess_profile_v6.json")
    save_localization_profile(loc,art/"localization_profile_v6.json")
    _write(art/"threshold.json",threshold); _write(art/"fusion_policy.json",fusion_cfg); save_decision_model(decision_model,art/"decision_model.json"); _write(art/"score_recipe.json",{"schema_version":SCHEMA_VERSION,"selected_recipe":"V69_PF1_DECISION_HEAD","decision_model":"decision_model.json","selection_data":"CALIBRATION_ONLY","final_test_used_for_selection":False}); _write(art/"line_policy_validation.json",line_policy); _write(art/"metrics.json",metrics); _write(art/"dataset.json",dataset); _write(art/"localization_validation.json",locval); _write(art/"production_validation.json",prod)
    _write(art/"config.json",{"schema_version":SCHEMA_VERSION,"runtime_version":RUNTIME_VERSION,"model":"efficientad","image_size":image_size,"train_good_only":True,"preprocess_version":"automotive_production_v6_9_pf1_scorefirst","train_config":train_cfg})
    groups=protocol["coverage"]["train"]["inspection_groups"]
    _write(art/"preprocess.json",{"version":SCHEMA_VERSION,"profile_file":"preprocess_profile_v6.json","operating_window_file":"operating_window.json","inspection_groups":groups,"company_roi_reference":"company POC: unnecessary illuminated background removal + buffer space; view/CAM ROI policy","inspection_mask":"stable GOOD surface plus narrow boundary halo; far background and stable openings excluded","note":"CAM/View groups are only created when recoverable metadata exists."})
    _write(art/"visualization.json",{"version":SCHEMA_VERSION,"profile_file":"localization_profile_v6.json","original_role":"INPUT validation: verify focus/lighting/framing before trusting AI","heatmap":"MODEL VIEW: fixed cross-image support evidence; auto-OK is color-capped to avoid false alarm red; never per-image min-max","overlay":"FINAL UI: OK=no red; REVIEW/NG=red model-evidence region; no label-dependent painting","contour":"FINAL UI: red contour marks model evidence for a non-OK decision; actual GOOD/BAD label never affects inference","ground_truth_status":locval["status"]})
    # V6.7 canonical artifacts: stable names are preferred by downstream 2~5차시 tools.
    save_operating_window(op,art/"operating_window.json")
    _write(art/"company_alignment.json",_company_alignment(protocol))

    # Legacy aliases retained only for old V6.x notebooks.
    shutil.copy2(run_root/"protocol_v6.json",art/"protocol.json")
    shutil.copy2(art/"preprocess_profile_v6.json",art/"preprocess_profile.json")
    shutil.copy2(art/"localization_profile_v6.json",art/"localization_profile.json")
    shutil.copy2(art/"operating_window.json",art/"operating_window_v67.json")
    shutil.copy2(art/"company_alignment.json",art/"company_poc_alignment_v67.json")

    # Company-line operational artifacts.
    save_decision_policy(art/"decision_policy.json", threshold)
    save_inspection_recipe(art/"inspection_recipe.json", art)
    save_audit_schema(art/"audit_schema.json")
    save_deployment_profiles(art/"deployment_profiles.json")

    train_good_scores=[float(r["score"]) for r in train if r["label"]=="good"]
    cal_good_scores=[float(r["score"]) for r in cal if r["label"]=="good"]
    _write(art/"score_baseline.json",build_score_baseline(train_good_scores,cal_good_scores))

    save_deployment_readiness(art/"deployment_validation.json",art)

    print("[V6.9-PF1] Artifacts exported:",art)
    print("[V6.9-PF1] Autonomous production ready:",production_ready)
    return art
