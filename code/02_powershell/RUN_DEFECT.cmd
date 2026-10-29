@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe engine\run_infer.py --image samples\bad\automotive_defect_01.jpg --actual DEFECT --output-name DEFECT_result
) else (
  py -3.12 engine\run_infer.py --image samples\bad\automotive_defect_01.jpg --actual DEFECT --output-name DEFECT_result
)
pause
