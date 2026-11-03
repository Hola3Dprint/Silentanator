$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& ./.venv/Scripts/python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name Silentanator --collect-data latex2mathml --collect-data matplotlib run_app.py
if ($LASTEXITCODE -ne 0) { throw 'Runner build failed.' }
& ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name SilentanatorSetup --collect-data latex2mathml --collect-data matplotlib setup_app.py
if ($LASTEXITCODE -ne 0) { throw 'Setup build failed.' }
Copy-Item -LiteralPath 'dist/Silentanator/Silentanator.exe' -Destination 'dist/SilentanatorSetup/Silentanator.exe' -Force
# Each executable uses its sibling _internal directory; merge runner dependencies.
Copy-Item -Path 'dist/Silentanator/_internal/*' -Destination 'dist/SilentanatorSetup/_internal' -Recurse -Force
& ./scripts/fetch_codex.ps1
if (-not (Test-Path -LiteralPath 'vendor/codex/codex.exe')) { throw 'Bundled Codex CLI is missing.' }
New-Item -ItemType Directory -Path 'dist/SilentanatorSetup/vendor/codex' -Force | Out-Null
Copy-Item -Path 'vendor/codex/*' -Destination 'dist/SilentanatorSetup/vendor/codex' -Recurse -Force
& ./.venv/Scripts/python.exe scripts/collect_licenses.py dist/SilentanatorSetup/licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Copy-Item -LiteralPath 'README.md','VERSION','THIRD_PARTY_NOTICES.md' -Destination 'dist/SilentanatorSetup' -Force
Write-Output 'Built dist/SilentanatorSetup. Keep the whole folder together.'
