AI Vision Dashboard - 범용 bundle 호환 수정본

수정 목적
- 기존 Dashboard의 UI/LAN 공유/검사이력/사람검증/PF1 기능은 유지
- 특정 나사 bundle 전용 Dashboard로 바꾸지 않고, bundle 메타데이터를 읽어 필요한 기능만 선택 적용

주요 수정
1. config.json/model_info.json이 없어도 decision_policy.json에서 model, image_size, score_mode, preprocess를 읽음
2. legacy 2-ZONE threshold 그대로 지원
3. 일반 3-ZONE review_low/ng_high 그대로 지원
4. Candidate4/PF1 artifacts가 있으면 기존 PF1 runtime 그대로 사용
5. ANOMALIB_RAW_NO_POSTPROCESS bundle은 post_processor=False로 추론하여 저장된 threshold의 score 공간을 보존
6. model_size small/medium 자동 판별
7. bundle이 명시한 preprocess recipe가 있을 때만 전용 입력 표준화 적용
   - 현재 screw orientation-center-scale standardization recipe 지원
   - 다른 bundle은 기존 입력 방식 유지
8. input_guard.json(min/max)과 기존 input_guard_profile.json 모두 지원
9. visualization.json의 evidence_cutoff/heatmap_low/high/min_contour_area가 있으면 저장된 시각화 기준 사용
   - 없으면 기존 범용 4-view 방식 유지
10. dataset.json의 TRAIN GOOD/CAL GOOD/FINAL GOOD 같은 교육용 키도 표시
11. final_metrics.json의 GOOD_OK/GOOD_REVIEW/GOOD_NG/BAD_OK/... 3-ZONE 집계 표시
12. gate.json이 NOT_APPROVED여도 추론은 가능하되 MASTER로 오인하지 않도록 경고

검증
- screw_company_edu_bundle_NOT_APPROVED.zip 계약 로딩 성공
  EfficientAD-S / image_size 256 / THREE_ZONE / RAW_ANOMALIB_NO_POSTPROCESS
  review_low=0.0936608724296093 / ng_high=0.1883765012025833
- Legacy 2-ZONE, 일반 3-ZONE, PF1 모드 계약 로딩 회귀 테스트 통과
- Python 문법 컴파일 검사 통과

주의
- 현재 개발 환경에는 anomalib 패키지를 새로 설치할 인터넷 연결이 없어 실제 model.ckpt end-to-end 추론은 여기서 재실행하지 못함.
- 실제 강사 PC에는 기존 Dashboard requirements.txt 환경(anomalib 2.3.3)이 있어야 함.
