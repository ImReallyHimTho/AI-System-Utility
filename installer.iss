; AI System Utility Installer
; Full professional Windows installer for your program

[Setup]
AppName=AI System Utility
AppVersion=1.0.0
DefaultDirName={pf}\AI System Utility
DefaultGroupName=AI System Utility
DisableProgramGroupPage=yes
OutputBaseFilename=AI_System_Utility_Installer
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableReadyMemo=yes
LicenseFile=license.txt

[Files]
Source: "dist\AI_System_Utility\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI System Utility"; Filename: "{app}\AI_System_Utility.exe"
Name: "{commondesktop}\AI System Utility"; Filename: "{app}\AI_System_Utility.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\AI_System_Utility.exe"; Description: "Launch AI System Utility"; Flags: nowait postinstall skipifsilent
