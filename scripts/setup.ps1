Param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path ".venv")) {
  & $Python -m venv .venv
}

$venvPython = Join-Path ".venv" "Scripts" "python.exe"
if (-not (Test-Path $venvPython)) {
  $venvPython = Join-Path ".venv" "bin" "python"
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython -m playwright install

if (-not (Test-Path ".env") -and (Test-Path "env.example")) {
  Copy-Item "env.example" ".env"
}

Write-Host "[ok] Environment ready. Activate with '.venv\\Scripts\\Activate.ps1' or 'source .venv/bin/activate'."
