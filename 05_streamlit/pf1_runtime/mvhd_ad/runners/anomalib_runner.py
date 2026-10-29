from __future__ import annotations
from pathlib import Path
import math, shutil, tempfile
import numpy as np
from PIL import Image
from ..config import InferConfig


def _import_anomalib():
    try:
        from anomalib.data import PredictDataset
        from anomalib.engine import Engine
        from anomalib.models import EfficientAd
        return PredictDataset, Engine, EfficientAd
    except Exception as e:
        raise RuntimeError(
            "Anomalib import failed. Install company_runtime requirements first: "
            "pip install -r requirements.txt"
        ) from e


def _device(cfg_device: str) -> str:
    import torch
    d=str(cfg_device).lower()
    if d.startswith("cuda") and torch.cuda.is_available(): return "cuda"
    return "cpu"


def _new_model(model_name: str, imagenet_dir: str | Path | None=None):
    _,_,EfficientAd=_import_anomalib()
    if model_name.lower() not in {"efficientad","efficient_ad","efficient-ad"}:
        raise ValueError(f"Unsupported model: {model_name}")
    kwargs={"visualizer":False}  # IMPORTANT V6.4: no ImageVisualizer PNG callback during bulk predict.
    if imagenet_dir is not None: kwargs["imagenet_dir"]=str(imagenet_dir)
    return EfficientAd(**kwargs)


def _predict_engine(device: str):
    _,Engine,_=_import_anomalib()
    # IMPORTANT V6.4 ProductionFix:
    # DO NOT pass enable_checkpointing=False here. EfficientAD/Anomalib can provide a
    # ModelCheckpoint callback; Lightning raises MisconfigurationException if the Trainer
    # is told checkpointing is disabled while that callback exists.
    return Engine(
        accelerator="gpu" if device=="cuda" else "cpu",
        devices=1,
        enable_progress_bar=False,
        logger=False,
    )


def _to_numpy(x):
    if x is None: return None
    try:
        import torch
        if torch.is_tensor(x): return x.detach().cpu().numpy()
    except Exception: pass
    return np.asarray(x)


def _field(obj,name):
    if isinstance(obj,dict): return obj.get(name)
    return getattr(obj,name,None)


def _flatten_predictions(preds) -> list[dict]:
    flat=[]
    for obj in preds or []:
        paths=_field(obj,"image_path"); scores=_field(obj,"pred_score"); maps=_field(obj,"anomaly_map"); labels=_field(obj,"pred_label")
        # Item-like object
        if isinstance(paths,(str,Path)) or paths is None and np.ndim(_to_numpy(scores))==0:
            flat.append({"image_path":str(paths) if paths is not None else None,"pred_score":float(np.asarray(_to_numpy(scores)).reshape(-1)[0]) if scores is not None else None,"anomaly_map":_normalize_map(maps),"pred_label":_scalar(labels)})
            continue
        # Batch-like object
        if paths is None:
            # Some dataclasses support indexing but do not expose image_path as a list until collated.
            try:
                n=len(obj)
                for i in range(n):
                    it=obj[i]; flat.append({"image_path":str(_field(it,"image_path")),"pred_score":_scalar(_field(it,"pred_score")),"anomaly_map":_normalize_map(_field(it,"anomaly_map")),"pred_label":_scalar(_field(it,"pred_label"))})
                continue
            except Exception as e:
                raise RuntimeError("Could not flatten Anomalib predictions") from e
        paths=list(paths) if not isinstance(paths,str) else [paths]
        sarr=_to_numpy(scores); marr=_to_numpy(maps); larr=_to_numpy(labels)
        for i,p in enumerate(paths):
            sc=None if sarr is None else float(np.asarray(sarr[i] if np.ndim(sarr)>0 else sarr).reshape(-1)[0])
            mp=None if marr is None else _normalize_map(marr[i] if np.ndim(marr)>=3 else marr)
            lb=None if larr is None else _scalar(larr[i] if np.ndim(larr)>0 else larr)
            flat.append({"image_path":str(p),"pred_score":sc,"anomaly_map":mp,"pred_label":lb})
    return flat


def _scalar(x):
    if x is None:return None
    a=_to_numpy(x)
    try:return float(np.asarray(a).reshape(-1)[0])
    except Exception:return str(x)


def _normalize_map(x):
    if x is None:return None
    a=np.asarray(_to_numpy(x),dtype=np.float32)
    while a.ndim>2 and a.shape[0]==1: a=a[0]
    if a.ndim==3 and a.shape[-1]==1:a=a[...,0]
    if a.ndim!=2: a=np.squeeze(a)
    if a.ndim!=2: raise RuntimeError(f"Unexpected anomaly_map shape: {a.shape}")
    return a.astype(np.float32,copy=False)


def predict_many_with_anomalib(
    cfg: InferConfig,
    paths: list[str|Path],
    preprocess_profile_path: str|Path|None=None,
    metadata: list[dict]|None=None,
    paths_are_prepared: bool=False,
    imagenet_dir: str|Path|None=None,
) -> list[dict]:
    """Run EfficientAD predict without Anomalib's visualizer side effects.

    Raw images are standardized with the V6 profile unless `paths_are_prepared=True`.
    Numeric filenames are used in a temp directory so results can be restored to input order.
    """
    paths=[Path(p).expanduser().resolve() for p in paths]
    if not paths:return []
    if metadata is not None and len(metadata)!=len(paths): raise ValueError("metadata length mismatch")
    if not paths_are_prepared and preprocess_profile_path is None: raise ValueError("preprocess_profile_path is required for raw images")
    PredictDataset,_,_=_import_anomalib(); device=_device(cfg.device)
    from ..preprocess import standardize_image
    with tempfile.TemporaryDirectory(prefix="mvhd_v64_predict_") as td:
        root=Path(td); info=[]
        for i,p in enumerate(paths):
            dest=root/f"{i:06d}__{p.stem}.png"
            md=metadata[i] if metadata else {}
            if paths_are_prepared:
                # Re-encode, rather than symlink, so Colab/Windows behavior is identical.
                rgb=np.asarray(Image.open(p).convert("RGB")); Image.fromarray(rgb).save(dest,optimize=False)
                info.append({"source_path":str(p),"prepared_path":str(p),"inspection_group_used":md.get("inspection_group","GENERIC"),"alignment_score":md.get("alignment_score_prepared")})
            else:
                s=standardize_image(p,preprocess_profile_path,md.get("inspection_group","GENERIC"),md.get("gt_mask_path")); Image.fromarray(s.rgb).save(dest,optimize=False)
                info.append({"source_path":str(p),"prepared_path":None,"inspection_group_used":s.inspection_group,"alignment_score":float(s.alignment_score),"standardized_rgb":s.rgb,"standardized_gt_mask":s.gt_mask})
        ds=PredictDataset(path=str(root),image_size=(cfg.image_size,cfg.image_size))
        model=_new_model(cfg.model,imagenet_dir=imagenet_dir)
        engine=_predict_engine(device)
        preds=engine.predict(model=model,dataset=ds,ckpt_path=str(cfg.checkpoint())) or []
        flat=_flatten_predictions(preds)
        if len(flat)!=len(paths): raise RuntimeError(f"Prediction count mismatch: {len(flat)} != {len(paths)}")
        ordered=[None]*len(paths)
        for pred in flat:
            name=Path(pred.get("image_path") or "").name
            try: idx=int(name.split("__",1)[0])
            except Exception: idx=len([x for x in ordered if x is not None])
            rec={**info[idx],**pred}; ordered[idx]=rec
        if any(x is None for x in ordered): raise RuntimeError("Could not restore prediction order")
        return ordered
