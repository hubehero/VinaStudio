; Inno Setup script for VinaStudio Windows installer
; Requires Inno Setup 6.3+ (https://jrsoftware.org/isinfo.php)
;
; Usage:
;   iscc /DVERSION=0.1.0 vinastudio.iss
;
; The /DVERSION flag overrides the default below.

#ifndef VERSION
  #define VERSION "0.1.0"
#endif

#define MyAppName "VinaStudio"
#define MyAppPublisher "VinaStudio Contributors"
#define MyAppURL "https://github.com/VinaStudio/vina_simple"
#define MyAppExeName "vinastudio.exe"
#define MyAppSource "..\dist\vinastudio"

; VC++ Redistributable 2015-2022 (x64)
#define VcRedistUrl "https://aka.ms/vs/17/release/vc_redist.x64.exe"
#define VcRedistFileName "vc_redist.x64.exe"

[Setup]
AppId={{B7A3E4F2-91D6-4C8A-A5F3-2E8B7C6D1F0A}
AppName={#MyAppName}
AppVersion={#VERSION}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
LicenseFile=..\..\LICENSE
OutputDir=..\dist
OutputBaseFilename=vinastudio-{#VERSION}-setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
WizardSizePercent=110
DisableProgramGroupPage=yes
DisableDirPage=no
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "associatefiles"; Description: "Associate .pdb and .sdf files with VinaStudio"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "{#MyAppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; File associations — .pdb
Root: HKCR; Subkey: ".pdb\OpenWithProgids"; ValueType: string; ValueName: "VinaStudio.pdb"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.pdb"; ValueType: string; ValueName: ""; ValueData: "PDB File (VinaStudio)"; Flags: uninsdeletekey; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.pdb\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.pdb\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatefiles

; File associations — .sdf
Root: HKCR; Subkey: ".sdf\OpenWithProgids"; ValueType: string; ValueName: "VinaStudio.sdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.sdf"; ValueType: string; ValueName: ""; ValueData: "SDF File (VinaStudio)"; Flags: uninsdeletekey; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.sdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associatefiles
Root: HKCR; Subkey: "VinaStudio.sdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatefiles

[Code]
// ---------------------------------------------------------------------------
// VC++ Redistributable 2015-2022 (x64) detection
// ---------------------------------------------------------------------------
function VCRedistInstalled: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not VCRedistInstalled then
  begin
    if MsgBox('VinaStudio requires the VC++ Redistributable 2015-2022.' + #13#10 +
              'Please download and install it from:' + #13#10 +
              '{#VcRedistUrl}' + #13#10#13#10 +
              'Continue anyway?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
