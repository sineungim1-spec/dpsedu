# V6.9-PF1 ScoreFirst policy fix

This runtime keeps the established Input Guard / Alignment / Surface ROI + Boundary Halo /
EfficientAD / Calibration / 4-view / Audit / Drift / Deployment structure and changes only
the final decision-fusion contract.

## Fixed policy contract
- Image-level decision score is the primary OK / REVIEW / NG decision.
- `score >= ng_high` is always NG; localization cannot downgrade it to REVIEW.
- `review_low <= score < ng_high` is REVIEW; localization cannot auto-promote it to NG.
- Localization is explanatory evidence for Heatmap / Overlay / Contour.
- Safety may only promote a score-level OK near `review_low` to REVIEW, only when Calibration
  selects that fail-safe and visible+safety evidence agree.
- The safety fail-safe is allowed to remain disabled when it adds REVIEW without buying safety.
- Final Test is never used to select policy numbers.

This patch exists because the earlier EvidenceBand fusion could convert many score-level BAD NG
cases to REVIEW and could increase BAD->OK. PF1 is intentionally monotonic with respect to score.
