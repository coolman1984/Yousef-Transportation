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
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
arabic.DesktopIcon=ضع أيقونة على سطح المكتب
english.DesktopIcon=Put an icon on the desktop
arabic.AutoStart=التشغيل مع ويندوز (موصى به)
english.AutoStart=Start with Windows (recommended)
arabic.LanAccess=السماح لأجهزة المكتب الأخرى بالدخول (للمكاتب التي فيها أكثر من جهاز فقط)
english.LanAccess=Let the other PCs of the office connect (only for offices with more than one PC)
arabic.Firewall=ضبط حماية بيانات التشغيل...
english.Firewall=Protecting the program data...
arabic.OpenNow=افتح «أوامر التحرك» الآن
english.OpenNow=Open Trip Orders now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "autostart"; Description: "{cm:AutoStart}"
; the one-PC pilot listens on this PC only; the other PCs of an office get in only when this box is ticked
Name: "lanaccess"; Description: "{cm:LanAccess}"; Flags: unchecked

[Dirs]
; data, backups, signing keys and settings: kept when the program is updated or removed. Access is narrowed in [Run] below (icacls):
; only SYSTEM, the administrators and ONE operator account (the person who installs, or /OPERATOR=DOMAIN\name) may read or write it.
Name: "{commonappdata}\TripOrders"; Permissions: admins-full system-full; Flags: uninsneveruninstall

[Files]
Source: "..\build\to_main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\TripOrders.exe"; Parameters: "--background"; Tasks: autostart

[Run]
; B2: the data tree is not shared with the other Windows accounts of this PC (databases and the raw signing keys live there)
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\TripOrders"" /inheritance:r /grant:r ""*S-1-5-18:(OI)(CI)F"" ""*S-1-5-32-544:(OI)(CI)F"" ""{param:OPERATOR|{username}}:(OI)(CI)M"" /remove:g ""*S-1-5-32-545"" ""*S-1-5-11"""; Flags: runhidden; StatusMsg: "{cm:Firewall}"
; B3: the firewall rule exists only when the office asked for it, and only for private/domain networks (never a public Wi-Fi)
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\TripOrders.exe"" enable=yes profile=private,domain"; Flags: runhidden; Tasks: lanaccess
Filename: "{app}\TripOrders.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\TripOrders.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TripOrders.exe"; Flags: runhidden; RunOnceId: "StopTripOrders"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; RunOnceId: "FirewallRule"

[Messages]
arabic.FinishedLabel=تم تثبيت البرنامج. بياناتك محفوظة في %ProgramData%\TripOrders وبتفضل موجودة بعد التحديثات.%n%nالبرنامج يعمل على هذا الجهاز فقط. لو عندك أكثر من جهاز في المكتب، أعد التثبيت واختر «السماح لأجهزة المكتب الأخرى» ثم اقرأ دليل الشبكة.
english.FinishedLabel=The program is installed. Your data is kept in %ProgramData%\TripOrders (also after updates).%n%nThe program works on this PC only. For an office with more than one PC, run the installer again and tick "Let the other PCs of the office connect", then read the network guide.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Cfg: String;
begin
  { other PCs of the office: listen on every network card, but only if the office asked for it and has no settings file yet }
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('lanaccess') then
  begin
    Cfg := ExpandConstant('{commonappdata}\TripOrders\config.json');
    if not FileExists(Cfg) then
      SaveStringToFile(Cfg, '{"host": "0.0.0.0"}', False);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { stop the running program (it is safe to stop at any moment), so its files can be replaced }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM TripOrders.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
  Result := '';
end;
