"""Pro Screen Recorder - Siêu Nhẹ & Đỉnh Cao Cho Windows.
Quay màn hình phần cứng GPU, khay hệ thống, hiệu ứng chuyển động, âm thanh thông báo.
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import customtkinter as ctk

from settings import Settings
from recorder_engine import RecorderEngine
from region_selector import RegionSelector
from floating_bar import FloatingBar
from library_window import LibraryWindow
from hotkey_manager import HotkeyManager
from countdown_overlay import CountdownOverlay
from notification_pill import NotificationPill
from desktop_support import (
    SingleInstance, set_high_dpi_aware, exclude_from_capture,
    set_dark_titlebar, play_sound_cue, create_tray
)

ctk.deactivate_automatic_dpi_awareness()
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ProScreenRecorderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Pro Screen Recorder - Ghi Màn Hình & Micro")
        self.geometry("600x860")
        self.minsize(540, 720)
        self.configure(fg_color="#0b0f19")

        # Set window icon & native Windows dark titlebar
        self.icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if self.icon_path.is_file():
            try:
                self.iconbitmap(str(self.icon_path))
            except Exception:
                pass
        set_dark_titlebar(self)

        self.settings = Settings()
        self.engine = RecorderEngine(self.settings, on_update_callback=self._on_engine_update)
        self.floating_bar = None
        self.library_win = None
        self.last_saved_file = None
        self.tray = None
        self.pill = None
        self._main_was_visible = False
        # UI update coalescing guard & state cache
        self._ui_update_pending = False
        self._latest_stats = None

        # Pulsing recording glow animation state
        self._pulse_glow = False

        # Global Hotkeys
        self.hotkeys = HotkeyManager(
            on_toggle_record=self._on_hotkey_toggle_record,
            on_toggle_pause=self._on_hotkey_toggle_pause,
            key_record=getattr(self.settings, "hotkey_start_stop", "F9"),
            key_pause=getattr(self.settings, "hotkey_pause_resume", "F10")
        )
        self.hotkeys.start()

        # Build UI in a scrollable frame
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="#0b0f19")
        self.main_scroll.pack(fill="both", expand=True)

        self._build_header()
        self._build_record_card()
        self._build_toast_card()
        self._build_audio_card()
        self._build_capture_settings_card()
        self._build_footer()

        # Initialize System Tray in background thread
        self._init_tray()

        # Handle window close [X]
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- Window Display Management ---

    def show_from_tray(self):
        """Restore window cleanly from system tray to foreground."""
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    def hide_to_tray(self):
        """Minimize cleanly to Windows taskbar notification area."""
        if getattr(self.settings, "sound_cues", True):
            play_sound_cue("tray")
        self.withdraw()

        if self.tray:
            try:
                self.tray.notify(
                    "Pro Screen Recorder đang chạy trong khay hệ thống.\nNhấn F9 để Bắt đầu/Dừng quay!",
                    "Đã ẩn xuống khay hệ thống"
                )
            except Exception:
                pass

    def fade_in(self):
        self.show_from_tray()

    def fade_out_to_tray(self):
        self.hide_to_tray()

    # --- System Tray Integration ---

    def _init_tray(self):
        def _run_tray():
            try:
                self.tray = create_tray(
                    icon_path=self.icon_path,
                    on_open=self._on_tray_open,
                    on_toggle_record=self._on_tray_toggle_record,
                    on_toggle_pause=self._on_tray_toggle_pause,
                    on_open_library=self._on_tray_open_library,
                    on_open_desktop=self._on_tray_open_desktop,
                    on_quit=self._on_tray_quit
                )
                self.tray.run()
            except Exception:
                pass

        threading.Thread(target=_run_tray, daemon=True).start()

    def _on_tray_open(self, icon=None, item=None):
        self.after(0, self.show_from_tray)

    def _on_tray_toggle_record(self, icon=None, item=None):
        self.after(0, self.toggle_recording)

    def _on_tray_toggle_pause(self, icon=None, item=None):
        self.after(0, self.toggle_pause)

    def _on_tray_open_library(self, icon=None, item=None):
        self.after(0, self.open_library)

    def _on_tray_open_desktop(self, icon=None, item=None):
        self.after(0, self._open_output_dir)

    def _on_tray_quit(self, icon=None, item=None):
        self.after(0, self.quit_app)

    # --- UI Builders ---

    def _build_header(self):
        header = ctk.CTkFrame(self.main_scroll, fg_color="#111827", height=55, corner_radius=10)
        header.pack(fill="x", side="top", padx=16, pady=(10, 6))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=16, pady=10)

        ctk.CTkLabel(
            left, text="🎥 PRO SCREEN RECORDER",
            font=("Segoe UI", 16, "bold"), text_color="#f8fafc"
        ).pack(side="left")

        ctk.CTkLabel(
            left, text="Pro Edition • Siêu Nhẹ & GPU",
            font=("Segoe UI", 11), text_color="#38bdf8"
        ).pack(side="left", padx=(10, 0))

        # Right buttons: Minimize to Tray & Library
        btn_tray = ctk.CTkButton(
            header, text="📥 Thu Khay", width=100, height=32,
            fg_color="#0284c7", hover_color="#0369a1",
            corner_radius=8, font=("Segoe UI", 12, "bold"),
            command=self.hide_to_tray
        )
        btn_tray.pack(side="right", padx=(4, 14), pady=10)

        btn_lib = ctk.CTkButton(
            header, text="📹 Thư Viện", width=95, height=32,
            fg_color="#1e293b", hover_color="#334155",
            corner_radius=8, font=("Segoe UI", 12, "bold"),
            command=self.open_library
        )
        btn_lib.pack(side="right", padx=(4, 4), pady=10)

    def _build_record_card(self):
        self.record_card = ctk.CTkFrame(self.main_scroll, fg_color="#161e2e", corner_radius=14, border_width=1, border_color="#1f2937")
        self.record_card.pack(fill="x", padx=16, pady=6)

        # Main Record Button
        self.btn_record = ctk.CTkButton(
            self.record_card, text="🔴  BẮT ĐẦU GHI HÌNH (F9)",
            height=54, corner_radius=10,
            fg_color="#dc2626", hover_color="#b91c1c",
            font=("Segoe UI", 16, "bold"),
            command=self.toggle_recording
        )
        self.btn_record.pack(fill="x", padx=16, pady=(16, 8))

        # Secondary Control (Pause / Resume)
        sub_row = ctk.CTkFrame(self.record_card, fg_color="transparent")
        sub_row.pack(fill="x", padx=16, pady=(0, 10))

        self.btn_pause = ctk.CTkButton(
            sub_row, text="⏸ Tạm Dừng (F10)", height=34,
            fg_color="#374151", hover_color="#4b5563",
            corner_radius=8, font=("Segoe UI", 13),
            state="disabled",
            command=self.toggle_pause
        )
        self.btn_pause.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_folder_text = "📁 Mở Desktop" if Path(self.settings.output_dir).resolve() == (Path.home() / "Desktop").resolve() else "📁 Thư mục lưu"
        self.btn_open_rec_folder = ctk.CTkButton(
            sub_row, text=btn_folder_text, height=34, width=125,
            fg_color="#374151", hover_color="#4b5563",
            corner_radius=8, font=("Segoe UI", 13),
            command=self._open_output_dir
        )
        self.btn_open_rec_folder.pack(side="right", padx=(4, 0))

        # Live Stats Display
        self.stats_box = ctk.CTkFrame(self.record_card, fg_color="#0f172a", corner_radius=10)
        self.stats_box.pack(fill="x", padx=16, pady=(4, 14))

        stats_row = ctk.CTkFrame(self.stats_box, fg_color="transparent")
        stats_row.pack(fill="x", padx=14, pady=8)

        self.lbl_status = ctk.CTkLabel(
            stats_row, text="● SẴN SÀNG", font=("Segoe UI", 12, "bold"),
            text_color="#10b981"
        )
        self.lbl_status.pack(side="left")

        self.lbl_timer = ctk.CTkLabel(
            stats_row, text="00:00:00", font=("Consolas", 18, "bold"),
            text_color="#f8fafc"
        )
        self.lbl_timer.pack(side="left", expand=True)

        self.lbl_details = ctk.CTkLabel(
            stats_row, text="30 FPS  •  0 MB", font=("Segoe UI", 12),
            text_color="#94a3b8"
        )
        self.lbl_details.pack(side="right")

    def _build_toast_card(self):
        """Instant non-blocking notification banner shown when video finishes saving."""
        self.toast_card = ctk.CTkFrame(
            self.main_scroll, fg_color="#064e3b",
            corner_radius=12, border_width=1, border_color="#059669"
        )

        inner = ctk.CTkFrame(self.toast_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        left_info = ctk.CTkFrame(inner, fg_color="transparent")
        left_info.pack(side="left", fill="both", expand=True)

        self.lbl_toast_title = ctk.CTkLabel(
            left_info, text="✅ ĐÃ LƯU VIDEO THÀNH CÔNG!",
            font=("Segoe UI", 13, "bold"), text_color="#6ee7b7", anchor="w"
        )
        self.lbl_toast_title.pack(fill="x")

        self.lbl_toast_subtitle = ctk.CTkLabel(
            left_info, text="REC_...mp4",
            font=("Segoe UI", 11), text_color="#d1fae5", anchor="w"
        )
        self.lbl_toast_subtitle.pack(fill="x")

        btn_box = ctk.CTkFrame(inner, fg_color="transparent")
        btn_box.pack(side="right")

        btn_play = ctk.CTkButton(
            btn_box, text="▶ Xem ngay", width=84, height=30,
            fg_color="#10b981", hover_color="#059669",
            corner_radius=6, font=("Segoe UI", 11, "bold"),
            command=self._play_last_video
        )
        btn_play.pack(side="left", padx=4)

        btn_loc = ctk.CTkButton(
            btn_box, text="📂 Vị trí", width=70, height=30,
            fg_color="#047857", hover_color="#065f46",
            corner_radius=6, font=("Segoe UI", 11),
            command=self._locate_last_video
        )
        btn_loc.pack(side="left", padx=4)

        btn_close = ctk.CTkButton(
            btn_box, text="✕", width=28, height=30,
            fg_color="#064e3b", hover_color="#065f46",
            corner_radius=6, font=("Segoe UI", 12),
            command=self._hide_toast
        )
        btn_close.pack(side="left", padx=(2, 0))

    def _play_last_video(self):
        if self.last_saved_file and Path(self.last_saved_file).is_file():
            try:
                os.startfile(str(self.last_saved_file))
            except Exception:
                pass

    def _locate_last_video(self):
        if self.last_saved_file and Path(self.last_saved_file).is_file():
            try:
                subprocess.run(["explorer", f"/select,{self.last_saved_file}"])
            except Exception:
                try:
                    os.startfile(str(Path(self.last_saved_file).parent))
                except Exception:
                    pass

    def _hide_toast(self):
        self.toast_card.pack_forget()

    def _build_audio_card(self):
        card = ctk.CTkFrame(self.main_scroll, fg_color="#161e2e", corner_radius=14, border_width=1, border_color="#1f2937")
        card.pack(fill="x", padx=16, pady=6)

        # Title + Toggle
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            top_row, text="🎙️ THU ÂM MICROPHONE",
            font=("Segoe UI", 13, "bold"), text_color="#f8fafc"
        ).pack(side="left")

        self.switch_mic = ctk.CTkSwitch(
            top_row, text="Bật Micro",
            command=self._on_mic_switch_changed
        )
        if self.settings.record_mic:
            self.switch_mic.select()
        else:
            self.switch_mic.deselect()
        self.switch_mic.pack(side="right")

        # Device selector
        mid_row = ctk.CTkFrame(card, fg_color="transparent")
        mid_row.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(mid_row, text="Thiết bị:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))

        mics = self.engine.audio_mgr.list_microphones()
        self.mic_map = {m["name"]: m["index"] for m in mics}
        mic_options = list(self.mic_map.keys()) if self.mic_map else ["Microphone mặc định hệ thống"]

        self.combo_mic = ctk.CTkComboBox(
            mid_row, values=mic_options,
            command=self._on_mic_device_changed,
            height=30, corner_radius=8
        )
        self.combo_mic.pack(side="left", fill="x", expand=True)
        if mic_options:
            self.combo_mic.set(mic_options[0])

        # Volume Boost Slider (100% -> 200%)
        vol_row = ctk.CTkFrame(card, fg_color="transparent")
        vol_row.pack(fill="x", padx=16, pady=(6, 2))

        ctk.CTkLabel(vol_row, text="Khuếch đại mic:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))
        self.lbl_vol_val = ctk.CTkLabel(
            vol_row, text=f"{int(self.settings.mic_volume * 100)}%",
            font=("Segoe UI", 11, "bold"), text_color="#38bdf8", width=42
        )
        self.lbl_vol_val.pack(side="right")

        self.slider_mic_vol = ctk.CTkSlider(
            vol_row, from_=0.5, to=2.0, number_of_steps=15,
            command=self._on_mic_volume_changed
        )
        self.slider_mic_vol.set(self.settings.mic_volume)
        self.slider_mic_vol.pack(side="left", fill="x", expand=True)

        # Live VU Meter Bar
        vu_row = ctk.CTkFrame(card, fg_color="transparent")
        vu_row.pack(fill="x", padx=16, pady=(6, 4))

        ctk.CTkLabel(vu_row, text="Mức âm:", font=("Segoe UI", 11), text_color="#64748b").pack(side="left", padx=(0, 8))

        self.mic_vu_canvas = tk.Canvas(vu_row, height=12, bg="#0f172a", highlightthickness=0)
        self.mic_vu_canvas.pack(side="left", fill="x", expand=True)
        self.mic_vu_bar = self.mic_vu_canvas.create_rectangle(0, 0, 0, 12, fill="#10b981", width=0)

        # Status text for mic level and testing guidance
        self.lbl_mic_status = ctk.CTkLabel(
            card,
            text="💡 Mẹo: Nhấn 'Thử Micro' để kiểm tra sóng âm và chỉnh độ to trước khi quay.",
            font=("Segoe UI", 11), text_color="#64748b", anchor="w"
        )
        self.lbl_mic_status.pack(fill="x", padx=16, pady=(2, 6))

        # Test Mic Action Controls
        test_row = ctk.CTkFrame(card, fg_color="transparent")
        test_row.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_test_mic = ctk.CTkButton(
            test_row, text="🎤 Bật Thử Mic", width=125, height=28,
            fg_color="#0284c7", hover_color="#0369a1",
            corner_radius=7, font=("Segoe UI", 11, "bold"),
            command=self._toggle_test_mic
        )
        self.btn_test_mic.pack(side="left", padx=(0, 8))

        self.btn_test_sample = ctk.CTkButton(
            test_row, text="🎧 Ghi & Nghe lại 3s", width=145, height=28,
            fg_color="#334155", hover_color="#475569",
            corner_radius=7, font=("Segoe UI", 11),
            command=self._start_sample_test
        )
        self.btn_test_sample.pack(side="left", padx=(0, 12))

        self.chk_live_monitor = ctk.CTkCheckBox(
            test_row, text="Nghe trực tiếp qua loa/tai nghe",
            font=("Segoe UI", 11), text_color="#94a3b8",
            command=self._on_live_monitor_toggled
        )
        self.chk_live_monitor.pack(side="left")

    def _build_capture_settings_card(self):
        card = ctk.CTkFrame(self.main_scroll, fg_color="#161e2e", corner_radius=14, border_width=1, border_color="#1f2937")
        card.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            card, text="⚙️ THIẾT LẬP GHI HÌNH CHUYÊN NGHIỆP",
            font=("Segoe UI", 13, "bold"), text_color="#f8fafc"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        # Row 1: Mode Area Selection
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(row1, text="Phạm vi:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))

        self.seg_area = ctk.CTkSegmentedButton(
            row1, values=["Toàn màn hình", "Chọn vùng quay"],
            command=self._on_area_mode_changed
        )
        self.seg_area.set("Toàn màn hình")
        self.seg_area.pack(side="left", padx=(0, 8))

        self.btn_select_region = ctk.CTkButton(
            row1, text="📐 Chọn vùng...", width=100, height=28,
            fg_color="#0284c7", hover_color="#0369a1",
            corner_radius=6, font=("Segoe UI", 11),
            state="disabled",
            command=self._launch_region_selector
        )
        self.btn_select_region.pack(side="left")

        # Row 2: Resolution & Countdown
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(row2, text="Độ phân giải:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))
        self.combo_res = ctk.CTkComboBox(
            row2, values=["Native (Gốc)", "1080p Full HD", "720p HD"],
            width=130, height=28,
            command=self._on_res_changed
        )
        res_map = {"Native": "Native (Gốc)", "1080p": "1080p Full HD", "720p": "720p HD"}
        self.combo_res.set(res_map.get(self.settings.resolution_preset, "Native (Gốc)"))
        self.combo_res.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row2, text="Đếm ngược:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))
        self.combo_cd = ctk.CTkComboBox(
            row2, values=["3 giây", "5 giây", "Tắt đếm ngược"],
            width=120, height=28,
            command=self._on_cd_changed
        )
        cd_map = {3: "3 giây", 5: "5 giây", 0: "Tắt đếm ngược"}
        self.combo_cd.set(cd_map.get(self.settings.countdown_seconds, "3 giây"))
        self.combo_cd.pack(side="left")

        # Row 3: FPS & Quality
        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(row3, text="Khung hình:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))
        self.combo_fps = ctk.CTkComboBox(
            row3, values=["30 FPS (Nhẹ nhất)", "60 FPS (Mượt mà)"],
            width=140, height=28,
            command=self._on_fps_changed
        )
        self.combo_fps.set(f"{self.settings.fps} FPS ({'Nhẹ nhất' if self.settings.fps == 30 else 'Mượt mà'})")
        self.combo_fps.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row3, text="Chất lượng:", font=("Segoe UI", 12), text_color="#94a3b8").pack(side="left", padx=(0, 8))
        self.combo_quality = ctk.CTkComboBox(
            row3, values=["Standard", "High", "Ultra"],
            width=100, height=28,
            command=self._on_quality_changed
        )
        self.combo_quality.set(self.settings.quality)
        self.combo_quality.pack(side="left")

        # Row 4: Mouse Effects (Highlight Halo & Click Ripples)
        row4 = ctk.CTkFrame(card, fg_color="transparent")
        row4.pack(fill="x", padx=16, pady=6)

        self.chk_cursor = ctk.CTkCheckBox(
            row4, text="Hiện con trỏ chuột",
            command=self._on_cursor_toggled
        )
        if self.settings.record_cursor:
            self.chk_cursor.select()
        else:
            self.chk_cursor.deselect()
        self.chk_cursor.pack(side="left", padx=(0, 14))

        self.chk_halo = ctk.CTkCheckBox(
            row4, text="Vòng sáng vàng (Halo)",
            command=self._on_halo_toggled
        )
        if getattr(self.settings, "mouse_halo", True):
            self.chk_halo.select()
        else:
            self.chk_halo.deselect()
        self.chk_halo.pack(side="left", padx=(0, 14))

        self.chk_ripple = ctk.CTkCheckBox(
            row4, text="Hiệu ứng click chuột",
            command=self._on_ripple_toggled
        )
        if getattr(self.settings, "mouse_click_ripple", True):
            self.chk_ripple.select()
        else:
            self.chk_ripple.deselect()
        self.chk_ripple.pack(side="left")

        # Row 5: Pro Integration Toggles (Floating bar, Sound cues, Close to tray)
        row5 = ctk.CTkFrame(card, fg_color="transparent")
        row5.pack(fill="x", padx=16, pady=(4, 6))

        self.chk_float = ctk.CTkCheckBox(
            row5, text="Thanh nổi (Tàng hình)",
            command=self._on_float_toggled
        )
        if self.settings.show_floating_bar:
            self.chk_float.select()
        else:
            self.chk_float.deselect()
        self.chk_float.pack(side="left", padx=(0, 14))

        self.chk_sound = ctk.CTkCheckBox(
            row5, text="Âm thanh hiệu ứng",
            command=self._on_sound_toggled
        )
        if getattr(self.settings, "sound_cues", True):
            self.chk_sound.select()
        else:
            self.chk_sound.deselect()
        self.chk_sound.pack(side="left", padx=(0, 14))

        self.chk_close_tray = ctk.CTkCheckBox(
            row5, text="Đóng [X] thu xuống khay",
            command=self._on_close_tray_toggled
        )
        if getattr(self.settings, "close_to_tray", True):
            self.chk_close_tray.select()
        else:
            self.chk_close_tray.deselect()
        self.chk_close_tray.pack(side="left")

        # Hint note
        hint_lbl = ctk.CTkLabel(
            card,
            text="✨ Thanh nổi hiện trên màn hình để bạn thao tác nhưng hoàn toàn tàng hình 100% trong video clip.",
            font=("Segoe UI", 11), text_color="#0284c7", justify="left"
        )
        hint_lbl.pack(anchor="w", padx=18, pady=(0, 12))

    def _build_footer(self):
        footer = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        footer.pack(fill="x", side="bottom", padx=16, pady=12)

        ctk.CTkLabel(
            footer,
            text="⌨️ Phím tắt: F9 (Bắt đầu/Dừng)  •  F10 (Tạm dừng/Tiếp tục)",
            font=("Segoe UI", 11), text_color="#64748b"
        ).pack(side="left")

        btn_quit = ctk.CTkButton(
            footer, text="Thoát hoàn toàn", width=120, height=28,
            fg_color="#334155", hover_color="#475569",
            corner_radius=6, font=("Segoe UI", 11),
            command=self.quit_app
        )
        btn_quit.pack(side="right")

    # --- Event Handlers & State Management ---

    def _toggle_test_mic(self):
        if self.engine.state in ("recording", "paused"):
            return
        if self.engine.audio_mgr.is_testing:
            self._stop_test_mic()
        else:
            self._start_test_mic()

    def _start_test_mic(self):
        if not self.settings.record_mic:
            self.switch_mic.select()
            self._on_mic_switch_changed()

        idx = self.mic_map.get(self.combo_mic.get())
        vol = getattr(self.settings, "mic_volume", 1.0)
        live_play = bool(self.chk_live_monitor.get())

        try:
            self.engine.audio_mgr.start_test_monitor(
                mic_index=idx,
                volume=vol,
                live_playback=live_play,
                on_rms=self._on_test_rms_received
            )
            self.btn_test_mic.configure(text="⏹ Dừng Thử Mic", fg_color="#dc2626", hover_color="#b91c1c")
            self.lbl_mic_status.configure(
                text="● Đang thử mic: Hãy nói vào micro để kiểm tra sóng âm...",
                text_color="#38bdf8"
            )
        except Exception as e:
            messagebox.showwarning("Lỗi Micro", f"Không thể bật thử micro: {e}", parent=self)

    def _stop_test_mic(self):
        self.engine.audio_mgr.stop_test_monitor()
        try:
            self.btn_test_mic.configure(text="🎤 Bật Thử Mic", fg_color="#0284c7", hover_color="#0369a1")
            self.lbl_mic_status.configure(
                text="💡 Mẹo: Nhấn 'Thử Micro' để kiểm tra sóng âm và chỉnh độ to trước khi quay.",
                text_color="#64748b"
            )
            self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, 0, 12)
        except Exception:
            pass

    def _on_test_rms_received(self, rms):
        def _apply():
            if not self.winfo_exists() or not self.engine.audio_mgr.is_testing:
                return
            canvas_w = self.mic_vu_canvas.winfo_width()
            if canvas_w > 10:
                bar_w = int(max(0.0, min(1.0, rms)) * canvas_w)
                if rms < 0.70:
                    color = "#10b981"
                    status_desc = f"Tín hiệu tốt ({int(rms * 100)}%)"
                    status_col = "#34d399"
                elif rms < 0.88:
                    color = "#f59e0b"
                    status_desc = f"Âm lượng khá lớn ({int(rms * 100)}%)"
                    status_col = "#fbbf24"
                else:
                    color = "#ef4444"
                    status_desc = f"Quá to / Nguy cơ rè ({int(rms * 100)}%) - Nên giảm thanh khuếch đại"
                    status_col = "#f87171"

                if rms < 0.05:
                    status_desc = "Âm lượng nhỏ hoặc chưa nói... (Hãy nói thử vào mic)"
                    status_col = "#94a3b8"

                self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, bar_w, 12)
                self.mic_vu_canvas.itemconfig(self.mic_vu_bar, fill=color)
                self.lbl_mic_status.configure(text=f"● Đang thử mic: {status_desc}", text_color=status_col)

        self.after(0, _apply)

    def _on_live_monitor_toggled(self):
        enable = bool(self.chk_live_monitor.get())
        idx = self.mic_map.get(self.combo_mic.get())
        self.engine.audio_mgr.set_test_live_playback(enable, mic_index=idx)

    def _start_sample_test(self):
        if self.engine.state in ("recording", "paused"):
            return

        self._stop_test_mic()

        if not self.settings.record_mic:
            self.switch_mic.select()
            self._on_mic_switch_changed()

        self.btn_test_sample.configure(state="disabled", text="⏳ Đang chuẩn bị...")
        self.btn_test_mic.configure(state="disabled")

        idx = self.mic_map.get(self.combo_mic.get())
        vol = getattr(self.settings, "mic_volume", 1.0)

        def _progress(status, remaining, rms):
            self.after(0, lambda: self._on_sample_test_progress(status, remaining, rms))

        def _finish(success, message):
            self.after(0, lambda: self._on_sample_test_finish(success, message))

        self.engine.audio_mgr.test_record_and_playback_sample(
            mic_index=idx,
            volume=vol,
            duration=3.0,
            on_progress=_progress,
            on_finish=_finish
        )

    def _on_sample_test_progress(self, status, remaining, rms):
        if not self.winfo_exists():
            return
        canvas_w = self.mic_vu_canvas.winfo_width()
        if canvas_w > 10:
            bar_w = int(max(0.0, min(1.0, rms)) * canvas_w)
            color = "#10b981" if rms < 0.85 else "#ef4444"
            self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, bar_w, 12)
            self.mic_vu_canvas.itemconfig(self.mic_vu_bar, fill=color)

        if status == "recording":
            self.btn_test_sample.configure(text=f"🔴 Nói thử: {remaining:.1f}s", fg_color="#dc2626")
            self.lbl_mic_status.configure(
                text=f"🔴 Đang thu âm 3s: Hãy nói thử câu chào 'Alo 1, 2, 3' ({remaining:.1f}s còn lại)...",
                text_color="#ef4444"
            )
        elif status == "playing":
            self.btn_test_sample.configure(text=f"🔊 Phát lại: {remaining:.1f}s", fg_color="#0284c7")
            self.lbl_mic_status.configure(
                text=f"🔊 Đang phát lại qua loa ({remaining:.1f}s): Bạn hãy lắng nghe độ trong trẻo và âm lượng...",
                text_color="#38bdf8"
            )

    def _on_sample_test_finish(self, success, message):
        if not self.winfo_exists():
            return
        self.btn_test_sample.configure(state="normal", text="🎧 Ghi & Nghe lại 3s", fg_color="#334155")
        self.btn_test_mic.configure(state="normal")
        self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, 0, 12)
        if success:
            self.lbl_mic_status.configure(
                text="✅ Đã kiểm tra xong! Nếu bạn nghe giọng rõ ràng, bạn đã sẵn sàng bấm quay video.",
                text_color="#10b981"
            )
        else:
            self.lbl_mic_status.configure(
                text=f"⚠️ Thử mic không hoàn tất: {message}",
                text_color="#f59e0b"
            )

    def _on_mic_switch_changed(self):
        enabled = bool(self.switch_mic.get())
        self.settings.record_mic = enabled
        self.settings.save()
        if not enabled and self.engine.audio_mgr.is_testing:
            self._stop_test_mic()

    def _on_mic_device_changed(self, choice):
        idx = self.mic_map.get(choice)
        self.settings.mic_device_index = idx
        self.settings.save()
        if self.engine.audio_mgr.is_testing:
            self._start_test_mic()

    def _on_mic_volume_changed(self, value):
        self.settings.mic_volume = round(float(value), 2)
        self.lbl_vol_val.configure(text=f"{int(self.settings.mic_volume * 100)}%")
        self.settings.save()
        if self.engine.audio_mgr.is_testing:
            self.engine.audio_mgr.set_test_volume(self.settings.mic_volume)

    def _on_area_mode_changed(self, choice):
        if choice == "Chọn vùng quay":
            self.btn_select_region.configure(state="normal")
            self._launch_region_selector()
        else:
            self.btn_select_region.configure(state="disabled")
            self.engine.set_region(None)

    def _launch_region_selector(self):
        self.withdraw()

        def on_region_picked(region):
            self.deiconify()
            if region:
                self.engine.set_region(region)
                self.btn_select_region.configure(text=f"📐 {region[2]}x{region[3]}")
            else:
                self.seg_area.set("Toàn màn hình")
                self.btn_select_region.configure(state="disabled", text="📐 Chọn vùng...")
                self.engine.set_region(None)

        selector = RegionSelector(on_region_picked, parent=self)
        selector.start()

    def _on_res_changed(self, choice):
        preset = "Native"
        if "720p" in choice:
            preset = "720p"
        elif "1080p" in choice:
            preset = "1080p"
        self.settings.resolution_preset = preset
        self.settings.save()

    def _on_cd_changed(self, choice):
        cd = 3
        if "5" in choice:
            cd = 5
        elif "Tắt" in choice:
            cd = 0
        self.settings.countdown_seconds = cd
        self.settings.save()

    def _on_fps_changed(self, choice):
        fps = 60 if "60" in choice else 30
        self.settings.fps = fps
        self.settings.save()

    def _on_quality_changed(self, choice):
        self.settings.quality = choice
        self.settings.save()

    def _on_cursor_toggled(self):
        self.settings.record_cursor = bool(self.chk_cursor.get())
        self.settings.save()

    def _on_halo_toggled(self):
        self.settings.mouse_halo = bool(self.chk_halo.get())
        self.settings.save()

    def _on_ripple_toggled(self):
        self.settings.mouse_click_ripple = bool(self.chk_ripple.get())
        self.settings.save()

    def _on_float_toggled(self):
        self.settings.show_floating_bar = bool(self.chk_float.get())
        self.settings.save()

    def _on_sound_toggled(self):
        self.settings.sound_cues = bool(self.chk_sound.get())
        self.settings.save()

    def _on_close_tray_toggled(self):
        self.settings.close_to_tray = bool(self.chk_close_tray.get())
        self.settings.save()

    def _open_output_dir(self):
        try:
            os.startfile(self.settings.output_dir)
        except Exception:
            pass

    def open_library(self):
        if self.library_win and self.library_win.winfo_exists():
            self.library_win.lift()
            self.library_win.focus_force()
            return
        self.library_win = LibraryWindow(self, self.settings.output_dir)

    # --- Recording Control & Pulsing Glow Animation ---

    def _pulse_record_button(self):
        if not self.winfo_exists():
            return
        if self.engine.state == "recording":
            self._pulse_glow = not self._pulse_glow
            col = "#dc2626" if self._pulse_glow else "#991b1b"
            self.btn_record.configure(fg_color=col)
            self.lbl_status.configure(text_color="#ef4444" if self._pulse_glow else "#f87171")
            self.after(500, self._pulse_record_button)
        elif self.engine.state == "paused":
            self.btn_record.configure(fg_color="#b45309")
            self.lbl_status.configure(text_color="#eab308")

    def toggle_recording(self):
        if self.engine.state == "idle":
            self.start_recording()
        elif self.engine.state in ("recording", "paused"):
            self.stop_recording()

    def start_recording(self):
        self._stop_test_mic()
        self._hide_toast()
        cd = getattr(self.settings, "countdown_seconds", 3)
        if cd > 0:
            self.withdraw()
            overlay = CountdownOverlay(
                seconds=cd,
                on_finish=self._actual_start_recording,
                on_cancel=self._on_countdown_cancelled,
                parent=self
            )
            overlay.start()
        else:
            self._actual_start_recording()

    def _on_countdown_cancelled(self):
        self.fade_in()

    def _actual_start_recording(self):
        try:
            success = self.engine.start()
            if not success:
                self.fade_in()
                return
        except Exception as e:
            self.fade_in()
            messagebox.showerror("Lỗi Ghi Hình", str(e), parent=self)
            return

        if getattr(self.settings, "sound_cues", True):
            play_sound_cue("start")

        # UI state
        self.btn_record.configure(text="⏹  DỪNG GHI HÌNH (F9)", fg_color="#dc2626", hover_color="#b91c1c")
        self.btn_pause.configure(state="normal", text="⏸ Tạm Dừng (F10)")
        self.lbl_status.configure(text="● ĐANG QUAY", text_color="#ef4444")

        # Start breathing pulse glow
        self._pulse_record_button()

        # Show floating bar if enabled
        if self.settings.show_floating_bar:
            if not self.floating_bar or not self.floating_bar.winfo_exists():
                self.floating_bar = FloatingBar(
                    self,
                    on_pause=self.pause_recording,
                    on_resume=self.resume_recording,
                    on_stop=self.stop_recording,
                    on_restore=self._restore_from_floating
                )
            self.engine.set_excluded_rect_provider(self.floating_bar.get_screen_rect)
        else:
            self.engine.set_excluded_rect_provider(None)

        if self.settings.minimize_on_start:
            self.withdraw()

    def toggle_pause(self):
        if self.engine.state == "recording":
            self.pause_recording()
        elif self.engine.state == "paused":
            self.resume_recording()

    def pause_recording(self):
        if self.engine.pause():
            if getattr(self.settings, "sound_cues", True):
                play_sound_cue("pause")
            self.btn_pause.configure(text="▶ Tiếp Tục (F10)", fg_color="#0284c7", hover_color="#0369a1")
            self.lbl_status.configure(text="❚❚ TẠM DỪNG", text_color="#eab308")
            if self.floating_bar and self.floating_bar.winfo_exists():
                self.floating_bar.is_paused = True
                self.floating_bar.btn_pause.configure(text="▶", fg_color="#0284c7")

    def resume_recording(self):
        if self.engine.resume():
            if getattr(self.settings, "sound_cues", True):
                play_sound_cue("resume")
            self.btn_pause.configure(text="⏸ Tạm Dừng (F10)", fg_color="#374151", hover_color="#4b5563")
            self.lbl_status.configure(text="● ĐANG QUAY", text_color="#ef4444")
            self._pulse_record_button()
            if self.floating_bar and self.floating_bar.winfo_exists():
                self.floating_bar.is_paused = False
                self.floating_bar.btn_pause.configure(text="⏸", fg_color="#334155")

    def stop_recording(self, reason=None):
        self._stop_reason = reason
        self.engine.set_excluded_rect_provider(None)
        if getattr(self.settings, "sound_cues", True):
            play_sound_cue("stop")

        # Check if the main window was visibly open on screen
        try:
            self._main_was_visible = (self.state() != "iconic" and self.winfo_viewable())
        except Exception:
            self._main_was_visible = False

        self.lbl_status.configure(text="⏳ ĐANG XỬ LÝ & LƯU...", text_color="#38bdf8")
        self.btn_record.configure(state="disabled", text="⏳ Đang đóng gói file...")
        self.btn_pause.configure(state="disabled")

        # If main window is NOT visible and floating bar is not active, show mini notification pill
        if not self._main_was_visible and not (self.floating_bar and self.floating_bar.winfo_exists()):
            try:
                if self.pill and self.pill.winfo_exists():
                    self.pill.destroy()
                save_msg = "⚠️ Ổ đĩa đầy (<150MB)! Đang lưu..." if reason == "low_disk" else "⏳ Đang lưu bản ghi video..."
                self.pill = NotificationPill(self, text=save_msg, is_loading=True)
            except Exception:
                pass

        def _do_stop():
            try:
                final_file = self.engine.stop()
            except Exception as e:
                print(f"Error in engine.stop: {e}")
                final_file = None
            self.after(0, lambda: self._on_stop_complete(final_file))

        threading.Thread(target=_do_stop, daemon=True).start()

    def _on_stop_complete(self, final_file):
        is_low_disk = getattr(self, "_stop_reason", None) == "low_disk"
        self._stop_reason = None

        # Update main window controls quietly in background
        self.btn_record.configure(state="normal", text="🔴  BẮT ĐẦU GHI HÌNH (F9)", fg_color="#dc2626", hover_color="#b91c1c")
        self.btn_pause.configure(state="disabled", text="⏸ Tạm Dừng (F10)", fg_color="#374151")
        self.lbl_status.configure(text="● SẴN SÀNG", text_color="#10b981")
        self.lbl_timer.configure(text="00:00:00")
        self.lbl_details.configure(text="30 FPS  •  0 MB")

        # Reset VU meter
        self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, 0, 12)

        file_name = Path(final_file).name if final_file else ""
        size_mb = 0.0
        if final_file and Path(final_file).is_file():
            self.last_saved_file = Path(final_file)
            size_mb = self.last_saved_file.stat().st_size / (1024 * 1024)

            # Refresh library if open
            if self.library_win and self.library_win.winfo_exists():
                self.library_win.refresh_list()

        # Handle Floating bar: show saved confirmation and close
        if self.floating_bar and self.floating_bar.winfo_exists():
            try:
                self.floating_bar.show_saved_and_close()
            except Exception:
                pass
            self.floating_bar = None

        # User-centric behavior:
        # If the main window was already open, show in-app toast card.
        # IF IT WAS MINIMIZED / IN TRAY: NEVER POP UP THE MAIN WINDOW!
        if self._main_was_visible:
            if final_file and Path(final_file).is_file():
                toast_title = "⚠️ Ổ ĐĨA ĐẦY - ĐÃ TỰ ĐỘNG LƯU AN TOÀN!" if is_low_disk else "✅ ĐÃ LƯU VIDEO THÀNH CÔNG!"
                self.lbl_toast_title.configure(text=toast_title)
                self.lbl_toast_subtitle.configure(text=f"📁 {file_name}   •   {size_mb:.1f} MB")
                self.toast_card.pack(fill="x", padx=16, pady=4, after=self.record_card)
        else:
            # Show sleek Notification Pill at top of screen for 3.5s
            if final_file and Path(final_file).is_file():
                success_text = f"⚠️ Ổ đĩa đầy (<150MB)! Đã tự động lưu: {file_name} ({size_mb:.1f} MB)" if is_low_disk else f"✅ Đã lưu: {file_name} ({size_mb:.1f} MB)"
                if self.pill and self.pill.winfo_exists():
                    self.pill.set_success(success_text, file_path=final_file)
                else:
                    try:
                        self.pill = NotificationPill(
                            self,
                            text=success_text,
                            is_loading=False,
                            file_path=final_file
                        )
                    except Exception:
                        pass
                if is_low_disk and self.tray:
                    try:
                        self.tray.notify(
                            f"Ổ đĩa lưu trữ còn dưới 150MB. Bản ghi đã được tự động lưu an toàn:\n{file_name}",
                            "⚠️ Cảnh báo ổ đĩa đầy - Đã lưu bản ghi"
                        )
                    except Exception:
                        pass
                        pass

                # Windows System Tray Notification
                if self.tray:
                    try:
                        self.tray.notify(
                            f"File: {file_name} ({size_mb:.1f} MB)\nĐã lưu thẳng ra Desktop của bạn!",
                            "✅ Đã lưu bản ghi màn hình"
                        )
                    except Exception:
                        pass

    def _restore_from_floating(self):
        self.fade_in()

    def _on_engine_update(self, stats):
        self._latest_stats = stats
        if not self._ui_update_pending:
            self._ui_update_pending = True
            self.after(0, self._apply_ui_update)

    def _apply_ui_update(self):
        self._ui_update_pending = False
        if not self.winfo_exists() or not self._latest_stats:
            return

        stats = self._latest_stats
        if stats.get("low_disk") and self.engine.state in ("recording", "paused"):
            self.stop_recording(reason="low_disk")
            return

        elapsed = stats.get("elapsed", 0.0)
        fps = stats.get("fps", 0.0)
        size_mb = stats.get("size_bytes", 0) / (1024 * 1024)
        mic_rms = stats.get("mic_rms", 0.0)

        # Update floating bar if visible (even if main window is hidden)
        if self.floating_bar and self.floating_bar.winfo_exists():
            self.floating_bar.update_stats(elapsed, mic_rms)

        # Only touch main window widgets if the main window is actually visible!
        # Skipping canvas coords/redraws when minimized eliminates UI thread overhead completely.
        if self.state() != "iconic" and self.winfo_viewable():
            m, s = divmod(int(elapsed), 60)
            h, m = divmod(m, 60)
            self.lbl_timer.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.lbl_details.configure(text=f"{fps:.1f} FPS  •  {size_mb:.1f} MB")

            # Mic VU meter
            canvas_w = self.mic_vu_canvas.winfo_width()
            if canvas_w > 10:
                bar_w = int(max(0.0, min(1.0, mic_rms)) * canvas_w)
                color = "#10b981" if mic_rms < 0.8 else "#ef4444"
                self.mic_vu_canvas.coords(self.mic_vu_bar, 0, 0, bar_w, 12)
                self.mic_vu_canvas.itemconfig(self.mic_vu_bar, fill=color)

    # --- Hotkeys Handlers ---

    def _on_hotkey_toggle_record(self):
        self.after(0, self.toggle_recording)

    def _on_hotkey_toggle_pause(self):
        self.after(0, self.toggle_pause)

    # --- Teardown & Exit ---

    def on_close(self):
        if self.engine.state in ("recording", "paused"):
            confirm = messagebox.askyesno(
                "Đang ghi hình",
                "Quá trình ghi hình đang diễn ra. Bạn có muốn dừng và lưu lại video trước khi đóng không?",
                parent=self
            )
            if confirm:
                self.stop_recording()
                return

        # If close to tray is enabled, minimize smoothly to tray
        if getattr(self.settings, "close_to_tray", True):
            self.hide_to_tray()
        else:
            self.quit_app()

    def _poll_wakeup_event(self):
        """Restore window smoothly when user double-clicks desktop shortcut while running."""
        if hasattr(self, "_wakeup_event") and self._wakeup_event:
            try:
                if ctypes.windll.kernel32.WaitForSingleObject(self._wakeup_event, 0) == 0:
                    self.show_from_tray()
                    self.lift()
                    self.focus_force()
                    self.attributes("-topmost", True)
                    self.after(250, lambda: self.attributes("-topmost", False))
            except Exception:
                pass
        if self.winfo_exists():
            self.after(400, self._poll_wakeup_event)

    def quit_app(self):
        """Clean teardown and full exit."""
        self._stop_test_mic()
        self.hotkeys.stop()
        if self.floating_bar and self.floating_bar.winfo_exists():
            self.floating_bar.destroy()
        if self.library_win and self.library_win.winfo_exists():
            self.library_win.destroy()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        self.engine.audio_mgr.close()
        self.destroy()


def main():
    set_high_dpi_aware()
    instance = SingleInstance("Local\\ProScreenRecorder.Instance")
    if instance.already_running:
        hwnd = ctypes.windll.user32.FindWindowW(None, "Pro Screen Recorder - Ghi Màn Hình & Micro")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Thông báo", "Pro Screen Recorder đang chạy trên máy tính (hãy kiểm tra khay hệ thống cạnh đồng hồ).")
            root.destroy()
        sys.exit(0)

    app = ProScreenRecorderApp()
    app.mainloop()
    instance.close()


if __name__ == "__main__":
    main()
