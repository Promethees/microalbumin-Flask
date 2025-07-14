; App Runner script for MyApp
!define APP_NAME "EasySensor Kit"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

RequestExecutionLevel admin
Name "${APP_NAME} Runner"
OutFile "EasySensor Kit.exe"

Section
  Exec 'cmd.exe /c "$INSTDIR\startwindow-4-venv-run.bat"'
SectionEnd