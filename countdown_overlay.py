"""Sleek semi-transparent countdown overlay before recording starts (3.. 2.. 1.. GO!)."""
import tkinter as tk
import ctypes
from desktop_support import exclude_from_capture


class CountdownOverlay:
    def __init__(self, seconds=3, on_finish=None, on_cancel=None, parent=None):
        self.count = seconds
        self.on_finish = on_finish
        self.on_cancel = on_cancel
        self.parent = parent
        self.root = None
        self.label = None

    def start(self):
        u32 = ctypes.windll.user32
        vw = u32.GetSystemMetrics(0)
        vh = u32.GetSystemMetrics(1)

        is_standalone = self.parent is None
        if self.parent:
            self.root = tk.Toplevel(self.parent)
        else:
            self.root = tk.Tk()

        self.root.overrideredirect(True)
        self.root.geometry(f"{vw}x{vh}+0+0")
        self.root.attributes("-alpha", 0.75)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#020617")

        exclude_from_capture(self.root)

        # Center canvas
        canvas = tk.Canvas(self.root, bg="#020617", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        cx = vw // 2
        cy = vh // 2

        self.circle_id = canvas.create_oval(cx - 90, cy - 90, cx + 90, cy + 90, outline="#38bdf8", width=4)
        self.text_id = canvas.create_text(
            cx, cy,
            text=str(self.count),
            fill="#f8fafc",
            font=("Segoe UI", 64, "bold")
        )
        self.hint_id = canvas.create_text(
            cx, cy + 130,
            text="Nhấn Space để quay ngay  •  ESC để hủy",
            fill="#94a3b8",
            font=("Segoe UI", 13)
        )

        def _play_beep(pitch):
            def _b():
                try:
                    import winsound
                    winsound.Beep(pitch, 60)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_b, daemon=True).start()

        _play_beep(880)

        def _tick():
            self.count -= 1
            if self.count > 0:
                _play_beep(880)
                canvas.itemconfig(self.text_id, text=str(self.count))
                self.root.after(1000, _tick)
            else:
                _play_beep(1318)
                canvas.itemconfig(self.text_id, text="GO!", fill="#10b981")
                self.root.after(350, self._done)

        self.root.bind("<space>", lambda e: self._done())
        self.root.bind("<Return>", lambda e: self._done())
        self.root.bind("<Button-1>", lambda e: self._done())
        self.root.bind("<Escape>", lambda e: self._cancel())

        self.root.after(1000, _tick)
        self.root.focus_force()
        if is_standalone:
            self.root.mainloop()

    def _done(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
        if self.on_finish:
            self.on_finish()

    def _cancel(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
        if self.on_cancel:
            self.on_cancel()
