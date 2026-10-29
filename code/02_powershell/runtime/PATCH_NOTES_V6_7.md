# V6.7 DecisionFusion

- Existing 20-Epoch EfficientAD checkpoint is reused; no retraining required.
- Calibration-only standardized logistic decision head over 18 spatial anomaly/residual features.
- 5-fold OOF hyperparameter selection.
- Calibration operating band minimizes REVIEW subject to BAD->OK <=1 and GOOD->NG <=1.
- Auto-NG requires calibrated visible evidence; safety evidence may promote OK to REVIEW.
- Visible red localization calibration targets <=1 GOOD red image on Calibration while maximizing BAD hit.
- Diagnostic fallback candidate can draw red Overlay/Contour on REVIEW/NG when strong localized support exists.
- Heatmap uses fixed cross-image scaling and caps auto-OK alarm colors; no per-image min-max.
- Final Test remains locked and is evaluation-only.
- Meeting line-policy counts does not by itself certify a real production deployment; GT masks/site commissioning are separate gates.
