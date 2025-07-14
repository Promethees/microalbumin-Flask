tell application "Finder"
    set appPath to POSIX path of (container of (path to me))
    set commandPath to quoted form of (appPath & "uninstall.command")
end tell
tell application "Terminal"
    do script "sudo " & commandPath
    activate
end tell