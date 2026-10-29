$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[INFO] .venv not found. Using py -3.12" -ForegroundColor Yellow
    py -3.12 engine\run_infer.py --image samples\bad\automotive_defect_01.jpg --actual DEFECT --output-name DEFECT_result
} else {
    & $python engine\run_infer.py --image samples\bad\automotive_defect_01.jpg --actual DEFECT --output-name DEFECT_result
}
