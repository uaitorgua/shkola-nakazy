; Інсталятор «Накази ШКОЛА» (Inno Setup 6). Збирається з tools\build.py або вручну:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 packaging\installer.iss
;
; ВАЖЛИВО: база наказів лежить у %APPDATA%\nakazy-shkola і НЕ видаляється ні під час оновлення,
; ні під час видалення програми (розділу [UninstallDelete] для даних немає навмисно).
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Накази ШКОЛА"
#define AppExe "NakazyShkola.exe"
#define Publisher "ГС «Українська асоціація інноваційних технологій»"

[Setup]
AppId={{7D3E258D-703E-4E92-8324-D7402E0B9ADC}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL=https://uait.org.ua
AppSupportURL=https://uait.org.ua
DefaultDirName={autopf}\NakazyShkola
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=NakazyShkola-Setup-{#AppVersion}
SetupIconFile=..\assets\logo.ico
LicenseFile=..\LICENSE.txt
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
ShowLanguageDialog=no
DisableProgramGroupPage=yes
CloseApplications=yes
#ifdef SignTool
SignTool={#SignTool}
#endif

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі"; GroupDescription: "Додатково:"
Name: "trustcert"; Description: "Довіряти сертифікату ГС «УАІТ» (без попередження «Невідомий видавець»)"; GroupDescription: "Додатково:"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\certs\UAIT_CodeSigning.cer"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Видалити {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "certutil.exe"; Parameters: "-user -addstore Root ""{app}\UAIT_CodeSigning.cer"""; Flags: runhidden; Tasks: trustcert; Check: FileExists(ExpandConstant('{app}\UAIT_CodeSigning.cer'))
Filename: "certutil.exe"; Parameters: "-user -addstore TrustedPublisher ""{app}\UAIT_CodeSigning.cer"""; Flags: runhidden; Tasks: trustcert; Check: FileExists(ExpandConstant('{app}\UAIT_CodeSigning.cer'))
Filename: "{app}\{#AppExe}"; Description: "Запустити {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Перед оновленням: копія бази поруч (додатково до копій, які робить сама програма)
procedure CurStepChanged(CurStep: TSetupStep);
var Db, Dst: String;
begin
  if CurStep = ssInstall then begin
    Db := ExpandConstant('{userappdata}\nakazy-shkola\nakazy.db');
    if FileExists(Db) then begin
      Dst := ExpandConstant('{userappdata}\nakazy-shkola\backups\nakazy-before-update-{#AppVersion}.db');
      ForceDirectories(ExtractFileDir(Dst));
      FileCopy(Db, Dst, False);
    end;
  end;
end;

// Під час видалення лише нагадуємо, де лишились дані
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('Програму видалено. Ваша база наказів і резервні копії збережені в теці ' +
           ExpandConstant('{userappdata}\nakazy-shkola') + '.', mbInformation, MB_OK);
end;
