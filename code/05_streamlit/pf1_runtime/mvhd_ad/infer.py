from __future__ import annotations
from pathlib import Path
import argparse,json
import numpy as np
from PIL import Image
from .config import InferConfig
from .artifact_paths import resolve_artifact
from .preprocess import standardize_image
from .localization import decode_localization_profile,make_views,candidate_present,display_candidate_present
from .decision_engine import score_image as decision_score_image
from .fusion_policy import raw_triage,fuse_triage
from .runners.anomalib_runner import predict_many_with_anomalib

def infer_image(runtime_root: str|Path,image_path: str|Path,output_dir: str|Path,device: str="cpu",actual: str="UNKNOWN") -> dict:
    root=Path(runtime_root).expanduser().resolve(); art=root/'artifacts'; ckpt=root/'model'/'model.ckpt'
    if not ckpt.exists(): ckpt=root/'model.ckpt'
    pp=resolve_artifact(art,'preprocess_profile'); lp_path=resolve_artifact(art,'localization_profile')
    th=json.loads(resolve_artifact(art,'threshold').read_text(encoding='utf-8')); dm=json.loads(resolve_artifact(art,'decision_model').read_text(encoding='utf-8')); fp_path=art/'fusion_policy.json'; fusion_cfg=json.loads(fp_path.read_text(encoding='utf-8')) if fp_path.exists() else None; lp=decode_localization_profile(lp_path)
    s=standardize_image(image_path,pp,'GENERIC'); out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    prepared=out/'00_standardized_input.png'; Image.fromarray(s.rgb).save(prepared,optimize=False)
    cfg=InferConfig(model='efficientad',checkpoint_path=ckpt,image_size=256,device=device)
    pred=predict_many_with_anomalib(cfg,[prepared],paths_are_prepared=True,metadata=[{'inspection_group':s.inspection_group,'alignment_score_prepared':s.alignment_score}])[0]
    g=lp['groups'].get(s.inspection_group) or lp['groups'].get('GENERIC') or next(iter(lp['groups'].values()))
    score=decision_score_image(pred['anomaly_map'],s.rgb,g,dm)
    raw=raw_triage(score,th)
    action_th=lp.get('thresholds_action') or lp.get('thresholds_global'); safety_th=lp.get('thresholds_safety') or action_th; display_cfg=lp.get('display_fallback',{})
    action=candidate_present(pred['anomaly_map'],s.rgb,g,action_th); display=display_candidate_present(pred['anomaly_map'],s.rgb,g,display_cfg) if display_cfg else False
    visible=bool(action or display); safety=candidate_present(pred['anomaly_map'],s.rgb,g,safety_th)
    fused,reason=fuse_triage(raw,visible,safety,score=score,fusion_policy=fusion_cfg)
    binary='NG' if score>=float(th['review_low']) else 'OK'
    views=make_views(s.rgb,pred['anomaly_map'],g,action_th,fused,out,display_cfg=display_cfg,safety_th=safety_th)
    result={'image':Path(image_path).name,'actual':actual,'score':score,'score_recipe':'V69_DECISION_HEAD','score_is_probability':True,
            'threshold':float(th['review_low']),'review_low':float(th['review_low']),'ng_high':float(th['ng_high']),
            'binary_decision':binary,'score_triage':raw,'production_triage':fused,'fusion_reason':reason,
            'action_candidate_present':bool(action),'display_fallback_present':bool(display),'visible_candidate_present':visible,'safety_candidate_present':bool(safety),
            'camera_view_group':s.inspection_group,'alignment_score':s.alignment_score,**views,
            'localization_status':'CANDIDATE_ONLY' if lp.get('validation',{}).get('labeled_bad_images',0)==0 else 'GT_CALIBRATED',
            'rule':'V6.9 FinalCandidate: OK=no red; REVIEW/NG=red model-evidence marker/region in Heatmap/Overlay/Contour; actual GOOD/BAD label never affects inference'}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--runtime-root',required=True); ap.add_argument('--image',required=True); ap.add_argument('--output',default='outputs/latest'); ap.add_argument('--device',default='cpu'); ap.add_argument('--actual',default='UNKNOWN'); a=ap.parse_args(); print(json.dumps(infer_image(a.runtime_root,a.image,a.output,a.device,a.actual),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
