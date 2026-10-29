# AI Vision 기업연계 프로젝트: GitHub + Netlify 통합 배포본

**다른 GitHub 계정에 업로드하기 위한 계정 독립형 통합 폴더입니다.** Netlify는 사이트의 네 차시 소개/체험 화면을 제공하며, 3차시 HTML만 직접 실행합니다. 2차시의 모델 추론 및 5차시 Streamlit Python 추론은 Netlify 서버에서 실행되지 않습니다.

## 폴더 구성

```text
├─ netlify.toml                       ← Netlify 설정 (publish = site)
├─ site/
│  ├─ index.html                     ← 통합 첫 화면
│  ├─ site-config.json               ← 계정/외부 링크 연결 설정
│  ├─ 02/index.html                  ← PowerShell 실제 평가기록 및 방법
│  ├─ 03/index.html                  ← 시뮬레이터 체험 페이지
│  ├─ 03/simulator.html              ← 3차시 HTML 원본 그대로
│  ├─ 04/index.html                  ← Colab 원본 연결 자리
│  └─ 05/index.html                  ← Streamlit 정적 미리보기
├─ code/
│  ├─ 02_powershell/                 ← 제공된 2차시 원본 실행 소스/설정(모델·샘플 제외)
│  └─ 05_streamlit/                  ← 제공된 5차시 Streamlit 원본 소스(캐시 제외)
├─ colab/
│  └─ 04_COLAB_연결용_안내.ipynb       ← 실제 학습 코드 아님
└─ tools/
   ├─ generate_qr.py               ← 최종 배포 URL로 QR PNG 5개 생성
   └─ verify_package.py            ← 파일 검증
```

## 5분 배포 순서 (새 계정)

1. 이 ZIP 파일을 컴퓨터에서 **압축 해제**합니다. GitHub에 ZIP 파일만 업로드하면 사이트로 자동 풀리지 않습니다.
2. 새 GitHub 계정에서 **빈 저장소(repository)**를 하나 생성합니다. 공개 범위는 제공된 자료의 공개 권한을 확인하여 결정하세요. 공개용 웹사이트를 만들 경우 저장소 내용을 공개해도 되는지 먼저 검토합니다.
3. 압축 해제한 폴더에서 터미널을 열어 아래 예시 명령을 실행합니다. GitHub Desktop으로 해당 폴더를 열어 Publish Repository를 눌러도 됩니다.

   ```sh
   git init
   git add .
   git commit -m "AI Vision 2-5차시 통합 아카이브"
   git branch -M main
   git remote add origin https://github.com/새계정/새저장소.git
   git push -u origin main
   ```

   이미 git 저장소가 있다면 `git init`, `git remote add`는 생략하고 기존 설정을 확인합니다.

4. Netlify에서 **Add new project → Import an existing project → GitHub**로 해당 저장소를 선택합니다. 설정은 루트 `netlify.toml`을 읽어서 **Publish directory = `site`**, 빌드 명령 없이 정적 사이트로 배포됩니다.
5. 발급된 `https://사이트명.netlify.app/`로 들어가 4개 차시 링크를 확인합니다. 변경이 GitHub에 push되면 연결된 Netlify가 사이트를 재배포할 수 있습니다.

## 반드시 수정할 파일: `site/site-config.json`

```json
{
  "_설명": "다른 GitHub 계정 및 Netlify 계정용. 빈 칸은 연결 전 상태로 표시됩니다.",
  "project_name": "AI Vision 기업연계 수업 디지털 결과물",
  "github_repository": "https://github.com/새계정/새저장소",
  "colab_url": "https://colab.research.google.com/...원본노트북...",
  "streamlit_url": "https://...streamlit.app",
  "session02_video_url": "https://...공개가능한시연영상..."
}
```

빈 주소는 지우지 않아도 되며 해당 버튼이 '연결 전' 상태가 됩니다. 실제 URL로 교체하면 됩니다. 실제 원본 Colab 링크가 없으면 연결용 안내 노트북만 표시할 수 있습니다.

## 보고서에 사용할 차시별 링크

- 2차시 `https://사이트명.netlify.app/02/`
- 3차시 `https://사이트명.netlify.app/03/`
- 4차시 `https://사이트명.netlify.app/04/`
- 5차시 `https://사이트명.netlify.app/05/`

사이트 배포 뒤에 실제 주소를 기준으로 QR을 생성해야 합니다.

```sh
pip install "qrcode[pil]"
python tools/generate_qr.py https://사이트명.netlify.app
```

그러면 `qr-output/` 아래 고해상도 QR PNG 5개(통합홈 + 2~5차시)와 검수용 최종 URL 텍스트 파일이 생성됩니다. QR을 인쇄하기 전에 스마트폰으로 스캔 테스트하세요.

## 원본 제공 상태 / 사실관계

| 차시 | 첨부 확인 | 정적 홈페이지 실행 | GitHub 안의 원본 |
|---|---|---|---|
| 02 PowerShell EfficientAD | 제공됨 | 설명·검증 기록만 | Python/PowerShell 실행 소스, runtime, artifacts. 모델·샘플 제외 |
| 03 촬영조건·ROI HTML | 제공됨 | **직접 작동** | `site/03/simulator.html` 원본 |
| 04 Google Colab | **원본 미제공** | 링크 안내 페이지 | 연결용 안내 `.ipynb`만 |
| 05 Streamlit Dashboard | 제공됨 | 정적 검증기록 미리보기 | 실제 Python 앱 소스, 실행 환경은 별도 |

2차시 기록: GOOD 48(OK20, REVIEW24, NG4), BAD 64(OK0, REVIEW14, NG50), 전체 112, AUROC 약 0.9102. 이 수치는 모델 패키지에 기록된 자료이며 사이트에서 재실행·재검증한 결과가 아닙니다. 결과를 학생 개인의 성적 향상이나 실제 기업 현장 승인 결과로 제시하지 마세요.

## 공개 전 반드시 확인할 사항

- 회사 제공 모델, 샘플 이미지, 내부 설정/성능 자료, 기업명, 코드의 **공개 허락 및 저작권** 여부를 확인하세요. 이 패키지는 모델과 샘플 이미지 업로드를 기본 차단했지만, `code/02_powershell/artifacts/` 등 메타데이터는 포함하므로 권한 없는 공개라면 해당 소스 폴더를 **삭제하고 공개**하세요.
- Netlify는 정적 웹만 호스팅합니다. Streamlit 앱을 따로 공개하더라도 대용량 ML 모델과 추론 서버는 별도 리소스와 권한이 필요합니다.
- 3차시 원본 HTML에는 실제 제공 기업 관련 문구가 있을 수 있으므로 대외 공개 여부를 확인하세요.
- 4차시 실제 학습 노트북과 5차시 실시간 앱 연결은 사용자가 자료 및 배포 URL을 추가해야 완성됩니다.
- 첨부된 Python 모델이 실제 회사의 승인된 운영 시스템임을 의미하지 않습니다. 인간 검증(HUMAN_IN_THE_LOOP)을 유지합니다.

## 검증

```sh
python tools/verify_package.py
```

**자세한 배포 체크리스트**: `배포_및_QR_안내.md`를 참고하세요.
