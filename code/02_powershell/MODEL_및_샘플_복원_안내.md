# 2차시 로컬 실행 복원

이 GitHub 배포용 패키지에는 원본의 **model/model.ckpt (75,214,193 bytes)**, `samples/` 이미지 및 JSON을 포함하지 않았습니다. 회사 제공 자료와 모델의 공개 권한을 확인할 수 없기 때문입니다.

로컬 PC에서 원래 사용하던 `Car_EfficientAD (2).zip`을 다시 열어 이 폴더에 다음 항목을 **원래 상대경로 그대로** 복사하세요.

- `model/model.ckpt`
- `samples/good/automotive_good_01.jpg`
- `samples/bad/automotive_defect_01.jpg`
- `samples/sample_good.json` 및 `samples/sample_bad.json` (사용 목적에 따라)

모델 SHA256 확인값은 원본 `README_FIRST.txt`에서 확인하세요. 원본 `00_install_windows.ps1`로 설치 후 `run_bad.ps1`, `run_good.ps1`을 실행합니다.

**주의:** 파일을 복원한 다음에도 `git add -f` 등을 사용해 실수로 GitHub에 업로드하지 마세요. `.gitignore`가 공개 유출 방지를 위해 해당 경로를 차단합니다.
