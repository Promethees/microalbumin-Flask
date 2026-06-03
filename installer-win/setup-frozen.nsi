; setup-frozen.nsi — installer for the no-source (PyInstaller) Windows build.
;
; Unlike setup.nsi (the source build) this bundles the frozen onedir
; (dist\EasyOKAPI\) directly into the installer — no token page, no download, no
; git/pyenv/python/venv. User data lives in %LOCALAPPDATA%\EasyOKAPI and is
; migrated from any old source install (which kept its data under
; $INSTDIR\code\) on first frozen install. Running the app needs no admin (CDC
; serial, not HID); only installing does.
;
; Compile from the REPO ROOT so the relative paths below resolve:
;   makensis /DAPP_VERSION=1.1.8 installer-win\setup-frozen.nsi

!define APP_NAME "EasyOKAPI"
!ifndef APP_VERSION
  !error "APP_VERSION is not defined. Pass it with: makensis /DAPP_VERSION=x.x.x setup-frozen.nsi"
!endif
!define INSTALL_DIR "$PROGRAMFILES64\EasyOKAPI"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "EasyOKAPI_Setup_${APP_VERSION}_frozen.exe"
InstallDir "${INSTALL_DIR}"
BrandingText "EasyOKAPI ${APP_VERSION}"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ICON "installer-win\setup.ico"
!define MUI_UNICON "installer-win\setup.ico"

!define MUI_WELCOMEPAGE_TITLE "Welcome to EasyOKAPI Setup"
!define MUI_WELCOMEPAGE_TEXT "This will install EasyOKAPI ${APP_VERSION} (no-source build).$\r$\n$\r$\nNo internet connection, token, or Python install is required — everything is bundled. Your measurement data, calibration curves, and reports are kept in your user profile and preserved across updates.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "EasyOKAPI ${APP_VERSION} Installed"
!define MUI_FINISHPAGE_TEXT "EasyOKAPI has been installed and a Desktop shortcut created.$\r$\n$\r$\nYour data lives in %LOCALAPPDATA%\EasyOKAPI and is preserved across updates."
!define MUI_FINISHPAGE_RUN "$INSTDIR\EasyOKAPI.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "--port 5099 --alias 127.0.0.1"
!define MUI_FINISHPAGE_RUN_TEXT "Launch EasyOKAPI now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Merge SRC into DST without overwriting newer/existing files (robocopy /XO skips
; older source files; existing same-time files are skipped). Exit codes 0-7 = ok.
!macro MigrateDir SRC DST
  IfFileExists "${SRC}\*.*" 0 +3
    nsExec::ExecToLog 'robocopy "${SRC}" "${DST}" /E /XO /NJH /NJS /NFL /NDL /NC /NS /NP'
    Pop $0
!macroend

Section "Install" SEC01
  StrCpy $R0 "$LOCALAPPDATA\EasyOKAPI"   ; per-user writable data root (matches state.py)

  ; ── Migrate data from an old source install (once) ──────────────────────────
  ; The source build kept user data under $INSTDIR\code\{data,json,report,log}.
  IfFileExists "$R0\.migrated_from_source" skip_migrate 0
  IfFileExists "$INSTDIR\code\main.py" 0 skip_migrate
    DetailPrint "Migrating data from previous installation..."
    CreateDirectory "$R0"
    !insertmacro MigrateDir "$INSTDIR\code\data"   "$R0\data"
    !insertmacro MigrateDir "$INSTDIR\code\json"   "$R0\json"
    !insertmacro MigrateDir "$INSTDIR\code\report" "$R0\report"
    !insertmacro MigrateDir "$INSTDIR\code\log"    "$R0\log"
    IfFileExists "$R0\activation.json" +2 0
      CopyFiles /SILENT "$INSTDIR\code\activation.json" "$R0\activation.json"
    IfFileExists "$R0\user_settings.json" +2 0
      CopyFiles /SILENT "$INSTDIR\code\user_settings.json" "$R0\user_settings.json"
    FileOpen $9 "$R0\.migrated_from_source" w
    FileWrite $9 "1"
    FileClose $9
  skip_migrate:

  ; ── Remove any previous install payload (source code dir + old runner) ──────
  RMDir /r "$INSTDIR\code"
  Delete "$INSTDIR\launcher.ps1"
  Delete "$INSTDIR\startwindow-*.bat"
  Delete "$INSTDIR\nssm.exe"

  ; ── Lay down the frozen onedir (EasyOKAPI.exe + _internal\) ─────────────────
  SetOutPath "$INSTDIR"
  File /r "dist\EasyOKAPI\*"

  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\EasyOKAPI.exe" "--port 5099 --alias 127.0.0.1"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  DetailPrint "EasyOKAPI ${APP_VERSION} installed. Data lives in $R0."
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
  ; User data in %LOCALAPPDATA%\EasyOKAPI is intentionally left intact.
SectionEnd
