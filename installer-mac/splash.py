#!/usr/bin/env python3
"""EasyOKAPI GUI splash window — Mac/Linux launcher (tkinter).

Accessibility
-------------
A borderless, always-on-top window that never takes focus is invisible to a
screen reader and, worse, sits over whatever the user is actually reading. So:

  * **It is skipped when a screen reader is running** (VoiceOver on macOS,
    Orca on Linux) and whenever ``EASYOKAPI_NO_SPLASH=1`` is set. The launch
    proceeds exactly as before — the splash reports progress, it does not
    control it.
  * **Progress is also written to stdout** as plain lines, so a user who
    started the app from a terminal hears each stage from their screen reader
    instead of watching a bar they cannot see.
  * **It never takes focus and never blocks.** Nothing in it has to be
    dismissed, and it closes itself when the server is ready — there is no
    time limit to run out of, and no step that waits on the user.

See docs/accessibility/INSTALLERS.md and the published statement at
https://www.easyokapi.cbbiotec.vn/accessibility.
"""

import os, sys, time, threading, platform, subprocess


def _screen_reader_running():
    """True when VoiceOver (macOS) or Orca (Linux) is active.

    Best-effort and deliberately silent: a probe that fails must not stop the
    application from launching.
    """
    if os.environ.get("EASYOKAPI_NO_SPLASH") == "1":
        return True
    try:
        name = "VoiceOver" if platform.system() == "Darwin" else "orca"
        return subprocess.call(["pgrep", "-x", name],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _say(pct, label):
    """Report a stage on stdout — the accessible half of the progress bar."""
    try:
        sys.stdout.write("EasyOKAPI: %3d%%  %s\n" % (pct, label))
        sys.stdout.flush()
    except Exception:
        pass


# A window nobody can read is only in the way. Report on stdout and exit; the
# launcher scripts do not wait on this process.
if _screen_reader_running():
    _say(0, "Launching EasyOKAPI, please wait…")
    sys.exit(0)

try:
    import tkinter as tk
except ImportError:
    sys.exit(0)

PIPE    = "/tmp/easyokapi_progress.pipe"
BG      = "#1E1E2E"
SURFACE = "#313244"
TEXT    = "#CDD6F4"
SUBTLE  = "#585B70"
MUTED   = "#45475A"
ACCENT  = "#89B4FA"

IS_MAC = platform.system() == "Darwin"
FONT   = "Helvetica Neue" if IS_MAC else "DejaVu Sans"

_FAKE_LABELS = {
     0: "Initialising…",
    10: "Setting up environment…",
    20: "Activating virtual environment…",
    35: "Running preflight checks…",
    42: "Launching application…",
}


class Splash:
    W, H = 480, 170

    def __init__(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            return  # no display available

        self.root  = root
        self._pct  = 0
        self._real = False
        self._done = False
        self._dx   = self._dy = 0

        root.overrideredirect(True)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        # Borderless windows have no title bar to carry a name; set one anyway
        # so the window manager, the dock and any assistive technology that
        # does see it have something to call this.
        root.title("EasyOKAPI — launching")

        # Center on screen
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")

        if IS_MAC:
            try:
                root.wm_attributes("-transparent", True)
                root.configure(bg="systemTransparent")
                cv = tk.Canvas(root, width=self.W, height=self.H,
                               bg="systemTransparent", highlightthickness=0)
                cv.place(x=0, y=0)
                self._rounded_rect(cv, 0, 0, self.W, self.H, 12, BG)
            except Exception:
                root.configure(bg=BG)
        else:
            root.configure(bg=BG)
            try:
                root.wm_attributes("-type", "splash")
            except tk.TclError:
                pass

        self._build_widgets(root)

        root.bind("<Button-1>",  self._drag_start)
        root.bind("<B1-Motion>", self._drag_move)

        self._fake_tick()
        threading.Thread(target=self._reader, daemon=True).start()
        root.mainloop()

    # ── Widget layout ─────────────────────────────────────────────────────────

    def _build_widgets(self, root):
        tk.Label(root, text="EasyOKAPI", bg=BG, fg=TEXT,
                 font=(FONT, 22, "bold")).place(x=0, y=28, width=self.W)
        tk.Label(root, text="Launching, please wait…", bg=BG, fg=SUBTLE,
                 font=(FONT, 11)).place(x=0, y=58, width=self.W)

        TX, TY, TW = 36, 96, self.W - 72

        track = tk.Frame(root, bg=SURFACE, width=TW, height=6)
        track.place(x=TX, y=TY)

        self._fill = tk.Frame(track, bg=ACCENT, height=6, width=0)
        self._fill.place(x=0, y=0)
        self._tw = TW

        self._sv = tk.StringVar(value="Initialising…")
        self._pv = tk.StringVar(value="0%")

        tk.Label(root, textvariable=self._sv, bg=BG, fg=MUTED,
                 font=(FONT, 10), anchor="w").place(x=TX, y=TY + 14, width=TW - 40)
        tk.Label(root, textvariable=self._pv, bg=BG, fg=MUTED,
                 font=(FONT, 10), anchor="e").place(x=TX + TW - 36, y=TY + 14, width=36)

    # ── Rounded-rect helper (macOS transparent canvas) ────────────────────────

    def _rounded_rect(self, canvas, x1, y1, x2, y2, r, color):
        corners = [
            (x1,     y1,     x1+2*r, y1+2*r,  90, 90),
            (x2-2*r, y1,     x2,     y1+2*r,   0, 90),
            (x2-2*r, y2-2*r, x2,     y2,      270, 90),
            (x1,     y2-2*r, x1+2*r, y2,      180, 90),
        ]
        for x0, y0, xe, ye, start, extent in corners:
            canvas.create_arc(x0, y0, xe, ye, start=start, extent=extent,
                              fill=color, outline=color)
        canvas.create_rectangle(x1+r, y1,   x2-r, y2,   fill=color, outline=color)
        canvas.create_rectangle(x1,   y1+r, x2,   y2-r, fill=color, outline=color)

    # ── Drag support ──────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    # ── Progress update (always called on main thread via after()) ─────────────

    def _set(self, pct, label):
        pct = min(max(pct, self._pct), 100)  # never go backward, cap at 100
        changed_label = (label and label != self._sv.get())
        self._pct = pct
        self._fill.config(width=int(self._tw * pct / 100))
        self._sv.set(label)
        self._pv.set(f"{pct}%")
        # Tk does not expose this bar to assistive technology, so each real
        # stage is also written to stdout. Only on a stage change: a line per
        # percent would be unreadable.
        if changed_label:
            _say(pct, label)
        if pct >= 100 and not self._done:
            self._done = True
            self.root.after(700, self.root.destroy)

    # ── Fake slow animation (0 → 45%) while waiting for real data ─────────────

    def _fake_tick(self):
        if self._real or self._done or self._pct >= 45:
            return
        label = _FAKE_LABELS.get(self._pct + 1, self._sv.get())
        self._set(self._pct + 1, label)
        self.root.after(200, self._fake_tick)

    # ── FIFO reader (background thread) ───────────────────────────────────────

    def _reader(self):
        for _ in range(100):           # wait up to 10 s for FIFO to appear
            if os.path.exists(PIPE):
                break
            time.sleep(0.1)

        try:
            with open(PIPE, "r") as f:
                for line in f:
                    parts = line.strip().split(" ", 1)
                    try:
                        raw   = int(parts[0])
                        label = parts[1] if len(parts) > 1 else ""
                    except (ValueError, IndexError):
                        continue
                    display = max(50 + raw // 2, self._pct)  # map 0-100 → 50-100
                    self._real = True
                    self.root.after(0, self._set, display, label)
                    if raw >= 100:
                        break
        except Exception:
            pass

        self.root.after(0, self._set, 100, "Server ready!")


if __name__ == "__main__":
    Splash()
