"""Sleek draggable floating mini-bar during screen recording."""
import ctypes
import tkinter as tk
import customtkinter as ctk
from desktop_support import exclude_from_capture


class FloatingBar(tk.Toplevel):
    def __init__(self, parent, on_pause, on_resume, on_stop, on_restore):
        super().__init__(parent)
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop
        self.on_restore = on_restore

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#0f172a")

        # Initial geometry (bottom center or top right)
        sw = self.winfo_screenwidth()
        w, h = 340, 52
        x = (sw - w) // 2
        y = 24
        self.geometry(f"{w}x{h}+{x}+{y}")
        exclude_from_capture(self)

        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = 0
        self._win_start_y = 0

        container = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=12, border_width=1, border_color="#334155")
        container.pack(fill="both", expand=True, padx=2, pady=2)
        container.bind("<ButtonPress-1>", self._start_drag)
        container.bind("<B1-Motion>", self._on_drag)

        # Pulse Record indicator
        self.dot = ctk.CTkLabel(container, text="●", text_color="#ef4444", font=("Segoe UI", 18, "bold"), width=24)
        self.dot.pack(side="left", padx=(10, 4))
        self.dot.bind("<ButtonPress-1>", self._start_drag)
        self.dot.bind("<B1-Motion>", self._on_drag)

        # Timer label
        self.timer_label = ctk.CTkLabel(container, text="00:00", font=("Consolas", 15, "bold"), text_color="#f8fafc", width=60)
        self.timer_label.pack(side="left", padx=2)
        self.timer_label.bind("<ButtonPress-1>", self._start_drag)
        self.timer_label.bind("<B1-Motion>", self._on_drag)

        # Mic meter bar (compact mini visualizer)
        self.mic_canvas = tk.Canvas(container, width=32, height=14, bg="#0f172a", highlightthickness=0)
        self.mic_canvas.pack(side="left", padx=6)
        self.mic_canvas.bind("<ButtonPress-1>", self._start_drag)
        self.mic_canvas.bind("<B1-Motion>", self._on_drag)
        self.mic_bar = self.mic_canvas.create_rectangle(0, 0, 0, 14, fill="#10b981", width=0)

        # Pause / Resume button
        self.btn_pause = ctk.CTkButton(
            container, text="⏸", width=34, height=32,
            fg_color="#334155", hover_color="#475569",
            corner_radius=8, font=("Segoe UI", 13, "bold"),
            command=self._toggle_pause
        )
        self.btn_pause.pack(side="left", padx=4)

        # Stop button
        self.btn_stop = ctk.CTkButton(
            container, text="⏹", width=34, height=32,
            fg_color="#dc2626", hover_color="#b91c1c",
            corner_radius=8, font=("Segoe UI", 13, "bold"),
            command=self._trigger_stop
        )
        self.btn_stop.pack(side="left", padx=4)

        # Restore main window button
        self.btn_restore = ctk.CTkButton(
            container, text="🗗", width=34, height=32,
            fg_color="#334155", hover_color="#475569",
            corner_radius=8, font=("Segoe UI", 12),
            command=self.on_restore
        )
        self.btn_restore.pack(side="left", padx=(4, 10))

        self.is_paused = False
        self._pulse_state = True
        self._cached_rect = (x, y, w, h)
        self.bind("<Configure>", lambda e: self._update_cached_rect())
        self._pulse_timer()

    def _start_drag(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._win_start_x = self.winfo_x()
        self._win_start_y = self.winfo_y()

    def _on_drag(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        new_x = self._win_start_x + dx
        new_y = self._win_start_y + dy
        self.geometry(f"+{new_x}+{new_y}")
        self._cached_rect = (new_x, new_y, self.winfo_width(), self.winfo_height())

    def _pulse_timer(self):
        if not self.winfo_exists():
            return
        if not self.is_paused:
            self._pulse_state = not self._pulse_state
            color = "#ef4444" if self._pulse_state else "#7f1d1d"
            self.dot.configure(text_color=color)
        else:
            self.dot.configure(text_color="#eab308")  # Yellow when paused
        self.after(600, self._pulse_timer)

    def _trigger_stop(self):
        try:
            self.btn_stop.configure(text="⏳", state="disabled")
            self.btn_pause.configure(state="disabled")
            self.timer_label.configure(text="Đang lưu...")
        except Exception:
            pass
        self.on_stop()

    def show_saved_and_close(self):
        try:
            if not self.winfo_exists():
                return
            self.dot.configure(text="✔", text_color="#10b981")
            self.timer_label.configure(text="Đã lưu!", text_color="#10b981")
            self.after(1600, self.destroy)
        except Exception:
            try:
                self.destroy()
            except Exception:
                pass

    def _toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.btn_pause.configure(text="▶", fg_color="#0284c7", hover_color="#0369a1")
            self.on_pause()
        else:
            self.is_paused = False
            self.btn_pause.configure(text="⏸", fg_color="#334155", hover_color="#475569")
            self.on_resume()

    def update_stats(self, elapsed_sec, mic_rms):
        if not self.winfo_exists():
            return
        m, s = divmod(int(elapsed_sec), 60)
        h, m = divmod(m, 60)
        if h > 0:
            time_str = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            time_str = f"{m:02d}:{s:02d}"
        self.timer_label.configure(text=time_str)

        # Update mic VU meter
        bar_w = int(max(0.0, min(1.0, mic_rms)) * 32)
        color = "#10b981" if mic_rms < 0.8 else "#ef4444"
        self.mic_canvas.coords(self.mic_bar, 0, 0, bar_w, 14)
        self.mic_canvas.itemconfig(self.mic_bar, fill=color)

    def _update_cached_rect(self):
        try:
            if self.winfo_exists():
                self._cached_rect = (self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height())
            else:
                self._cached_rect = None
        except Exception:
            self._cached_rect = None

    def get_screen_rect(self):
        """Thread-safe screen rect for background capture thread."""
        return getattr(self, "_cached_rect", None)
