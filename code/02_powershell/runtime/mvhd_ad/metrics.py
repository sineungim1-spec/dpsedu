from __future__ import annotations
import math
import numpy as np
try:
    from sklearn.metrics import roc_auc_score, average_precision_score
except Exception:
    roc_auc_score = average_precision_score = None


def binary_metrics(labels, scores, threshold: float) -> dict:
    y=np.asarray(labels,dtype=np.int8); s=np.asarray(scores,dtype=float); pred=(s>=float(threshold)).astype(np.int8)
    tp=int(((pred==1)&(y==1)).sum()); tn=int(((pred==0)&(y==0)).sum()); fp=int(((pred==1)&(y==0)).sum()); fn=int(((pred==0)&(y==1)).sum())
    precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.; specificity=tn/(tn+fp) if tn+fp else 0.; acc=(tp+tn)/len(y) if len(y) else 0.; f1=2*precision*recall/(precision+recall) if precision+recall else 0.
    return {"threshold":float(threshold),"accuracy":acc,"precision":precision,"recall":recall,"specificity":specificity,"f1":f1,"tn":tn,"fp":fp,"fn":fn,"tp":tp,"n":int(len(y))}


def ranking_metrics(labels, scores) -> dict:
    y=np.asarray(labels,dtype=np.int8); s=np.asarray(scores,dtype=float)
    out={"image_AUROC":None,"image_AUPR":None}
    if len(np.unique(y))<2: return out
    if roc_auc_score is not None:
        out["image_AUROC"]=float(roc_auc_score(y,s)); out["image_AUPR"]=float(average_precision_score(y,s)); return out
    # Small dependency-free fallback: rank-based AUROC, trapezoidal PR approximation.
    order=np.argsort(s); ranks=np.empty_like(order,dtype=float); ranks[order]=np.arange(1,len(s)+1)
    pos=y==1; n1=int(pos.sum()); n0=len(y)-n1
    out["image_AUROC"]=float((ranks[pos].sum()-n1*(n1+1)/2)/(n1*n0)) if n1 and n0 else None
    desc=np.argsort(-s); yy=y[desc]; tp=np.cumsum(yy==1); fp=np.cumsum(yy==0); rec=tp/max(1,n1); pre=tp/np.maximum(1,tp+fp)
    out["image_AUPR"]=float(np.trapz(np.r_[1.,pre],np.r_[0.,rec]))
    return out


def full_metrics(labels, scores, threshold: float) -> dict:
    return {**ranking_metrics(labels,scores), **binary_metrics(labels,scores,threshold)}
