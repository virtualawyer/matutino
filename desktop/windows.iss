; Windows installer for the desktop app (Inno Setup 6). Build the app with
; PyInstaller first, then from the repository root:
;     ISCC /DVersion=0.5.0 desktop\windows.iss
; Installs for the current user only: no administrator rights needed.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8AD33C98-487F-530A-95D8-170B3F62E7B5}
AppName=Matutino
AppVersion={#Version}
AppPublisher=Matutino
AppPublisherURL=https://github.com/virtualawyer/matutino
AppSupportURL=https://github.com/virtualawyer/matutino/issues
DefaultDirName={autopf}\Matutino
DefaultGroupName=Matutino
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..
OutputBaseFilename=Matutino-{#Version}-Windows-Setup
SetupIconFile=icon\Matutino.ico
UninstallDisplayIcon={app}\Matutino.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "startup"; Description: "Open Matutino when I sign in, so the paper prints on time"
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; Flags: unchecked

[Files]
Source: "..\dist\Matutino\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Matutino"; Filename: "{app}\Matutino.exe"
Name: "{autodesktop}\Matutino"; Filename: "{app}\Matutino.exe"; Tasks: desktopicon

[Registry]
; The same entry the app's "Open at login" switch writes.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Matutino"; ValueData: """{app}\Matutino.exe"" --background"; Tasks: startup

[Run]
Filename: "{app}\Matutino.exe"; Description: "Open Matutino now"; Flags: nowait postinstall skipifsilent

[Code]
// Remove the sign-in entry however it was made (installer or the app's own switch).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Matutino');
end;
