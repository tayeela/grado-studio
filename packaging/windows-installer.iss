#ifndef MyAppVersion
  #define MyAppVersion "0.9.0-beta.8"
#endif
#define MyAppName "ГРАДО Студия"
#define MyAppExeName "ГРАДО Студия.exe"

[Setup]
AppId={{F07D96CF-ED71-4CF8-AB1D-B4568E8ED50B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ГРАДО
DefaultDirName={autopf}\ГРАДО Студия
DefaultGroupName=ГРАДО Студия
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=GRADO-Studio-Setup-{#MyAppVersion}
SetupIconFile=AppIcon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "..\dist\ГРАДО Студия\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ГРАДО Студия"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ГРАДО Студия"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.grado"; ValueType: string; ValueData: "GradoStudio.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\GradoStudio.Project"; ValueType: string; ValueData: "Проект ГРАДО"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\GradoStudio.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\GradoStudio.Project\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить ГРАДО Студию"; Flags: nowait postinstall skipifsilent
