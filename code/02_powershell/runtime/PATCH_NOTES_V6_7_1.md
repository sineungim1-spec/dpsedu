# V6.7.1 DecisionFusion Hotfix

V6.7의 판정/시각화 설계는 유지하면서 STEP 8 calibration 중 발생한
OpenCV bool-mask 오류를 수정했습니다.

## 수정
`display_candidate_mask()`의 fallback marker 생성에서
`cv2.circle()`에 bool ndarray를 넘기던 코드를 제거했습니다.

기존:
- bool mask -> cv2.circle() -> OpenCV 4.14 Bad argument

수정:
- uint8 marker에 cv2.circle()
- marker > 0 으로 bool 변환
- ROI mask와 AND

## 영향
- model.ckpt 변경 없음
- decision-head 원리 변경 없음
- threshold 정책 변경 없음
- localization calibration 원리 변경 없음
- V6.7 STEP 8을 처음부터 다시 실행하면 됨
