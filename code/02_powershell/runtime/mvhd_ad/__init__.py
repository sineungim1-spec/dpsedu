from .config import DatasetSpec, TrainConfig, InferConfig, RUNTIME_VERSION, SCHEMA_VERSION
from .train import mvhd_train, trainer, TrainerFacade
from .export import export_artifacts_from_ckpt
from .infer import infer_image
from .line_runtime import run_line_inspection
from .input_guard import evaluate_input_guard
from .production_gate import evaluate_deployment_readiness
from .bundle import package_model_bundle, package_company_master_bundle
from .roi_sim import roi_variants, compare_roi_scores
from .deployment import deployment_profiles
from .score_engine import select_score_recipe, score_record
from .fusion_policy import fuse_triage, policy_metrics

# Backward compatibility
train = mvhd_train

__all__ = [
    "DatasetSpec", "TrainConfig", "InferConfig",
    "RUNTIME_VERSION", "SCHEMA_VERSION",
    "mvhd_train", "train", "trainer", "TrainerFacade",
    "export_artifacts_from_ckpt",
    "infer_image", "run_line_inspection", "evaluate_input_guard",
    "evaluate_deployment_readiness",
    "package_model_bundle", "package_company_master_bundle",
    "roi_variants", "compare_roi_scores", "deployment_profiles",
    "select_score_recipe", "score_record", "fuse_triage", "policy_metrics",
]
