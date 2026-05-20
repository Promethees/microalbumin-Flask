; runner.nsi
; Requests admin silently, then delegates to the WPF splash screen (launcher.ps1).

Name "EasyOKAPI"
OutFile "EasyOKAPI.exe"
InstallDir "$EXEDIR"
RequestExecutionLevel admin
Icon "ht.ico"
SilentInstall silent

Section
  SetOutPath "$INSTDIR"

  IfFileExists "$INSTDIR\launcher.ps1" lbl_found lbl_missing

  lbl_found:
    CreateShortCut "$DESKTOP\EasyOKAPI.lnk" "$INSTDIR\EasyOKAPI.exe" "" "$INSTDIR\ht.ico" 0
    ExecWait '"$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\launcher.ps1"'
    Goto lbl_done

  lbl_missing:
    MessageBox MB_OK "Error: launcher.ps1 not found.$\n$\nExpected: $INSTDIR\launcher.ps1"

  lbl_done:
SectionEnd
