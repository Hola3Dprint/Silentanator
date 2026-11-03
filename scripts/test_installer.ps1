$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (Test-Path -LiteralPath 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/Silentanator') {
    throw 'Run the installer tests in a clean environment without an existing registered installation.'
}
$taskQa = [IO.Path]::GetFullPath((Join-Path $taskRoot '.qa'))
New-Item -ItemType Directory -Path $taskQa -Force | Out-Null
$taskInstall = Join-Path $taskQa ('InstallSmoke-' + [Guid]::NewGuid().ToString('N'))
$taskInstaller = Join-Path $taskRoot 'release/Silentanator-Setup.exe'
$taskLog = Join-Path $taskQa 'installer-smoke-error.log'
$taskSettings = Join-Path $env:LOCALAPPDATA 'Silentanator/settings.json'
$taskBefore = if (Test-Path -LiteralPath $taskSettings) { (Get-FileHash -LiteralPath $taskSettings).Hash } else { $null }
function Invoke-InstallTest {
    $taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList '--quiet','--no-shortcuts','--dir',"`"$taskInstall`"",'--log',"`"$taskLog`"" -WindowStyle Hidden -Wait -PassThru
    if ($taskProcess.ExitCode -ne 0) { Get-Content -LiteralPath $taskLog; throw 'Installer smoke test failed.' }
}
Invoke-InstallTest
$taskReport = Join-Path $taskQa 'installed-app-check.json'
$taskCharts = Join-Path $taskQa 'installed-chart-check'
$taskApp = Start-Process -FilePath (Join-Path $taskInstall 'Silentanator.exe') -ArgumentList '--check-install','--check-charts',"`"$taskCharts`"",'--report',"`"$taskReport`"" -WindowStyle Hidden -Wait -PassThru
if ($taskApp.ExitCode -ne 0) { throw 'Installed runtime check failed.' }
$taskResult = Get-Content -LiteralPath $taskReport -Raw | ConvertFrom-Json
if (-not $taskResult.ok -or $taskResult.codex -ne (Join-Path $taskInstall 'vendor/codex/codex.exe')) { throw 'Bundled CLI discovery failed.' }
if (-not $taskResult.chart -or -not (Test-Path -LiteralPath $taskResult.chart)) { throw 'Installed chart generation failed.' }
$taskPersonal = Join-Path $taskInstall 'my-kept-notes.txt'
Set-Content -LiteralPath $taskPersonal -Value 'Keep this personal file.'
Invoke-InstallTest
if ((Get-Content -LiteralPath $taskPersonal -Raw).Trim() -ne 'Keep this personal file.') { throw 'Upgrade did not preserve extra files.' }
$taskUpdateReport = Join-Path $taskQa 'apply-update-report.json'
$taskUpdate = Start-Process -FilePath $taskInstaller -ArgumentList '--apply-update','--no-shortcuts','--dir',"`"$taskInstall`"",'--update-report',"`"$taskUpdateReport`"",'--log',"`"$taskLog`"" -WindowStyle Hidden -Wait -PassThru
if ($taskUpdate.ExitCode -ne 0) { Get-Content -LiteralPath $taskLog; throw 'Update handoff installation failed.' }
if ((Get-Content -LiteralPath $taskUpdateReport -Raw | ConvertFrom-Json).state -ne 'installed') { throw 'Update handoff did not report success.' }
if ((Get-Content -LiteralPath $taskPersonal -Raw).Trim() -ne 'Keep this personal file.') { throw 'One-click update removed personal files.' }
$taskResolved = (Resolve-Path -LiteralPath $taskInstall).Path
if (-not $taskResolved.StartsWith($taskQa + [IO.Path]::DirectorySeparatorChar) -or
    (Get-Content -LiteralPath (Join-Path $taskResolved '.silentanator-install') -Raw).Trim() -ne 'f9334ef5-a351-4fba-a0a0-b563af7c6697') {
    throw 'Uninstall test target verification failed.'
}
$taskUninstall = Start-Process -FilePath (Join-Path $taskResolved 'Uninstall.exe') -ArgumentList '--quiet' -WindowStyle Hidden -Wait -PassThru
if ($taskUninstall.ExitCode -ne 0) { throw 'Uninstaller failed.' }
for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
    if (-not (Test-Path -LiteralPath (Join-Path $taskInstall 'Uninstall.exe'))) { break }
    Start-Sleep -Seconds 1
}
if (Test-Path -LiteralPath (Join-Path $taskInstall 'Silentanator.exe')) { throw 'Uninstall did not remove the app.' }
if ((Get-Content -LiteralPath $taskPersonal -Raw).Trim() -ne 'Keep this personal file.') { throw 'Uninstall removed personal files.' }
if (Test-Path -LiteralPath 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/Silentanator') { throw 'Uninstall registration remains.' }
$taskAfter = if (Test-Path -LiteralPath $taskSettings) { (Get-FileHash -LiteralPath $taskSettings).Hash } else { $null }
if ($taskBefore -ne $taskAfter) { throw 'Installer changed personal settings.' }
# Remove only the disposable sentinel and its now-empty test directory.
Remove-Item -LiteralPath $taskPersonal -Force
Remove-Item -LiteralPath $taskInstall
Write-Output 'Install, bundled runtime, upgrade, native uninstall, and personal-file preservation passed.'
