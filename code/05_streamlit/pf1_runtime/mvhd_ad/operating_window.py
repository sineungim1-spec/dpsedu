from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image
from .config import SCHEMA_VERSION


def image_proxy_metrics(rgb: np.ndarray, obj_mask: np.ndarray, alignment_score: float) -> dict:
    gray=cv2.cvtColor(rgb.astype(np.uint8),cv2.COLOR_RGB2GRAY).astype(np.float32)/255.; m=obj_mask>0; h,w=m.shape
    ys,xs=np.where(m); cx=float(xs.mean()) if len(xs) else w/2; cy=float(ys.mean()) if len(ys) else h/2
    product=gray[m] if m.any() else gray.ravel(); bg=gray[~m] if (~m).any() else gray.ravel(); edge=np.zeros_like(m); edge[:2]=edge[-2:]=True; edge[:,:2]=True; edge[:,-2:]=True
    lap=cv2.Laplacian(gray,cv2.CV_32F,ksize=3)
    return {
        "foreground_ratio":float(m.mean()),"centroid_offset_px":float(np.hypot(cx-(w-1)/2,cy-(h-1)/2)),"product_mean_gray":float(product.mean()),"product_std_gray":float(product.std()),"background_mean_gray":float(bg.mean()),"product_background_contrast":float(abs(product.mean()-bg.mean())),"glare_ratio":float((product>.95).mean()),"dark_ratio":float((product<.05).mean()),"edge_touch_ratio":float((m&edge).sum()/max(1,m.sum())),"sharpness":float(lap[m].var() if m.any() else lap.var()),"alignment_score":float(alignment_score),
    }


def _summary(vals: list[float], rule: str) -> dict:
    a=np.asarray(vals,dtype=float); med=float(np.median(a)); q01=float(np.quantile(a,.01)); q99=float(np.quantile(a,.99)); mad=float(np.median(np.abs(a-med))); scale=max(1e-5,q99-q01,1.4826*mad)
    lower=(q01-.20*scale) if rule in {"both","lower"} else None; upper=(q99+.20*scale) if rule in {"both","upper"} else None
    if lower is not None and min(a)>=0: lower=max(0.,lower)
    return {"median":med,"q01":q01,"q99":q99,"mad":mad,"scale":scale,"lower":lower,"upper":upper,"n":len(vals),"rule":rule}


def build_operating_window(train_records: list[dict]) -> dict:
    rules={"foreground_ratio":"both","centroid_offset_px":"upper","product_mean_gray":"both","product_std_gray":"both","background_mean_gray":"both","product_background_contrast":"lower","glare_ratio":"upper","dark_ratio":"both","edge_touch_ratio":"upper","sharpness":"lower","alignment_score":"lower"}
    by=defaultdict(lambda:defaultdict(list))
    for r in train_records:
        rgb=np.asarray(Image.open(r["prepared_path"]).convert("RGB")); # current object mask is reconstructed from prepared image for operating proxies
        bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
        from .preprocess import detect_product
        mask,_=detect_product(bgr); vals=image_proxy_metrics(rgb,(mask>0).astype(np.uint8),float(r.get("alignment_score_prepared",1.0)))
        g=r.get("inspection_group_used") or r.get("inspection_group") or "GENERIC"
        for k,v in vals.items(): by[g][k].append(v)
    groups={g:{"count":len(next(iter(mm.values()))) if mm else 0,"metrics":{k:_summary(v,rules[k]) for k,v in mm.items()}} for g,mm in by.items()}
    return {"schema_version":SCHEMA_VERSION,"kind":"operating_window","image_size":256,"groups":groups,"site_validation_protocol":{"C1_score_margin":"For a known GOOD baseline sweep, target Score < image threshold * 0.6.","C2_sensitivity":"Within the intended operating window, target |delta Score| <= 0.05.","C3_repeatability":"At an identical setting repeated 3 times, target score sigma <= 0.02.","variables":["lighting","shadow","reflection","camera_distance","product_position","background","ROI"],"note":"Physical lux/mm/angle limits require actual-line commissioning; this automatic gate uses image proxies only."},"runtime_policy":{"status_OK":"inside TRAIN-GOOD learned image envelope","status_WARN":"one mild image-side deviation; production review recommended","status_REVIEW_INPUT":"multiple or severe deviations; treat acquisition/input before defect decision"}}


def save_operating_window(obj: dict,path: str|Path)->Path:
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8");return p
