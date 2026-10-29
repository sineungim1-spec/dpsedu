from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json, shutil
from .config import TrainConfig, RUNTIME_VERSION
from .protocol import build_protocol, save_protocol
from .preprocess import build_preprocess_profile, prepare_standardized_dataset


def _imports():
    try:
        from anomalib.data import Folder
        from anomalib.engine import Engine
        from anomalib.models import EfficientAd
        return Folder,Engine,EfficientAd
    except Exception as e:
        raise RuntimeError("Anomalib is required. Run: pip install -r company_runtime/requirements.txt") from e


def mvhd_train(cfg: TrainConfig) -> Path:
    cfg.validate(); root=cfg.dataset.resolved_root()
    if cfg.output_dir is not None:
        run_root=Path(cfg.output_dir).expanduser().resolve()
    else:
        stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
        run_root=cfg.base_output_dir()/f"efficientad_v64__{stamp}"
    run_root.mkdir(parents=True,exist_ok=True)
    print(f"[{RUNTIME_VERSION}] Runtime      : {RUNTIME_VERSION}")
    print(f"[{RUNTIME_VERSION}] Data root    : {root}")
    print(f"[{RUNTIME_VERSION}] Epochs       : requested={cfg.max_epochs}, effective={cfg.max_epochs} (no hidden minimum)")
    print("[1/5] Building leakage-free TRAIN/CALIBRATION/FINAL TEST protocol ...")
    protocol=build_protocol(cfg.dataset,cfg.seed); save_protocol(protocol,run_root/"protocol_v6.json")
    print("       counts:",protocol["counts"])
    if protocol["leakage_check"]["capture_group_leakage_count"]:
        raise RuntimeError("Capture-group leakage detected")
    print("[2/5] Building V6.4 product/surface/boundary preprocess profile from TRAIN GOOD ...")
    pp=run_root/"preprocess_profile_v6.json"; build_preprocess_profile(protocol,pp,cfg.image_size,halo_px=3)
    protocol=prepare_standardized_dataset(protocol,pp,run_root); save_protocol(protocol,run_root/"protocol_v6.json")
    cfg_path=cfg.save(run_root/"train_config.json")
    print("[3/5] Preparing Anomalib Folder datamodule (TRAIN=GOOD only; CALIBRATION used for validation) ...")
    Folder,Engine,EfficientAd=_imports(); prepared=run_root/"prepared"
    dm=Folder(
        name="automotive_part_v64",
        root=str(prepared),
        normal_dir="train/good",
        abnormal_dir="calibration/bad",
        normal_test_dir="calibration/good",
        train_batch_size=cfg.batch_size,
        eval_batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        seed=cfg.seed,
    )
    print("[4/5] Training EfficientAD ...")
    # IMPORTANT V6.4.2:
    # Do not pass a short-string model size here.
    # anomalib 2.3.3 can reject that representation with
    # "not a valid EfficientAdModelSize".
    # Omitting model_size uses EfficientAd's official default
    # EfficientAdModelSize.S (the Small model), keeping train/inference consistent.
    model=EfficientAd(
        imagenet_dir=str(Path(cfg.efficientad_imagenet_dir).expanduser()),
        lr=cfg.lr,
        weight_decay=cfg.weight_decay,
        visualizer=False,  # prevents automatic test/predict PNG generation
    )
    device=str(cfg.device).lower()
    try:
        import torch
        accelerator="gpu" if device.startswith("cuda") and torch.cuda.is_available() else "cpu"
    except Exception: accelerator="cpu"
    # Checkpointing is intentionally left enabled/default. V6.4 only removes the bad
    # `enable_checkpointing=False` from inference, not from training.
    # V6.4.3 Colab/Kaggle Rich recursion hotfix
    #
    # Anomalib/Lightning의 기본 Rich progress 환경에서 EfficientAD가
    # pretrained teacher weights를 내려받을 때, 외부 tqdm 출력과 Rich/IPython
    # stream proxy가 서로 flush를 재귀 호출하여 RecursionError가 발생할 수 있습니다.
    #
    # Lightning의 표준 TQDMProgressBar를 명시적으로 사용하면 Rich stream proxy를
    # 우회하여 Anomalib의 weight-download tqdm과 충돌하지 않습니다.
    from lightning.pytorch.callbacks import TQDMProgressBar

    engine=Engine(
        accelerator=accelerator,
        devices=1,
        max_epochs=int(cfg.max_epochs),
        default_root_dir=str(run_root/"anomalib_results"),
        logger=False,
        callbacks=[TQDMProgressBar(refresh_rate=1)],
    )
    engine.fit(model=model,datamodule=dm)
    target=run_root/cfg.ckpt_name
    # Explicit final checkpoint guarantees a stable path regardless of Anomalib's versioned result folder.
    engine.trainer.save_checkpoint(str(target),weights_only=False)
    if not target.exists():
        cands=sorted(run_root.rglob("*.ckpt"),key=lambda p:p.stat().st_mtime,reverse=True)
        if not cands: raise RuntimeError("Training finished but no checkpoint was produced")
        shutil.copy2(cands[0],target)
    print(f"[5/5] Saved checkpoint: {target}")
    return target


class TrainerFacade:
    def fit(self,cfg: TrainConfig) -> Path:
        return mvhd_train(cfg)

trainer=TrainerFacade()
