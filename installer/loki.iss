; ============================================================================
; LOKI Chaos Agent — Official Windows Installer Script (Inno Setup 6+)
; ============================================================================
; Compile locally or in CI:
;   iscc /DMyAppVersion=1.10.0 installer\loki.iss
;
; Output:
;   dist\loki-setup-windows-amd64.exe
; ============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "1.10.0"
#endif

#ifndef MySourceExe
  #define MySourceExe "..\dist\loki.exe"
#endif

#define MyAppName "LOKI Chaos Agent"
#define MyAppPublisher "Elabsurdo984"
#define MyAppURL "https://github.com/Elabsurdo984/loki-agent"
#define MyAppExeName "loki.exe"

[Setup]
AppId={{8F9B3A42-6D1C-4E8A-9B2E-5C7F1A0D3E91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\LOKI
DefaultGroupName={#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=yes
; Allow user to choose between non-admin per-user install (%LOCALAPPDATA%\Programs\LOKI)
; and admin system-wide install (C:\Program Files\LOKI)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\dist
OutputBaseFilename=loki-setup-windows-amd64
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "addtopath"; Description: "Add LOKI to your PATH environment variable (run 'loki' from any terminal)"; GroupDescription: "System & Shell Integration:"
Name: "contextmenu"; Description: "Add ""Open LOKI Agent here"" to folder right-click context menu"; GroupDescription: "System & Shell Integration:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon} (launches LOKI Interactive Chat)"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installchromium"; Description: "Download and configure Playwright Chromium browser engine during installation"; GroupDescription: "Browser Engine Setup:"; Flags: unchecked

[Files]
Source: "{#MySourceExe}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
Source: "..\assets\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "chat"; IconFilename: "{app}\logo.ico"; Comment: "Launch LOKI Conversational QA & Chaos Testing Terminal"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "chat"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon; Comment: "Launch LOKI Conversational QA & Chaos Testing Terminal"

[Registry]
; Right-click inside a folder background -> "Open LOKI Agent here"
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\LOKI"; ValueType: string; ValueName: ""; ValueData: "Open LOKI Agent here"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\LOKI"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\LOKI\command"; ValueType: string; ValueName: ""; ValueData: "cmd.exe /s /k ""pushd ""%V"" & ""{app}\{#MyAppExeName}"" chat"""; Tasks: contextmenu

; Right-click on a folder icon -> "Open LOKI Agent here"
Root: HKA; Subkey: "Software\Classes\Directory\shell\LOKI"; ValueType: string; ValueName: ""; ValueData: "Open LOKI Agent here"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\LOKI"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\LOKI\command"; ValueType: string; ValueName: ""; ValueData: "cmd.exe /s /k ""pushd ""%V"" & ""{app}\{#MyAppExeName}"" chat"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "install-browser chromium"; StatusMsg: "Downloading Playwright Chromium browser engine (this may take a minute)..."; Flags: waituntilterminated; Tasks: installchromium
Filename: "{app}\{#MyAppExeName}"; Parameters: "chat"; Description: "Launch LOKI Interactive Terminal (loki chat)"; Flags: nowait postinstall skipifsilent

[Code]
const
  SystemEnvSubKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  UserEnvSubKey = 'Environment';

function GetEnvRegSubKey(): String;
begin
  if IsAdminInstallMode() then
    Result := SystemEnvSubKey
  else
    Result := UserEnvSubKey;
end;

procedure EnvAddPath(PathToAdd: String);
var
  Paths: String;
  RegKey: String;
begin
  RegKey := GetEnvRegSubKey();
  if not RegQueryStringValue(HKA, RegKey, 'Path', Paths) then
    Paths := '';

  if Pos(';' + Uppercase(PathToAdd) + ';', ';' + Uppercase(Paths) + ';') > 0 then
    exit;

  if (Paths <> '') and (Copy(Paths, Length(Paths), 1) <> ';') then
    Paths := Paths + ';';

  Paths := Paths + PathToAdd;
  RegWriteExpandStringValue(HKA, RegKey, 'Path', Paths);
end;

procedure EnvRemovePath(PathToRemove: String);
var
  Paths: String;
  RegKey: String;
  P: Integer;
begin
  RegKey := GetEnvRegSubKey();
  if not RegQueryStringValue(HKA, RegKey, 'Path', Paths) then
    exit;

  P := Pos(';' + Uppercase(PathToRemove) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;

  if P = 1 then
  begin
    Delete(Paths, 1, Length(PathToRemove));
    if (Length(Paths) > 0) and (Paths[1] = ';') then
      Delete(Paths, 1, 1);
  end
  else
  begin
    Delete(Paths, P - 1, Length(PathToRemove) + 1);
  end;

  RegWriteExpandStringValue(HKA, RegKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
