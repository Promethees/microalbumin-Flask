# Installing EasyOKAPI with assistive technology

This is the practical companion to the accessibility statement published at
<https://www.easyokapi.cbbiotec.vn/accessibility>. The statement says what we
claim; this says how to actually get the software installed, and what we did to
the installers to make that possible.

If any of it does not work for you, that is a defect. Write to
`tqmthong@gmail.com` — we aim to acknowledge within 5 working days and to
provide a fix or a dated plan within 20.

---

## 1. The short version

| Platform | Graphical installer | Non-graphical route (recommended with a screen reader) |
|---|---|---|
| Windows  | `EasyOKAPI_Setup_<version>.exe` — NSIS wizard, native Win32 controls, works with Narrator and NVDA | Same `.exe` with `/S` for a silent install, or the `startwindow-*.bat` scripts in the install folder |
| macOS    | `EasyOKAPI.app` first run — native `osascript` dialogs, works with VoiceOver | `sudo bash <app>/Contents/Resources/setup.sh <token>` |
| Linux    | `setup.sh` → a Tk window | `./setup.sh --token <token>` or `./setup.sh --no-gui` |

**Nothing in any installer is timed.** No dialogue expires, no step advances on
its own, and no screen has a countdown. You can leave an installer open and
come back to it.

---

## 2. Windows

The wizard is standard NSIS/MUI2, so every control is a real Win32 control:
Narrator and NVDA read the page title, the button labels and the field
contents, and Tab / Shift+Tab / Space / Enter / Escape do what they do
everywhere else in Windows.

What we changed for this claim:

- **High Contrast is honoured.** The installer normally paints itself in a dark
  indigo theme with a photographic background. When Windows reports High
  Contrast is on (`SPI_GETHIGHCONTRAST`), *all* of that is skipped — colours,
  title-bar tinting, progress-bar colours and both background bitmaps — and the
  wizard runs in the colours you chose. The compile-time `InstallColors`
  directive was removed for the same reason: it could not be turned off at run
  time.
- **The token field has a label that reads on its own.** The static text
  immediately precedes the edit control in tab order, which is how a Win32
  screen reader derives an edit box's name, and it says where the token comes
  from and how long it lasts rather than just naming it.
- **The token is not masked.** A masked field reads as "bullet" once per
  character and hides a mis-paste. The token is single-use and expires in 30
  minutes, so masking bought very little.
- **Errors return focus to the field they describe.** Leaving the token page
  empty shows a message box naming the field and what to do, then puts the
  caret back in it.
- **Progress is text.** `ShowInstDetails show` means the install log is a real,
  readable list of what happened — not only a moving bar.

### Silent install

```
EasyOKAPI_Setup_<version>.exe /S /D=C:\Program Files\EasyOKAPI
```

`/S` runs with no interface at all. `/D=` must be last and unquoted (an NSIS
convention). A silent install cannot prompt for the token, so use the graphical
wizard once per machine, or the frozen build, which reads the token from the
activation server.

---

## 3. macOS

First launch of `EasyOKAPI.app` runs the setup dialogues through
`osascript`. These are native macOS alerts: VoiceOver reads them, and
Tab / Space / Return / Escape behave normally.

- **The token dialogue is not a secure field.** It used `with hidden answer`,
  which VoiceOver announces as "bullet" per character; it now shows the text,
  and the prompt states where to get the token and that nothing is timed.
- **The splash screen gets out of the way.** The launcher shows a borderless,
  always-on-top progress window that no screen reader can read. It is skipped
  entirely when VoiceOver is running, and progress is written to the terminal
  instead. You can force that with `EASYOKAPI_NO_SPLASH=1`.

### Installing from the terminal

```
sudo bash "/Applications/EasyOKAPI/EasyOKAPI.app/Contents/Resources/setup.sh" <token>
```

Everything the wizard does happens here too, and each step prints a line as it
completes. The full log is at `/tmp/easyokapi-setup.log`.

---

## 4. Linux

The graphical prompt is a Tk window. **Tk exposes very little to AT-SPI**, so
Orca reads it poorly no matter how the window is written — this is a published
limitation, not an oversight. The command-line path is the supported route:

```
./setup.sh --token <token>     # no prompt at all
./setup.sh --no-gui            # prompt on the terminal instead of in a window
EASYOKAPI_NO_GUI=1 ./setup.sh  # same, from the environment
./setup.sh --help              # the above, on the terminal
```

`setup.sh` also skips the window on its own when it can see a screen reader in
the session (an `orca` process, or accessibility enabled in the GTK
environment).

If you do use the window, it has been made as workable as Tk allows:

- focus starts in the token field, and every control has a visible focus ring
  (Tk draws none by default on a flat button);
- Tab moves, Space and Enter activate, **Escape cancels**, Return in the field
  installs — and the window says so on screen;
- the token is shown in clear, with a "Hide token while typing" checkbox for a
  shared screen;
- the window can be resized and its text reflows;
- the validation message is text, never a colour change alone, and focus moves
  to the field it describes;
- the error colour was changed from red-400 to red-300, which clears 4.5:1 on
  the indigo background — the old one was 3.7:1.

The terminal prompt reads the token **visibly** rather than with `read -s`: a
silent prompt echoes nothing, so a screen reader announces nothing while you
paste and a typo cannot be found.

---

## 5. What is still not good enough

Recorded here as well as in the published statement, because these are the
things most likely to cost someone an installation:

1. **Tk on Linux.** The graphical prompt will not read properly under Orca.
   Mitigated by `--token` / `--no-gui`, not fixed. Fixing it means replacing Tk
   with GTK, which is a larger change than the prompt deserves.
2. **The Windows silent install cannot take a token.** `/S` skips the page that
   collects it. A machine therefore needs one interactive install, or the
   frozen build.
3. **Long unattended steps are quiet.** Building Python with pyenv can run for
   several minutes with nothing but log lines. There is no progress
   announcement in that window; the log is the only feedback.

---

## 6. For maintainers

- The High Contrast guard is `DetectHighContrast` + `$HighContrast` in both
  `installer-win/setup.nsi` and `installer-win/setup-frozen.nsi`. Every
  `_Dark*` helper returns early when it is set. **If you add another theming
  helper, add the guard**, or High Contrast breaks again.
- `_OnInit` is reported by `makensis` as *"not referenced — zeroing code out"*
  in both scripts. That predates this work (the same warning appears on the
  committed baseline), and it is why the detection runs from `_OnGUIInit`
  instead. It also means the `background.bmp` extraction in `_OnInit` never
  happens — worth fixing separately.
- `installer-mac/splash.py` and `installer-linux/splash.py` are byte-identical
  by design. Change one, copy it over the other.
- Nothing here may introduce a timed dialogue. `osascript`'s
  `giving up after` is banned in this project for that reason — grep for it
  before shipping.
