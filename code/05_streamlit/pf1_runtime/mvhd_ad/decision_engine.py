from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from .localization import _gray, residual_map
from .config import SCHEMA_VERSION

FEATURE_NAMES = [
    "anom_top_015","anom_top_030","anom_top_060",
    "joint_top_030","joint_top_060","joint_top_100","surface_joint",
    "za_q999_surface","za_max_surface","zr_q999_surface","joint_q999_surface",
    "joint_area_25","joint_area_35","strong_area_60","strong_area_80",
    "largest_joint_component","boundary_joint_top","surface_resid_top",
]

def _top_mean(vals, fraction, min_k=8):
    v=np.asarray(vals,dtype=np.float32); v=v[np.isfinite(v)]
    if not len(v): return 0.0
    k=min(len(v),max(int(min_k),int(round(len(v)*float(fraction)))))
    return float(np.partition(v,len(v)-k)[-k:].mean())

def _largest_component(mask: np.ndarray) -> float:
    n,_,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    return float(stats[1:,cv2.CC_STAT_AREA].max()) if n>1 else 0.0

def feature_dict(amap: np.ndarray, rgb: np.ndarray, g: dict) -> dict[str,float]:
    m=(g["master_mask"]>0); surface=(g.get("surface_mask",g["master_mask"])>0); boundary=m & ~surface
    za=np.maximum((np.asarray(amap,dtype=np.float32)-g["anom_med"])/np.maximum(g["anom_scale"],1e-6),0)
    rr=residual_map(_gray(rgb),g["reference_gray"])
    zr=np.maximum((rr-g["resid_med"])/np.maximum(g["resid_scale"],1e-6),0)
    joint=np.minimum(za,zr*1.15)
    anom=np.concatenate([za[surface],za[boundary]*.60])
    joint_all=np.concatenate([joint[surface],joint[boundary]/1.35])
    js=joint[surface]; zs=za[surface]; rs=zr[surface]
    jb=joint[boundary]/1.35 if boundary.any() else np.asarray([],dtype=np.float32)
    joint25=((za>=3.0)&(zr>=2.5)&m)
    joint35=((za>=4.0)&(zr>=3.5)&m)
    vals={
        "anom_top_015":_top_mean(anom,.0015,24),
        "anom_top_030":_top_mean(anom,.0030,24),
        "anom_top_060":_top_mean(anom,.0060,24),
        "joint_top_030":_top_mean(joint_all,.0030,20),
        "joint_top_060":_top_mean(joint_all,.0060,24),
        "joint_top_100":_top_mean(joint_all,.0100,32),
        "surface_joint":_top_mean(js,.0060,20),
        "za_q999_surface":float(np.quantile(zs,.999)) if zs.size else 0.0,
        "za_max_surface":float(zs.max()) if zs.size else 0.0,
        "zr_q999_surface":float(np.quantile(rs,.999)) if rs.size else 0.0,
        "joint_q999_surface":float(np.quantile(js,.999)) if js.size else 0.0,
        "joint_area_25":float(joint25.sum()/max(1,m.sum())),
        "joint_area_35":float(joint35.sum()/max(1,m.sum())),
        "strong_area_60":float(((za>=6.0)&m).sum()/max(1,m.sum())),
        "strong_area_80":float(((za>=8.0)&m).sum()/max(1,m.sum())),
        "largest_joint_component":_largest_component(joint25)/max(1,m.sum()),
        "boundary_joint_top":_top_mean(jb,.010,8) if jb.size else 0.0,
        "surface_resid_top":_top_mean(rs,.005,16),
    }
    return vals

def _group(profile: dict, record: dict) -> dict:
    name=record.get("inspection_group_used") or record.get("inspection_group") or "GENERIC"
    return profile["groups"].get(name) or profile["groups"].get("GENERIC") or next(iter(profile["groups"].values()))

def features_for_record(record: dict, profile: dict) -> np.ndarray:
    rgb=np.asarray(Image.open(record["prepared_path"]).convert("RGB"))
    d=feature_dict(record["anomaly_map"],rgb,_group(profile,record))
    return np.asarray([d[n] for n in FEATURE_NAMES],dtype=np.float64)

def features_for_image(amap: np.ndarray, rgb: np.ndarray, group: dict) -> np.ndarray:
    d=feature_dict(amap,rgb,group)
    return np.asarray([d[n] for n in FEATURE_NAMES],dtype=np.float64)

def _sigmoid(x):
    x=np.clip(np.asarray(x,dtype=float),-40,40)
    return 1.0/(1.0+np.exp(-x))

def policy_counts(labels: np.ndarray, scores: np.ndarray, low: float, high: float) -> dict:
    y=np.asarray(labels,dtype=np.int8); s=np.asarray(scores,dtype=float)
    tri=np.where(s<low,0,np.where(s<high,1,2)) # OK REVIEW NG
    out={"good":{"OK":0,"REVIEW":0,"NG":0},"bad":{"OK":0,"REVIEW":0,"NG":0}}
    for cls,name in ((0,"good"),(1,"bad")):
        for code,tname in ((0,"OK"),(1,"REVIEW"),(2,"NG")):
            out[name][tname]=int(((y==cls)&(tri==code)).sum())
    review=out['good']['REVIEW']+out['bad']['REVIEW']
    return {"counts":out,"bad_ok":out['bad']['OK'],"good_ng":out['good']['NG'],"review_n":review,"review_rate":review/max(1,len(y)),"good_ok":out['good']['OK'],"bad_ng":out['bad']['NG']}

def select_operating_band(labels, scores, max_bad_ok: int=1, max_good_ng: int=1) -> dict:
    y=np.asarray(labels,dtype=np.int8); s=np.asarray(scores,dtype=float)
    u=np.unique(s[np.isfinite(s)]); eps=max(1e-8,float(np.ptp(u))*1e-8 if len(u)>1 else 1e-8)
    cand=np.asarray([u[0]-eps,*u,u[-1]+eps],dtype=float)
    best=None
    for low in cand:
        bad_ok=int(((y==1)&(s<low)).sum())
        if bad_ok>max_bad_ok: continue
        for high in cand:
            if high<low: continue
            good_ng=int(((y==0)&(s>=high)).sum())
            if good_ng>max_good_ng: continue
            m=policy_counts(y,s,float(low),float(high))
            # Maximize useful automatic decisions under the two hard safety constraints.
            key=(-m['review_n'], m['good_ok']+m['bad_ng'], m['bad_ng'], m['good_ok'], high-low)
            if best is None or key>best[0]: best=(key,float(low),float(high),m)
    if best is None:
        return {"review_low":float(np.min(s)-eps),"ng_high":float(np.max(s)+eps),**policy_counts(y,s,float(np.min(s)-eps),float(np.max(s)+eps)),"feasible":False}
    _,low,high,m=best
    return {"review_low":low,"ng_high":high,**m,"feasible":True,"constraints":{"max_bad_ok":max_bad_ok,"max_good_ng":max_good_ng}}

def _fit_model(X,y,C,class_weight):
    sc=StandardScaler().fit(X); Z=sc.transform(X)
    clf=LogisticRegression(C=float(C),class_weight=class_weight,solver='liblinear',max_iter=3000,random_state=42)
    clf.fit(Z,y)
    return sc,clf

def fit_decision_model(cal_records: list[dict], profile: dict) -> dict:
    X=np.vstack([features_for_record(r,profile) for r in cal_records]); y=np.asarray([1 if r['label']=='bad' else 0 for r in cal_records],dtype=np.int8)
    skf=StratifiedKFold(n_splits=5,shuffle=True,random_state=42)
    diagnostics=[]; best=None
    for cw in (None,'balanced'):
      for C in (.01,.03,.1,.3,1.0,3.0):
        oof=np.zeros(len(y),dtype=float)
        for tr,va in skf.split(X,y):
            sc,clf=_fit_model(X[tr],y[tr],C,cw)
            oof[va]=_sigmoid(clf.decision_function(sc.transform(X[va])))
        band=select_operating_band(y,oof,1,1)
        auc=float(roc_auc_score(y,oof))
        # Feasibility dominates; then low review and robust rank separation.
        feasible=bool(band['bad_ok']<=1 and band['good_ng']<=1)
        utility=(1000 if feasible else 0) - 4*band['review_rate'] + 2*auc + .01*(band['good_ok']+band['bad_ng'])
        row={"C":C,"class_weight":cw,"oof_auc":auc,"oof_band":band,"utility":utility,"feasible":feasible}
        diagnostics.append(row)
        key=(feasible,utility,auc,-band['review_rate'])
        if best is None or key>best[0]: best=(key,C,cw,row)
    _,C,cw,selection=best
    sc,clf=_fit_model(X,y,C,cw)
    full_scores=_sigmoid(clf.decision_function(sc.transform(X)))
    band=select_operating_band(y,full_scores,1,1)
    return {
        "schema_version":SCHEMA_VERSION,"kind":"calibration_supervised_decision_head",
        "model":"standardized_logistic_regression","feature_names":FEATURE_NAMES,
        "C":float(C),"class_weight":cw,"mean":sc.mean_.tolist(),"scale":sc.scale_.tolist(),
        "coef":clf.coef_[0].tolist(),"intercept":float(clf.intercept_[0]),
        "selection_data":"CALIBRATION_ONLY","final_test_used_for_selection":False,
        "oof_selection":selection,"candidate_diagnostics":diagnostics,
        "calibration_operating_band":band,
        "target":"minimize REVIEW subject to BAD->OK <=1 and GOOD->NG <=1 on Calibration",
    }

def score_vector(x: np.ndarray, model: dict) -> float:
    z=(np.asarray(x,dtype=float)-np.asarray(model['mean'],dtype=float))/np.maximum(np.asarray(model['scale'],dtype=float),1e-12)
    logit=float(np.dot(np.asarray(model['coef'],dtype=float),z)+float(model['intercept']))
    return float(_sigmoid(logit))

def score_record(record: dict, profile: dict, model: dict) -> float:
    return score_vector(features_for_record(record,profile),model)

def score_image(amap: np.ndarray, rgb: np.ndarray, group: dict, model: dict) -> float:
    return score_vector(features_for_image(amap,rgb,group),model)

def save_decision_model(model: dict, path: str|Path) -> Path:
    p=Path(path); p.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8'); return p
