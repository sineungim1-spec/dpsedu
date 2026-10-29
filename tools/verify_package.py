#!/usr/bin/env python3
"""Non-executing integrity and publish-safety check."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent
required=['netlify.toml','site/index.html','site/02/index.html','site/03/index.html','site/03/simulator.html','site/04/index.html','site/05/index.html','site/assets/style.css','site/assets/common.js','site/site-config.json','code/02_powershell/run_bad.ps1','code/05_streamlit/app.py','colab/README.md']
missing=[s for s in required if not (root/s).is_file()]
large=[(str(p.relative_to(root)),p.stat().st_size) for p in root.rglob('*') if p.is_file() and p.stat().st_size>20_000_000]
models=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.ckpt','.pt','.pth','.onnx','.safetensors')]
config=json.loads((root/'site/site-config.json').read_text(encoding='utf8'))
assert not missing, f'필수 파일 누락: {missing}'
assert not large, f'20MB 넘는 파일: {large}'
assert not models, f'공개용 저장소에 모델 발견: {models}'
assert 'colab_url' in config and 'streamlit_url' in config
print('OK: 사이트 4차시, JS/CSS, Netlify 설정, 로컬 소스 파일 존재')
print('OK: 공개용 묶음에 모델 가중치 및 대용량 파일 없음')
print('파일 수:',sum(p.is_file() for p in root.rglob('*')))
