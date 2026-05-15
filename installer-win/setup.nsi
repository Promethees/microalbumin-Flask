; Installer script for EasyOKAPI
; Requires NSIS 3.0 or later

; Define the application name and version
!define APP_NAME "EasyOKAPI"
; APP_VERSION must be passed at compile time: makensis /DAPP_VERSION=x.x.x setup.nsi
!ifndef APP_VERSION
  !error "APP_VERSION is not defined. Pass it with: makensis /DAPP_VERSION=x.x.x setup.nsi"
!endif
!define INSTALL_DIR "$PROGRAMFILES\EasyOKAPI"
!define RUNNER_NAME "${APP_NAME}" 
!define MUI_ICON "setup.ico"

; Request admin privileges for the installer
RequestExecutionLevel admin

; Set the compression method
SetCompressor lzma

; Installer metadata
Name "${APP_NAME} ${APP_VERSION}"
OutFile "EasyOKAPI_Setup.exe"
InstallDir "${INSTALL_DIR}"
ShowInstDetails show
ShowUninstDetails show

; Modern UI and nsDialogs
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "WinMessages.nsh"

; Variables
Var Dialog
Var TokenInput
Var EasyOKAPIToken

; AI assistant page variables
Var AIDialog
Var AIEnabledCheck
Var AILangEN
Var AILangVI
Var AILangZH
Var AILangFR
Var AILangJA
Var AILangRU
Var AIModelDrop
Var AIEnabled
Var AILangArray
Var AIModel
Var AIEnabledStr

; Custom pages
Page custom TokenPage TokenPageLeave
Page custom AISetupPage AISetupPageLeave

; Define installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Set language
!insertmacro MUI_LANGUAGE "English"

; ── AI Assistant setup page ──────────────────────────────────────────────────
Function AISetupPage
  !insertmacro MUI_HEADER_TEXT "AI Assistant (Optional)" "Configure the built-in AI assistant powered by Ollama (local LLM)"

  nsDialogs::Create 1018
  Pop $AIDialog
  ${If} $AIDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateCheckBox} 0u 0u 100% 12u "Enable AI Assistant — answers questions in 6 languages (EN/VI/ZH/FR/JA/RU)"
  Pop $AIEnabledCheck
  ${NSD_Check} $AIEnabledCheck

  ${NSD_CreateLabel} 0u 18u 100% 10u "Languages (check all you want to use):"
  Pop $0
  ${NSD_CreateCheckBox} 0u 30u 110u 12u "English"
  Pop $AILangEN
  ${NSD_Check} $AILangEN
  ${NSD_CreateCheckBox} 115u 30u 110u 12u "Tieng Viet"
  Pop $AILangVI
  ${NSD_CreateCheckBox} 0u 44u 110u 12u "Zhongwen (CN)"
  Pop $AILangZH
  ${NSD_CreateCheckBox} 115u 44u 110u 12u "Francais"
  Pop $AILangFR
  ${NSD_CreateCheckBox} 0u 58u 110u 12u "Japanese"
  Pop $AILangJA
  ${NSD_CreateCheckBox} 115u 58u 110u 12u "Russian"
  Pop $AILangRU

  ${NSD_CreateLabel} 0u 76u 50u 10u "Model:"
  Pop $0
  ${NSD_CreateDropList} 55u 74u 240u 80u ""
  Pop $AIModelDrop
  SendMessage $AIModelDrop ${CB_ADDSTRING} 0 "STR:qwen2.5:7b (4.7 GB) — Best multilingual"
  SendMessage $AIModelDrop ${CB_ADDSTRING} 0 "STR:qwen2.5:3b (1.9 GB) — Lighter version"
  SendMessage $AIModelDrop ${CB_ADDSTRING} 0 "STR:llama3.2:3b (2.0 GB) — Good English/French"
  SendMessage $AIModelDrop ${CB_ADDSTRING} 0 "STR:mistral:7b (4.1 GB) — Good European languages"
  SendMessage $AIModelDrop ${CB_SETCURSEL} 0 0

  ${NSD_CreateLabel} 0u 92u 100% 30u "The AI model must be downloaded separately after installation.$\r$\nInstall Ollama (ollama.com), then use the Robot button inside the app to download."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function AISetupPageLeave
  ${NSD_GetState} $AIEnabledCheck $AIEnabled

  ; Build preferred_languages JSON array from checked language boxes
  StrCpy $AILangArray "["
  StrCpy $0 "0"  ; first-item flag

  ${NSD_GetState} $AILangEN $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"en"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"en"'
    ${EndIf}
  ${EndIf}

  ${NSD_GetState} $AILangVI $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"vi"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"vi"'
    ${EndIf}
  ${EndIf}

  ${NSD_GetState} $AILangZH $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"zh"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"zh"'
    ${EndIf}
  ${EndIf}

  ${NSD_GetState} $AILangFR $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"fr"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"fr"'
    ${EndIf}
  ${EndIf}

  ${NSD_GetState} $AILangJA $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"ja"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"ja"'
    ${EndIf}
  ${EndIf}

  ${NSD_GetState} $AILangRU $1
  ${If} $1 == ${BST_CHECKED}
    ${If} $0 == "0"
      StrCpy $AILangArray '$AILangArray"ru"'
      StrCpy $0 "1"
    ${Else}
      StrCpy $AILangArray '$AILangArray,"ru"'
    ${EndIf}
  ${EndIf}

  StrCpy $AILangArray "$AILangArray]"
  ; Ensure at least one language
  ${If} $AILangArray == "[]"
    StrCpy $AILangArray '["en"]'
  ${EndIf}

  ; Extract model name
  ${NSD_GetText} $AIModelDrop $AIModel
  ${If} $AIModel == "qwen2.5:3b (1.9 GB) — Lighter version"
    StrCpy $AIModel "qwen2.5:3b"
  ${ElseIf} $AIModel == "llama3.2:3b (2.0 GB) — Good English/French"
    StrCpy $AIModel "llama3.2:3b"
  ${ElseIf} $AIModel == "mistral:7b (4.1 GB) — Good European languages"
    StrCpy $AIModel "mistral:7b"
  ${Else}
    StrCpy $AIModel "qwen2.5:7b"
  ${EndIf}
FunctionEnd

; ── EasyOKAPI token page ──────────────────────────────────────────────────────
; Custom page to prompt for EasyOKAPI token
Function TokenPage
  !insertmacro MUI_HEADER_TEXT "EasyOKAPI Token" "Enter your Generated EasyOKAPI Token to clone the private repository."
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "Please enter your Generated EasyOKAPI Token:"
  Pop $0
  ${NSD_CreateText} 0 26u 100% 12u ""
  Pop $TokenInput
  nsDialogs::Show
FunctionEnd

Function TokenPageLeave
  ${NSD_GetText} $TokenInput $EasyOKAPIToken
  ${If} $EasyOKAPIToken == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "Please enter a valid EasyOKAPI token."
    Abort
  ${EndIf}
FunctionEnd

Section "Install" SEC01
  ; Set output path to the installation directory
  SetOutPath "$INSTDIR"
  
  ; Include the batch files
  File "startwindow-1-git.bat"
  File "startwindow-0-clone-repo.bat"
  File "startwindow-2-pyenv.bat"
  File "startwindow-3-python.bat"
  File "startwindow-4-venv.bat"
  File "startwindow-5-run.bat"
  
  ; Include the precompiled app runner
  File "EasyOKAPI.exe"
  File "ht.ico"

  ; Execute the setup batch scripts with admin privileges
  DetailPrint "Running startwindow-1-git.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-1-git.bat"' $0
  DetailPrint "startwindow-1-git.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-0-clone-repo.bat..."
  ExecWait '"cmd.exe" /c ""$INSTDIR\startwindow-0-clone-repo.bat" "$INSTDIR\code" "$EasyOKAPIToken""' $0
  DetailPrint "startwindow-0-clone-repo.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-2-pyenv.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-2-pyenv.bat"' $0
  DetailPrint "startwindow-2-pyenv.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-3-python.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-3-python.bat"' $0
  DetailPrint "startwindow-3-python.bat completed with exit code: $0"

  ; Write ai_settings.json before venv setup (startwindow-4-venv.bat skips its own prompt if file exists)
  CreateDirectory "$INSTDIR\code"
  ${If} $AIEnabled == ${BST_CHECKED}
    StrCpy $AIEnabledStr "true"
  ${Else}
    StrCpy $AIEnabledStr "false"
    StrCpy $AILangArray '["en"]'
    StrCpy $AIModel "qwen2.5:7b"
  ${EndIf}
  DetailPrint "Writing AI settings: enabled=$AIEnabledStr langs=$AILangArray model=$AIModel"
  FileOpen $0 "$INSTDIR\code\ai_settings.json" w
  FileWrite $0 '{$\n  "enabled": $AIEnabledStr,$\n  "preferred_languages": $AILangArray,$\n  "model": "$AIModel",$\n  "ollama_url": "http://localhost:11434",$\n  "first_run_shown": false$\n}$\n'
  FileClose $0

  DetailPrint "Running startwindow-4-venv.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-4-venv.bat"' $0
  DetailPrint "startwindow-4-venv.bat completed with exit code: $0"
  
  ; Create desktop shortcut for the app runner
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${RUNNER_NAME}.exe"
  
  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  ExecWait 'net stop "${RUNNER_NAME}"'
  ExecWait '"$INSTDIR\nssm.exe" remove "${RUNNER_NAME}" confirm'
  Delete "$SMPROGRAMS\${APP_NAME}\*.*"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  ; Delete AI settings file
  Delete "$INSTDIR\code\ai_settings.json"

  ; Delete installed files
  Delete "$INSTDIR\startwindow-1-git.bat"
  Delete "$INSTDIR\startwindow-0-clone-repo.bat"
  Delete "$INSTDIR\startwindow-2-pyenv.bat"
  Delete "$INSTDIR\startwindow-3-python.bat"
  Delete "$INSTDIR\startwindow-4-venv.bat"
  Delete "$INSTDIR\startwindow-5-run.bat"
  Delete "$INSTDIR\${RUNNER_NAME}.exe"
  Delete "$INSTDIR\code\*.*"
  ; Delete desktop shortcut
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$INSTDIR\Uninstall.exe"
  
  ; Delete installation directory
  RMDir /r "$INSTDIR"
SectionEnd