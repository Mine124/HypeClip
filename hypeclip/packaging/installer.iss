#define MyAppName "HypeClip Studio"
#define MyAppVersion "2.1.0"
#define MyAppExeName "HypeClip.exe"

[Setup]
AppId={{D4A8E1F2-77C9-4B6A-9E52-3C1B63E952D4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\HypeClip
DefaultGroupName={#MyAppName}
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=HypeClip-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
  GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\HypeClip\*"; DestDir: "{app}"; \
  Flags: recursesubdirs ignoreversion createallsubdirs

[Dirs]
Name: "{localappdata}\HypeClip"; Permissions: users-modify
Name: "{localappdata}\HypeClip\app"; Permissions: users-modify
Name: "{localappdata}\HypeClip\backups"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (Debug)"; Filename: "{app}\HypeClip-Debug.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\HypeClip\work"