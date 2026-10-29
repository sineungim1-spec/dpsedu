# V6.8 EvidenceBand

목표:
- GOOD -> NG <= 1
- BAD -> OK <= 1
- Final Test는 정책 선택에 사용하지 않음
- BAD/REVIEW 사례에서 화면이 비어 보이는 문제 해소

핵심 변경:
1. SAFETY localization grid를 더 넓혀 Calibration BAD safety miss <= 1을 우선 탐색.
2. 생산 판정을 단일 score band가 아니라 Score + Visible + Safety evidence의 2D EvidenceBand로 변경.
3. Calibration line policy는 BAD->OK=0, GOOD->NG<=1을 hard constraint로 두고 REVIEW를 최소화.
4. RED는 강한 visible defect candidate에만 사용.
5. REVIEW의 약한 safety evidence는 AMBER로 Overlay/Contour/Review Evidence Map에 표시.
6. actual GOOD/BAD label은 inference/색상 결정에 절대 사용하지 않음.

주의:
Final Test에서 목표 달성은 보장하지 않습니다. Final Test를 보고 threshold/policy를 다시 맞추면 데이터 누수가 되므로 금지합니다.
