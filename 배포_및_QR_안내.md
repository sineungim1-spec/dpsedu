# 새 GitHub 계정으로 옮길 때 체크리스트

## 1. ZIP을 풀고 GitHub로 업로드

- [ ] 압축을 푼 폴더의 **내용물 전체**를 새 GitHub 저장소에 올리기
- [ ] `netlify.toml`이 저장소의 최상위에 있는지 확인
- [ ] `site/03/simulator.html`이 존재하는지 확인
- [ ] `code/02_powershell/model/model.ckpt`가 GitHub에 없는지 확인
- [ ] 기업 제공 코드/설정/모델 관련 공개 권한 확인

## 2. Netlify에 연결

- [ ] 새 저장소에서 import
- [ ] Base directory: 비움
- [ ] Build command: 비움
- [ ] Publish directory: `site` (루트 `netlify.toml` 자동 설정)
- [ ] 공개 URL에서 `/`, `/02/`, `/03/`, `/04/`, `/05/` 접속 확인
- [ ] `/03/simulator.html`에서 변수 조절 및 Before/After 비교 확인

## 3. 4차시·5차시 외부 링크 설정

- [ ] 실제 4차시 `.ipynb` 업로드 후 `site/site-config.json`의 `colab_url`에 링크 입력
- [ ] 실제 Streamlit Cloud 앱 배포 **검증 완료 후** `streamlit_url` 입력
- [ ] 2차시 실행 영상이 있다면 업로드 권한을 확인하고 `session02_video_url` 입력
- [ ] 커밋/푸시 후 Netlify 재배포 확인

## 4. 연구보고서 QR 인쇄 전

- [ ] 실제 Netlify 도메인이 확정되면 `python tools/generate_qr.py https://내사이트.netlify.app` 실행
- [ ] 생성된 5개 PNG와 최종URL.txt의 링크를 교차 검토
- [ ] 모바일에서 4개 QR코드 직접 스캔
- [ ] 3차시는 PC화면 권장 문구 포함
- [ ] 2·5차시 '정적 기록'을 '실시간 AI 판정'으로 잘못 표현하지 않았는지 확인
- [ ] 보고서 본문에는 핵심 결과와 학생 활동 증거를 QR 없이도 확인 가능하게 수록
