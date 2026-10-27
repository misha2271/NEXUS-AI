; Native per-user installer. All application files come from the tested onedir.
#ifndef AppVersion
  #error AppVersion must be supplied by scripts/build_installer.py
#endif
#ifndef SourceDir
  #error SourceDir must be supplied by scripts/build_installer.py
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by scripts/build_installer.py
#endif

[Setup]
AppId=NEXUS-AI-Desktop
AppName=NEXUS AI
AppVersion={#AppVersion}
AppPublisher=NEXUS AI contributors
AppPublisherURL=https://github.com/misha2271/NEXUS-AI
DefaultDirName={localappdata}\Programs\NEXUS AI
DefaultGroupName=NEXUS AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=NEXUS-AI-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LanguageDetectionMethod=none
ShowLanguageDialog=yes
UninstallDisplayIcon={app}\NEXUS-AI.exe
Uninstallable=yes
CloseApplications=no
RestartApplications=no
ChangesAssociations=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NEXUS AI"; Filename: "{app}\NEXUS-AI.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\NEXUS AI"; Filename: "{app}\NEXUS-AI.exe"; WorkingDir: "{app}"; Tasks: desktopicon

; No [Run], [Registry], [UninstallDelete], model download, service or firewall rules.
; Uninstall removes installed program files and shortcuts, preserving user data.
