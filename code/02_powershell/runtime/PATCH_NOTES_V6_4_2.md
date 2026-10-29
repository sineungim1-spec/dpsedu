# V6.4.2 ProductionFix

## 핵심 수정

Anomalib 2.3.3 환경에서 EfficientAD 학습 시작 시:

`ValueError: 's' is not a valid EfficientAdModelSize`

오류가 발생할 수 있었습니다.

원인은 V6.4/V6.4.1에서 EfficientAD 생성 시 모델 크기를 짧은 문자열로 넘긴 부분입니다.

V6.4.2에서는 `model_size` 인자를 직접 넘기지 않고,
Anomalib EfficientAd의 공식 기본값 `EfficientAdModelSize.S`를 사용합니다.
따라서 의도했던 EfficientAD-S(소형 모델)는 그대로 유지됩니다.

## 그대로 유지되는 기능

- GOOD-only 학습
- capture-group leakage 방지
- TRAIN / CALIBRATION / FINAL TEST 분리
- 요청 epoch 그대로 실행
- inference checkpoint callback 충돌 수정
- ImageVisualizer OFF
- V6.4 preprocess / boundary halo
- image threshold / localization threshold 분리
- 기존 4차시 노트북 API 호환
- requirements.txt / requirements_colab.txt 동시 제공
