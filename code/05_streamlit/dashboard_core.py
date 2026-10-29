
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import numpy as np
from PIL import Image, ImageDraw


def install_pathlib_pickle_compat() -> None:
    """Compatibility for checkpoints containing Python 3.13 pathlib._local refs."""
    import os
    import pathlib
    import sys
    import types

    shim = sys.modules.get("pathlib._local")
    if shim is None:
        shim = types.ModuleType("pathlib._local")
        shim.__package__ = "pathlib"
        shim.__doc__ = "Compatibility shim for Python 3.13 pathlib pickles."

        for name in (
            "Path",
            "PurePath",
            "PosixPath",
            "WindowsPath",
            "PurePosixPath",
            "PureWindowsPath",
        ):
            if hasattr(pathlib, name):
                setattr(shim, name, getattr(pathlib, name))

        # Colab/Linux checkpoint -> Windows runtime compatibility
        if os.name == "nt":
            shim.PosixPath = pathlib.WindowsPath

        sys.modules["pathlib._local"] = shim


install_pathlib_pickle_compat()

class BundleValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BundleContract:
    root: Path
    ckpt_path: Path
    model_info: dict[str, Any]
    config: dict[str, Any]
    threshold_info: dict[str, Any]
    metrics: dict[str, Any]
    dataset: dict[str, Any]
    project_name: str
    model_name: str
    image_size: int
    learning_rate: float
    threshold_path: Path
    above_is_ng: bool
    warnings: tuple[str, ...]

    @property
    def threshold(self) -> float:
        # Legacy compatibility: for 3-zone bundles this is review_low.
        return float(self.threshold_info["threshold"])

    @property
    def threshold_mode(self) -> str:
        return str(self.threshold_info.get("mode", "TWO_ZONE"))

    @property
    def is_three_zone(self) -> bool:
        return self.threshold_mode == "THREE_ZONE"

    @property
    def review_low(self) -> float | None:
        v = self.threshold_info.get("review_low")
        return float(v) if v is not None else None

    @property
    def ng_high(self) -> float | None:
        v = self.threshold_info.get("ng_high")
        return float(v) if v is not None else None

    @property
    def score_mode(self) -> str:
        # Candidate4/PF1 bundle: use its decision head + ROI/localization artifacts.
        needed = (
            "decision_model.json",
            "localization_profile_v6.json",
            "preprocess_profile_v6.json",
        )
        if all(_find_metadata_json(self.root, name) is not None for name in needed):
            return "PF1_DECISION"

        # Generic education/company bundles may explicitly preserve the raw
        # Anomalib score by disabling the post-processor.  This must be honored
        # because their saved thresholds were calibrated in that score space.
        declared = str(
            self.threshold_info.get("score_mode")
            or self.config.get("score_mode")
            or ""
        ).upper()
        post_processor = self.config.get("post_processor", None)
        if ("RAW_NO_POSTPROCESS" in declared
                or "RAW_ANOMALIB_NO_POSTPROCESS" in declared
                or post_processor is False):
            return "RAW_ANOMALIB_NO_POSTPROCESS"
        return "RAW_ANOMALIB"


def ascii_runtime_root() -> Path:
    """Use an ASCII-only path so Anomalib path validation does not see Korean project folders."""
    candidates = []
    if os.name == "nt":
        candidates += [Path("C:/AI_VISION_RUNTIME")]
    candidates += [Path(tempfile.gettempdir()) / "AI_VISION_RUNTIME", Path.cwd() / "_AI_RUNTIME_ASCII"]
    for p in candidates:
        try:
            s = str(p)
            if all(ord(ch) < 128 and ch.isprintable() for ch in s):
                p.mkdir(parents=True, exist_ok=True)
                test = p / ".write_test"
                test.write_text("ok", encoding="ascii")
                test.unlink(missing_ok=True)
                return p.resolve()
        except Exception:
            pass
    raise RuntimeError("영문 경로의 임시 런타임 폴더를 만들 수 없습니다.")


RUNTIME_ROOT = ascii_runtime_root()

# One teacher PC serves many browser sessions.
# Up to 3 heavy EfficientAD inference jobs run concurrently.
# Additional requests wait in a queue so the instructor PC is not overloaded.
WORKSHOP_MAX_CONCURRENT_INFERENCES = 3


class WorkshopInferencePool:
    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self._semaphore = threading.BoundedSemaphore(value=self.limit)
        self._lock = threading.Lock()
        self._active = 0
        self._waiting = 0
        self._completed = 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "limit": self.limit,
                "active": self._active,
                "waiting": self._waiting,
                "completed": self._completed,
            }

    def acquire(self, timeout: float = 300.0) -> tuple[bool, float]:
        started = time.perf_counter()
        with self._lock:
            self._waiting += 1

        acquired = False
        try:
            acquired = self._semaphore.acquire(timeout=timeout)
        finally:
            with self._lock:
                self._waiting -= 1
                if acquired:
                    self._active += 1

        return acquired, time.perf_counter() - started

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
            self._completed += 1
        self._semaphore.release()


WORKSHOP_INFERENCE_POOL = WorkshopInferencePool(
    WORKSHOP_MAX_CONCURRENT_INFERENCES
)


def get_workshop_inference_status() -> dict[str, int]:
    return WORKSHOP_INFERENCE_POOL.snapshot()


def bundle_identity(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_extract(zip_path: Path, target: Path) -> None:
    target_resolved = target.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # Only expected plain files/directories; reject absolute/traversal paths.
            member_path = (target / member.filename).resolve()
            try:
                member_path.relative_to(target_resolved)
            except ValueError as exc:
                raise BundleValidationError(f"위험한 ZIP 경로: {member.filename}") from exc
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
            else:
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(member_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _detect_bundle_root(extracted: Path) -> Path:
    if (extracted / "model.ckpt").is_file():
        return extracted
    candidates = []
    for p in extracted.rglob("model.ckpt"):
        if p.is_file() and p.parent not in candidates:
            candidates.append(p.parent)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise BundleValidationError("model.ckpt를 가진 bundle 후보 폴더가 여러 개입니다.")
    raise BundleValidationError("bundle 안에서 model.ckpt를 찾지 못했습니다.")


def extract_bundle_bytes(data: bytes, namespace: str = "local") -> tuple[str, Path]:
    bundle_id = bundle_identity(data)
    package_dir = RUNTIME_ROOT / namespace / "bundles" / bundle_id
    content = package_dir / "content"
    marker = package_dir / ".ok"
    if marker.exists():
        return bundle_id, _detect_bundle_root(content)

    if package_dir.exists():
        shutil.rmtree(package_dir, ignore_errors=True)
    content.mkdir(parents=True, exist_ok=True)
    zip_path = package_dir / "bundle.zip"
    zip_path.write_bytes(data)
    try:
        _safe_extract(zip_path, content)
        root = _detect_bundle_root(content)
        marker.write_text("ok", encoding="ascii")
        return bundle_id, root
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        raise


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BundleValidationError(f"필수 파일 누락: {path.name}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BundleValidationError(f"JSON 읽기 실패: {path.name}: {exc}") from exc
    if not isinstance(obj, dict):
        raise BundleValidationError(f"JSON 최상위 형식 오류: {path.name}")
    return obj



def _load_json_optional(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BundleValidationError(f"JSON 읽기 실패: {path.name}: {exc}") from exc
    return obj if isinstance(obj, dict) else {}


def _first_value(obj: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return default


def _find_metadata_json(root: Path, filename: str) -> Path | None:
    for p in (root / "artifacts" / filename, root / filename):
        if p.is_file():
            return p
    matches = [p for p in root.rglob(filename) if p.is_file()]
    return matches[0] if len(matches) == 1 else None


def _resolve_threshold_path(root: Path, model_info: dict[str, Any]) -> Path:
    rel = _first_value(model_info, ("threshold_file", "threshold_path"), None)
    if rel:
        rel_path = Path(str(rel))
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise BundleValidationError("threshold 파일 경로가 안전하지 않습니다.")
        p = root / rel_path
        if p.is_file():
            return p
    for p in (root / "artifacts" / "threshold.json", root / "threshold.json"):
        if p.is_file():
            return p
    matches = [p for p in root.rglob("threshold.json") if p.is_file()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise BundleValidationError("threshold.json 후보가 여러 개입니다.")
    raise BundleValidationError("bundle에서 threshold.json을 찾지 못했습니다.")


def _normalize_threshold(raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    # New Candidate4-style 3-zone contract. It may not contain a legacy `threshold` key.
    review_low = _safe_float(raw.get("review_low"))
    ng_high = _safe_float(raw.get("ng_high"))
    if review_low is not None and ng_high is not None:
        if ng_high < review_low:
            raise BundleValidationError("ng_high는 review_low보다 작을 수 없습니다.")
        out = dict(raw)
        out["review_low"] = review_low
        out["ng_high"] = ng_high
        out["threshold"] = _safe_float(raw.get("threshold"))
        if out["threshold"] is None:
            out["threshold"] = review_low
        out["above_is_ng"] = True
        out["mode"] = "THREE_ZONE"
        out.setdefault(
            "rule",
            "score < review_low => OK; review_low <= score < ng_high => REVIEW; score >= ng_high => NG",
        )
        return out, True

    # Existing legacy 2-zone contract: keep the original behavior unchanged.
    value = _first_value(raw, ("threshold", "operational_threshold", "image_threshold"), None)
    if value is None:
        raise BundleValidationError("threshold.json에서 Threshold 숫자를 찾지 못했습니다.")
    try:
        threshold = float(value)
    except Exception as exc:
        raise BundleValidationError("Threshold가 숫자가 아닙니다.") from exc
    if not np.isfinite(threshold):
        raise BundleValidationError("Threshold가 유효한 숫자가 아닙니다.")

    if isinstance(raw.get("above_is_ng"), bool):
        above_is_ng = bool(raw["above_is_ng"])
    else:
        rule = str(_first_value(raw, ("rule", "threshold_rule"), "")).lower()
        compact = rule.replace(" ", "")
        if "score>=threshold" in compact or (">=threshold" in compact and "ng" in compact):
            above_is_ng = True
        elif "score<=threshold" in compact and "ng" in compact:
            above_is_ng = False
        else:
            raise BundleValidationError(
                "Threshold는 찾았지만 OK/NG 판정 규칙을 해석하지 못했습니다. "
                "threshold.json에 rule 또는 above_is_ng가 필요합니다."
            )
    out = dict(raw)
    out["threshold"] = threshold
    out["above_is_ng"] = above_is_ng
    out["mode"] = "TWO_ZONE"
    out.setdefault("rule", "score >= threshold => NG" if above_is_ng else "score <= threshold => NG")
    return out, above_is_ng


def _looks_like_efficientad(model_info: dict[str, Any], config: dict[str, Any]) -> bool | None:
    values = [
        _first_value(config, ("model", "model_name", "model_type"), None),
        _first_value(model_info, ("model", "model_name", "model_type"), None),
    ]
    saw = False
    for v in values:
        if v is None:
            continue
        saw = True
        compact = re.sub(r"[^a-z0-9]", "", str(v).lower())
        if "efficientad" in compact:
            return True
    return False if saw else None


def _metric_value(metrics: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in metrics and metrics[key] is not None:
            return metrics[key]
    return None


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        x = float(v)
        return x if np.isfinite(x) else None
    except Exception:
        return None


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _need(obj: dict[str, Any], keys: list[str], label: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise BundleValidationError(f"{label} 필수 필드 누락: {', '.join(missing)}")


def load_bundle_contract(root: Path) -> BundleContract:
    ckpt = root / "model.ckpt"
    if not ckpt.is_file() or ckpt.stat().st_size < 1024:
        raise BundleValidationError("model.ckpt가 없거나 크기가 비정상적입니다.")

    model_info = _load_json_optional(root / "model_info.json")
    config_file = _load_json_optional(_find_metadata_json(root, "config.json"))
    decision_policy = _load_json_optional(_find_metadata_json(root, "decision_policy.json"))

    # ------------------------------------------------------------------
    # Universal metadata compatibility
    # ------------------------------------------------------------------
    # 4차시 Candidate4 교육용 bundle은 정식 company master처럼
    # model_info.json/config.json/dataset.json을 모두 갖지 않을 수 있습니다.
    # 대신 EDUCATION_SUMMARY.json + preprocess_profile_v6.json +
    # protocol_v6.json 안에 같은 의미의 메타데이터가 들어 있습니다.
    # 범용 Dashboard는 특정 bundle 이름을 하드코딩하지 않고, 존재하는
    # 메타데이터 소스에서 필요한 최소 계약을 합성합니다.
    education_summary = _load_json_optional(_find_metadata_json(root, "EDUCATION_SUMMARY.json"))
    preprocess_profile = _load_json_optional(_find_metadata_json(root, "preprocess_profile_v6.json"))
    if not preprocess_profile:
        preprocess_profile = _load_json_optional(_find_metadata_json(root, "preprocess_profile.json"))
    operating_window = _load_json_optional(_find_metadata_json(root, "operating_window.json"))
    protocol = _load_json_optional(_find_metadata_json(root, "protocol_v6.json"))
    if not protocol:
        protocol = _load_json_optional(_find_metadata_json(root, "protocol.json"))

    # Explicit config.json has the highest priority.  Other files only fill
    # missing values, so legacy/company/screw bundles keep their old behavior.
    config = dict(decision_policy)
    for key in ("model", "model_name", "model_type", "epochs", "max_epochs", "seed"):
        if key not in config and education_summary.get(key) is not None:
            config[key] = education_summary[key]
    if "seed" not in config and protocol.get("seed") is not None:
        config["seed"] = protocol["seed"]
    for source in (preprocess_profile, operating_window):
        if "image_size" not in config and source.get("image_size") is not None:
            config["image_size"] = source["image_size"]
    config.update(config_file)

    metrics = _load_json_optional(_find_metadata_json(root, "metrics.json"))
    dataset = _load_json_optional(_find_metadata_json(root, "dataset.json"))
    if not dataset and protocol:
        # Normalize protocol_v6 into the dataset schema used by the dashboard.
        dataset = {
            "source": protocol.get("data_root"),
            "protocol": protocol.get("protocol"),
            "counts": protocol.get("counts") if isinstance(protocol.get("counts"), dict) else {},
            "leakage_check": protocol.get("leakage_check") if isinstance(protocol.get("leakage_check"), dict) else {},
        }
    provenance = _load_json_optional(_find_metadata_json(root, "provenance.json"))

    threshold_path = _resolve_threshold_path(root, model_info)
    threshold_raw = _load_json(threshold_path)
    threshold_info, above_is_ng = _normalize_threshold(threshold_raw)

    warnings: list[str] = []
    model_check = _looks_like_efficientad(model_info, config)
    if model_check is False:
        detected = _first_value(config, ("model", "model_name", "model_type"), None)
        if detected is None:
            detected = _first_value(model_info, ("model", "model_name", "model_type"), "unknown")
        raise BundleValidationError(
            f"이 대시보드는 EfficientAD model.ckpt를 대상으로 합니다. 감지된 모델: {detected}"
        )
    if model_check is None:
        warnings.append("모델명 메타데이터가 없어 실제 checkpoint 로딩으로 EfficientAD 호환성을 확인합니다.")

    image_size_value = _first_value(config, ("image_size", "input_size"), None)
    if image_size_value is None:
        image_size_value = _first_value(model_info, ("image_size", "input_size"), None)
    if image_size_value is None:
        image_size_value = _first_value(preprocess_profile, ("image_size", "input_size"), None)
    if image_size_value is None:
        image_size_value = _first_value(operating_window, ("image_size", "input_size"), None)
    if image_size_value is None:
        raise BundleValidationError(
            "bundle에서 image_size를 찾지 못했습니다. "
            "config/model_info/preprocess_profile/operating_window 중 하나에 image_size가 필요합니다."
        )
    try:
        if isinstance(image_size_value, (list, tuple)) and image_size_value:
            image_size = int(image_size_value[0])
        elif isinstance(image_size_value, str) and "x" in image_size_value.lower():
            image_size = int(re.split(r"[xX]", image_size_value.strip())[0])
        else:
            image_size = int(image_size_value)
    except Exception as exc:
        raise BundleValidationError("image_size를 정수 크기로 해석하지 못했습니다.") from exc
    if image_size <= 0:
        raise BundleValidationError("image_size가 유효하지 않습니다.")

    try:
        learning_rate = float(_first_value(config, ("learning_rate", "lr"), 1e-4))
    except Exception:
        learning_rate = 1e-4
        warnings.append("learning_rate 메타데이터를 읽지 못해 추론용 기본값 1e-4를 사용합니다.")

    provenance_project = _first_value(
        provenance, ("project", "project_name", "dataset"), None
    )
    summary_project = _first_value(
        education_summary, ("project", "project_name", "master_reference"), None
    )
    protocol_project = _first_value(protocol, ("protocol",), None)
    project_name = str(_first_value(
        model_info,
        ("project", "project_name", "source"),
        _first_value(
            config,
            ("project", "project_name"),
            provenance_project or summary_project or protocol_project or "EfficientAD Project",
        ),
    ))
    model_name = str(_first_value(
        model_info,
        ("model_name", "model_type", "model"),
        _first_value(
            config,
            ("model_name", "model", "model_type"),
            _first_value(education_summary, ("model", "model_name", "model_type"), "EfficientAD"),
        ),
    ))

    version = _first_value(config, ("anomalib_version",), None)
    if version is not None and str(version) != "2.3.3":
        warnings.append(
            f"bundle 메타데이터 anomalib_version={version}; 현재 runtime은 2.3.3입니다. "
            "실제 checkpoint 로딩으로 호환성을 확인합니다."
        )

    gate = _load_json_optional(_find_metadata_json(root, "gate.json"))
    bundle_status = str(gate.get("bundle_status", "")).strip().upper()
    if bundle_status and bundle_status not in {"MASTER", "APPROVED", "PASS"}:
        warnings.append(
            f"bundle 상태가 {bundle_status}입니다. 대시보드 추론은 허용하지만 "
            "검증 완료 MASTER로 표시하지 않습니다."
        )

    deployment_validation = _load_json_optional(
        _find_metadata_json(root, "deployment_validation.json")
    )
    if deployment_validation:
        status = str(deployment_validation.get("status", "")).strip()
        production_ready = deployment_validation.get("production_ready")
        if production_ready is False or status:
            msg = "교육/검증용 bundle"
            if status:
                msg += f" ({status})"
            warnings.append(
                f"{msg}입니다. 대시보드에서 추론은 가능하지만 Production Ready로 표시하지 않습니다."
            )

    if contract_review_low := _safe_float(threshold_info.get("review_low")):
        contract_ng_high = _safe_float(threshold_info.get("ng_high"))
        if contract_ng_high is not None and abs(contract_ng_high - contract_review_low) < 1e-12:
            warnings.append(
                "review_low와 ng_high가 같아 현재 bundle은 실질적으로 OK/NG 2구간처럼 동작합니다. "
                "Dashboard는 저장된 판정규칙을 그대로 사용합니다."
            )

    recipe = _bundle_preprocess_name(BundleContract(
        root=root, ckpt_path=ckpt, model_info=model_info, config=config,
        threshold_info=threshold_info, metrics=metrics, dataset=dataset,
        project_name="", model_name="", image_size=image_size, learning_rate=learning_rate,
        threshold_path=threshold_path, above_is_ng=above_is_ng, warnings=(),
    ))
    if recipe and not ("screw" in recipe.lower() and "orientation" in recipe.lower() and "standard" in recipe.lower()):
        warnings.append(
            f"bundle이 별도 preprocess recipe를 선언했습니다: {recipe}. "
            "현재 대시보드에 전용 구현이 없으면 원본 입력으로 추론합니다."
        )

    metric_threshold = _safe_float(_metric_value(metrics, ("threshold", "operational_threshold", "image_threshold")))
    if threshold_info.get("mode") == "TWO_ZONE" and metric_threshold is not None and abs(metric_threshold - threshold_info["threshold"]) > 1e-9:
        warnings.append("metrics.json과 threshold.json의 Threshold가 다릅니다. 실제 판정에는 threshold.json 값을 사용합니다.")

    return BundleContract(
        root=root,
        ckpt_path=ckpt,
        model_info=model_info,
        config=config,
        threshold_info=threshold_info,
        metrics=metrics,
        dataset=dataset,
        project_name=project_name,
        model_name=model_name,
        image_size=image_size,
        learning_rate=learning_rate,
        threshold_path=threshold_path,
        above_is_ng=above_is_ng,
        warnings=tuple(warnings),
    )


def stage_image_bytes(image_bytes: bytes, original_name: str, namespace: str, bundle_id: str) -> Path:
    ext = Path(original_name).suffix.lower()
    if ext not in {".png",".jpg",".jpeg",".bmp"}:
        ext = ".png"
    h = hashlib.sha256(image_bytes).hexdigest()[:24]
    d = RUNTIME_ROOT / namespace / "inputs" / bundle_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{h}{ext}"
    p.write_bytes(image_bytes)
    return p


PF1_RUNTIME_ROOT = Path(__file__).resolve().parent / "pf1_runtime"

def _load_pf1_visuals(output_dir: Path) -> dict[str, Image.Image]:
    names = {
        "original": "01_original.png",
        "heatmap": "02_heatmap.png",
        "overlay": "03_overlay_masked.png",
        "contour": "04_contour.png",
    }
    out: dict[str, Image.Image] = {}
    for key, name in names.items():
        p = output_dir / name
        if not p.is_file():
            raise RuntimeError(f"PF1 시각화 파일 누락: {name}")
        with Image.open(p) as im:
            out[key] = im.convert("RGB").copy()
    return out

def _bundle_preprocess_name(contract: BundleContract) -> str:
    return str(
        contract.config.get("preprocess")
        or contract.config.get("preprocess_recipe")
        or contract.config.get("input_recipe")
        or ""
    ).strip()


def _screw_object_mask_rgb(image_rgb: np.ndarray) -> tuple[np.ndarray, int]:
    """Object mask used by the screw education bundle's saved preprocessing recipe."""
    import cv2

    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    background = float(np.median(border))
    diff = np.abs(gray.astype(np.float32) - background)
    diff = np.clip(diff, 0, 255).astype(np.uint8)
    _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    object_mask = np.zeros_like(mask)
    if count > 1:
        biggest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        object_mask[labels == biggest] = 255
    return object_mask, int(round(background))


def _screw_crop_square_with_pad(
    image: np.ndarray, mask: np.ndarray, bg: int, image_size: int
) -> np.ndarray:
    import cv2

    ys, xs = np.where(mask > 0)
    if len(xs) < 50:
        return cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_AREA)

    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = int(max(x2 - x1 + 1, y2 - y1 + 1) * 1.28)
    side = max(side, 32)

    sx1 = int(round(cx - side / 2))
    sy1 = int(round(cy - side / 2))
    sx2, sy2 = sx1 + side, sy1 + side
    pad_left, pad_top = max(0, -sx1), max(0, -sy1)
    pad_right = max(0, sx2 - image.shape[1])
    pad_bottom = max(0, sy2 - image.shape[0])

    if any((pad_left, pad_top, pad_right, pad_bottom)):
        image = cv2.copyMakeBorder(
            image,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv2.BORDER_CONSTANT,
            value=(bg, bg, bg),
        )
        sx1 += pad_left
        sx2 += pad_left
        sy1 += pad_top
        sy2 += pad_top

    crop = image[sy1:sy2, sx1:sx2]
    return cv2.resize(crop, (image_size, image_size), interpolation=cv2.INTER_AREA)


def _standardize_screw_rgb(image_rgb: np.ndarray, image_size: int) -> np.ndarray:
    """Exact named recipe used by the screw education bundle.

    This is opt-in only. Other bundles remain untouched.
    """
    import cv2
    import math

    mask, bg = _screw_object_mask_rgb(image_rgb)
    ys, xs = np.where(mask > 0)
    if len(xs) < 50:
        return cv2.resize(image_rgb, (image_size, image_size), interpolation=cv2.INTER_AREA)

    pts = np.column_stack([xs, ys]).astype(np.float32)
    pts -= pts.mean(axis=0, keepdims=True)
    cov = np.cov(pts, rowvar=False)
    values, vectors = np.linalg.eigh(cov)
    axis = vectors[:, np.argmax(values)]
    angle = math.degrees(math.atan2(axis[1], axis[0]))
    while angle >= 90:
        angle -= 180
    while angle < -90:
        angle += 180

    center = (image_rgb.shape[1] / 2, image_rgb.shape[0] / 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rot = cv2.warpAffine(
        image_rgb,
        M,
        (image_rgb.shape[1], image_rgb.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(bg, bg, bg),
    )
    rot_mask = cv2.warpAffine(
        mask,
        M,
        (mask.shape[1], mask.shape[0]),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    ys2, xs2 = np.where(rot_mask > 0)
    if len(xs2) >= 50:
        x1, x2 = int(xs2.min()), int(xs2.max())
        width = max(3, x2 - x1 + 1)
        cut = max(1, width // 3)
        left_area = int((rot_mask[:, x1:x1 + cut] > 0).sum())
        right_area = int((rot_mask[:, x2 - cut + 1:x2 + 1] > 0).sum())
        if right_area > left_area:
            rot = cv2.flip(rot, -1)
            rot_mask = cv2.flip(rot_mask, -1)

    return _screw_crop_square_with_pad(rot, rot_mask, bg, image_size)


def _prepare_bundle_input(
    contract: BundleContract, image_path: Path
) -> tuple[Path, Image.Image | None, str]:
    """Apply only a preprocessing recipe explicitly declared by the bundle.

    Unknown/legacy bundles are passed through unchanged, preserving the dashboard's
    universal behavior.
    """
    recipe = _bundle_preprocess_name(contract).lower()
    if not recipe:
        return image_path, None, "NONE"

    if "screw" in recipe and "orientation" in recipe and "standard" in recipe:
        import cv2

        bgr = cv2.imread(str(image_path))
        if bgr is None:
            raise RuntimeError("검사 이미지를 읽을 수 없습니다.")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        standardized = _standardize_screw_rgb(rgb, int(contract.image_size))

        src_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()[:24]
        recipe_hash = hashlib.sha256(recipe.encode("utf-8")).hexdigest()[:8]
        out_dir = RUNTIME_ROOT / "preprocessed" / recipe_hash
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{src_hash}.png"
        if not out_path.is_file():
            cv2.imwrite(str(out_path), cv2.cvtColor(standardized, cv2.COLOR_RGB2BGR))
        return out_path, Image.fromarray(standardized, "RGB"), "BUNDLE_PREPROCESS_ROI"

    # A bundle may describe a recipe the dashboard does not know yet.  Do not
    # silently invent preprocessing; keep backward compatibility and warn by mode.
    return image_path, None, "DECLARED_UNSUPPORTED"


def _generic_input_guard(contract: BundleContract, image_path: Path) -> dict[str, Any] | None:
    """Apply either the newer min/max guard or the legacy z-score profile."""
    import cv2

    # New education/company schema: input_guard.json with fixed min/max limits.
    limits_path = _find_metadata_json(contract.root, "input_guard.json")
    if limits_path is not None:
        limits = _load_json_optional(limits_path)
        required = (
            "brightness_min", "brightness_max", "sharpness_min",
            "object_ratio_min", "object_ratio_max",
        )
        if all(_safe_float(limits.get(k)) is not None for k in required):
            try:
                img = cv2.imread(str(image_path))
                if img is None:
                    return None
                img = cv2.resize(img, (contract.image_size, contract.image_size))
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                brightness = float(gray.mean())
                sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                roi_mask, _ = _screw_object_mask_rgb(rgb)
                object_ratio = float((roi_mask > 0).mean())
                values = {
                    "brightness": brightness,
                    "sharpness": sharpness,
                    "object_ratio": object_ratio,
                }
                ok = (
                    float(limits["brightness_min"]) <= brightness <= float(limits["brightness_max"])
                    and sharpness >= float(limits["sharpness_min"])
                    and float(limits["object_ratio_min"]) <= object_ratio <= float(limits["object_ratio_max"])
                )
                return {"status": "OK" if ok else "CHECK", "metrics": values, "limits": limits}
            except Exception:
                return None

    # Legacy generic schema.
    profile_path = _find_metadata_json(contract.root, "input_guard_profile.json")
    if profile_path is None:
        return None
    profile = _load_json_optional(profile_path)
    required = ("mean_gray", "sharpness", "object_ratio")
    if not all(isinstance(profile.get(k), dict) for k in required):
        return None
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (contract.image_size, contract.image_size))
        mean_gray = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        border = np.concatenate([gray[0], gray[-1], gray[:,0], gray[:,-1]])
        bg = float(np.median(border))
        diff = np.abs(gray.astype(np.float32) - bg).astype(np.uint8)
        _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        object_ratio = float((mask > 0).mean())
        values = {"mean_gray": mean_gray, "sharpness": sharpness, "object_ratio": object_ratio}
        z = {}
        for k in required:
            mu = float(profile[k].get("mean", 0.0))
            sd = max(float(profile[k].get("std", 1e-6)), 1e-6)
            z[k] = (values[k] - mu) / sd
        ok = (abs(z["mean_gray"]) <= 4 and abs(z["sharpness"]) <= 4 and
              abs(z["object_ratio"]) <= 4 and object_ratio > 0.003)
        return {"status": "OK" if ok else "CHECK", "metrics": values, "z": z}
    except Exception:
        return None


def _bundle_visuals(
    contract: BundleContract,
    base_image: Image.Image,
    anomaly_map: np.ndarray,
    decision: str,
) -> dict[str, Image.Image] | None:
    """Use bundle-saved visualization calibration when present.

    Falls back to the dashboard's existing generic top-5% visualization when the
    bundle does not provide a visualization.json contract.
    """
    import cv2

    vis_path = _find_metadata_json(contract.root, "visualization.json")
    if vis_path is None:
        return None
    vis = _load_json_optional(vis_path)
    cutoff = _safe_float(vis.get("evidence_cutoff"))
    low = _safe_float(vis.get("heatmap_low"))
    high = _safe_float(vis.get("heatmap_high"))
    if cutoff is None or low is None or high is None or high <= low:
        return None

    amap = np.asarray(anomaly_map, dtype=np.float32)
    h, w = amap.shape[-2], amap.shape[-1]
    base = base_image.convert("RGB").resize((w, h), Image.Resampling.BILINEAR)
    base_arr = np.asarray(base).copy()
    norm = np.clip((amap - low) / (high - low + 1e-12), 0, 1)

    try:
        cmap = matplotlib.colormaps["jet"]
    except Exception:
        import matplotlib.pyplot as plt
        cmap = plt.get_cmap("jet")
    heat_arr = (cmap(norm)[..., :3] * 255).astype(np.uint8)
    heat = Image.fromarray(heat_arr, "RGB")

    evidence = amap >= cutoff
    recipe = _bundle_preprocess_name(contract).lower()
    if "screw" in recipe and "orientation" in recipe:
        roi, _ = _screw_object_mask_rgb(base_arr)
        kernel = np.ones((3, 3), np.uint8)
        surface = cv2.erode(roi, kernel, iterations=1)
        outer = cv2.dilate(roi, kernel, iterations=2)
        halo = cv2.subtract(outer, surface)
        final_roi = cv2.bitwise_or(surface, halo) > 0
        evidence &= final_roi

    # This matches the education bundle: OK is not painted as a confirmed defect.
    if str(decision).upper() == "OK":
        evidence[:] = False

    binary = evidence.astype(np.uint8) * 255
    min_area = int(_safe_int(vis.get("min_contour_area")) or 0)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    clean = np.zeros_like(binary)
    for cnt in contours:
        if cv2.contourArea(cnt) >= min_area:
            cv2.drawContours(clean, [cnt], -1, 255, -1)
    evidence = clean > 0

    overlay_arr = base_arr.copy()
    red = np.zeros_like(base_arr)
    red[..., 0] = 255
    overlay_arr[evidence] = (0.45 * base_arr[evidence] + 0.55 * red[evidence]).astype(np.uint8)
    overlay = Image.fromarray(overlay_arr, "RGB")

    contour_bgr = cv2.cvtColor(base_arr.copy(), cv2.COLOR_RGB2BGR)
    contours, _ = cv2.findContours((evidence.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(contour_bgr, contours, -1, (0, 0, 255), 2)
    contour = Image.fromarray(cv2.cvtColor(contour_bgr, cv2.COLOR_BGR2RGB), "RGB")
    return {"original": base, "heatmap": heat, "overlay": overlay, "contour": contour}


def _triage_score(contract: BundleContract, score: float) -> str:
    if contract.is_three_zone:
        assert contract.review_low is not None and contract.ng_high is not None
        if score < contract.review_low:
            return "OK"
        if score < contract.ng_high:
            return "REVIEW"
        return "NG"
    return (("NG" if score >= contract.threshold else "OK") if contract.above_is_ng
            else ("NG" if score <= contract.threshold else "OK"))

def run_efficientad_inference(*, contract: BundleContract, image_path: Path) -> dict[str, Any]:
    try:
        import torch
        import anomalib
        from anomalib.data import PredictDataset
        from anomalib.engine import Engine
        from anomalib.models import EfficientAd
    except Exception as exc:
        raise RuntimeError("Anomalib/PyTorch를 불러오지 못했습니다.") from exc

    installed = getattr(anomalib, "__version__", None)
    if installed is not None and str(installed) != "2.3.3":
        raise RuntimeError(f"Anomalib 실행 버전 불일치: {installed}")

    image_size = int(contract.image_size)
    lr = float(contract.learning_rate)

    for p in (contract.ckpt_path, image_path):
        if any((not ch.isprintable()) or ord(ch) >= 128 for ch in str(p)):
            raise RuntimeError(f"추론 경로가 ASCII 안전 경로가 아닙니다: {p}")

    install_pathlib_pickle_compat()

    acquired, queue_wait_sec = WORKSHOP_INFERENCE_POOL.acquire(timeout=300)
    if not acquired:
        raise RuntimeError("추론 대기시간이 5분을 초과했습니다. 잠시 후 다시 시도하세요.")

    try:
        accelerator = "gpu" if torch.cuda.is_available() else "cpu"
        started = time.perf_counter()

        # Candidate4/PF1 artifacts exist -> use the exact PF1 score + ROI/localization path.
        if contract.score_mode == "PF1_DECISION":
            if not PF1_RUNTIME_ROOT.is_dir():
                raise RuntimeError("PF1 호환 runtime이 대시보드에 포함되어 있지 않습니다.")
            pf1_path = str(PF1_RUNTIME_ROOT)
            if pf1_path not in sys.path:
                sys.path.insert(0, pf1_path)
            try:
                from mvhd_ad.infer import infer_image as pf1_infer_image
                from mvhd_ad.input_guard import evaluate_input_guard as pf1_input_guard
            except Exception as exc:
                raise RuntimeError("Candidate4/PF1 호환 runtime을 불러오지 못했습니다.") from exc

            output_dir = RUNTIME_ROOT / "pf1_outputs" / hashlib.sha256(
                (str(contract.root) + str(image_path) + str(time.time_ns())).encode("utf-8")
            ).hexdigest()[:24]
            output_dir.mkdir(parents=True, exist_ok=True)

            pf1 = pf1_infer_image(
                contract.root, image_path, output_dir, device=accelerator, actual="UNKNOWN"
            )
            try:
                guard = pf1_input_guard(image_path, contract.root / "artifacts")
            except Exception:
                guard = None
            elapsed = time.perf_counter() - started
            visuals = _load_pf1_visuals(output_dir)
            score = float(pf1["score"])
            decision = str(pf1.get("production_triage") or _triage_score(contract, score))

            return {
                "score": score,
                "decision": decision,
                "elapsed_sec": elapsed,
                "queue_wait_sec": queue_wait_sec,
                "anomaly_map": None,
                "visuals": visuals,
                "input_guard": guard,
                "score_mode": "PF1_DECISION",
                "roi_mode": "PF1_ROI",
                "review_low": contract.review_low,
                "ng_high": contract.ng_high,
            }

        # Generic path.  Preserve legacy behavior unless the bundle explicitly
        # declares a preprocessing recipe or raw-no-postprocess score contract.
        inference_path, prepared_preview, preprocess_mode = _prepare_bundle_input(
            contract, image_path
        )

        pre_processor = EfficientAd.configure_pre_processor(
            image_size=(image_size, image_size)
        )
        declared_size = str(contract.config.get("model_size", "")).strip().lower()
        if declared_size not in {"small", "medium"}:
            compact_model = re.sub(r"[^a-z0-9]", "", str(contract.model_name).lower())
            declared_size = "medium" if (compact_model.endswith("m") or "medium" in compact_model) else "small"

        if contract.score_mode == "RAW_ANOMALIB_NO_POSTPROCESS":
            model = EfficientAd(
                lr=lr,
                model_size=declared_size,
                pre_processor=pre_processor,
                post_processor=False,
                evaluator=False,
                visualizer=False,
            )
        else:
            model = EfficientAd(lr=lr, model_size=declared_size, pre_processor=pre_processor)

        engine = Engine(accelerator=accelerator, devices=1, logger=False)
        dataset = PredictDataset(path=inference_path, image_size=(image_size, image_size))

        predictions = engine.predict(
            model=model,
            dataset=dataset,
            ckpt_path=str(contract.ckpt_path),
            return_predictions=True,
        )
        elapsed = time.perf_counter() - started
    finally:
        WORKSHOP_INFERENCE_POOL.release()

    if not predictions:
        raise RuntimeError("예측 결과가 없습니다.")
    batch = predictions[0]
    if getattr(batch, "pred_score", None) is None:
        raise RuntimeError("pred_score가 없습니다.")
    if getattr(batch, "anomaly_map", None) is None:
        raise RuntimeError("anomaly_map이 없습니다.")

    def npy(v):
        if hasattr(v, "detach"): v = v.detach()
        if hasattr(v, "cpu"): v = v.cpu()
        if hasattr(v, "numpy"): v = v.numpy()
        return np.asarray(v)

    score = float(npy(batch.pred_score).reshape(-1)[0])
    amap = npy(batch.anomaly_map).squeeze()
    while amap.ndim > 2:
        amap = amap[0]
    if amap.ndim != 2:
        raise RuntimeError(f"anomaly_map shape 오류: {amap.shape}")
    amap = amap.astype(np.float32)

    decision = _triage_score(contract, score)
    base_for_visuals = prepared_preview
    if base_for_visuals is None:
        try:
            with Image.open(inference_path) as im:
                base_for_visuals = im.convert("RGB").copy()
        except Exception:
            base_for_visuals = None
    bundle_visuals = (
        _bundle_visuals(contract, base_for_visuals, amap, decision)
        if base_for_visuals is not None else None
    )
    return {
        "score": score,
        "decision": decision,
        "elapsed_sec": elapsed,
        "queue_wait_sec": queue_wait_sec,
        "anomaly_map": amap,
        "visuals": bundle_visuals,
        "input_guard": _generic_input_guard(contract, inference_path),
        "score_mode": contract.score_mode,
        "roi_mode": preprocess_mode,
        "review_low": contract.review_low,
        "ng_high": contract.ng_high,
    }


def anomaly_visuals(original: Image.Image, anomaly_map: np.ndarray) -> dict[str, Image.Image]:
    amap = np.asarray(anomaly_map, dtype=np.float32)
    amin, amax = float(amap.min()), float(amap.max())
    norm = (amap - amin) / (amax - amin) if amax > amin else np.zeros_like(amap)

    # Matplotlib 3.11+ compatible colormap lookup.
    try:
        cmap = matplotlib.colormaps["turbo"]
    except Exception:
        import matplotlib.pyplot as plt
        cmap = plt.get_cmap("turbo")
    rgba = cmap(norm)
    heat_arr = (rgba[..., :3] * 255).astype(np.uint8)
    heat = Image.fromarray(heat_arr, "RGB")
    base = original.convert("RGB").resize((amap.shape[1], amap.shape[0]), Image.Resampling.BILINEAR)
    overlay = Image.blend(base, heat, 0.40)

    # Visualization-only contour: top 5% of the REAL anomaly map.
    # It is never used for OK/NG decision.
    q = float(np.quantile(norm, 0.95))
    mask = norm >= max(q, 0.60)
    edge = np.zeros_like(mask, dtype=bool)
    edge[1:, :] |= mask[1:, :] != mask[:-1, :]
    edge[:-1, :] |= mask[:-1, :] != mask[1:, :]
    edge[:, 1:] |= mask[:, 1:] != mask[:, :-1]
    edge[:, :-1] |= mask[:, :-1] != mask[:, 1:]
    contour = base.copy()
    arr = np.asarray(contour).copy()
    arr[edge] = np.array([255, 48, 48], dtype=np.uint8)
    contour = Image.fromarray(arr, "RGB")
    return {"original": base, "heatmap": heat, "overlay": overlay, "contour": contour}


def pil_to_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    bio = io.BytesIO()
    img.save(bio, format=fmt)
    return "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode("ascii")


def contract_public(contract: BundleContract) -> dict[str, Any]:
    m, d, c, mi = contract.metrics, contract.dataset, contract.config, contract.model_info

    final_external = _load_json_optional(_find_metadata_json(contract.root, "final_metrics.json"))
    calibration_external = _load_json_optional(_find_metadata_json(contract.root, "calibration_metrics.json"))

    # Prefer an explicit final_metrics.json, then metrics.json/final_test.
    # Education-only 4차시 bundles can legitimately have no Final Test and keep
    # their validated figures under metrics.json/calibration.  In that case show
    # Calibration metrics rather than an empty performance panel.
    if final_external:
        perf = final_external
    elif isinstance(m.get("final_test"), dict):
        perf = m["final_test"]
    elif isinstance(m.get("calibration"), dict):
        perf = m["calibration"]
    else:
        perf = m

    def pick_metric(aliases: tuple[str, ...]) -> Any:
        v = _metric_value(perf, aliases)
        if v is None:
            v = _metric_value(m, aliases)
        return v

    auroc = _safe_float(pick_metric(("auroc", "image_AUROC", "image_auroc", "AUROC")))
    f1 = _safe_float(pick_metric(("f1", "image_F1Score", "image_f1score", "F1")))
    if f1 is None and isinstance(perf.get("threshold_search"), dict):
        f1 = _safe_float(perf["threshold_search"].get("f1_at_threshold"))
    precision = _safe_float(pick_metric(("precision", "image_precision")))
    recall = _safe_float(pick_metric(("recall", "image_recall")))
    accuracy = _safe_float(pick_metric(("accuracy", "image_accuracy")))

    tn = _safe_int(pick_metric(("true_normal_ok", "tn", "TN")))
    fp = _safe_int(pick_metric(("false_positive", "fp", "FP")))
    fn = _safe_int(pick_metric(("false_negative", "fn", "FN")))
    tp = _safe_int(pick_metric(("true_anomaly_ng", "tp", "TP")))
    review = _safe_int(pick_metric(("review", "REVIEW", "review_n")))
    review_rate = _safe_float(pick_metric(("review_rate", "REVIEW_RATE")))

    # Education/company 3-zone schema stores class-zone counts directly.
    if contract.is_three_zone and any(k in perf for k in (
        "GOOD_OK", "GOOD_REVIEW", "GOOD_NG", "BAD_OK", "BAD_REVIEW", "BAD_NG"
    )):
        tn = _safe_int(perf.get("GOOD_OK")) if perf.get("GOOD_OK") is not None else tn
        fp = _safe_int(perf.get("GOOD_NG")) if perf.get("GOOD_NG") is not None else fp
        fn = _safe_int(perf.get("BAD_OK")) if perf.get("BAD_OK") is not None else fn
        tp = _safe_int(perf.get("BAD_NG")) if perf.get("BAD_NG") is not None else tp
        gr = _safe_int(perf.get("GOOD_REVIEW")) or 0
        br = _safe_int(perf.get("BAD_REVIEW")) or 0
        if review is None:
            review = gr + br
        if review_rate is None:
            review_rate = _safe_float(perf.get("REVIEW_RATE"))

    # Candidate4 metrics.json stores real 3-zone production counts in line_policy_final_test.
    # Education-only bundles may have only line_policy_calibration.
    if isinstance(m.get("line_policy_final_test"), dict):
        policy = m.get("line_policy_final_test")
    elif isinstance(m.get("line_policy_calibration"), dict):
        policy = m.get("line_policy_calibration")
    else:
        policy = {}
    counts = policy.get("counts") if isinstance(policy.get("counts"), dict) else {}
    if contract.is_three_zone and counts:
        gc = counts.get("good") if isinstance(counts.get("good"), dict) else {}
        bc = counts.get("bad") if isinstance(counts.get("bad"), dict) else {}
        tn = _safe_int(gc.get("OK")) if gc.get("OK") is not None else tn
        fp = _safe_int(gc.get("NG")) if gc.get("NG") is not None else fp
        fn = _safe_int(bc.get("OK")) if bc.get("OK") is not None else fn
        tp = _safe_int(bc.get("NG")) if bc.get("NG") is not None else tp
        if review is None:
            review = (_safe_int(gc.get("REVIEW")) or 0) + (_safe_int(bc.get("REVIEW")) or 0)
        if review_rate is None:
            review_rate = _safe_float(policy.get("review_rate"))

    dataset_cards: list[tuple[str, int]] = []
    known_counts = [
        ("원본 Train GOOD", "original_train_good_count"),
        ("수업 학습 GOOD", "classroom_train_good_count"),
        ("Test GOOD", "test_good_count"),
        ("Test BAD", "test_bad_count"),
        ("GOOD", "good_count"),
        ("BAD", "bad_count"),
        ("Train GOOD", "train_good_count"),
        ("Train BAD", "train_bad_count"),
    ]
    for label, key in known_counts:
        value = _safe_int(d.get(key))
        if value is not None:
            dataset_cards.append((label, value))

    nested_counts = d.get("counts") if isinstance(d.get("counts"), dict) else {}
    nested_aliases = [
        ("Train GOOD", "train_good"),
        ("Train BAD", "train_bad"),
        ("Calibration GOOD", "calibration_good"),
        ("Calibration BAD", "calibration_bad"),
        ("Final GOOD", "final_test_good"),
        ("Final BAD", "final_test_bad"),
    ]
    existing_labels = {label for label, _ in dataset_cards}
    for label, key in nested_aliases:
        value = _safe_int(nested_counts.get(key))
        if value is not None and label not in existing_labels:
            dataset_cards.append((label, value))

    # Education bundles may store these counts directly at top-level, including
    # human-readable keys with spaces/capital letters.
    for label, keys in [
        ("Train GOOD", ("train_good", "TRAIN GOOD")),
        ("Train BAD", ("train_bad", "TRAIN BAD")),
        ("Calibration GOOD", ("calibration_good", "CAL GOOD", "CALIBRATION GOOD")),
        ("Calibration BAD", ("calibration_bad", "CAL BAD", "CALIBRATION BAD")),
        ("Final GOOD", ("final_good", "FINAL GOOD")),
        ("Final BAD", ("final_bad", "FINAL BAD")),
    ]:
        value = None
        for key in keys:
            value = _safe_int(d.get(key))
            if value is not None:
                break
        if value is not None and label not in {x for x,_ in dataset_cards}:
            dataset_cards.append((label,value))

    config_public = {}
    aliases = [
        ("model", ("model", "model_name", "model_type")),
        ("anomalib_version", ("anomalib_version",)),
        ("image_size", ("image_size", "input_size")),
        ("epochs", ("epochs", "max_epochs")),
        ("batch_size", ("batch_size",)),
        ("learning_rate", ("learning_rate", "lr")),
        ("seed", ("seed",)),
        ("device", ("device",)),
        ("auxiliary_data", ("auxiliary_data", "imagenette_dir", "aux_data")),
    ]
    for out_key, keys in aliases:
        v = _first_value(c, keys, None)
        if v is not None:
            config_public[out_key] = v
    config_public.setdefault("model", contract.model_name)
    config_public["image_size"] = contract.image_size
    config_public["score_mode"] = contract.score_mode
    config_public["threshold_mode"] = contract.threshold_mode
    if contract.is_three_zone:
        config_public["review_low"] = contract.review_low
        config_public["ng_high"] = contract.ng_high
    else:
        config_public["threshold"] = contract.threshold
    config_public["threshold_rule"] = contract.threshold_info.get("rule")
    try:
        config_public["threshold_source"] = str(contract.threshold_path.relative_to(contract.root))
    except Exception:
        config_public["threshold_source"] = contract.threshold_path.name

    return {
        "project": contract.project_name,
        "model": contract.model_name,
        "image_size": contract.image_size,
        "threshold": contract.threshold,
        "review_low": contract.review_low,
        "ng_high": contract.ng_high,
        "threshold_mode": contract.threshold_mode,
        "score_mode": contract.score_mode,
        "threshold_rule": contract.threshold_info.get("rule"),
        "score_meaning": "Anomaly/Decision Score (불량 확률이 아님)",
        "warnings": list(contract.warnings),
        "dataset": {
            "source": _first_value(d, ("source", "data_root", "dataset_name"), None),
            "license_note": _first_value(d, ("license_note", "license"), None),
            "cards": dataset_cards,
            "raw": d,
        },
        "metrics": {
            "auroc": auroc,
            "f1": f1,
            "precision": precision,
            "recall": recall,
            "accuracy": accuracy,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "tp": tp,
            "review": review,
            "review_rate": review_rate,
            "raw": m,
            "final_raw": final_external,
            "calibration_raw": calibration_external,
        },
        "config": config_public,
        "raw": {
            "model_info": mi,
            "config": c,
            "threshold": contract.threshold_info,
            "metrics": m,
            "final_metrics": final_external,
            "calibration_metrics": calibration_external,
            "dataset": d,
        },
    }

