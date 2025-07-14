; runner.nsi
; NSIS script to create an executable that runs startwindow-4-venv-run.bat as administrator

;--------------------------------
; Include Modern UI and plugins
!include "MUI2.nsh"
!include "LogicLib.nsh"

;--------------------------------
; General
Name "Easy Sensor Web Interface Runner"
OutFile "EasySensor Kit.exe"
InstallDir "$EXEDIR"
RequestExecutionLevel admin ; Request admin privileges for the installer

;--------------------------------
; Interface Settings
!define MUI_ABORTWARNING

;--------------------------------
; Pages
!insertmacro MUI_PAGE_INSTFILES

;--------------------------------
; Languages
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Sections
Section "MainSection" SEC01
  SetOutPath "$INSTDIR"
  
  ; Copy the batch file to the installation directory (optional, assuming it's already there)
  ; File "startwindow-5-run.bat"
  
  ; Create a desktop shortcut to the executable
  CreateShortCut "$DESKTOP\EasySensor Kit.lnk" "$INSTDIR\EasySensor Kit.exe" "" "$INSTDIR\EasySensor Kit.exe" 0
  
  ; Execute the batch file as administrator
  ExecWait '"$SYSDIR\cmd.exe" /c "$INSTDIR\startwindow-5-run.bat"'
SectionEnd

;--------------------------------
; Descriptions
LangString DESC_SEC01 ${LANG_ENGLISH} "Running the Program, use Ctrl + C in the running Server window to terminate."

; Assign description to section (optional, requires components page)
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} $(DESC_SEC01)
!insertmacro MUI_FUNCTION_DESCRIPTION_END