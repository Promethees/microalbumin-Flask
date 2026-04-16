; Installer script for EasyOKAPI
; Requires NSIS 3.0 or later

; Define the application name and version
!define APP_NAME "EasyOKAPI"
!define APP_VERSION "1.0.0"
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
Var GitHubToken

; Custom page for token input
Page custom TokenPage TokenPageLeave

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

; Custom page to prompt for GitHub token
Function TokenPage
  !insertmacro MUI_HEADER_TEXT "GitHub Token" "Enter your GitHub Personal Access Token to clone the private repository."
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "Please enter your GitHub Personal Access Token:"
  Pop $0
  ${NSD_CreateText} 0 26u 100% 12u ""
  Pop $TokenInput
  nsDialogs::Show
FunctionEnd

Function TokenPageLeave
  ${NSD_GetText} $TokenInput $GitHubToken
  ${If} $GitHubToken == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "Please enter a valid GitHub token."
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

  ; Execute the setup batch scripts with admin privileges
  DetailPrint "Running startwindow-1-git.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-1-git.bat"' $0
  DetailPrint "startwindow-1-git.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-0-clone-repo.bat..."
  ExecWait '"$INSTDIR\startwindow-0-clone-repo.bat" "$INSTDIR\code" "$GitHubToken"' $0
  DetailPrint "Github token used was $GitHubToken $0"
  DetailPrint "startwindow-0-clone-repo.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-2-pyenv.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-2-pyenv.bat"' $0
  DetailPrint "startwindow-2-pyenv.bat completed with exit code: $0"
  
  DetailPrint "Running startwindow-3-python.bat..."
  ExecWait '"cmd.exe" /c "$INSTDIR\startwindow-3-python.bat"' $0
  DetailPrint "startwindow-3-python.bat completed with exit code: $0"

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