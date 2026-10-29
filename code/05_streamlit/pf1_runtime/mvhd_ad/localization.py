from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import itertools, json
import cv2
import numpy as np
from PIL import Image
from .array_codec import encode_array, decode_array
from .config import SCHEMA_VERSION


def _gray(rgb): return cv2.cvtColor(np.asarray(rgb,dtype=np.uint8),cv2.COLOR_RGB2GRAY).astype(np.float32)/255.

def residual_map(gray: np.ndarray, ref: np.ndarray) -> np.ndarray:
    g=cv2.GaussianBlur(gray,(0,0),.8); r=cv2.GaussianBlur(ref.astype(np.float32),(0,0),.8)
    inten=np.abs(g-r); eg=cv2.Laplacian(g,cv2.CV_32F,ksize=3); er=cv2.Laplacian(r,cv2.CV_32F,ksize=3); e=np.abs(eg-er)
    scale=max(float(np.quantile(e,.995)),1e-6); e=np.clip(e/scale,0,1)
    return np.clip(inten+.08*e,0,1)


def _robust_stack(stack: np.ndarray, floor: float) -> tuple[np.ndarray,np.ndarray]:
    med=np.median(stack,axis=0).astype(np.float32); mad=np.median(np.abs(stack-med[None,...]),axis=0).astype(np.float32)
    scale=np.maximum(1.4826*mad,float(floor)).astype(np.float32)
    return med,scale


def build_localization_profile(train_records: list[dict], preprocess_profile: dict) -> dict:
    from .preprocess import _decode_profile
    pp=_decode_profile(preprocess_profile); by=defaultdict(list)
    for r in train_records: by[r.get("inspection_group_used") or r.get("inspection_group") or "GENERIC"].append(r)
    groups={}
    for name,rr in by.items():
        pg=pp["groups"].get(name) or pp["groups"].get("GENERIC") or next(iter(pp["groups"].values()))
        am=[]; res=[]
        for r in rr:
            amap=np.asarray(r["anomaly_map"],dtype=np.float32); rgb=np.asarray(Image.open(r["prepared_path"]).convert("RGB"))
            am.append(amap); res.append(residual_map(_gray(rgb),pg["reference_gray"]))
        astack=np.stack(am,axis=0); rstack=np.stack(res,axis=0)
        afloor=max(1e-5,float(np.quantile(np.std(astack,axis=0),.25))*.25)
        rfloor=max(1e-4,float(np.quantile(np.std(rstack,axis=0),.25))*.25)
        amed,ascale=_robust_stack(astack,afloor); rmed,rscale=_robust_stack(rstack,rfloor)
        groups[name]={"count":len(rr),"anom_med":amed,"anom_scale":ascale,"resid_med":rmed,"resid_scale":rscale,"reference_gray":pg["reference_gray"],"master_mask":pg["master_mask"],"surface_mask":pg["surface_mask"]}
    return {"schema_version":SCHEMA_VERSION,"kind":"localization_profile","algorithm":"V6.6 GOOD spatial baseline + dual ACTION/SAFETY candidate calibration","thresholds_global":None,"thresholds_action":None,"thresholds_safety":None,"thresholds_by_group":{},"validation":{},"groups":groups}


def _region_filter(base: np.ndarray,min_area: int) -> np.ndarray:
    m=(base>0).astype(np.uint8)*255; k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,k); m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,k)
    n,lab,stats,_=cv2.connectedComponentsWithStats((m>0).astype(np.uint8),8); out=np.zeros_like(m)
    for i in range(1,n):
        if int(stats[i,cv2.CC_STAT_AREA])>=int(min_area): out[lab==i]=255
    return (out>0).astype(np.uint8)


def normalized_evidence(amap: np.ndarray, rgb: np.ndarray, g: dict):
    m=(g["master_mask"]>0); surface=(g.get("surface_mask",g["master_mask"])>0); boundary=m & ~surface
    za=np.maximum((np.asarray(amap,dtype=np.float32)-g["anom_med"])/np.maximum(g["anom_scale"],1e-6),0)
    rr=residual_map(_gray(rgb),g["reference_gray"]); zr=np.maximum((rr-g["resid_med"])/np.maximum(g["resid_scale"],1e-6),0)
    return za,zr,m,surface,boundary


def evidence_maps(amap: np.ndarray, rgb: np.ndarray, g: dict, th: dict) -> tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray]:
    za,zr,m,surface,boundary=normalized_evidence(amap,rgb,g)
    az=float(th["anomaly_z"]); rz=float(th["residual_z"]); strong=float(th["strong_anomaly_z"]); bm=float(th.get("boundary_multiplier",1.35))
    surf=(((za>=az)&(zr>=rz)) | (za>=strong)) & surface
    edge=(((za>=az*bm)&(zr>=rz*bm)) | (za>=strong*bm)) & boundary
    cand=_region_filter(surf|edge,int(th["min_area"]))

    # V6.6 display evidence removes V6.5's artificial 0.30 residual floor.
    # Supported evidence must be jointly unusual; very strong anomaly may still appear.
    zratio=za/max(az,1e-6); rratio=zr/max(rz,1e-6); strong_ratio=za/max(strong,1e-6)
    supported=np.minimum(zratio,rratio)
    evidence=np.maximum(supported,strong_ratio*.82)
    evidence[boundary]/=bm; evidence[~m]=0
    return cand,evidence,za,zr


def decision_score(amap: np.ndarray, g: dict) -> float:
    # Backward fallback only. V6.6 main export/inference uses score_engine recipe.
    m=(g["master_mask"]>0); surface=(g.get("surface_mask",g["master_mask"])>0); boundary=m & ~surface
    za=np.maximum((np.asarray(amap,dtype=np.float32)-g["anom_med"])/np.maximum(g["anom_scale"],1e-6),0)
    vals=np.concatenate([za[surface],za[boundary]*.60]); vals=vals[np.isfinite(vals)]
    if not len(vals): return 0.0
    k=min(len(vals),max(24,int(round(len(vals)*.003))))
    return float(np.partition(vals,len(vals)-k)[-k:].mean())


def _cache_records(records: list[dict], profile: dict) -> list[dict]:
    out=[]
    for r in records:
        g=profile["groups"].get(r.get("inspection_group_used")) or profile["groups"].get("GENERIC") or next(iter(profile["groups"].values()))
        rgb=np.asarray(Image.open(r["prepared_path"]).convert("RGB")); za,zr,m,surface,boundary=normalized_evidence(r["anomaly_map"],rgb,g)
        out.append({"label":r["label"],"za":za,"zr":zr,"surface":surface,"boundary":boundary})
    return out


def _eval_cache(cache: list[dict], th: dict) -> dict:
    good_fp=bad_hit=good_n=bad_n=0
    az=float(th["anomaly_z"]); rz=float(th["residual_z"]); strong=float(th["strong_anomaly_z"]); bm=float(th.get("boundary_multiplier",1.35)); area=int(th["min_area"])
    for x in cache:
        za=x["za"]; zr=x["zr"]; surface=x["surface"]; boundary=x["boundary"]
        surf=(((za>=az)&(zr>=rz)) | (za>=strong)) & surface
        edge=(((za>=az*bm)&(zr>=rz*bm)) | (za>=strong*bm)) & boundary
        hit=bool(_region_filter(surf|edge,area).any())
        if x["label"]=="good": good_n+=1; good_fp+=int(hit)
        else: bad_n+=1; bad_hit+=int(hit)
    return {"good_red_image_fp":good_fp,"good_n":good_n,"good_fp_rate":good_fp/max(1,good_n),"bad_candidate_image_hit":bad_hit,"bad_n":bad_n,"bad_candidate_image_recall":bad_hit/max(1,bad_n)}



def calibrate_localization_dual(cal_records: list[dict], profile: dict) -> tuple[dict,dict,dict]:
    cache=_cache_records(cal_records,profile)

    # ACTION/VISIBLE:
    # calibration GOOD red <= 1 우선, 그 안에서 BAD visible hit 최대화.
    action_grid=[]
    for az,rz,strong,area,bm in itertools.product(
        [3.5,4.5,5.5,6.5,7.5,9.0,10.5],
        [2.0,2.5,3.5,4.5,5.5],
        [7.,8.,10.,12.,16.,20.],
        [4,8,12,20,32],
        [1.20,1.35,1.50]
    ):
        if strong<=az:
            continue
        th={
            'anomaly_z':az,
            'residual_z':rz,
            'strong_anomaly_z':strong,
            'min_area':area,
            'boundary_multiplier':bm
        }
        action_grid.append((th,_eval_cache(cache,th)))

    action_pool=[
        x for x in action_grid
        if x[1]['good_red_image_fp']<=1
    ]

    if action_pool:
        action=max(
            action_pool,
            key=lambda x:(
                x[1]['bad_candidate_image_hit'],
                -x[1]['good_red_image_fp'],
                -x[0]['min_area'],
                -x[0]['anomaly_z']
            )
        )
        action_method='good_red_image_fp_le_1_then_max_bad_hit'
    else:
        action=min(
            action_grid,
            key=lambda x:(
                x[1]['good_red_image_fp'],
                -x[1]['bad_candidate_image_hit']
            )
        )
        action_method='min_good_red_fp_then_max_bad_hit'

    # SAFETY:
    # red로 그리지 않아도 REVIEW로 끌어올리는 용도이므로 더 민감하게.
    # calibration BAD safety miss <= 1 우선, 그 안에서 GOOD safety hit 최소화.
    safety_grid=[]
    for az,rz,strong,area,bm in itertools.product(
        [1.5,2.0,2.5,3.0,3.5,4.0,4.5],
        [0.8,1.2,1.6,2.0,2.5,3.0],
        [3.,4.,5.,6.,7.,8.,10.],
        [2,4,8,12],
        [1.10,1.20,1.35]
    ):
        if strong<=az:
            continue
        th={
            'anomaly_z':az,
            'residual_z':rz,
            'strong_anomaly_z':strong,
            'min_area':area,
            'boundary_multiplier':bm
        }
        safety_grid.append((th,_eval_cache(cache,th)))

    safety_pool=[
        x for x in safety_grid
        if (x[1]['bad_n']-x[1]['bad_candidate_image_hit'])<=1
    ]

    if safety_pool:
        safety=min(
            safety_pool,
            key=lambda x:(
                x[1]['good_red_image_fp'],
                -x[1]['bad_candidate_image_hit'],
                x[0]['anomaly_z'],
                x[0]['min_area']
            )
        )
        safety_method='bad_safety_miss_le_1_then_min_good_review_hit'
    else:
        safety=max(
            safety_grid,
            key=lambda x:(
                x[1]['bad_candidate_image_hit'],
                -x[1]['good_red_image_fp'],
                -x[0]['anomaly_z']
            )
        )
        safety_method='max_bad_safety_hit_then_min_good_review_hit'

    action_th,action_diag=action
    safety_th,safety_diag=safety

    action_th={
        **action_th,
        'calibration_method':action_method,
        'role':'ACTION_VISIBLE_RED'
    }
    safety_th={
        **safety_th,
        'calibration_method':safety_method,
        'role':'SAFETY_REVIEW_EVIDENCE'
    }

    display_cfg=calibrate_display_fallback(
        cal_records,
        profile,
        action_th,
        max_good_fp=1
    )

    return action_th,safety_th,{
        'action':action_diag,
        'safety':safety_diag,
        'display_fallback':display_cfg,
        'action_grid_candidates':len(action_grid),
        'safety_grid_candidates':len(safety_grid),
    }


def calibrate_localization(cal_records: list[dict], profile: dict) -> tuple[dict,dict]:
    # backward-compatible wrapper
    action,safety,diag=calibrate_localization_dual(cal_records,profile)
    return action,{**diag["action"],"safety_thresholds":safety,"safety_diagnostics":diag["safety"]}


def candidate_present(amap: np.ndarray, rgb: np.ndarray, g: dict, th: dict) -> bool:
    cand,_,_,_=evidence_maps(amap,rgb,g,th); return bool(cand.any())


def _display_support(amap: np.ndarray, rgb: np.ndarray, g: dict) -> tuple[np.ndarray,np.ndarray]:
    za,zr,m,surface,boundary=normalized_evidence(amap,rgb,g)
    joint=np.minimum(za/3.5,zr/2.5)
    strong=za/10.0
    support=np.maximum(joint,strong*.72).astype(np.float32)
    support[boundary]/=1.25
    support[~m]=0
    return support,m


def _display_score(amap: np.ndarray, rgb: np.ndarray, g: dict) -> float:
    support,m=_display_support(amap,rgb,g)
    v=support[m]

    if not len(v):
        return 0.0

    k=min(
        len(v),
        max(12,int(round(len(v)*.0015)))
    )

    return float(
        np.partition(v,len(v)-k)[-k:].mean()
    )


def calibrate_display_fallback(
    cal_records: list[dict],
    profile: dict,
    action_th: dict,
    max_good_fp: int=1
) -> dict:
    vals=[]

    for r in cal_records:
        g=(
            profile['groups'].get(r.get('inspection_group_used'))
            or profile['groups'].get('GENERIC')
            or next(iter(profile['groups'].values()))
        )

        rgb=np.asarray(
            Image.open(r['prepared_path']).convert('RGB')
        )

        action=candidate_present(
            r['anomaly_map'],
            rgb,
            g,
            action_th
        )

        vals.append(
            (
                r['label'],
                _display_score(
                    r['anomaly_map'],
                    rgb,
                    g
                ),
                bool(action)
            )
        )

    scores=np.asarray(
        [x[1] for x in vals],
        dtype=float
    )
    labels=np.asarray(
        [1 if x[0]=='bad' else 0 for x in vals],
        dtype=np.int8
    )
    actions=np.asarray(
        [x[2] for x in vals],
        dtype=bool
    )

    u=np.unique(scores)

    eps=max(
        1e-8,
        float(np.ptp(u))*1e-8
        if len(u)>1 else 1e-8
    )

    best=None

    for t in [
        float(u[0]-eps),
        *map(float,u),
        float(u[-1]+eps)
    ]:
        visible=actions | (scores>=t)

        good_fp=int(
            ((labels==0)&visible).sum()
        )
        bad_hit=int(
            ((labels==1)&visible).sum()
        )

        if good_fp<=max_good_fp:
            key=(bad_hit,-good_fp,-t)

            if best is None or key>best[0]:
                best=(key,t,good_fp,bad_hit)

    if best is None:
        best=(
            (0,0,0),
            float(u[-1]+eps),
            int(((labels==0)&actions).sum()),
            int(((labels==1)&actions).sum())
        )

    _,t,gfp,bhit=best

    return {
        'schema_version':SCHEMA_VERSION,
        'trigger_score':float(t),
        'calibration_visible_good_fp':int(gfp),
        'calibration_visible_bad_hit':int(bhit),
        'calibration_action_good_fp':int(
            ((labels==0)&actions).sum()
        ),
        'calibration_action_bad_hit':int(
            ((labels==1)&actions).sum()
        ),
        'calibration_good_n':int((labels==0).sum()),
        'calibration_bad_n':int((labels==1).sum()),
        'max_good_fp':int(max_good_fp),
        'role':'VISIBLE_DIAGNOSTIC_FALLBACK_UNION_WITH_ACTION',
        'selection_data':'CALIBRATION_ONLY',
        'final_test_used_for_selection':False,
    }


def display_candidate_mask(
    amap: np.ndarray,
    rgb: np.ndarray,
    g: dict,
    cfg: dict
) -> tuple[np.ndarray,float]:
    support,m=_display_support(amap,rgb,g)
    score=_display_score(amap,rgb,g)

    mask=np.zeros_like(
        m,
        dtype=bool
    )

    if score<float(
        cfg.get('trigger_score',1e9)
    ):
        return mask,score

    vals=support[m]

    if not len(vals):
        return mask,score

    peak=float(vals.max())
    q=float(np.quantile(vals,.995))
    cut=max(.72*peak,q,.85)

    raw=(support>=cut)&m
    raw=_region_filter(
        raw,
        4
    ).astype(bool)

    if not raw.any():
        y,x=np.unravel_index(
            np.argmax(support),
            support.shape
        )

        marker=np.zeros_like(
            m,
            dtype=np.uint8
        )

        cv2.circle(
            marker,
            (int(x),int(y)),
            2,
            1,
            -1
        )

        mask=(marker>0)&m
    else:
        mask=raw

    return mask.astype(bool),score


def display_candidate_present(
    amap: np.ndarray,
    rgb: np.ndarray,
    g: dict,
    cfg: dict
) -> bool:
    mask,_=display_candidate_mask(
        amap,
        rgb,
        g,
        cfg
    )

    return bool(mask.any())


def validate_localization(records: list[dict], profile: dict, th: dict) -> dict:
    good_fp=0; bad_hit=0; bad_n=0; labeled=0; lesion_hit=0; lesion_total=0; tp=fp=fn=0
    for r in records:
        g=profile["groups"].get(r.get("inspection_group_used")) or profile["groups"].get("GENERIC") or next(iter(profile["groups"].values()))
        rgb=np.asarray(Image.open(r["prepared_path"]).convert("RGB")); cand,_,_,_=evidence_maps(r["anomaly_map"],rgb,g,th); hit=bool(cand.any())
        if r["label"]=="good": good_fp+=int(hit); continue
        bad_n+=1; bad_hit+=int(hit)
        gp=r.get("prepared_gt_mask_path")
        if gp and Path(gp).exists():
            gt=np.asarray(Image.open(gp).convert("L"))>127; labeled+=1; lesion_total+=1; lesion_hit+=int(bool((cand>0)[gt].any()) if gt.any() else False)
            tp+=int(((cand>0)&gt).sum()); fp+=int(((cand>0)&~gt).sum()); fn+=int(((cand==0)&gt).sum())
    precision=tp/(tp+fp) if tp+fp else None; recall=tp/(tp+fn) if tp+fn else None
    f1=(2*precision*recall/(precision+recall)) if precision is not None and recall is not None and precision+recall else None
    iou=tp/(tp+fp+fn) if tp+fp+fn else None
    good_n=sum(1 for r in records if r["label"]=="good")
    return {"labeled_bad_images":labeled,"good_red_image_fp":good_fp,"good_n":good_n,"good_red_image_fp_rate":good_fp/max(1,good_n),"bad_candidate_image_hit":bad_hit,"bad_n":bad_n,"bad_candidate_image_recall":bad_hit/max(1,bad_n),"lesion_hit":lesion_hit,"lesion_total":lesion_total,"lesion_hit_recall":lesion_hit/lesion_total if lesion_total else None,"pixel_precision":precision,"pixel_recall":recall,"pixel_f1":f1,"pixel_iou":iou,"localization_100_percent_pass":bool(labeled and lesion_hit==lesion_total and good_fp==0),"status":"VERIFIED_WITH_GT_MASKS" if labeled else "UNVERIFIED_NO_FINAL_TEST_GROUND_TRUTH_MASKS","truth_note":"Image-level BAD candidate hit uses BAD labels only; pixel/lesion correctness requires human GT masks."}


def encode_localization_profile(profile: dict) -> dict:
    out={k:v for k,v in profile.items() if k!="groups"}; out["groups"]={}
    for name,g in profile["groups"].items():
        out["groups"][name]={"count":g["count"]}
        for k in ("anom_med","anom_scale","resid_med","resid_scale","reference_gray","master_mask","surface_mask"):
            out["groups"][name][k]=encode_array(np.asarray(g[k]))
    return out


def decode_localization_profile(obj_or_path: dict | str | Path) -> dict:
    obj=obj_or_path if isinstance(obj_or_path,dict) else json.loads(Path(obj_or_path).read_text(encoding="utf-8")); out={k:v for k,v in obj.items() if k!="groups"}; out["groups"]={}
    for name,g in obj["groups"].items():
        gg={"count":g["count"]}
        for k,v in g.items():
            if k=="count": continue
            gg[k]=decode_array(v)
        out["groups"][name]=gg
    return out


def save_localization_profile(profile: dict, path: str | Path) -> Path:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(encode_localization_profile(profile),ensure_ascii=False,indent=2),encoding="utf-8"); return p





def make_views(rgb: np.ndarray, amap: np.ndarray, group: dict, th: dict, decision: str,
               out_dir: str | Path, display_cfg: dict|None=None, safety_th: dict|None=None) -> dict:
    action_cand,_,_,_=evidence_maps(amap,rgb,group,th)
    inspected=group['master_mask']>0
    support,_=_display_support(amap,rgb,group)

    scaled=np.clip((support-.55)/1.75,0,1)
    scaled=np.power(scaled,1.18)
    if decision=='OK':
        scaled=np.minimum(scaled,.40)

    norm=(scaled*255).astype(np.uint8)
    heat=cv2.cvtColor(cv2.applyColorMap(norm,cv2.COLORMAP_TURBO),cv2.COLOR_BGR2RGB)
    heat[~inspected]=np.array([82,82,82],np.uint8)

    fallback=np.zeros_like(action_cand,dtype=bool)
    safety_cand=np.zeros_like(action_cand,dtype=bool)
    display_score=0.0

    if decision!='OK' and display_cfg is not None:
        fallback,display_score=display_candidate_mask(amap,rgb,group,display_cfg)
    if decision!='OK' and safety_th is not None:
        safety_cand,_,_,_=evidence_maps(amap,rgb,group,safety_th)

    alarm_raw=np.zeros_like(action_cand,dtype=bool)
    if decision!='OK':
        alarm_raw=(action_cand|fallback|safety_cand)&inspected
        if not alarm_raw.any():
            masked_support=np.where(inspected,support,-np.inf)
            if np.isfinite(masked_support).any():
                y,x=np.unravel_index(np.nanargmax(masked_support),masked_support.shape)
                marker=np.zeros_like(inspected,dtype=np.uint8)
                cv2.circle(marker,(int(x),int(y)),2,1,-1)
                alarm_raw=(marker>0)&inspected

    # Keep strongest 3 connected evidence regions for a clean company UI.
    alarm_focus=np.zeros_like(alarm_raw,dtype=bool)
    if alarm_raw.any():
        n,labels,stats,_=cv2.connectedComponentsWithStats(alarm_raw.astype(np.uint8),8)
        comps=[]
        for cid in range(1,n):
            comp=(labels==cid)
            area=int(stats[cid,cv2.CC_STAT_AREA])
            if area<=0:
                continue
            peak=float(support[comp].max()) if comp.any() else 0.0
            mean=float(support[comp].mean()) if comp.any() else 0.0
            comps.append((peak+.25*mean+.02*np.log1p(area),cid))
        for _,cid in sorted(comps,reverse=True)[:3]:
            alarm_focus |= (labels==cid)

    if not alarm_focus.any() and alarm_raw.any():
        alarm_focus=alarm_raw.copy()

    # SAME display mask for Heatmap / Overlay / Contour.
    if alarm_focus.any():
        kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        alarm_display=(cv2.dilate(alarm_focus.astype(np.uint8),kernel,1)>0)&inspected
    else:
        alarm_display=np.zeros_like(alarm_focus,dtype=bool)

    heat[alarm_display]=np.array([255,0,0],np.uint8)

    overlay=rgb.copy()
    blend=np.clip(.84*rgb.astype(float)+.16*heat.astype(float),0,255).astype(np.uint8)
    overlay[inspected]=blend[inspected]
    overlay[alarm_display]=np.clip(
        .10*rgb[alarm_display].astype(float)+.90*np.array([255,0,0]),0,255
    ).astype(np.uint8)

    contour=rgb.copy(); cnts=[]
    if alarm_display.any():
        cnts,_=cv2.findContours(alarm_display.astype(np.uint8)*255,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(contour,cnts,-1,(255,0,0),2)

    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    Image.fromarray(rgb).save(out/'01_original.png')
    Image.fromarray(heat).save(out/'02_heatmap.png')
    Image.fromarray(overlay).save(out/'03_overlay_masked.png')
    Image.fromarray(contour).save(out/'04_contour.png')

    for legacy_name in ['05_candidate_map.png','06_review_evidence_map.png']:
        p=out/legacy_name
        if p.exists(): p.unlink()

    return {
        'alarm_regions':len(cnts),
        'alarm_pixels_raw':int(alarm_raw.sum()),
        'alarm_pixels_focused':int(alarm_focus.sum()),
        'alarm_pixels_displayed':int(alarm_display.sum()),
        'action_candidate_present':bool(action_cand.any()),
        'display_fallback_present':bool(fallback.any()),
        'safety_candidate_present':bool(safety_cand.any()),
        'red_alarm_present':bool(alarm_display.any()),
        'display_evidence_score':float(display_score),
        'visual_policy':'ONE SHARED RED MASK across Heatmap/Overlay/Contour; actual label never used',
    }

def validate_visible_localization(records: list[dict], profile: dict, action_th: dict, display_cfg: dict) -> dict:
    counts={'good':0,'bad':0}; hits={'good':0,'bad':0}
    for r in records:
        g=profile['groups'].get(r.get('inspection_group_used')) or profile['groups'].get('GENERIC') or next(iter(profile['groups'].values()))
        rgb=np.asarray(Image.open(r['prepared_path']).convert('RGB'))
        a=candidate_present(r['anomaly_map'],rgb,g,action_th)
        d=display_candidate_present(r['anomaly_map'],rgb,g,display_cfg)
        counts[r['label']]+=1
        hits[r['label']]+=int(a or d)
    return {
        'schema_version':SCHEMA_VERSION,
        'good_visible_fp':hits['good'],
        'good_n':counts['good'],
        'good_visible_fp_rate':hits['good']/max(1,counts['good']),
        'bad_visible_hit':hits['bad'],
        'bad_n':counts['bad'],
        'bad_visible_recall':hits['bad']/max(1,counts['bad']),
        'truth_note':'Visible red evidence is calibration-selected and label-independent at inference; lesion correctness still requires GT masks.',
    }
