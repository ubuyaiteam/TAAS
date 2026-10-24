; ============================================================================
;  TAAS installer script for Inno Setup 6.3 or newer (free: https://jrsoftware.org/isdl.php)
;
;  Put this file in the project folder (next to build_exe.bat), then:
;    1. Run build_exe.bat           -> makes release\TAAS.exe
;    2. Open this file in Inno Setup and press Compile (F9)
;    3. The installer appears in the "installer_output" folder: TAAS_Setup_1.1.0.exe
;
;  The values like {#MyAppName} are filled in by the compiler from the #define lines below,
;  so they look empty in the editor. That is normal.
;  If release\client_secret.json exists when you compile, it is put inside the installer.
;  Share such an installer only inside your team.
; ============================================================================

; ---- change these when needed -------------------------------------------------
; Keep MyAppVersion equal to __version__ in taas\__init__.py.
#define MyAppName "TAAS"
#define MyAppFullName "TAAS - Tool for Automatic Article Submission"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Ubuy"
#define MyAppExeName "TAAS.exe"
; -------------------------------------------------------------------------------

[Setup]
; AppId identifies TAAS for upgrades and uninstall. Never change it, or a new install will not
; replace the old one.
AppId={{B3F1A6D2-7C54-4E0B-9A1D-5E2C8F4D6A71}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installs for the current user without an administrator password.
; The user can still choose "for all users" in the first dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=TAAS_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppFullName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; If TAAS is open during an update, offer to close it.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\USER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
; the Google client file is optional: it is only included when it was in the release folder
Source: "release\client_secret.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Settings, the Gemini key and the Google sign-in live in %APPDATA%\TAAS, not in the install folder,
// so they survive updates. On uninstall the user decides whether to remove them too.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataFolder: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataFolder := ExpandConstant('{userappdata}\TAAS');
    if (not UninstallSilent) and DirExists(DataFolder) then
    begin
      if MsgBox('Also delete your TAAS settings, Gemini key and Google sign-in?' + #13#10 + #13#10 +
                'Folder: ' + DataFolder + #13#10 + #13#10 +
                'Choose No to keep them (for example if you plan to install TAAS again).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataFolder, True, True, True);
      end;
    end;
  end;
end;
