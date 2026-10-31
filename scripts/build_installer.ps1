param([switch]$SkipAppBuild)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not $SkipAppBuild) { & ./build.ps1 }
if (-not (Test-Path -LiteralPath 'dist/SilentanatorSetup/vendor/codex/codex.exe')) {
    throw 'Build the complete application with build.ps1 first.'
}
$taskVersion = (Get-Content -LiteralPath VERSION -Raw).Trim()
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $taskCompiler)) { throw 'The built-in .NET Framework C# compiler is missing.' }
$taskUninstaller = [IO.Path]::GetFullPath((Join-Path $taskRoot 'dist/SilentanatorSetup/Uninstall.exe'))
$taskSource = (Resolve-Path -LiteralPath (Join-Path $taskRoot 'installer/Uninstall.cs')).Path
& $taskCompiler /nologo /target:winexe /optimize+ /r:System.Windows.Forms.dll "/out:$taskUninstaller" $taskSource
if ($LASTEXITCODE -ne 0) { throw 'Native uninstaller compilation failed.' }
Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.md' -Destination 'dist/SilentanatorSetup' -Force
New-Item -ItemType Directory -Path 'dist/SilentanatorSetup/licenses/dotnet' -Force | Out-Null
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/dotnet/runtime/v8.0.33/LICENSE.TXT' -OutFile 'dist/SilentanatorSetup/licenses/dotnet/LICENSE.TXT'
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/dotnet/runtime/v8.0.33/THIRD-PARTY-NOTICES.TXT' -OutFile 'dist/SilentanatorSetup/licenses/dotnet/THIRD-PARTY-NOTICES.TXT'
$taskPayload = Join-Path $taskRoot 'build/installer-payload.zip'
$taskInfo = Join-Path $taskRoot 'build/installer-payload.json'
& ./.venv/Scripts/python.exe scripts/package_payload.py dist/SilentanatorSetup $taskPayload $taskInfo
if ($LASTEXITCODE -ne 0) { throw 'Could not package installer payload.' }
New-Item -ItemType Directory -Path release -Force | Out-Null
dotnet publish installer/Silentanator.Installer.csproj -c Release -r win-x64 --self-contained true `
    --configfile installer/NuGet.Config -o release `
    "-p:PayloadFile=$taskPayload" "-p:PayloadInfo=$taskInfo" "-p:Version=$taskVersion"
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
$taskInstaller = Join-Path $taskRoot 'release/Silentanator-Setup.exe'
$taskValidation = Join-Path $taskRoot 'build/installer-validation.json'
$taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList '--validate-payload','--report',"`"$taskValidation`"" -WindowStyle Hidden -Wait -PassThru
if ($taskProcess.ExitCode -ne 0) { throw 'Installer payload validation failed.' }
$taskHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $taskInstaller).Hash.ToLowerInvariant()
Set-Content -LiteralPath 'release/SHA256SUMS.txt' -Value "$taskHash  Silentanator-Setup.exe" -Encoding ascii
Write-Output "Installer ready: $taskInstaller"
