from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import hashlib, json, random, re
from .config import DatasetSpec, SCHEMA_VERSION

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

_CAM_RE = re.compile(r"(?:CAM(?:ERA)?)[_\- ]*0*(\d+)", re.I)
_VIEW_RE = re.compile(r"(?:VIEW|V)[_\- ]*(0|90|180|270|U)(?:DEG|D)?(?:\b|[_\-])", re.I)
_DEG_RE = re.compile(r"(?:^|[_\- ])(0|90|180|270)(?:DEG|°)(?:$|[_\- ])", re.I)
_INDEX_RE = re.compile(r"(?:FRAME|PRODUCT|PART|IDX|INDEX)[_\- ]*0*(\d+)", re.I)
_TS_RE = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[T_\- ]?([0-2]\d)[:\-]?([0-5]\d)[:\-]?([0-5]\d)(?:[._](\d{1,6}))?", re.I)


def _forced_split(path: Path) -> str | None:
    parts = {p.lower() for p in path.parts}
    if "final_test" in parts or "final" in parts: return "final_test"
    if "calibration" in parts or "cal" in parts: return "calibration"
    if "train" in parts: return "train"
    return None


def _parse_time_ms(text: str) -> tuple[str | None, int | None]:
    m = _TS_RE.search(text)
    if not m: return None, None
    frac = (m.group(7) or "0")[:6].ljust(6, "0")
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6)), int(frac))
        return dt.isoformat(timespec="milliseconds"), int(dt.timestamp() * 1000)
    except ValueError:
        return None, None


def parse_image_metadata(path: Path, default_view: str | None = None) -> dict:
    text = "_".join(path.parts[-4:])
    cm = _CAM_RE.search(text)
    camera = f"CAM{int(cm.group(1))}" if cm else "GENERIC"
    vm = _VIEW_RE.search(text) or _DEG_RE.search(text)
    view = vm.group(1).upper() if vm else (str(default_view).upper() if default_view is not None else "UNKNOWN")
    im = _INDEX_RE.search(text)
    product_index = int(im.group(1)) if im else None
    timestamp, time_ms = _parse_time_ms(text)
    inspection_group = "GENERIC" if camera == "GENERIC" else f"{camera}_V{view}"
    return {
        "camera": camera,
        "view": view,
        "selector": "?",
        "timestamp": timestamp,
        "time_ms": time_ms,
        "product_index": product_index,
        "inspection_group": inspection_group,
    }


def _list_images(folder: Path) -> list[Path]:
    if not folder.is_dir(): return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT)


def _mask_for(path: Path, mask_dir: Path) -> str | None:
    for ext in (".png", ".bmp", ".tif", ".tiff"):
        p = mask_dir / f"{path.stem}{ext}"
        if p.exists(): return str(p.resolve())
    return None


def _capture_groups(records: list[dict], tolerance_ms: int = 1800) -> None:
    # Explicit product index is the strongest cross-camera key.  Timestamp clustering
    # is only used when a stable index is absent.  Images without either stay unique.
    indexed = defaultdict(list)
    timed = defaultdict(list)
    unique = []
    for i, r in enumerate(records):
        if r["product_index"] is not None:
            indexed[(r["view"], r["product_index"])].append(i)
        elif r["time_ms"] is not None:
            timed[r["view"]].append(i)
        else:
            unique.append(i)

    gid = 0
    def assign(indices: list[int]):
        nonlocal gid
        suffix = hashlib.sha1("|".join(sorted(records[i]["inspection_group"] for i in indices)).encode()).hexdigest()[:12]
        cap = f"CAP_{gid:04d}_{suffix}"
        gid += 1
        for i in indices: records[i]["capture_group_id"] = cap

    for _, inds in sorted(indexed.items(), key=lambda kv: str(kv[0])):
        # If the same product index appears in widely separated captures, split by time gaps.
        with_time = sorted(inds, key=lambda i: records[i]["time_ms"] if records[i]["time_ms"] is not None else -1)
        if any(records[i]["time_ms"] is not None for i in with_time):
            chunk, last = [], None
            for i in with_time:
                t = records[i]["time_ms"]
                if last is not None and t is not None and t - last > tolerance_ms and chunk:
                    assign(chunk); chunk = []
                chunk.append(i)
                if t is not None: last = t
            if chunk: assign(chunk)
        else:
            assign(with_time)

    for _, inds in sorted(timed.items()):
        inds = sorted(inds, key=lambda i: records[i]["time_ms"])
        chunk, anchor = [], None
        for i in inds:
            t = records[i]["time_ms"]
            if anchor is None or t - anchor <= tolerance_ms:
                chunk.append(i)
                if anchor is None: anchor = t
            else:
                assign(chunk); chunk = [i]; anchor = t
        if chunk: assign(chunk)

    for i in unique: assign([i])


def _allocate_groups(groups: list[tuple[str, list[int]]], target_counts: tuple[int, int, int], rng: random.Random) -> dict[str, str]:
    """Allocate GOOD-only groups to train/cal/final while keeping groups intact."""
    groups = groups[:]
    rng.shuffle(groups)
    targets = {"train": target_counts[0], "calibration": target_counts[1], "final_test": target_counts[2]}
    counts = {k: 0 for k in targets}
    out = {}
    for gid, inds in groups:
        # Greedy by largest remaining image deficit; avoids leakage and stays close to ratios.
        remaining = {k: targets[k] - counts[k] for k in targets}
        split = max(remaining, key=lambda k: (remaining[k], -counts[k]))
        out[gid] = split
        counts[split] += len(inds)
    return out


def build_protocol(dataset: DatasetSpec, seed: int = 42) -> dict:
    root = dataset.resolved_root()
    good_dir, bad_dir = root / dataset.good_name(), root / dataset.bad_name()
    good, bad = _list_images(good_dir), _list_images(bad_dir)
    if not good: raise FileNotFoundError(f"GOOD images not found: {good_dir}")
    if not bad: raise FileNotFoundError(f"BAD images not found: {bad_dir}")
    records = []
    mask_dir = root / dataset.defect_mask_dir
    for label, paths in (("good", good), ("bad", bad)):
        for p in paths:
            m = parse_image_metadata(p, dataset.default_view)
            records.append({
                "path": str(p.resolve()),
                "relative_path": str(p.resolve().relative_to(root)),
                "label": label,
                "forced_split": _forced_split(p.resolve().relative_to(root)),
                **m,
                "capture_group_id": None,
                "split": None,
                "prepared_relative_path": None,
                "gt_mask_path": _mask_for(p, mask_dir) if label == "bad" else None,
            })
    _capture_groups(records)

    by_gid = defaultdict(list)
    for i, r in enumerate(records): by_gid[r["capture_group_id"]].append(i)
    rng = random.Random(seed)
    forced_conflicts = []
    assignments = {}
    mixed_groups = []

    # Forced splits first.
    for gid, inds in by_gid.items():
        fs = {records[i]["forced_split"] for i in inds if records[i]["forced_split"]}
        if len(fs) > 1:
            forced_conflicts.append(gid)
        elif len(fs) == 1:
            s = next(iter(fs))
            if s == "train" and any(records[i]["label"] == "bad" for i in inds):
                raise ValueError(f"BAD capture group cannot be forced into TRAIN: {gid}")
            assignments[gid] = s

    unassigned = [(gid, inds) for gid, inds in by_gid.items() if gid not in assignments]
    good_only, bad_or_mixed = [], []
    for gid, inds in unassigned:
        labels = {records[i]["label"] for i in inds}
        if labels == {"good"}: good_only.append((gid, inds))
        else:
            bad_or_mixed.append((gid, inds))
            if len(labels) > 1: mixed_groups.append(gid)

    n_good = sum(len(inds) for _, inds in good_only)
    train_target = int(round(n_good * 0.75))
    rem = n_good - train_target
    cal_target = (rem + 1) // 2
    final_target = rem - cal_target
    assignments.update(_allocate_groups(good_only, (train_target, cal_target, final_target), rng))

    # Groups containing BAD never enter train. Balance BAD image counts between CAL and FINAL.
    rng.shuffle(bad_or_mixed)
    cal_bad = final_bad = 0
    for gid, inds in bad_or_mixed:
        nbad = sum(records[i]["label"] == "bad" for i in inds)
        s = "calibration" if cal_bad <= final_bad else "final_test"
        assignments[gid] = s
        if s == "calibration": cal_bad += nbad
        else: final_bad += nbad

    for r in records:
        r["split"] = assignments[r["capture_group_id"]]
        if r["label"] == "bad" and r["split"] == "train":
            raise AssertionError("Protocol violation: BAD in TRAIN")

    counts = {
        "train_good": sum(r["split"] == "train" and r["label"] == "good" for r in records),
        "train_bad": sum(r["split"] == "train" and r["label"] == "bad" for r in records),
        "calibration_good": sum(r["split"] == "calibration" and r["label"] == "good" for r in records),
        "calibration_bad": sum(r["split"] == "calibration" and r["label"] == "bad" for r in records),
        "final_test_good": sum(r["split"] == "final_test" and r["label"] == "good" for r in records),
        "final_test_bad": sum(r["split"] == "final_test" and r["label"] == "bad" for r in records),
    }
    coverage = {}
    for s in ("train", "calibration", "final_test"):
        rr = [r for r in records if r["split"] == s]
        coverage[s] = {
            "images": len(rr), "good": sum(r["label"] == "good" for r in rr), "bad": sum(r["label"] == "bad" for r in rr),
            "cameras": sorted({r["camera"] for r in rr}), "views": sorted({r["view"] for r in rr}),
            "inspection_groups": sorted({r["inspection_group"] for r in rr}),
        }
    split_sets = defaultdict(set)
    for r in records: split_sets[r["capture_group_id"]].add(r["split"])
    leaked = [g for g, ss in split_sets.items() if len(ss) > 1]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol": "grouped_train_calibration_final_test",
        "seed": seed,
        "data_root": str(root),
        "rules": {
            "train": "GOOD only",
            "calibration": "held-out GOOD + BAD; used for thresholds/calibration",
            "final_test": "never used for model fitting or threshold selection",
            "capture_grouping": "same view + product index and/or timestamp within 1.8 s across cameras when metadata is available; otherwise image-isolated",
        },
        "counts": counts,
        "coverage": coverage,
        "leakage_check": {
            "capture_group_leakage_count": len(leaked), "capture_group_leakage_groups": leaked,
            "mixed_view_label_group_count": len(mixed_groups), "mixed_view_label_groups": mixed_groups,
            "mixed_view_label_groups_isolated_from_train": all(assignments[g] != "train" for g in mixed_groups),
            "forced_split_conflict_count": len(forced_conflicts), "forced_split_conflict_groups": forced_conflicts,
        },
        "records": records,
    }


def save_protocol(protocol: dict, path: str | Path) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_protocol(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
