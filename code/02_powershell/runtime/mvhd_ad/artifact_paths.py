from __future__ import annotations
from pathlib import Path

ALIASES = {
    "protocol": ["protocol.json", "protocol_v6.json"],
    "preprocess_profile": ["preprocess_profile.json", "preprocess_profile_v6.json"],
    "localization_profile": ["localization_profile.json", "localization_profile_v6.json"],
    "operating_window": ["operating_window.json", "operating_window_v67.json", "operating_window_v66.json", "operating_window_v65.json", "operating_window_v64.json", "operating_window_v63.json"],
    "company_alignment": ["company_alignment.json", "company_poc_alignment_v67.json", "company_poc_alignment_v66.json", "company_poc_alignment_v65.json", "company_poc_alignment_v64.json", "company_poc_alignment_v63.json"],
    "threshold": ["threshold.json"],
    "metrics": ["metrics.json"],
    "dataset": ["dataset.json"],
    "production_validation": ["production_validation.json"],
    "decision_policy": ["decision_policy.json"],
    "fusion_policy": ["fusion_policy.json"],
    "inspection_recipe": ["inspection_recipe.json"],
    "score_baseline": ["score_baseline.json"],
    "score_recipe": ["score_recipe.json"],
    "line_policy_validation": ["line_policy_validation.json"],
    "decision_model": ["decision_model.json"],
}

def resolve_artifact(artifacts_dir: str | Path, key: str, required: bool=True) -> Path | None:
    art = Path(artifacts_dir)
    if key not in ALIASES:
        raise KeyError(f"Unknown artifact key: {key}")
    for name in ALIASES[key]:
        p = art / name
        if p.exists():
            return p
    if required:
        raise FileNotFoundError(f"Artifact '{key}' not found under {art}. Tried: {ALIASES[key]}")
    return None
