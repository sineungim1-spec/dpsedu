# V6.8.1 Visual4 RedEvidence

최종 출력은 다시 4개만 유지합니다.

1. Original
2. Heatmap
3. Overlay
4. Contour

시각화 정책:
- OK: 빨간 alarm 없음
- REVIEW / NG:
  - ACTION + DISPLAY + SAFETY evidence를 하나의 RED evidence로 통합
  - Heatmap / Overlay / Contour 모두 빨간색으로 동일한 근거를 표시
  - 세 evidence가 모두 비어도 inspection ROI 내 strongest model-evidence 위치를 작은 빨간 marker로 표시

중요:
실제 GOOD/BAD 라벨은 inference나 빨간색 표시 여부에 사용하지 않습니다.
따라서 외부 UNKNOWN 이미지에도 동일하게 적용됩니다.
