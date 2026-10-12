; Inno Setup script of the Trip Orders (built by tools/build_windows.py).
; The same TripOrders-Setup.exe installs the program on a new PC and updates it on a PC that already has it:
; only the program in Program Files is replaced, the data in %ProgramData%\TripOrders is never touched.

#define MyAppName "Trip Orders"
#ifndef AppChannel
  #define AppChannel "commercial"
#endif
#if AppChannel == "ci-test"
  #define AppDisplayName "Trip Orders - CI TEST - NOT FOR CUSTOMERS"
  #define AppFileSuffix "-CI-TEST-NOT-FOR-CUSTOMERS"
#else
  #define AppDisplayName "Trip Orders"
  #define AppFileSuffix ""
#endif
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
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName} {#AppVersion}
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
OutputBaseFilename=TripOrders-Setup-{#AppVersion}{#AppFileSuffix}
SetupIconFile=..\build\triporders.ico
UninstallDisplayIcon={app}\TripOrders.exe
UninstallDisplayName={#AppDisplayName}
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
arabic.ThisPcOnly=هذا الجهاز فقط (أجهزة المكتب الأخرى لا تستطيع الدخول)
english.ThisPcOnly=This PC only (other PCs of the office cannot connect)
arabic.Firewall=ضبط حماية بيانات التشغيل...
english.Firewall=Protecting the program data...
arabic.OpenNow=افتح «أوامر التحرك» الآن
english.OpenNow=Open Trip Orders now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "autostart"; Description: "{cm:AutoStart}"
; by default every PC of the office LAN can connect (owner decision 6 Oct 2026, reconfirmed 11 Oct); ticking this box restricts the program to this PC
Name: "thispconly"; Description: "{cm:ThisPcOnly}"; Flags: unchecked

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
; B3: the firewall rule is limited to private/domain networks (never a public Wi-Fi) and is not added when the office chose "this PC only"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\TripOrders.exe"" enable=yes profile=private,domain"; Flags: runhidden; Tasks: not thispconly
Filename: "{app}\TripOrders.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\TripOrders.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TripOrders.exe"; Flags: runhidden; RunOnceId: "StopTripOrders"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; RunOnceId: "FirewallRule"

[Messages]
arabic.FinishedLabel=تم تثبيت البرنامج. بياناتك محفوظة في %ProgramData%\TripOrders وبتفضل موجودة بعد التحديثات.%n%nيمكن لأجهزة المكتب الأخرى الدخول إلى البرنامج عبر شبكة المكتب. إذا أردت أن يعمل على هذا الجهاز فقط، أعد التثبيت واختر «هذا الجهاز فقط». اقرأ دليل الشبكة لمزيد من التفاصيل.
english.FinishedLabel=The program is installed. Your data is kept in %ProgramData%\TripOrders (also after updates).%n%nThe other PCs of the office can connect over the office network. To keep the program on this PC only, run the installer again and tick "This PC only". Read the network guide for details.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Cfg: String;
begin
  { this PC only: listen on this PC alone, but only if the office asked for it and has no settings file yet (the program default is the office LAN); written before the program is started }
  if (CurStep = ssInstall) and WizardIsTaskSelected('thispconly') then
  begin
    Cfg := ExpandConstant('{commonappdata}\TripOrders\config.json');
    ForceDirectories(ExtractFilePath(Cfg));
    if not FileExists(Cfg) then
      SaveStringToFile(Cfg, '{"host": "127.0.0.1"}', False);
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
