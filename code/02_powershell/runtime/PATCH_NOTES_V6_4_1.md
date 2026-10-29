# V6.4.1 ProductionFix Compatibility

V6.4의 모델/판정/시각화 로직은 유지하고, 4차시 기존 노트북과의 API 호환성을 보강한 패치입니다.

## 수정
- `mvhd_ad/types.py` 추가
  - `from mvhd_ad.types import DatasetSpec, TrainConfig` 지원
- `mvhd_ad.__init__`에서 `train = mvhd_train` 명시
  - `from mvhd_ad import train as mvhd_train` 후 `mvhd_train(cfg)` 호출 지원
- `requirements_colab.txt` alias 추가
  - `requirements.txt`와 동일 내용
- V6.4의 inference checkpoint callback 수정, ImageVisualizer OFF, threshold/localization 구조는 그대로 유지

## 권장 새 import
```python
from mvhd_ad import mvhd_train, DatasetSpec, TrainConfig
```
