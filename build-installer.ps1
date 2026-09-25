param([string]$Compiler = '', [string]$Version = '0.1.1', [switch]$RebuildExe)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($RebuildExe) { & .\build-exe.ps1 }
if (-not (Test-Path -LiteralPath '.\dist\DotaBuildHelper.exe')) { throw 'Build the application with .\build-exe.ps1 first.' }
if (-not $Compiler) {
    $candidates = @((Join-Path $PSScriptRoot 'build\installer-tools\inno\ISCC.exe'),
                    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Compiler) { throw 'Install Inno Setup 6, or pass -Compiler with the full ISCC.exe path.' }
& $Compiler "/DAppVersion=$Version" '.\packaging\installer.iss'
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Get-Item -LiteralPath '.\dist\DotaBuildHelper-Setup.exe' | Select-Object FullName,Length
