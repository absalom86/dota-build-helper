param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Prevent unrelated developer tools (e.g. Poppler ICU DLLs) on PATH from
# being bundled in place of the Windows libraries Qt expects.
$taskBuildPath = $env:PATH
try {
    $env:PATH = "$PSScriptRoot\.venv\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    & '.\.venv\Scripts\python.exe' -m PyInstaller --clean --noconfirm --distpath $OutputDirectory packaging\DotaBuildHelper.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
} finally {
    $env:PATH = $taskBuildPath
}
Get-Item -LiteralPath (Join-Path $OutputDirectory 'DotaBuildHelper.exe') | Select-Object FullName,Length
