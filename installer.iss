; Instalador de "Stream Dock M18 by JARCMASTER"  (Inno Setup 6)
; Un solo ejecutable.  Compilar con:  iscc installer.iss   (tras  python build.py)

#define AppName      "Stream Dock M18 by JARCMASTER"
#define AppVersion   "1.0.0"
#define Publisher    "JARCMASTER"
#define Exe          "StreamDockM18.exe"
#define RunValueName "StreamDockM18_JARCMASTER"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#Exe}
OutputBaseFilename=StreamDockM18_by_JARCMASTER_Setup_{#AppVersion}
SetupIconFile=assets\app.ico
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#Exe}";    DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion
; datos del usuario (compartidos por el server y el configurador)
Source: "config.json"; DestDir: "{userappdata}\{#AppName}"; Flags: onlyifdoesntexist
Source: "icons\*";     DestDir: "{userappdata}\{#AppName}\icons"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Configurador";       Filename: "{app}\{#Exe}"; Parameters: "--config"; IconFilename: "{app}\app.ico"
Name: "{group}\Iniciar en bandeja"; Filename: "{app}\{#Exe}"; IconFilename: "{app}\app.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\{#Exe}"; Parameters: "--config"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Registry]
; arranque con Windows -> server (exe sin argumentos)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#RunValueName}"; ValueData: """{app}\{#Exe}"""; \
  Flags: uninsdeletevalue

[Run]
; arrancar el server ahora y abrir el configurador
Filename: "{app}\{#Exe}"; Description: "Iniciar {#AppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#Exe}"; Parameters: "--config"; Description: "Abrir el configurador"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#Exe} /F"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
