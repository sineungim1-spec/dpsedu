from __future__ import annotations
import numpy as np
from PIL import Image
from .localization import candidate_present, display_candidate_present
from .config import SCHEMA_VERSION


def _group(profile: dict, r: dict) -> dict:
    name = r.get("inspection_group_used") or r.get("inspection_group") or "GENERIC"
    return profile["groups"].get(name) or profile["groups"].get("GENERIC") or next(iter(profile["groups"].values()))


def raw_triage(score: float, threshold: dict) -> str:
    if score < float(threshold["review_low"]):
        return "OK"
    if score < float(threshold["ng_high"]):
        return "REVIEW"
    return "NG"


def _evidence_flags(r: dict, profile: dict, action_th: dict, safety_th: dict, display_cfg: dict):
    g = _group(profile, r)
    rgb = np.asarray(Image.open(r["prepared_path"]).convert("RGB"))
    action = candidate_present(r["anomaly_map"], rgb, g, action_th)
    display = display_candidate_present(r["anomaly_map"], rgb, g, display_cfg) if display_cfg else False
    visible = bool(action or display)
    safety = candidate_present(r["anomaly_map"], rgb, g, safety_th)
    return visible, bool(safety)


def _classify(score: float, visible: bool, safety: bool, policy: dict) -> tuple[str, str]:
    """PF1 monotonic score-first production policy.

    Invariants:
      * score is the primary OK/REVIEW/NG decision source;
      * localization never downgrades a score-level NG;
      * localization never upgrades REVIEW to NG;
      * safety may only promote a BORDERLINE score-level OK to REVIEW;
      * weak/isolated evidence cannot change an otherwise clean low-score OK.
    """
    ok_cut = float(policy["ok_cut"])
    ng_cut = float(policy["ng_cut"])
    safety_floor = float(policy.get("safety_review_floor", ok_cut))
    safety_enabled = bool(policy.get("safety_fail_safe_enabled", False))
    require_dual = bool(policy.get("safety_requires_visible_agreement", True))

    # Monotonicity first: a high score remains NG. Evidence is explanatory only.
    if score >= ng_cut:
        return "NG", "SCORE_AUTO_NG"

    # Middle band remains REVIEW. Evidence cannot auto-promote to NG.
    if score >= ok_cut:
        return "REVIEW", "SCORE_REVIEW_BAND"

    # Very limited fail-safe: only an OK close to the boundary can be held.
    if safety_enabled and score >= safety_floor and safety and (visible or not require_dual):
        return "REVIEW", "BORDERLINE_OK_STRONG_SAFETY_HOLD"

    return "OK", "SCORE_AUTO_OK"


def _candidate_floors(scores: np.ndarray, ok_cut: float, max_points: int = 25) -> list[float]:
    s = np.asarray(scores, dtype=float)
    s = s[np.isfinite(s) & (s < ok_cut)]
    # ok_cut means disabled because score < ok_cut is required for this branch.
    if len(s) == 0:
        return [float(ok_cut)]
    vals = np.unique(np.quantile(s, np.linspace(0.0, 1.0, min(max_points, len(s)))))
    return sorted(set([float(v) for v in vals] + [float(ok_cut)]))


def _counts(rows: list[dict], policy: dict) -> tuple[dict, dict]:
    counts = {"good": {"OK": 0, "REVIEW": 0, "NG": 0}, "bad": {"OK": 0, "REVIEW": 0, "NG": 0}}
    reasons: dict[str, int] = {}
    for x in rows:
        tri, reason = _classify(x["score"], x["visible"], x["safety"], policy)
        counts[x["label"]][tri] += 1
        reasons[reason] = reasons.get(reason, 0) + 1
    return counts, reasons


def calibrate_fusion_policy(records: list[dict], profile: dict, action_th: dict, safety_th: dict,
                            display_cfg: dict, threshold: dict | None = None,
                            max_bad_ok: int = 1, max_good_ng: int = 1) -> dict:
    """Calibrate only the *limited safety fail-safe* on Calibration.

    The score operating band is inherited from threshold.json / the calibration-only
    decision head. This function is deliberately not allowed to invent a second,
    evidence-gated NG rule. It can only decide whether a narrow, dual-evidence safety
    hold below review_low is useful. If it is not useful, it is disabled.
    """
    rows = []
    for r in records:
        visible, safety = _evidence_flags(r, profile, action_th, safety_th, display_cfg)
        rows.append({"label": r["label"], "score": float(r["score"]), "visible": visible, "safety": safety})

    if not rows:
        raise ValueError("Calibration records are required for PF1 policy calibration")

    scores = np.asarray([x["score"] for x in rows], dtype=float)
    if threshold is None:
        raise ValueError("PF1 requires the calibration-selected score threshold object")
    ok_cut = float(threshold["review_low"])
    ng_cut = float(threshold["ng_high"])
    if not np.isfinite([ok_cut, ng_cut]).all() or ng_cut < ok_cut:
        raise ValueError("Invalid PF1 score operating band")

    # Baseline is score-only. Search only for a safety promotion floor below ok_cut.
    candidates = [
        {"ok_cut": ok_cut, "ng_cut": ng_cut, "safety_review_floor": ok_cut,
         "safety_fail_safe_enabled": False, "safety_requires_visible_agreement": True}
    ]
    for floor in _candidate_floors(scores, ok_cut):
        if floor >= ok_cut:
            continue
        candidates.append({"ok_cut": ok_cut, "ng_cut": ng_cut, "safety_review_floor": float(floor),
                           "safety_fail_safe_enabled": True, "safety_requires_visible_agreement": True})

    ranked = []
    for p in candidates:
        counts, reasons = _counts(rows, p)
        bad_ok = counts["bad"]["OK"]
        good_ng = counts["good"]["NG"]
        review_n = counts["good"]["REVIEW"] + counts["bad"]["REVIEW"]
        good_ok = counts["good"]["OK"]
        bad_ng = counts["bad"]["NG"]
        feasible = bad_ok <= max_bad_ok and good_ng <= max_good_ng
        # Hard constraints -> minimum REVIEW -> minimum BAD escape -> useful auto decisions.
        # A fail-safe is therefore activated only when it buys safety without unnecessary REVIEW.
        key = (1 if feasible else 0, -review_n, -bad_ok, -good_ng, good_ok + bad_ng,
               0 if p["safety_fail_safe_enabled"] else 1, p["safety_review_floor"])
        ranked.append((key, p, counts, reasons, feasible))

    _, policy, counts, reasons, feasible = max(ranked, key=lambda x: x[0])
    bad_ok = counts["bad"]["OK"]
    good_ng = counts["good"]["NG"]
    review_n = counts["good"]["REVIEW"] + counts["bad"]["REVIEW"]
    n = sum(sum(v.values()) for v in counts.values())

    return {
        "schema_version": SCHEMA_VERSION,
        "policy": "V6.9-PF1 ScoreFirst Monotonic + Limited Safety FailSafe",
        **policy,
        "selection_data": "CALIBRATION_ONLY",
        "final_test_used_for_selection": False,
        "constraints": {"max_bad_ok": int(max_bad_ok), "max_good_ng": int(max_good_ng)},
        "calibration_counts": counts,
        "calibration_reasons": reasons,
        "calibration_bad_ok": int(bad_ok),
        "calibration_good_ng": int(good_ng),
        "calibration_review_n": int(review_n),
        "calibration_review_rate": float(review_n / max(1, n)),
        "feasible": bool(feasible),
        "score_is_primary_decision": True,
        "localization_role": "EXPLANATION_AND_DISPLAY",
        "safety_role": "LIMITED_OK_TO_REVIEW_FAIL_SAFE_ONLY",
        "ng_downgrade_allowed": False,
        "review_to_ng_by_localization_allowed": False,
        "auto_ok_rule": "score < ok_cut, except optional dual-evidence safety hold inside the calibrated borderline-OK band",
        "auto_ng_rule": "score >= ng_cut; localization is not required and cannot downgrade NG",
        "review_rule": "ok_cut <= score < ng_cut, plus optional calibrated borderline-OK safety hold",
    }


def fuse_triage(raw: str, visible_candidate: bool, safety_candidate: bool,
                score: float | None = None, fusion_policy: dict | None = None) -> tuple[str, str]:
    if fusion_policy is not None and score is not None:
        return _classify(float(score), bool(visible_candidate), bool(safety_candidate), fusion_policy)
    # Fail-closed compatibility path for legacy bundles without PF1 artifact.
    if raw == "NG":
        return "NG", "LEGACY_SCORE_NG_PRESERVED"
    if raw == "OK" and safety_candidate and visible_candidate:
        return "REVIEW", "LEGACY_DUAL_EVIDENCE_OK_HOLD"
    return raw, "LEGACY_SCORE_DECISION_PRESERVED"


def policy_metrics(records: list[dict], profile: dict, threshold: dict, action_th: dict,
                   safety_th: dict, display_cfg: dict, fusion_policy: dict | None = None) -> dict:
    counts = {"good": {"OK": 0, "REVIEW": 0, "NG": 0}, "bad": {"OK": 0, "REVIEW": 0, "NG": 0}}
    raw_counts = {"good": {"OK": 0, "REVIEW": 0, "NG": 0}, "bad": {"OK": 0, "REVIEW": 0, "NG": 0}}
    reasons: dict[str, int] = {}
    visible_hits = {"good": 0, "bad": 0}
    safety_hits = {"good": 0, "bad": 0}
    ng_downgrades = 0
    localization_ng_promotions = 0
    safety_promotions = 0

    for r in records:
        visible, safety = _evidence_flags(r, profile, action_th, safety_th, display_cfg)
        raw = raw_triage(float(r["score"]), threshold)
        fused, reason = fuse_triage(raw, visible, safety, score=float(r["score"]), fusion_policy=fusion_policy)
        label = r["label"]
        raw_counts[label][raw] += 1
        counts[label][fused] += 1
        reasons[reason] = reasons.get(reason, 0) + 1
        visible_hits[label] += int(visible)
        safety_hits[label] += int(safety)
        ng_downgrades += int(raw == "NG" and fused != "NG")
        localization_ng_promotions += int(raw != "NG" and fused == "NG")
        safety_promotions += int(raw == "OK" and fused == "REVIEW")

    good_n = sum(counts["good"].values())
    bad_n = sum(counts["bad"].values())
    n = good_n + bad_n
    bad_ok = counts["bad"]["OK"]
    good_ng = counts["good"]["NG"]
    review = counts["good"]["REVIEW"] + counts["bad"]["REVIEW"]

    return {
        "schema_version": SCHEMA_VERSION,
        "policy": "V6.9-PF1 ScoreFirst Monotonic + Limited Safety FailSafe",
        "counts": counts,
        "raw_score_triage_counts": raw_counts,
        "fusion_reasons": reasons,
        "visible_candidate_hits": visible_hits,
        "safety_candidate_hits": safety_hits,
        "good_n": good_n, "bad_n": bad_n, "n": n,
        "bad_auto_pass_escape": bad_ok, "bad_auto_pass_escape_rate": bad_ok / max(1, bad_n),
        "good_auto_reject": good_ng, "good_auto_reject_rate": good_ng / max(1, good_n),
        "good_auto_ok": counts["good"]["OK"], "good_auto_ok_rate": counts["good"]["OK"] / max(1, good_n),
        "bad_auto_ng": counts["bad"]["NG"], "bad_auto_ng_rate": counts["bad"]["NG"] / max(1, bad_n),
        "review_n": review, "review_rate": review / max(1, n),
        "target_good_ng_le_1": bool(good_ng <= 1),
        "target_bad_ok_le_1": bool(bad_ok <= 1),
        "target_review_le_40pct": bool(review / max(1, n) <= .40),
        "monotonicity": {
            "score_NG_downgraded": int(ng_downgrades),
            "localization_promoted_nonNG_to_NG": int(localization_ng_promotions),
            "safety_OK_to_REVIEW_promotions": int(safety_promotions),
            "passed": bool(ng_downgrades == 0 and localization_ng_promotions == 0),
        },
    }
