#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
[Setup]
AppId={{DD97C321-37AE-4B80-B47F-385DAFC8230C}
AppName=Dota Build Helper
AppVersion={#AppVersion}
AppPublisher=Dota Build Helper
DefaultDirName={localappdata}\Programs\Dota Build Helper
DefaultGroupName=Dota Build Helper
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=DotaBuildHelper-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\dota_helper\data\app-icon.ico
UninstallDisplayIcon={app}\DotaBuildHelper.exe
CloseApplications=yes
RestartApplications=no
InfoAfterFile=START-HERE.txt

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\DotaBuildHelper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "TESTING.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "START-HERE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dota_helper\data\OPENDOTA-LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "licenses\*.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{group}\Dota Build Helper"; Filename: "{app}\DotaBuildHelper.exe"; WorkingDir: "{app}"
Name: "{group}\Offline demo"; Filename: "{app}\DotaBuildHelper.exe"; Parameters: "--demo"; WorkingDir: "{app}"
Name: "{group}\Testing guide"; Filename: "{app}\TESTING.txt"
Name: "{group}\Quick setup"; Filename: "{app}\START-HERE.txt"
Name: "{autodesktop}\Dota Build Helper"; Filename: "{app}\DotaBuildHelper.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DotaBuildHelper.exe"; Description: "Launch Dota Build Helper"; Flags: nowait postinstall skipifsilent
