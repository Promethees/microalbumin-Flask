on run
    try
        -- ── Guard: block launch directly from the mounted DMG ───────────────
        set appPath to POSIX path of (path to me)
        if appPath starts with "/Volumes/" then
            display dialog "Please drag EasyOKAPI to your Applications folder first." & return & return & "Drag the icon onto the Applications shortcut in the DMG window, then launch it from your Applications folder or Launchpad." buttons {"OK"} default button "OK" with title "EasyOKAPI" with icon stop
            return
        end if

        set resDir to appPath & "Contents/Resources"
        set launchScript to resDir & "/launch-frozen.sh"

        -- ── Launch the bundled binary, detached ─────────────────────────────
        -- No token prompt, no sudo, no pyenv/venv/source download: the frozen
        -- binary is self-contained and creates its own per-user data folders on
        -- first run. Run it detached so this applet can exit while the app keeps
        -- serving its browser UI.
        do shell script "nohup bash " & quoted form of launchScript & " >/dev/null 2>&1 &"
    on error errMsg
        display dialog "EasyOKAPI encountered an error:" & return & errMsg buttons {"OK"} default button "OK" with title "EasyOKAPI" with icon stop
    end try
end run
