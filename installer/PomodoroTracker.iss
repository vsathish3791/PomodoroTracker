; Inno Setup script for Pomodoro Tracker. Built by build.py, which passes /DAppVersion.
; Installs for the current user only (no admin rights needed).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F0B8C55-2E4B-4C1E-9C55-7A3F5B1D2E90}
AppName=Pomodoro Tracker
AppVersion={#AppVersion}
AppPublisher=vsathish3791
DefaultDirName={localappdata}\Programs\Pomodoro Tracker
DefaultGroupName=Pomodoro Tracker
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer_output
OutputBaseFilename=PomodoroTracker-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\PomodoroTracker.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Pomodoro Tracker when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\PomodoroTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pomodoro Tracker"; Filename: "{app}\PomodoroTracker.exe"
Name: "{group}\Uninstall Pomodoro Tracker"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Pomodoro Tracker"; Filename: "{app}\PomodoroTracker.exe"; Tasks: desktopicon
Name: "{userstartup}\Pomodoro Tracker"; Filename: "{app}\PomodoroTracker.exe"; Tasks: startup

[Run]
Filename: "{app}\PomodoroTracker.exe"; Description: "Start Pomodoro Tracker now"; Flags: nowait postinstall skipifsilent

; Your tasks and history (%APPDATA%\PomodoroTracker\pomodoro.db) are kept when you uninstall.
