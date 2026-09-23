; ГРАДО 2 — Windows installer (Inno Setup 6). Built by .github/workflows/grado2-release.yml:
;   iscc /DMyAppVersion=<version> packaging\grado2-installer.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.13.0"
#endif
#define MyAppName "ГРАДО 2"
#define MyAppExeName "ГРАДО 2.exe"

[Setup]
AppId={{6B2E4C1F-7A90-4D2B-9E34-2C5A7F0B8D11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ГРАДО
DefaultDirName={autopf}\ГРАДО 2
DefaultGroupName=ГРАДО 2
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=GRADO2-Setup-{#MyAppVersion}
SetupIconFile=AppIcon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "..\dist\ГРАДО 2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ГРАДО 2"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ГРАДО 2"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить ГРАДО 2"; Flags: nowait postinstall skipifsilent
