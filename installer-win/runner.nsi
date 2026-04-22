; runner.nsi
; NSIS script to create an executable that runs startwindow-5-run.bat as administrator

;--------------------------------
; Include Modern UI and plugins
!include "MUI2.nsh"
!include "LogicLib.nsh"

;--------------------------------
; General
Name "EasyOKAPI Launcher"
OutFile "EasyOKAPI.exe"
InstallDir "$EXEDIR"
RequestExecutionLevel admin ; Request admin privileges for the launcher

;--------------------------------
; Interface Settings
!define MUI_ABORTWARNING 
!define MUI_ICON "runner.ico"


;--------------------------------
; Pages
!insertmacro MUI_PAGE_INSTFILES

;--------------------------------
; Languages
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Launcher Sections
Section "Launch Program" SEC01
  SetOutPath "$INSTDIR"
  
  ; Ensure the batch file exists before trying to run it
  IfFileExists "$INSTDIR\startwindow-5-run.bat" 0 +4
    CreateShortCut "$DESKTOP\EasyOKAPI.lnk" "$INSTDIR\EasyOKAPI.exe" "" "$INSTDIR\EasyOKAPI.exe" 0
    ; Run batch file minimized and then close NSIS window
    ExecWait '"$SYSDIR\cmd.exe" /min /c "$INSTDIR\startwindow-5-run.bat"'
    Quit
    Goto +2
  MessageBox MB_OK "Error: startwindow-5-run.bat not found in $INSTDIR"
SectionEnd

;--------------------------------
; Descriptions
LangString DESC_SEC01 ${LANG_ENGLISH} "Launches the EasyOKAPI Web Interface. Use Ctrl + C in the running Server window to terminate."

; Assign description to section
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} $(DESC_SEC01)
!insertmacro MUI_FUNCTION_DESCRIPTION_END