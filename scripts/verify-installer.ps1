param([string]$ExePath = '.\dist\DotaBuildHelper.exe')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{DD97C321-37AE-4B80-B47F-385DAFC8230C}_is1'
if (Test-Path $uninstallKey) { throw 'An installed copy already exists; use a clean Windows account for installer verification.' }
$testRoot = Join-Path $PWD ('.local\installer-validation-' + [guid]::NewGuid().ToString('N'))
$installDir = Join-Path $testRoot 'app'
$profile = Join-Path $testRoot 'profile'
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$setupArgs = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$installDir+'"'),
               '/GROUP="Dota Build Helper Installer Test"','/MERGETASKS="!desktopicon"',('/LOG="'+$testRoot+'\install.log"'))
$oldProfile = $env:DOTA_HELPER_HOME
try {
    $env:DOTA_HELPER_HOME = $profile
    & '.\.venv\Scripts\python.exe' -c "from dota_helper.credentials import save_token; from dota_helper.paths import user_data_dir; from dota_helper.profile import save_settings; save_token('installer-test-credential'); save_settings(user_data_dir()/'settings.json', {'gsi_token':'installer-fixture-connection-token','role':5,'upgrade_marker':'keep'})"
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare encrypted test profile' }
    $settings = Join-Path $profile 'settings.json'
    $seedSettingsHash = (Get-FileHash $settings).Hash
    $credentialFile = Join-Path $profile 'stratz-key.bin'
    $credentialHash = (Get-FileHash $credentialFile).Hash
    $setup = Start-Process '.\dist\DotaBuildHelper-Setup.exe' -ArgumentList $setupArgs -WindowStyle Hidden -PassThru -Wait
    if ($setup.ExitCode -ne 0) { throw "Setup failed: $($setup.ExitCode)" }
    if ((Get-FileHash $settings).Hash -ne $seedSettingsHash -or (Get-FileHash $credentialFile).Hash -ne $credentialHash) { throw 'Install changed existing profile' }
    $installedExe = Join-Path $installDir 'DotaBuildHelper.exe'
    if ((Get-FileHash $installedExe).Hash -ne (Get-FileHash -LiteralPath $ExePath).Hash) { throw 'Installed payload mismatch' }
    $shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Dota Build Helper Installer Test\Dota Build Helper.lnk'
    if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Start menu shortcut missing' }
    $guideShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Dota Build Helper Installer Test\Quick setup.lnk'
    if (-not (Test-Path -LiteralPath $guideShortcut)) { throw 'Quick setup shortcut missing' }
    if ((Get-FileHash (Join-Path $installDir 'START-HERE.txt')).Hash -ne (Get-FileHash '.\packaging\START-HERE.txt').Hash) { throw 'Quick setup guide missing or outdated' }
    if (-not (Test-Path $uninstallKey)) { throw 'Uninstall registration missing' }
    if (Test-Path -LiteralPath (Join-Path $installDir 'stratz-key.bin')) { throw 'Unexpected credential in installation' }
    $env:DOTA_HELPER_HOME = $profile
    $report = Join-Path $testRoot 'smoke.json'
    $app = Start-Process $installedExe -ArgumentList @('--self-test',('"'+$report+'"')) -WindowStyle Hidden -PassThru
    if (-not $app.WaitForExit(30000)) { throw 'Installed app did not complete smoke test' }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $result.ok -or -not $result.frozen -or -not $result.credential_available) { throw 'Installed app smoke or credential access failed' }
    $settings = Join-Path $profile 'settings.json'
    $settingsHash = (Get-FileHash $settings).Hash
    $upgrade = Start-Process '.\dist\DotaBuildHelper-Setup.exe' -ArgumentList $setupArgs -WindowStyle Hidden -PassThru -Wait
    if ($upgrade.ExitCode -ne 0 -or (Get-FileHash $settings).Hash -ne $settingsHash) { throw 'Reinstall failed or changed settings' }
    if ((Get-FileHash $credentialFile).Hash -ne $credentialHash) { throw 'Reinstall changed saved credential' }
    & '.\.venv\Scripts\python.exe' -c "from dota_helper.credentials import load_token; assert load_token() == 'installer-test-credential'; print('Saved credential decrypts after reinstall')"
    if ($LASTEXITCODE -ne 0) { throw 'Credential lost after reinstall' }
    $uninstaller = Join-Path $installDir 'unins000.exe'
    $remove = Start-Process $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -PassThru -Wait
    if ($remove.ExitCode -ne 0) { throw 'Uninstall failed' }
    if (Test-Path -LiteralPath $installedExe) { throw 'Uninstall left the app executable' }
    if (Test-Path -LiteralPath $shortcut) { throw 'Uninstall left the shortcut' }
    if (Test-Path $uninstallKey) { throw 'Uninstall left its registration' }
    if ((Get-FileHash $settings).Hash -ne $settingsHash) { throw 'Uninstall changed retained user settings' }
    if ((Get-FileHash $credentialFile).Hash -ne $credentialHash) { throw 'Uninstall changed saved credential' }
    [ordered]@{ok=$true;install=$true;shortcut=$true;installed_app_smoke=$true;reinstall=$true;
               uninstall=$true;settings_preserved=$true;credential_preserved=$true;credential_decrypts=$true;report=$report} | ConvertTo-Json |
        Tee-Object -FilePath (Join-Path $testRoot 'verification.json')
} finally { $env:DOTA_HELPER_HOME = $oldProfile }
