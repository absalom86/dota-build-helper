param([string]$ExePath = '.\dist\DotaBuildHelper.exe')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$taskOriginalData = $env:DOTA_HELPER_HOME
$taskReport = Join-Path $PWD '.local\exe-verification\report.json'
try {
    $env:DOTA_HELPER_HOME = Join-Path $PWD '.local\exe-verification\settings'
    if (Test-Path -LiteralPath $taskReport) { Remove-Item -LiteralPath $taskReport }
    $taskExe = Start-Process -FilePath $ExePath -ArgumentList @('--self-test', '.local/exe-verification/report.json') -WorkingDirectory $PWD -WindowStyle Hidden -PassThru
    if (-not $taskExe.WaitForExit(30000)) { throw "Executable smoke test timed out (PID $($taskExe.Id))." }
    if (-not (Test-Path -LiteralPath $taskReport)) { throw 'Executable produced no verification report.' }
    $taskResult = Get-Content -LiteralPath $taskReport -Raw | ConvertFrom-Json
    if (-not $taskResult.ok -or -not $taskResult.frozen) { throw ($taskResult | ConvertTo-Json -Depth 5) }
    $taskResult | ConvertTo-Json -Depth 5
} finally {
    $env:DOTA_HELPER_HOME = $taskOriginalData
}
