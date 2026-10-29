from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import json, math
import cv2
import numpy as np
from PIL import Image
from .array_codec import encode_array, decode_array
from .config import SCHEMA_VERSION

@dataclass
class Standardized:
    rgb: np.ndarray
    surface_mask: np.ndarray
    inspection_mask: np.ndarray
    current_object_mask: np.ndarray
    inspection_group: str
    alignment_score: float
    warp: np.ndarray
    transform: dict
    gt_mask: np.ndarray | None = None


def _border_pixels(img: np.ndarray, frac: float = .03) -> np.ndarray:
    h,w=img.shape[:2]; b=max(4,int(round(min(h,w)*frac)))
    return np.concatenate([img[:b].reshape(-1,3), img[-b:].reshape(-1,3), img[:,:b].reshape(-1,3), img[:,-b:].reshape(-1,3)], axis=0)


def _largest_central(mask: np.ndarray) -> np.ndarray:
    m=(mask>0).astype(np.uint8); n,lab,stats,cent=cv2.connectedComponentsWithStats(m,8)
    if n<=1: return m*255
    h,w=m.shape; cx,cy=w/2,h/2; best=None; bs=-1.0
    for i in range(1,n):
        area=float(stats[i,cv2.CC_STAT_AREA])
        if area < .02*h*w: continue
        x,y=cent[i]; d=((x-cx)/w)**2+((y-cy)/h)**2; s=area/(1+3*d)
        if s>bs: bs=s; best=i
    if best is None: best=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    return ((lab==best).astype(np.uint8)*255)


def detect_product(img_bgr: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    border=_border_pixels(img_bgr).astype(np.float32); bg=np.median(border,axis=0)
    dist=np.sqrt(((img_bgr.astype(np.float32)-bg)**2).sum(2)); d8=np.clip(dist,0,255).astype(np.uint8)
    otsu,_=cv2.threshold(d8,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    mask=(dist>max(18.,float(otsu)*.82)).astype(np.uint8)*255
    gray=cv2.cvtColor(img_bgr,cv2.COLOR_BGR2GRAY)
    bgpix=np.uint8([[np.clip(bg,0,255).astype(np.uint8)]])
    bg_gray=float(cv2.cvtColor(bgpix,cv2.COLOR_BGR2GRAY)[0,0])
    if bg_gray>=150:
        mask=cv2.bitwise_or(mask,(gray<max(80.,bg_gray-28.)).astype(np.uint8)*255)
    k3=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)); k5=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,k3)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,k5,iterations=2)
    return _largest_central(mask), bg


def coarse_standardize(path: str | Path, size: int=256) -> tuple[np.ndarray,np.ndarray,dict]:
    img=cv2.imread(str(path),cv2.IMREAD_COLOR)
    if img is None: raise FileNotFoundError(str(path))
    mask,bg=detect_product(img); ys,xs=np.where(mask>0)
    if not len(xs): raise RuntimeError(f"제품 영역을 인식하지 못했습니다: {path}")
    x0,x1,y0,y1=int(xs.min()),int(xs.max()),int(ys.min()),int(ys.max())
    bw,bh=x1-x0+1,y1-y0+1; mx=max(2,int(bw*.025)); my=max(2,int(bh*.025))
    x0=max(0,x0-mx); x1=min(img.shape[1]-1,x1+mx); y0=max(0,y0-my); y1=min(img.shape[0]-1,y1+my)
    crop=img[y0:y1+1,x0:x1+1]; cm=mask[y0:y1+1,x0:x1+1]
    ch,cw=crop.shape[:2]; scale=min(size/max(cw,1),size/max(ch,1)); nw,nh=max(1,int(round(cw*scale))),max(1,int(round(ch*scale)))
    r=cv2.resize(crop,(nw,nh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    rm=cv2.resize(cm,(nw,nh),interpolation=cv2.INTER_NEAREST)
    canvas=np.zeros((size,size,3),np.uint8); canvas[:]=np.clip(bg,0,255).astype(np.uint8)
    om=np.zeros((size,size),np.uint8); ox,oy=(size-nw)//2,(size-nh)//2
    canvas[oy:oy+nh,ox:ox+nw]=r; om[oy:oy+nh,ox:ox+nw]=rm
    tf={"src_shape": list(img.shape[:2]), "crop_xyxy":[x0,y0,x1,y1], "scale":float(scale), "resize_wh":[nw,nh], "offset_xy":[ox,oy], "size":size}
    return canvas,(om>0).astype(np.uint8),tf


def _apply_coarse_to_mask(mask_path: str | Path, tf: dict) -> np.ndarray:
    m=cv2.imread(str(mask_path),cv2.IMREAD_GRAYSCALE)
    if m is None: raise FileNotFoundError(str(mask_path))
    x0,y0,x1,y1=tf["crop_xyxy"]; nw,nh=tf["resize_wh"]; ox,oy=tf["offset_xy"]; size=tf["size"]
    crop=m[y0:y1+1,x0:x1+1]
    r=cv2.resize(crop,(nw,nh),interpolation=cv2.INTER_NEAREST)
    out=np.zeros((size,size),np.uint8); out[oy:oy+nh,ox:ox+nw]=r
    return (out>127).astype(np.uint8)


def _edge(gray: np.ndarray, valid: np.ndarray) -> np.ndarray:
    sx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3); sy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    return cv2.magnitude(sx,sy)*valid.astype(np.float32)


def _align(canvas_bgr: np.ndarray, obj_mask: np.ndarray, ref_gray: np.ndarray, surface_mask: np.ndarray, max_shift: float=12.0):
    gray=cv2.cvtColor(canvas_bgr,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.
    valid=((obj_mask>0)&(surface_mask>0)).astype(np.float32)
    se=_edge(gray,valid); te=_edge(ref_gray.astype(np.float32),valid)
    try:
        shift,response=cv2.phaseCorrelate(te,se); dx,dy=float(shift[0]),float(shift[1])
        if abs(dx)>max_shift or abs(dy)>max_shift or not np.isfinite(dx+dy): dx=dy=0.; response=0.
    except Exception:
        dx=dy=response=0.
    warp=np.array([[1,0,-dx],[0,1,-dy]],np.float32)
    b=cv2.warpAffine(canvas_bgr,warp,(canvas_bgr.shape[1],canvas_bgr.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    m=cv2.warpAffine(obj_mask.astype(np.uint8),warp,(obj_mask.shape[1],obj_mask.shape[0]),flags=cv2.INTER_NEAREST,borderValue=0)
    iou=float(((m>0)&(surface_mask>0)).sum()/max(1,((m>0)|(surface_mask>0)).sum()))
    score=float(max(0.,response)+.30*iou)
    return b,(m>0).astype(np.uint8),score,warp


def _decode_profile(profile_or_path: dict | str | Path) -> dict:
    obj=profile_or_path if isinstance(profile_or_path,dict) else json.loads(Path(profile_or_path).read_text(encoding="utf-8"))
    out={**obj,"groups":{}}
    for name,g in obj["groups"].items():
        gg=dict(g)
        for k in ("reference_bgr","reference_gray","surface_mask","master_mask"):
            if isinstance(gg.get(k),dict): gg[k]=decode_array(gg[k])
        out["groups"][name]=gg
    return out


def _group_for(profile: dict, preferred: str) -> str:
    if preferred in profile["groups"]: return preferred
    if "GENERIC" in profile["groups"]: return "GENERIC"
    return next(iter(profile["groups"]))


def standardize_image(path: str | Path, profile_or_path: dict | str | Path, inspection_group: str="GENERIC", gt_mask_path: str | None=None) -> Standardized:
    prof=_decode_profile(profile_or_path)
    canvas,obj,tf=coarse_standardize(path,int(prof["image_size"])); group=_group_for(prof,inspection_group); g=prof["groups"][group]
    b,m,align_score,warp=_align(canvas,obj,g["reference_gray"],g["surface_mask"])
    gt=None
    if gt_mask_path:
        raw_gt=_apply_coarse_to_mask(gt_mask_path,tf)
        gt=cv2.warpAffine(raw_gt.astype(np.uint8),warp,(raw_gt.shape[1],raw_gt.shape[0]),flags=cv2.INTER_NEAREST,borderValue=0)
        gt=(gt>0).astype(np.uint8)
    rgb=cv2.cvtColor(b,cv2.COLOR_BGR2RGB)
    return Standardized(rgb=rgb, surface_mask=(g["surface_mask"]>0).astype(np.uint8), inspection_mask=(g["master_mask"]>0).astype(np.uint8), current_object_mask=m, inspection_group=group, alignment_score=align_score, warp=warp, transform=tf, gt_mask=gt)


def _first_pass_reference(paths: list[Path], size: int) -> tuple[np.ndarray,np.ndarray,list[np.ndarray]]:
    canvases=[]; masks=[]
    for p in paths:
        c,m,_=coarse_standardize(p,size); canvases.append(c); masks.append(m)
    stack=np.stack(canvases,axis=0)
    ref=np.median(stack,axis=0).astype(np.uint8)
    occupancy=np.mean(np.stack(masks,axis=0)>0,axis=0)
    surface=(occupancy>=.90).astype(np.uint8)
    if surface.mean()<.05: surface=(occupancy>=.75).astype(np.uint8)
    return ref,surface,masks


def _build_group(paths: list[Path], size: int=256, halo_px: int=3) -> dict:
    ref0,surface0,_=_first_pass_reference(paths,size)
    rg0=cv2.cvtColor(ref0,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.
    aligned=[]; aligned_masks=[]; scores=[]
    for p in paths:
        c,m,_=coarse_standardize(p,size); b,am,sc,_=_align(c,m,rg0,surface0); aligned.append(b); aligned_masks.append(am); scores.append(sc)
    ref=np.median(np.stack(aligned,axis=0),axis=0).astype(np.uint8)
    ref_gray=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.
    occupancy=np.mean(np.stack(aligned_masks,axis=0)>0,axis=0)
    surface=(occupancy>=.90).astype(np.uint8)
    if surface.mean()<.05: surface=(occupancy>=.75).astype(np.uint8)
    k=2*halo_px+1
    master=(cv2.dilate(surface.astype(np.uint8),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k)))>0).astype(np.uint8)
    return {"reference_bgr":ref,"reference_gray":ref_gray,"surface_mask":surface,"master_mask":master,"inspection_halo_px":halo_px,"count":len(paths),"median_alignment_score":float(np.median(scores) if scores else 0.)}


def build_preprocess_profile(protocol: dict, output_path: str | Path, image_size: int=256, halo_px: int=3) -> dict:
    train=[r for r in protocol["records"] if r["split"]=="train" and r["label"]=="good"]
    if not train: raise RuntimeError("No TRAIN GOOD records")
    by=defaultdict(list)
    for r in train: by[r["inspection_group"]].append(Path(r["path"]))
    # A global fallback is useful only when specific CAM/View groups exist. Current generic datasets naturally stay GENERIC-only.
    groups={}
    if set(by)!={"GENERIC"}:
        groups["GENERIC"]=_build_group([Path(r["path"]) for r in train],image_size,halo_px)
    for name,paths in by.items(): groups[name]=_build_group(paths,image_size,halo_px)
    encoded={}
    for name,g in groups.items():
        encoded[name]={
            "reference_bgr":encode_array(g["reference_bgr"]), "reference_gray":encode_array(g["reference_gray"]),
            "surface_mask":encode_array(g["surface_mask"]), "master_mask":encode_array(g["master_mask"]),
            "inspection_halo_px":g["inspection_halo_px"], "count":g["count"], "median_alignment_score":g["median_alignment_score"],
        }
    obj={"schema_version":SCHEMA_VERSION,"kind":"preprocess_profile","image_size":image_size,"groups":encoded,"inspection_policy":"stable GOOD surface + narrow boundary halo for burr/edge defects; far background and stable inner openings excluded"}
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    return obj


def prepare_standardized_dataset(protocol: dict, profile_path: str | Path, run_root: str | Path) -> dict:
    run_root=Path(run_root); prepared=run_root/"prepared"; prepared.mkdir(parents=True,exist_ok=True)
    counters=defaultdict(int)
    for r in protocol["records"]:
        s=standardize_image(r["path"],profile_path,r["inspection_group"],r.get("gt_mask_path"))
        key=(r["split"],r["label"]); counters[key]+=1
        stem=Path(r["path"]).stem; digest=__import__('hashlib').sha1(r["relative_path"].encode()).hexdigest()[:8]
        rel=Path(r["split"])/r["label"]/f"{counters[key]:04d}_{stem}_{digest}.png"
        out=prepared/rel; out.parent.mkdir(parents=True,exist_ok=True); Image.fromarray(s.rgb).save(out,optimize=False)
        r["prepared_relative_path"]=str(Path("prepared")/rel)
        r["prepared_path"]=str(out.resolve())
        r["alignment_score_prepared"]=float(s.alignment_score)
        if s.gt_mask is not None:
            mrel=Path("prepared_masks")/r["split"]/f"{out.stem}.png"; mout=run_root/mrel; mout.parent.mkdir(parents=True,exist_ok=True)
            Image.fromarray((s.gt_mask*255).astype(np.uint8)).save(mout,optimize=False); r["prepared_gt_mask_path"]=str(mout.resolve())
    return protocol
