param([switch]$Demo, [switch]$Source)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskExe = Join-Path $PSScriptRoot 'dist\DotaBuildHelper.exe'
if (-not $Source -and (Test-Path -LiteralPath $taskExe)) {
    if ($Demo) {
        Start-Process -FilePath $taskExe -ArgumentList '--demo' -WorkingDirectory $PSScriptRoot -WindowStyle Normal
    } else {
        Start-Process -FilePath $taskExe -WorkingDirectory $PSScriptRoot -WindowStyle Normal
    }
    return
}
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Run setup.ps1 first to install the local Python environment.'
}
$taskArgs = @('-m', 'dota_helper')
if ($Demo) { $taskArgs += '--demo' }
# This is the interactive GUI itself; pythonw avoids opening an extra console.
Start-Process -FilePath $taskPython -ArgumentList $taskArgs -WorkingDirectory $PSScriptRoot -WindowStyle Normal
