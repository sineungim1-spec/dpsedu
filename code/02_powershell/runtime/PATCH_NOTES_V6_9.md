# V6.9 FinalCandidate

최종 수정 후보입니다.

- GOOD->NG <= 1, BAD->OK <= 1을 Calibration hard constraint로 유지
- safety_hold_cut를 추가해 REVIEW를 줄임
- Final Test는 정책 선택에 사용하지 않음
- Heatmap / Overlay / Contour는 동일한 단일 RED display mask 사용
- 화면은 strongest top-3 evidence regions만 표시해 산발적 빨간 표시를 줄임
- 5x5 display dilation으로 Heatmap/Overlay에서도 빨간 근거가 확실히 보이게 함
- OK에서는 빨간 alarm 없음
- actual GOOD/BAD 라벨은 inference/색상 결정에 사용하지 않음

종료 기준:
- Final Test GOOD->NG <= 1
- Final Test BAD->OK <= 1
- REVIEW <= 40% (권장 <= 35%)
- BAD REVIEW/NG에서 Heatmap/Overlay/Contour 빨간 위치가 서로 일치
- GOOD OK에서 빨간 alarm 없음
