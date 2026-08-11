on run
    try
        -- ── Guard: block launch directly from the mounted DMG ───────────────
        set appPath to POSIX path of (path to me)
        if appPath starts with "/Volumes/" then
            display dialog "Please drag EasyOKAPI to your Applications folder first." & return & return & "Drag the icon onto the Applications shortcut in the DMG window, then launch it from your Applications folder or Launchpad." buttons {"OK"} default button "OK" with title "EasyOKAPI" with icon stop
            return
        end if

        set resDir to appPath & "Contents/Resources"
        set setupScript to resDir & "/setup.sh"
        set launchScript to resDir & "/launch.sh"

        -- This .app ships inside the EasyOKAPI folder that gets dragged to
        -- /Applications, so the install root is simply its parent directory and
        -- the code tree hangs off code/ (mirrors installer-win). appPath carries a
        -- trailing slash; strip it before dirname.
        set installDir to do shell script "dirname " & quoted form of (text 1 thru -2 of appPath)
        set venvMarker to installDir & "/code/venv/bin/activate"

        -- ── First-run detection ──────────────────────────────────────────────
        set isInstalled to do shell script "[ -f " & quoted form of venvMarker & " ] && echo 1 || echo 0"

        if isInstalled is "0" then
            -- Welcome dialog
            set dlg to display dialog "Welcome to EasyOKAPI!" & return & return & "First-run setup is needed. EasyOKAPI will install its Python environment and download the application (5–10 minutes)." & return & return & "Make sure you are connected to the internet before continuing." buttons {"Cancel", "Set Up Now"} default button "Set Up Now" with title "EasyOKAPI Setup"
            if button returned of dlg is "Cancel" then return

            -- Collect the access token.
            --
            -- Deliberately NOT `with hidden answer`. VoiceOver reads a masked
            -- field as "bullet" once per character, so the token could be
            -- neither heard back nor checked for a bad paste — in exchange for
            -- hiding a single-use string that expires in 30 minutes. The
            -- dialog says where the token comes from, because "access token"
            -- on its own tells a first-time user nothing.
            set tokenDlg to display dialog "Enter your EasyOKAPI access token." & return & return & "Generate it in your EasyOKAPI account (Account → Download token). It is valid for 30 minutes. Nothing here is timed — take as long as you need." default answer "" buttons {"Cancel", "Continue"} default button "Continue" with title "EasyOKAPI Setup"
            if button returned of tokenDlg is "Cancel" then return
            set accessToken to text returned of tokenDlg
            if accessToken is "" then
                display dialog "An access token is required to download EasyOKAPI." & return & return & "Copy the token from your EasyOKAPI account, then launch EasyOKAPI again." buttons {"OK"} default button "OK" with title "EasyOKAPI Setup"
                return
            end if

            -- Run the merged installer in Terminal (needs sudo for system installs)
            tell application "Terminal"
                activate
                do script "sudo bash " & quoted form of setupScript & " " & quoted form of accessToken & "; exit"
            end tell

        else
            -- Normal launch: bash (not sudo) — launch.sh requests sudo internally
            tell application "Terminal"
                do script "bash " & quoted form of launchScript & "; exit"
            end tell
        end if

    on error errMsg
        display dialog "EasyOKAPI encountered an error:" & return & errMsg buttons {"OK"} default button "OK" with title "EasyOKAPI" with icon stop
    end try
end run
