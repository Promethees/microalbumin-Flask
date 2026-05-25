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
"""
import os
import sys
import tkinter as tk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH  = os.path.join(SCRIPT_DIR, "okapi.png")

# Dark indigo palette — matches the EasyOKAPI web app CSS variables and the
# Windows NSIS installer colour scheme.
BG        = "#312e81"   # indigo-900  — window background
CARD      = "#1e1b4b"   # indigo-950  — input field background
FG        = "#e2e8f0"   # slate-200   — body text
MUTED     = "#a5b4fc"   # indigo-300  — secondary / hint text
ACCENT    = "#6366f1"   # indigo-500  — primary button + highlight border
ACCENT_HV = "#4f46e5"   # indigo-600  — button hover
DANGER    = "#f87171"   # red-400     — validation error


class SetupWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EasyOKAPI Setup")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result = None
        self._logo_ref = None   # keep PhotoImage alive

        self._build()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ── UI construction ────────────────────────────────────────────────────────

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
                tk.Label(body, image=self._logo_ref, bg=BG).pack(pady=(0, 10))
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

        # Password entry
        self._token_var = tk.StringVar()
        self._entry = tk.Entry(
            body,
            textvariable=self._token_var,
            show="●",          # ● bullet
            width=42,
            bg=CARD, fg=FG, insertbackground=FG,
            relief="flat",
            font=("TkFixedFont", 11),
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground="#4338ca",
        )
        self._entry.pack(fill="x", ipady=7, pady=(0, 4))
        self._entry.bind("<Return>", lambda _: self._on_install())
        self._entry.focus_set()

        # Inline validation message (hidden until needed)
        self._err = tk.Label(body, text="", bg=BG, fg=DANGER,
                             font=("TkDefaultFont", 9), anchor="w")
        self._err.pack(fill="x", pady=(0, 18))

        # Buttons
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row, text="Cancel",
            command=self._on_cancel,
            bg="#374151", fg=FG,
            activebackground="#4b5563", activeforeground=FG,
            relief="flat", bd=0,
            font=("TkDefaultFont", 10), padx=18, pady=7,
            cursor="hand2",
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_row, text="  Install  ",
            command=self._on_install,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_HV, activeforeground="white",
            relief="flat", bd=0,
            font=("TkDefaultFont", 10, "bold"), padx=18, pady=7,
            cursor="hand2",
        ).pack(side="right")

        tk.Frame(body, bg=BG, height=4).pack()   # bottom padding

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_install(self):
        token = self._token_var.get().strip()
        if not token:
            self._err.config(text="A download token is required.")
            self._entry.focus_set()
            return
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
    app = SetupWindow()
    app.mainloop()
    if app.result:
        print(app.result, end="", flush=True)
        sys.exit(0)
    else:
        sys.exit(1)
