#!/usr/bin/env python3
"""
EasyOKAPI Setup UI — tkinter-based installer launcher.

Replaces zenity dialogs in setup.sh to avoid the Wayland rendering bug
where zenity shows a desktop screenshot instead of its window content.
tkinter works reliably on both X11 and Wayland without that issue.

Usage (called by setup.sh):
    python3 setup_ui.py
    exit 0 + prints token to stdout  →  user clicked Install with a token
    exit 1 (no output)               →  user cancelled

Accessibility
-------------
This window is assessed against the software clauses of EN 301 549 and against
WCAG 2.2 Level AA where a criterion applies to software; the published claim is
at https://www.easyokapi.cbbiotec.vn/accessibility. What that costs here:

  * **Every step is completable from the keyboard alone.** Tab moves, Space and
    Enter activate, Escape cancels, Return in the field installs. Focus starts
    in the token field and is visible on every control — Tk draws no focus ring
    on a `relief="flat"` button unless it is asked to, which is why every
    button below sets `highlightthickness`.
  * **Nothing is conveyed by colour alone.** The validation message is text,
    not a red border, and it is announced by moving focus back to the field it
    describes.
  * **The token is not masked by default.** It is a download credential, not a
    password: masking it made every character read as "bullet" to a screen
    reader and gained nothing, since the string is single-use and already on
    the clipboard. A "Hide token" checkbox is there for a shared screen.
  * **Tk exposes very little to AT-SPI**, so Orca reads this window poorly no
    matter what is done here. That is a published limitation, and it is why
    `setup.sh --token` exists: the command-line path is the supported route for
    a screen-reader user and is documented in docs/accessibility/INSTALLERS.md.

Set ``EASYOKAPI_NO_GUI=1`` to skip this window entirely (setup.sh then prompts
on the terminal, which every screen reader handles well).
"""
import os
import sys
import tkinter as tk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH  = os.path.join(SCRIPT_DIR, "okapi.png")

# Dark indigo palette — matches the EasyOKAPI web app CSS variables and the
# Windows NSIS installer colour scheme. Every pair below clears 4.5:1 against
# the surface it sits on; check any replacement before shipping it.
BG        = "#312e81"   # indigo-900  — window background
CARD      = "#1e1b4b"   # indigo-950  — input field background
FG        = "#e2e8f0"   # slate-200   — body text          (8.7:1 on BG)
MUTED     = "#a5b4fc"   # indigo-300  — secondary / hint    (5.9:1 on BG)
ACCENT    = "#6366f1"   # indigo-500  — primary button + highlight border
ACCENT_HV = "#4f46e5"   # indigo-600  — button hover
# red-400 (#f87171) was 3.7:1 on the indigo background — under the 4.5:1 that
# WCAG 1.4.3 asks for, and this is the only text that reports a mistake.
DANGER    = "#fca5a5"   # red-300     — validation error    (5.5:1 on BG)
FOCUS     = "#ffffff"   # focus ring; white keeps 3:1 against every surface here


class SetupWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        # The window title is the first thing a screen reader announces and the
        # only label a window manager shows — it has to say what this is and
        # what it is for, not just the product name.
        self.title("EasyOKAPI Setup — enter your download token")
        self.configure(bg=BG)
        # Resizable: a fixed window cannot be enlarged by someone who needs it
        # bigger, and Tk will not reflow what it cannot resize (WCAG 1.4.4).
        self.resizable(True, True)
        self.minsize(420, 380)
        self.result = None
        self._logo_ref = None   # keep PhotoImage alive

        self._build()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Escape cancels from anywhere in the window — the same contract as the
        # Cancel button, without having to find it (2.1.1).
        self.bind("<Escape>", lambda _: self._on_cancel())

    # ── UI construction ────────────────────────────────────────────────────────

    def _focusable(self, widget):
        """Give a control a focus ring Tk would otherwise not draw.

        `relief="flat"` buttons have no visual focus state of their own, so a
        keyboard user cannot see where they are (WCAG 2.4.7). The ring is white
        on every surface in this window, which keeps it above 3:1 (1.4.11).
        """
        widget.configure(highlightthickness=2,
                         highlightcolor=FOCUS,
                         highlightbackground=BG,
                         takefocus=True)
        return widget

    def _build(self):
        # Thin accent stripe at the top (like the Windows installer sidebar)
        tk.Frame(self, bg=ACCENT, height=6).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=36, pady=28)
        body.pack(fill="both", expand=True)

        # Logo
        if os.path.exists(ICON_PATH):
            try:
                raw = tk.PhotoImage(file=ICON_PATH)
                scale = max(1, raw.width() // 72)   # target ~72 px wide
                self._logo_ref = raw.subsample(scale, scale)
                # Decorative: the heading below already says what this window
                # is, so the logo carries no information of its own.
                tk.Label(body, image=self._logo_ref, bg=BG,
                         takefocus=False).pack(pady=(0, 10))
            except Exception:
                pass

        # Heading
        tk.Label(body, text="EasyOKAPI Setup",
                 bg=BG, fg=FG,
                 font=("TkDefaultFont", 17, "bold")).pack()
        tk.Label(body, text="HTBiotec · PyBadge Colorimeter Biosensor App",
                 bg=BG, fg=MUTED,
                 font=("TkDefaultFont", 9)).pack(pady=(2, 24))

        # Token label + hint
        tk.Label(body, text="Download Token",
                 bg=BG, fg=FG,
                 font=("TkDefaultFont", 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(body,
                 text="Enter the token generated in your EasyOKAPI account.",
                 bg=BG, fg=MUTED,
                 font=("TkDefaultFont", 9),
                 anchor="w").pack(fill="x", pady=(1, 6))

        # Token entry.
        #
        # Shown in clear by default. This is a single-use download token the
        # user has just copied out of their account page, not a password:
        # masking it turned every character into "bullet" for a screen reader
        # and made a typo impossible to spot, in exchange for hiding a string
        # that expires in 30 minutes. The checkbox below covers the case that
        # actually warrants it — a shared or projected screen.
        self._token_var = tk.StringVar()
        self._entry = tk.Entry(
            body,
            textvariable=self._token_var,
            width=42,
            bg=CARD, fg=FG, insertbackground=FG,
            relief="flat",
            font=("TkFixedFont", 11),
            highlightthickness=2,
            highlightcolor=FOCUS,
            highlightbackground="#4338ca",
        )
        self._entry.pack(fill="x", ipady=7, pady=(0, 4))
        self._entry.bind("<Return>", lambda _: self._on_install())
        self._entry.focus_set()

        self._hide_var = tk.BooleanVar(value=False)
        self._focusable(tk.Checkbutton(
            body, text="Hide token while typing",
            variable=self._hide_var, command=self._on_toggle_hide,
            bg=BG, fg=MUTED, selectcolor=CARD,
            activebackground=BG, activeforeground=FG,
            font=("TkDefaultFont", 9), anchor="w",
        )).pack(fill="x", pady=(0, 2))

        # Inline validation message (empty until needed). Kept in the layout
        # at all times so the window does not jump when it appears, and the
        # message is text — never a colour change on its own (WCAG 1.4.1).
        self._err = tk.Label(body, text="", bg=BG, fg=DANGER,
                             font=("TkDefaultFont", 9), anchor="w",
                             wraplength=380, justify="left")
        self._err.pack(fill="x", pady=(0, 18))

        # Buttons
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x")

        self._focusable(tk.Button(
            btn_row, text="Cancel",
            command=self._on_cancel,
            bg="#374151", fg=FG,
            activebackground="#4b5563", activeforeground=FG,
            relief="flat", bd=0,
            font=("TkDefaultFont", 10), padx=18, pady=7,
            cursor="hand2",
        )).pack(side="right", padx=(8, 0))

        install_btn = self._focusable(tk.Button(
            btn_row, text="  Install  ",
            command=self._on_install,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_HV, activeforeground="white",
            relief="flat", bd=0,
            font=("TkDefaultFont", 10, "bold"), padx=18, pady=7,
            cursor="hand2",
        ))
        install_btn.pack(side="right")
        # Space activates a focused Tk button by default; Enter does not. Both
        # are what a user expects from a default action, so both are bound.
        install_btn.bind("<Return>", lambda _: self._on_install())

        # The keyboard contract, stated on screen rather than left to be
        # discovered — this window has no menu and no help.
        tk.Label(body,
                 text="Tab moves between fields · Enter installs · Escape cancels",
                 bg=BG, fg=MUTED, font=("TkDefaultFont", 8),
                 anchor="w").pack(fill="x", pady=(12, 0))

        tk.Frame(body, bg=BG, height=4).pack()   # bottom padding

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_toggle_hide(self):
        self._entry.config(show="●" if self._hide_var.get() else "")

    def _on_install(self):
        token = self._token_var.get().strip()
        if not token:
            # 3.3.1 / 3.3.3 — say what is wrong and where to fix it, then put
            # the caret in that field. The message names the field because the
            # window is read out of order by some assistive technology.
            self._err.config(
                text="A download token is required. Paste the token from your "
                     "EasyOKAPI account into the Download Token field.")
            self._entry.focus_set()
            return
        self._err.config(text="")
        self.result = token
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")


if __name__ == "__main__":
    # An explicit opt-out of the graphical step. Tk tells AT-SPI almost
    # nothing, so a screen-reader user is better served by setup.sh's terminal
    # prompt; exiting 2 tells the caller to fall back to it rather than to
    # treat this as a cancellation. See docs/accessibility/INSTALLERS.md.
    if os.environ.get("EASYOKAPI_NO_GUI") == "1":
        sys.exit(2)

    app = SetupWindow()
    app.mainloop()
    if app.result:
        print(app.result, end="", flush=True)
        sys.exit(0)
    else:
        sys.exit(1)
