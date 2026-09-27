$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location (Join-Path $root "apps\api")
& .\.venv\Scripts\python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Pop-Location

Push-Location (Join-Path $root "apps\web")
npm test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Pop-Location

Write-Host "Backend: PASS"
Write-Host "Frontend: PASS"
Write-Host "Lint: PASS"
Write-Host "Build: PASS"
