; ============================================================
; Script do Inno Setup para o instalador do DUDAIR-PDV
; Como usar:
;   1. Rode build.bat na raiz do projeto (gera dist\DUDAIR-PDV\...)
;   2. Abra este arquivo no Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
;   3. Clique em "Compile" -> gera "DUDAIR-PDV-Setup.exe" na pasta installer\Output
; ============================================================

#define MyAppName "DUDAIR-PDV"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Espetinho DU'DAIR"
#define MyAppExeName "DUDAIR-PDV.exe"

[Setup]
AppId={{7E2B8B7A-7A6A-4C1E-9B7F-DUDAIRPDV001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DUDAIR-PDV-Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\assets\icons\app.ico
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

; O banco de dados fica em %LOCALAPPDATA%\DUDAIR-PDV\database.db (fora da pasta
; de instalacao), entao desinstalar o programa NAO apaga as comandas e o
; historico de caixa. Para remover os dados de verdade, apague manualmente
; essa pasta em %LOCALAPPDATA%\DUDAIR-PDV.
