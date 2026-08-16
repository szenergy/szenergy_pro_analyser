; Inno Setup Script for SZenergy Pro Analyser
; Compiles a fast, clean Windows Setup Installer

[Setup]
AppName=SZenergy Pro Analyser
AppVersion=1.0.0
DefaultDirName={autopf}\SZenergy Pro Analyser
DefaultGroupName=SZenergy Pro Analyser
OutputDir=dist
OutputBaseFilename=SZenergyPro-Analyser-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Files]
Source: "dist\SZenergy_Pro_Analyser\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SZenergy Pro Analyser"; Filename: "{app}\SZenergy_Pro_Analyser.exe"
Name: "{autodesktop}\SZenergy Pro Analyser"; Filename: "{app}\SZenergy_Pro_Analyser.exe"

[Run]
Filename: "{app}\SZenergy_Pro_Analyser.exe"; Description: "Launch SZenergy Pro Analyser"; Flags: postinstall nowait skipifsilent
