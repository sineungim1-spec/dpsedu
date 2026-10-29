[SESSION 02] Automotive AI Vision - Candidate4 E07-S EfficientAD PowerShell Package
================================================================================

목적
- 기존 2차시 실습 가이드의 실행 순서와 명령을 그대로 사용합니다.
- 내부 모델/판정 구조만 최종 선택 모델인 Candidate4 E07-S로 교체했습니다.
- 모델: EfficientAD-S / Candidate4 / epoch 7 / seed 73
- model.ckpt SHA256: 736266a37af3c16c0b3445a0505977851592b6fe5103ca4e744d146179ae6bc0

기존 실습과 동일한 실행
1) Python 3.12 및 라이브러리 설치
2) PowerShell 실행 허용
3) BAD 검사:  .\run_bad.ps1
4) 결과 확인: explorer .\outputs
5) GOOD 검사: .\run_good.ps1
6) 결과 확인: explorer .\outputs

Candidate4 E07-S에서 달라진 핵심
- 기존 단일 Threshold OK/NG가 아니라 회사형 3구간 판정입니다.
  score < review_low                  -> OK
  review_low <= score < ng_high      -> REVIEW
  score >= ng_high                   -> NG
- Calibration 기준값:
  review_low = 0.21444829232516993
  ng_high    = 0.5438568345905579
- ScoreFirst 정책: 이미지 score가 1차 판정의 중심이며, localization은 Heatmap/Overlay/Contour 설명 근거입니다.
- Original / Heatmap / Overlay / Contour 4-view는 동일한 red evidence 규칙을 사용합니다.
- HUMAN_IN_THE_LOOP 모드입니다. REVIEW/NG는 작업자 확인 대상이며 자동 폐기 승인 모델로 포장하지 않습니다.

Historical Final 참고
- GOOD: OK 20 / REVIEW 24 / NG 4
- BAD : OK 0 / REVIEW 14 / NG 50
- REVIEW: 38/112 = 33.93%
- AUROC: 0.91015625

출력
- outputs\DEFECT_result 또는 outputs\GOOD_result
- 00_standardized_input.png
- 01_original.png
- 02_heatmap.png
- 03_overlay_masked.png
- 04_contour.png
- result.json
- session02_result.json
- audit.jsonl

주의
- Score는 불량 확률이 아닙니다.
- 빨간 영역은 GT mask가 없는 경우 'defect candidate/evidence'입니다.
- 실제 GOOD/BAD 라벨은 판정 또는 빨간 표시 생성에 사용되지 않습니다.
