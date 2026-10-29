# V6.4.3 ProductionFix

## 핵심 수정: EfficientAD pretrained weights 다운로드 시 Rich/tqdm RecursionError

증상:
- `efficientad_pretrained_weights.zip: 0.00B ...`가 반복 출력됨
- `rich/file_proxy.py -> console.print -> IPython -> flush`가 재귀 호출됨
- 최종적으로 `RecursionError: maximum recursion depth exceeded`

원인:
- Jupyter/Colab 환경에서 Lightning/Anomalib의 Rich progress 출력과
  EfficientAD pretrained-weight 다운로드용 tqdm 출력이 충돌할 수 있음.

수정:
```python
from lightning.pytorch.callbacks import TQDMProgressBar

engine = Engine(
    ...,
    callbacks=[TQDMProgressBar(refresh_rate=1)],
)
```

이 방식은 Anomalib GitHub discussion #3287에서 동일 증상에 제시된 hotfix와 일치합니다.

## 기존 V6.4.2 수정 유지
- EfficientAD model_size 짧은 문자열 제거
- EfficientAD-S 기본 enum 사용
- GOOD-only 학습
- capture-group leakage 방지
- TRAIN / CALIBRATION / FINAL TEST 분리
- 20 epoch 요청 시 실제 20 epoch
- ImageVisualizer OFF
- inference checkpoint callback 충돌 수정
- image threshold / localization threshold 분리
- 기존 교육용 notebook API 호환
