; Inno Setup script to package ShopeeBestSeller.exe into an installer
#define MyAppName "Shopee Best-Seller Checker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your Company"
#define MyAppExeName "ShopeeBestSeller.exe"

[Setup]
AppId={{A7F47A2A-CB22-41B2-8E1E-FA83C7A1E4C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ShopeeBestSeller
DefaultGroupName={#MyAppName}
OutputDir=dist_installer
OutputBaseFilename=ShopeeBestSeller_Setup
Compression=lzma
SolidCompression=yes
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "thai"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\ShopeeBestSeller.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "สร้างไอคอนบนเดสก์ท็อป"; GroupDescription: "ตัวเลือกเพิ่มเติม:"; Flags: unchecked
