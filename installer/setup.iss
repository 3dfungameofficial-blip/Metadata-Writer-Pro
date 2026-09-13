; Inno Setup script — build with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
; Release checklist: bump MyAppVersion here together with APP_VERSION in
; metadata_writer_pro/app/__init__.py. Keep AppId stable forever so upgrades
; replace the old install instead of creating duplicates. User data in
; %APPDATA%\Metadata Writer Pro (settings, history, logs, backups) is
; intentionally NOT touched by install or uninstall, so it survives upgrades.
#define MyAppName "Metadata Writer Pro"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Metadata Writer Pro"
#define MyAppExeName "MetadataWriterPro.exe"

[Setup]
AppId={{8B4F6A2C-1D3E-4A5B-9C7D-2E6F0A1B3C4D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Metadata Writer Pro
DefaultGroupName=Metadata Writer Pro
OutputBaseFilename=MetadataWriterPro-Setup
OutputDir=..
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
SetupIconFile=..\assets\icon.ico
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MetadataWriterPro.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
