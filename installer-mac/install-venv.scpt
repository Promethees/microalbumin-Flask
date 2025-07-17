on run
    try
        -- Get the directory containing the .app
        tell application "Finder"
            set appPath to (path to me) as text
            set appContainer to container of (path to me) as text
            set commandFile to (appContainer & "install-venv.command") as text
            set commandPath to POSIX path of commandFile
        end tell
        
        -- Execute in Terminal with sudo
        tell application "Terminal"
            activate
            do script "sudo " & quoted form of commandPath & "; exit"
        end tell
    on error errMsg
        -- User-friendly error if .command file is missing
        display dialog "Error: " & errMsg & return & return & ¬
            "Please make sure:" & return & ¬
            "1. 'install-tools-clone-repo.command' is in the same folder as this app." & return & ¬
            "2. The app is not inside another folder (e.g., Downloads)." buttons {"OK"} default button "OK" with title "Installation Failed" with icon stop
    end try
end run