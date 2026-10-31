$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVendor = Join-Path $taskRoot 'vendor/codex'
$taskCache = Join-Path $taskRoot '.tools'
New-Item -ItemType Directory -Path $taskVendor,$taskCache -Force | Out-Null
$taskTag = 'rust-v0.166.0'
$taskAssets = @(
    @{ Name='codex-x86_64-pc-windows-msvc.exe.zip'; Hash='bf67d9662ed539f305849b74ad6420cc7b23aa2be07753710ca3db9134a0246d' },
    @{ Name='codex-command-runner-x86_64-pc-windows-msvc.exe'; Hash='5e68e3f5b4640af55db2873a0d0dc038907145708f9e735870d9279a8074c2df' },
    @{ Name='codex-windows-sandbox-setup-x86_64-pc-windows-msvc.exe'; Hash='3995c4f57199eb8023a0f3a585f6e9fdc4d5174c22a51837aaeb15beb52954f0' }
)
foreach ($taskAsset in $taskAssets) {
    $taskFile = Join-Path $taskCache $taskAsset.Name
    if (-not (Test-Path -LiteralPath $taskFile)) {
        Invoke-WebRequest -Uri "https://github.com/openai/codex/releases/download/$taskTag/$($taskAsset.Name)" -OutFile $taskFile
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $taskFile).Hash.ToLowerInvariant() -ne $taskAsset.Hash) {
        throw "Codex checksum mismatch: $($taskAsset.Name)"
    }
}
Expand-Archive -LiteralPath (Join-Path $taskCache $taskAssets[0].Name) -DestinationPath $taskVendor -Force
$taskExe = Join-Path $taskVendor 'codex-x86_64-pc-windows-msvc.exe'
if (Test-Path -LiteralPath $taskExe) { Move-Item -LiteralPath $taskExe -Destination (Join-Path $taskVendor 'codex.exe') -Force }
$taskPackage = Join-Path $taskVendor 'codex-package.json'
$taskMetadata = Get-Content -LiteralPath $taskPackage -Raw | ConvertFrom-Json
$taskMetadata.entrypoint = 'codex.exe'
$taskMetadata | ConvertTo-Json | Set-Content -LiteralPath $taskPackage -Encoding utf8
Copy-Item -LiteralPath (Join-Path $taskCache $taskAssets[1].Name) -Destination (Join-Path $taskVendor 'codex-command-runner.exe') -Force
Copy-Item -LiteralPath (Join-Path $taskCache $taskAssets[2].Name) -Destination (Join-Path $taskVendor 'codex-windows-sandbox-setup.exe') -Force
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/openai/codex/$taskTag/LICENSE" -OutFile (Join-Path $taskVendor 'LICENSE.txt')
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/openai/codex/$taskTag/NOTICE" -OutFile (Join-Path $taskVendor 'NOTICE.txt')
Set-Content -LiteralPath (Join-Path $taskVendor 'VERSION.txt') -Value $taskTag -Encoding utf8
Write-Output "Verified official Codex $taskTag."
