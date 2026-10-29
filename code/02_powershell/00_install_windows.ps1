$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-cache-dir torch==2.12.1 torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install anomalib==2.3.3 lightning==2.6.1 pytorch-lightning==2.6.1 timm==1.0.29 kornia==0.8.3 torchmetrics==1.9.0 omegaconf==2.3.1 einops==0.8.2 scikit-learn==1.9.0 matplotlib==3.11.1 opencv-python==5.0.0.93 pillow pandas
Write-Host "INSTALL COMPLETE - Candidate4 E07-S Session 02" -ForegroundColor Green
