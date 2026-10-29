# V6.8.2 Visual4 DisplayHelperHotfix

## 오류 원인
V6.8/V6.8.1 localization 재작성 과정에서 다음 함수 정의가 빠졌습니다.

- _display_support
- _display_score
- calibrate_display_fallback
- display_candidate_mask
- display_candidate_present

하지만 fusion_policy.py / infer.py / export.py는 계속 이 함수를 사용하고 있어서
import 단계에서 실패했습니다.

## 수정
- 누락된 display helper 전부 복구
- OpenCV bool-mask hotfix 유지
- calibrate_localization_dual()에 display_fallback 결과 복구
- V6.8의 넓어진 SAFETY calibration 정책 유지
- V6.8.1의 4-view 시각화 유지

## 최종 출력
Original / Heatmap / Overlay / Contour

## 시각화
- OK: 빨간 alarm 없음
- REVIEW/NG: 모델 evidence를 빨간색으로 표시
- 실제 GOOD/BAD 라벨은 inference/색상 결정에 사용하지 않음
