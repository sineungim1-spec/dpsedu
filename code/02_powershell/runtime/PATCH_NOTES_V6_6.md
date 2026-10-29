# V6.6 ProductionCandidate

V6.5 CompanyLine Foundation을 유지하면서 실제 판정 엔진을 개선한 버전입니다.

## 핵심 변경
- Calibration-only score recipe selection (9개 후보, 5-fold stability 포함)
- review_low: FN=0 강제 대신 Recall >= 0.98에서 Specificity 최대화
- ACTION localization: 화면에 보여줄 보수적 결함 후보
- SAFETY localization: 낮은 score의 의심 이미지를 REVIEW로 올리는 안전 후보
- Fusion policy: high-score인데 ACTION 근거가 없으면 NG를 REVIEW로 보류
- Final Test는 score recipe/threshold/localization/fusion 선택에 사용하지 않음
- Heatmap 저수준 광범위 반응 억제, per-image min-max 금지 유지
- 05_candidate_map.png 추가
- line_policy_validation.json 추가

## 목표
기존 checkpoint를 재학습하지 않고 FP/FN trade-off와 라인 운용 안전성을 개선합니다.
성능 목표 달성은 실제 STEP8 결과로만 판단하며 수치를 미리 보장하지 않습니다.
