"""Sleek floating notification pill shown when recording starts/stops.
Completely non-intrusive: does not steal focus, auto-dismisses after 3.5s.
"""
import os
import subprocess
from pathlib import Path
import tkinter as tk
import customtkinter as ctk
from desktop_support import exclude_from_capture


class NotificationPill(tk.Toplevel):
    def __init__(self, parent, text="⏳ Đang lưu bản ghi...", is_loading=True, file_path=None):
        super().__init__(parent)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#0f172a")
        exclude_from_capture(self)

        self.file_path = file_path

        # Center top of screen
        sw = self.winfo_screenwidth()
        w, h = 460, 48
        x = (sw - w) // 2
        y = 24
        self.geometry(f"{w}x{h}+{x}+{y}")

        border_col = "#0284c7" if is_loading else "#10b981"
        bg_col = "#082f49" if is_loading else "#064e3b"

        self.container = ctk.CTkFrame(
            self, fg_color=bg_col,
            corner_radius=12, border_width=1, border_color=border_col
        )
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        self.lbl_text = ctk.CTkLabel(
            self.container, text=text,
            font=("Segoe UI", 12, "bold"),
            text_color="#f8fafc"
        )
        self.lbl_text.pack(side="left", padx=(14, 8), fill="x", expand=True)

        self.btn_box = ctk.CTkFrame(self.container, fg_color="transparent")
        self.btn_box.pack(side="right", padx=(4, 10))

        if not is_loading and file_path and Path(file_path).is_file():
            btn_play = ctk.CTkButton(
                self.btn_box, text="▶ Xem", width=65, height=28,
                fg_color="#10b981", hover_color="#059669",
                corner_radius=6, font=("Segoe UI", 11, "bold"),
                command=self._play_file
            )
            btn_play.pack(side="left", padx=4)

        btn_close = ctk.CTkButton(
            self.btn_box, text="✕", width=26, height=28,
            fg_color="transparent", hover_color="#334155",
            corner_radius=6, font=("Segoe UI", 12),
            command=self.close
        )
        btn_close.pack(side="left")

        # Auto-dismiss after 3.5 seconds if complete
        if not is_loading:
            self.after(3500, self.fade_out_and_close)

    def set_success(self, text, file_path=None):
        if not self.winfo_exists():
            return
        self.file_path = file_path
        self.container.configure(fg_color="#064e3b", border_color="#10b981")
        self.lbl_text.configure(text=text, text_color="#6ee7b7")

        for w in self.btn_box.winfo_children():
            w.destroy()

        if file_path and Path(file_path).is_file():
            btn_play = ctk.CTkButton(
                self.btn_box, text="▶ Xem", width=65, height=28,
                fg_color="#10b981", hover_color="#059669",
                corner_radius=6, font=("Segoe UI", 11, "bold"),
                command=self._play_file
            )
            btn_play.pack(side="left", padx=4)

        btn_close = ctk.CTkButton(
            self.btn_box, text="✕", width=26, height=28,
            fg_color="transparent", hover_color="#065f46",
            corner_radius=6, font=("Segoe UI", 12),
            command=self.close
        )
        btn_close.pack(side="left")

        self.after(3500, self.fade_out_and_close)

    def _play_file(self):
        if self.file_path and Path(self.file_path).is_file():
            try:
                os.startfile(str(self.file_path))
            except Exception:
                pass
        self.close()

    def fade_out_and_close(self):
        if not self.winfo_exists():
            return

        def _step(current):
            if not self.winfo_exists():
                return
            next_val = max(0.0, current - 0.15)
            try:
                self.attributes("-alpha", next_val)
                if next_val > 0.0:
                    self.after(15, lambda: _step(next_val))
                else:
                    self.close()
            except Exception:
                self.close()

        _step(float(self.attributes("-alpha") or 1.0))

    def close(self):
        try:
            self.destroy()
        except Exception:
            pass
