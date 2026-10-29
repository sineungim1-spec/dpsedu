from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional
import json

RUNTIME_VERSION = "V6.9-PF1 ScoreFirst"
SCHEMA_VERSION = 6.9

@dataclass
class DatasetSpec:
    root: str | Path
    # V6.3-compatible names
    good_dirname: str = "good"
    bad_dirname: str = "bad"
    # Optional aliases accepted by some older teaching cells
    good_dir: Optional[str] = None
    bad_dir: Optional[str] = None
    defect_mask_dir: str = "defect_masks"
    default_view: Optional[str] = None

    def resolved_root(self) -> Path:
        return Path(self.root).expanduser().resolve()

    def good_name(self) -> str:
        return self.good_dir or self.good_dirname

    def bad_name(self) -> str:
        return self.bad_dir or self.bad_dirname

@dataclass
class TrainConfig:
    model: str = "efficientad"
    dataset: DatasetSpec = field(default_factory=lambda: DatasetSpec(root="."))
    # V6.3 used out_dir. output_dir is kept as an optional alias.
    out_dir: str | Path = "/content/ai_vision/outputs"
    output_dir: str | Path | None = None
    image_size: int = 256
    batch_size: int = 1
    num_workers: int = 0
    seed: int = 42
    device: str = "cuda"
    train_good_only: bool = True
    max_epochs: int = 2
    lr: float = 1e-4
    optimizer_name: str = "adam"
    efficientad_imagenet_dir: str | Path = "./datasets/imagenette"
    # Shared config fields retained for notebook compatibility. They are not used by EfficientAD itself.
    coreset_fraction: float = 0.1
    knn_k: int = 9
    weight_decay: float = 1e-5
    ckpt_name: str = "model.ckpt"

    def validate(self) -> None:
        if self.model.lower() not in {"efficientad", "efficient_ad", "efficient-ad"}:
            raise ValueError("V6.6 runtime currently supports EfficientAD only.")
        if self.image_size != 256:
            raise ValueError("V6.6 automotive runtime is calibrated for image_size=256.")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.max_epochs < 1:
            raise ValueError("max_epochs must be >= 1")
        if not self.train_good_only:
            raise ValueError("EfficientAD V6.6 protocol requires train_good_only=True")
        if self.optimizer_name.lower() != "adam":
            raise ValueError("EfficientAD V6.6 uses Anomalib's Adam optimizer configuration.")

    def base_output_dir(self) -> Path:
        return Path(self.output_dir if self.output_dir is not None else self.out_dir).expanduser().resolve()

    def to_jsonable(self) -> dict:
        d = asdict(self)
        d["dataset"]["root"] = str(d["dataset"]["root"])
        d["efficientad_imagenet_dir"] = str(d["efficientad_imagenet_dir"])
        d["out_dir"] = str(d["out_dir"])
        if d["output_dir"] is not None: d["output_dir"] = str(d["output_dir"])
        d["runtime_version"] = RUNTIME_VERSION
        d["schema_version"] = SCHEMA_VERSION
        d["requested_max_epochs"] = int(self.max_epochs)
        d["effective_max_epochs"] = int(self.max_epochs)  # no hidden minimum
        return d

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_jsonable(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

@dataclass
class InferConfig:
    model: str
    checkpoint_path: str | Path
    image_size: int = 256
    device: str = "cuda"

    def checkpoint(self) -> Path:
        return Path(self.checkpoint_path).expanduser().resolve()
