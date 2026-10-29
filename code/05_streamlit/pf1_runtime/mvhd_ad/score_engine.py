from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from PIL import Image
from .localization import _gray, residual_map
from .calibration import choose_thresholds
from .metrics import ranking_metrics, binary_metrics
from .config import SCHEMA_VERSION

RECIPE_NAMES = [
    "ANOM_TOP_015",
    "ANOM_TOP_030",
    "ANOM_TOP_060",
    "JOINT_TOP_030",
    "JOINT_TOP_060",
    "JOINT_TOP_100",
    "HYBRID_BALANCED",
    "HYBRID_SPECIFIC",
    "SURFACE_JOINT",
]


def _top_mean(vals: np.ndarray, fraction: float, min_k: int=16) -> float:
    v=np.asarray(vals,dtype=np.float32); v=v[np.isfinite(v)]
    if not len(v): return 0.0
    k=min(len(v),max(int(min_k),int(round(len(v)*float(fraction)))))
    return float(np.partition(v,len(v)-k)[-k:].mean())


def _normalized_maps(amap: np.ndarray, rgb: np.ndarray, g: dict):
    m=(g["master_mask"]>0); surface=(g.get("surface_mask",g["master_mask"])>0); boundary=m & ~surface
    za=np.maximum((np.asarray(amap,dtype=np.float32)-g["anom_med"])/np.maximum(g["anom_scale"],1e-6),0)
    rr=residual_map(_gray(rgb),g["reference_gray"])
    zr=np.maximum((rr-g["resid_med"])/np.maximum(g["resid_scale"],1e-6),0)
    return za,zr,m,surface,boundary


def score_features(amap: np.ndarray, rgb: np.ndarray, g: dict) -> dict[str,float]:
    za,zr,m,surface,boundary=_normalized_maps(amap,rgb,g)
    anom=np.concatenate([za[surface],za[boundary]*.60])
    joint=np.minimum(za, zr*1.15)
    joint_all=np.concatenate([joint[surface],joint[boundary]/1.35])
    joint_surface=joint[surface]

    a015=_top_mean(anom,.0015,24)
    a030=_top_mean(anom,.0030,24)
    a060=_top_mean(anom,.0060,24)
    j030=_top_mean(joint_all,.0030,20)
    j060=_top_mean(joint_all,.0060,24)
    j100=_top_mean(joint_all,.0100,32)
    jsurf=_top_mean(joint_surface,.0060,20)

    return {
        "ANOM_TOP_015":a015,
        "ANOM_TOP_030":a030,
        "ANOM_TOP_060":a060,
        "JOINT_TOP_030":j030,
        "JOINT_TOP_060":j060,
        "JOINT_TOP_100":j100,
        "HYBRID_BALANCED":.45*a030+.55*j060,
        "HYBRID_SPECIFIC":.25*a060+.75*j100,
        "SURFACE_JOINT":jsurf,
    }


def _group(profile: dict, record: dict) -> dict:
    name=record.get("inspection_group_used") or record.get("inspection_group") or "GENERIC"
    return profile["groups"].get(name) or profile["groups"].get("GENERIC") or next(iter(profile["groups"].values()))


def features_for_record(record: dict, profile: dict) -> dict[str,float]:
    rgb=np.asarray(Image.open(record["prepared_path"]).convert("RGB"))
    return score_features(record["anomaly_map"],rgb,_group(profile,record))


def _stratified_fold_ids(labels: np.ndarray, k: int=5) -> np.ndarray:
    fold=np.zeros(len(labels),dtype=np.int16)
    for cls in (0,1):
        idx=np.flatnonzero(labels==cls)
        for j,i in enumerate(idx): fold[i]=j%k
    return fold


def _cv_operating_point(labels: np.ndarray, scores: np.ndarray, k: int=5) -> dict:
    folds=_stratified_fold_ids(labels,k); tp=tn=fp=fn=0
    for f in range(k):
        tr=folds!=f; va=folds==f
        if not va.any() or len(np.unique(labels[tr]))<2: continue
        th=choose_thresholds(labels[tr],scores[tr])
        pred=(scores[va]>=float(th["threshold"])).astype(np.int8); y=labels[va]
        tp+=int(((pred==1)&(y==1)).sum()); tn+=int(((pred==0)&(y==0)).sum())
        fp+=int(((pred==1)&(y==0)).sum()); fn+=int(((pred==0)&(y==1)).sum())
    recall=tp/max(1,tp+fn); specificity=tn/max(1,tn+fp); precision=tp/max(1,tp+fp)
    f1=2*precision*recall/max(1e-12,precision+recall)
    return {"tp":tp,"tn":tn,"fp":fp,"fn":fn,"recall":recall,"specificity":specificity,"precision":precision,"f1":f1,"folds":k}


def select_score_recipe(cal_records: list[dict], profile: dict) -> dict:
    labels=np.asarray([1 if r["label"]=="bad" else 0 for r in cal_records],dtype=np.int8)
    feature_rows=[features_for_record(r,profile) for r in cal_records]
    diagnostics={}
    for name in RECIPE_NAMES:
        scores=np.asarray([row[name] for row in feature_rows],dtype=float)
        th=choose_thresholds(labels,scores)
        op=binary_metrics(labels,scores,th["threshold"])
        rank=ranking_metrics(labels,scores)
        cv=_cv_operating_point(labels,scores,5)
        # Safety first: full-calibration recall target is mandatory. Then reward specificity,
        # CV stability and rank separation. This is recipe selection, not Final-Test tuning.
        eligible=op["recall"]>=.98
        utility=(.50*op["specificity"]+.25*cv["specificity"]+.15*(rank["image_AUROC"] or 0.)+.10*cv["recall"])
        if cv["recall"]<.90: utility-=0.50*(.90-cv["recall"])
        diagnostics[name]={"eligible_recall_ge_0_98":bool(eligible),"utility":float(utility),"calibration_operating_point":op,"calibration_ranking":rank,"cv5_operating_point":cv}

    eligible=[n for n,d in diagnostics.items() if d["eligible_recall_ge_0_98"]]
    pool=eligible or list(diagnostics)
    selected=max(pool,key=lambda n:(diagnostics[n]["utility"],diagnostics[n]["calibration_operating_point"]["specificity"],diagnostics[n]["calibration_ranking"]["image_AUROC"] or -1))
    return {
        "schema_version":SCHEMA_VERSION,
        "kind":"score_recipe_selection",
        "selected_recipe":selected,
        "selection_data":"CALIBRATION_ONLY",
        "final_test_used_for_selection":False,
        "objective":"recall>=0.98, then reduce GOOD false alarms using calibration specificity + 5-fold stability + AUROC",
        "candidates":diagnostics,
    }


def score_record(record: dict, profile: dict, recipe: str|dict) -> float:
    name=recipe.get("selected_recipe") if isinstance(recipe,dict) else str(recipe)
    feats=features_for_record(record,profile)
    if name not in feats: raise KeyError(f"Unknown score recipe: {name}")
    return float(feats[name])


def score_image(amap: np.ndarray, rgb: np.ndarray, group: dict, recipe: str|dict) -> float:
    name=recipe.get("selected_recipe") if isinstance(recipe,dict) else str(recipe)
    feats=score_features(amap,rgb,group)
    if name not in feats: raise KeyError(f"Unknown score recipe: {name}")
    return float(feats[name])
