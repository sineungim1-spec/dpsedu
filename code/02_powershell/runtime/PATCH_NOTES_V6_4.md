# V6.4 ProductionFix 변경 기록

## A. 반드시 해결한 오류

이전 STEP8 bulk inference에서 다음 계열 충돌이 발생할 수 있었습니다.

`Trainer was configured with enable_checkpointing=False but found ModelCheckpoint in callbacks list.`

V6.4의 `mvhd_ad/runners/anomalib_runner.py`는 inference Engine에 `enable_checkpointing=False`를 전달하지 않습니다. 또한 `EfficientAd(..., visualizer=False)`를 사용하여 ImageVisualizer callback의 대량 PNG 저장도 막습니다.

## B. V6.3에서 관찰된 FP/Heatmap 문제에 대한 구조적 수정

V6.3은 불량 Recall/FN 안전성은 높았지만 정상 FP와 red-candidate FP가 과도했습니다. V6.4 runtime은 다음을 적용합니다.

- raw image score와 localization evidence 분리
- TRAIN GOOD spatial median/MAD baseline 기반 decision score
- surface / boundary-halo 분리, boundary는 더 엄격한 조건
- localization candidate grid-search에서 `GOOD red FP` 최소화와 BAD candidate hit를 함께 최적화
- heatmap scale을 localization threshold에 고정하여 전체 제품이 노랑으로 포화되는 현상 완화
- small component 제거 및 strong evidence 조건 강화

이는 **코드 정책 변경**이며, 새 성능을 보장/조작하는 것이 아닙니다. Calibration/Final Test를 다시 실행한 측정값만 보고해야 합니다.
