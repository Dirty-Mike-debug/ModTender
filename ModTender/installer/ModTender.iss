; Inno Setup script for ModTender. Built by GitHub Actions:
;   iscc /DMyAppVersion=0.6.0 installer\ModTender.iss
; Installs per-user (no admin prompt), so in-app updates can run silently.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2B1E-5A6D-4E7F-9B0C-1D2E3F4A5B6C}
AppName=ModTender
AppVersion={#MyAppVersion}
AppVerName=ModTender {#MyAppVersion}
AppPublisher=Dirty-Mike-debug
AppPublisherURL=https://github.com/Dirty-Mike-debug/ModTender
AppSupportURL=https://github.com/Dirty-Mike-debug/ModTender/issues
AppUpdatesURL=https://github.com/Dirty-Mike-debug/ModTender/releases
DefaultDirName={localappdata}\Programs\ModTender
DefaultGroupName=ModTender
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ModTender-Setup-{#MyAppVersion}
SetupIconFile=..\modtender\assets\modtender.ico
UninstallDisplayIcon={app}\ModTender.exe
UninstallDisplayName=ModTender
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=ModTender Setup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove the previous version's program files first so nothing stale is left behind.
; (Settings, backups and disabled mods live in %LOCALAPPDATA%\ModTender and are never touched.)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ModTender\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ModTender"; Filename: "{app}\ModTender.exe"
Name: "{autodesktop}\ModTender"; Filename: "{app}\ModTender.exe"; Tasks: desktopicon

[Run]
; Runs after a normal install (as a checkbox) and also after a silent in-app update.
Filename: "{app}\ModTender.exe"; Description: "{cm:LaunchProgram,ModTender}"; Flags: nowait postinstall
