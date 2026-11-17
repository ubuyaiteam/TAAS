; ============================================================================
;  TAAS installer script for Inno Setup 6.3 or newer
; ============================================================================

#define MyAppName "TAAS"
#define MyAppFullName "TAAS - Tool for Automatic Article Submission"
#ifndef MyAppVersion
  #define MyAppVersion "2.2.1"
#endif
#define MyAppPublisher "Ubuy"
#define MyAppExeName "TAAS.exe"

[Setup]
; --- Application Information ---
AppId={{B3F1A6D2-7C54-4E0B-9A1D-5E2C8F4D6A71}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

; --- Installation Directories & Shortcuts ---
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; --- Privileges & System Architecture ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; --- Output & Compression ---
OutputDir=release
OutputBaseFilename=TAAS_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; --- Icons & Display ---
SetupIconFile=assets\taas-logo.ico
UninstallDisplayName={#MyAppFullName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; --- Process Handling ---
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\TAAS.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\USER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataFolder: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataFolder := ExpandConstant('{userappdata}\{#MyAppName}');
    if (not UninstallSilent) and DirExists(DataFolder) then
    begin
      if MsgBox('Also delete your TAAS settings, Gemini key, and Google sign-in?' + #13#10#13#10 +
                'Folder: ' + DataFolder + #13#10#13#10 +
                'Choose No to keep them.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataFolder, True, True, True);
      end;
    end;
  end;
end;
