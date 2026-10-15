#ifndef AppVersion
  #define AppVersion "1.2.8"
#endif
#ifndef PayloadDir
  #error PayloadDir must point at the allowlisted release payload
#endif

[Setup]
AppId={{A39C7B4E-E571-44F8-A317-A47390D380BF}
AppName=CodexControl
AppVersion={#AppVersion}
AppPublisher=CodexControl contributors
AppCopyright=CodexControl contributors
DefaultDirName={localappdata}\Programs\CodexControl
DefaultGroupName=CodexControl
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputBaseFilename=CodexControl-{#AppVersion}-windows-x64-Setup
SetupIconFile=build-assets\CodexControl.ico
UninstallDisplayIcon={app}\CodexControl.exe
LicenseFile={#PayloadDir}\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=no
TimeStampsInUTC=yes
TimeStampRounding=0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start CodexControl when I sign in"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\CodexControl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\CodexControl"; Filename: "{app}\CodexControl.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\CodexControl"; Filename: "{app}\CodexControl.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\CodexControl"; Filename: "{app}\CodexControl.exe"; Parameters: "--hidden"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\CodexControl.exe"; Description: "Launch CodexControl"; Flags: nowait postinstall skipifsilent unchecked

; No wildcard delete entries: uninstall preserves all user account/config data.
