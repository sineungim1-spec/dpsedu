AI Vision Dashboard 수정본

수정 이유
- 기존 app.py가 `from lan_info import get_lan_ip`를 사용했지만
  배포 ZIP에 lan_info.py가 빠져 있어
  ModuleNotFoundError: No module named 'lan_info'가 발생했습니다.

수정 내용
1. lan_info.py를 배포본에 추가했습니다.
2. app.py에도 fallback 함수를 넣어 lan_info.py가 실수로 빠져도
   Dashboard 자체가 중단되지 않도록 보강했습니다.
3. 기존 dashboard_core.py, diagnose_environment.py, requirements.txt,
   .streamlit/config.toml은 그대로 유지했습니다.

기존 .venv를 삭제하거나 패키지를 다시 설치할 필요가 없습니다.

사용 방법
1. 기존 폴더에서 app.py를 이 수정본 app.py로 교체하고 lan_info.py를 추가하거나,
   더 간단하게 이 ZIP을 새 폴더에 압축 해제합니다.
2. 이미 만든 .venv를 새 폴더로 옮기는 것보다,
   기존 AI_Vision_dashboard 폴더에 수정본 파일들을 덮어쓰는 방법을 권장합니다.
3. PowerShell에서:
   .\.venv\Scripts\python.exe -m streamlit run app.py

정상 실행되면:
Local URL: http://localhost:8501
Network URL: http://<내 LAN IP>:8501
가 표시됩니다.
