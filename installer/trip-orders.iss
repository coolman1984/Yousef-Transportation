; Inno Setup script of the Trip Orders (built by tools/build_windows.py).
; The same TripOrders-Setup.exe installs the program on a new PC and updates it on a PC that already has it:
; only the program in Program Files is replaced, the data in %ProgramData%\TripOrders is never touched.

#define MyAppName "Trip Orders"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Mohamed Fawzy"
#endif
#ifndef AppCopyright
  #define AppCopyright "(c) 2026 Mohamed Fawzy"
#endif

[Setup]
AppId={{51A5FF77-EE7F-474F-9A55-53DEEF2A4B7A}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\TripOrders
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
DisableDirPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TripOrders-Setup-{#AppVersion}
SetupIconFile=..\build\triporders.ico
UninstallDisplayIcon={app}\TripOrders.exe
UninstallDisplayName={#MyAppName}
LicenseFile=..\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put an icon on the desktop"
Name: "autostart"; Description: "Start with Windows (recommended - keeps this PC in sync with the others)"

[Dirs]
; data, backups and settings: writable for everybody who uses this PC, kept when the program is updated or removed
Name: "{commonappdata}\TripOrders"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\build\to_main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"; Parameters: "--background"; Tasks: autostart

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; StatusMsg: "Allowing the other PCs to connect..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\TripOrders.exe"" enable=yes profile=any"; Flags: runhidden
Filename: "{app}\TripOrders.exe"; Description: "Open the {#MyAppName} now"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\TripOrders.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TripOrders.exe"; Flags: runhidden; RunOnceId: "StopTripOrders"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; RunOnceId: "FirewallRule"

[Messages]
FinishedLabel=The program is installed. Your data is kept in %ProgramData%\TripOrders (also after updates).

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { stop the running program (it is safe to stop at any moment), so its files can be replaced }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM TripOrders.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
  Result := '';
end;
