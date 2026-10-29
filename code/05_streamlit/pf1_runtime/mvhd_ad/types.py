"""Backward-compatibility imports for V6.x teaching notebooks.

Older notebooks imported:
    from mvhd_ad.types import DatasetSpec, TrainConfig

V6.4 moved these dataclasses to mvhd_ad.config.
This module intentionally re-exports them so old and new notebooks both work.
"""
from .config import (
    DatasetSpec,
    TrainConfig,
    InferConfig,
    RUNTIME_VERSION,
    SCHEMA_VERSION,
)

__all__ = [
    "DatasetSpec",
    "TrainConfig",
    "InferConfig",
    "RUNTIME_VERSION",
    "SCHEMA_VERSION",
]
