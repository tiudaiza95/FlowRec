"""Recordings Library Window: View, Play, Open Folder, and Manage recordings."""
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from desktop_support import set_dark_titlebar


class LibraryWindow(ctk.CTkToplevel):
    def __init__(self, parent, output_dir):
        super().__init__(parent)
        self.transient(parent)
        self.output_dir = Path(output_dir)

        self.title("Thư Viện Video Đã Quay - Pro Screen Recorder")
        self.geometry("740x500")
        self.minsize(600, 400)
        self.configure(fg_color="#0f172a")

        icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if icon_path.is_file():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass
        set_dark_titlebar(self)

        def _on_throttle(e):
            if e.widget == self:
                time.sleep(0.012)
        self.bind("<Configure>", _on_throttle)

        # Header
        header = ctk.CTkFrame(self, fg_color="#1e293b", height=60, corner_radius=0)
        header.pack(fill="x", side="top")

        ctk.CTkLabel(
            header, text="📹 Video Đã Quay",
            font=("Segoe UI", 18, "bold"), text_color="#f8fafc"
        ).pack(side="left", padx=20, pady=15)

        btn_open_folder = ctk.CTkButton(
            header, text="📁 Mở Thư Mục", width=120, height=34,
            fg_color="#334155", hover_color="#475569",
            command=self._open_folder
        )
        btn_open_folder.pack(side="right", padx=15, pady=15)

        btn_refresh = ctk.CTkButton(
            header, text="🔄 Làm Mới", width=100, height=34,
            fg_color="#0284c7", hover_color="#0369a1",
            command=self.refresh_list
        )
        btn_refresh.pack(side="right", padx=5, pady=15)

        # Video List Scrollable Frame
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#0f172a")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=15)

        self.refresh_list()

    def refresh_list(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if not self.output_dir.is_dir():
            lbl = ctk.CTkLabel(self.scroll_frame, text="Thư mục chưa có video nào.", text_color="#94a3b8")
            lbl.pack(pady=40)
            return

        if self.output_dir.resolve() == (Path.home() / "Desktop").resolve():
            videos = sorted(
                [p for p in self.output_dir.glob("REC_*.mp4")],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
        else:
            videos = sorted(
                [p for p in self.output_dir.glob("*.mp4") if not p.name.startswith("~")],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

        if not videos:
            lbl = ctk.CTkLabel(
                self.scroll_frame,
                text="Chưa có bản ghi hình nào. Hãy nhấn Bắt đầu để quay video đầu tiên!",
                font=("Segoe UI", 14), text_color="#94a3b8"
            )
            lbl.pack(pady=60)
            return

        for video_path in videos:
            self._create_video_card(video_path)

    def _create_video_card(self, video_path: Path):
        stat = video_path.stat()
        size_mb = stat.st_size / (1024 * 1024)
        mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y  %H:%M:%S")

        card = ctk.CTkFrame(self.scroll_frame, fg_color="#1e293b", corner_radius=10, border_width=1, border_color="#334155")
        card.pack(fill="x", pady=6, padx=4)

        # Left: Icon & info
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.pack(side="left", fill="both", expand=True, padx=15, pady=12)

        name_lbl = ctk.CTkLabel(
            left_box, text=video_path.name,
            font=("Segoe UI", 14, "bold"), text_color="#38bdf8", anchor="w"
        )
        name_lbl.pack(fill="x")

        details_lbl = ctk.CTkLabel(
            left_box,
            text=f"🕒 {mtime_str}   •   💾 {size_mb:.1f} MB",
            font=("Segoe UI", 12), text_color="#94a3b8", anchor="w"
        )
        details_lbl.pack(fill="x", pady=(3, 0))

        # Right: Action Buttons
        right_box = ctk.CTkFrame(card, fg_color="transparent")
        right_box.pack(side="right", padx=12, pady=10)

        btn_play = ctk.CTkButton(
            right_box, text="▶ Xem", width=70, height=32,
            fg_color="#059669", hover_color="#047857",
            command=lambda p=video_path: self._play_video(p)
        )
        btn_play.pack(side="left", padx=4)

        btn_locate = ctk.CTkButton(
            right_box, text="📂 Vị trí", width=70, height=32,
            fg_color="#334155", hover_color="#475569",
            command=lambda p=video_path: self._locate_file(p)
        )
        btn_locate.pack(side="left", padx=4)

        btn_del = ctk.CTkButton(
            right_box, text="🗑️", width=36, height=32,
            fg_color="#ef4444", hover_color="#dc2626",
            command=lambda p=video_path: self._delete_video(p)
        )
        btn_del.pack(side="left", padx=4)

    def _play_video(self, path: Path):
        try:
            os.startfile(str(path))
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở video: {e}", parent=self)

    def _locate_file(self, path: Path):
        try:
            subprocess.run(["explorer", f"/select,{path}"])
        except Exception:
            try:
                os.startfile(str(path.parent))
            except Exception:
                pass

    def _delete_video(self, path: Path):
        confirm = messagebox.askyesno(
            "Xóa video",
            f"Bạn có chắc muốn xóa video '{path.name}' không?",
            icon="warning",
            parent=self
        )
        if confirm:
            try:
                path.unlink(missing_ok=True)
                self.refresh_list()
            except PermissionError:
                messagebox.showerror(
                    "Không thể xóa tệp",
                    f"Video '{path.name}' đang được mở bởi ứng dụng khác (trình phát video hoặc Media Player).\n\nVui lòng đóng video trước khi xóa.",
                    parent=self
                )
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xóa file: {e}", parent=self)

    def _open_folder(self):
        try:
            os.startfile(str(self.output_dir))
        except Exception:
            pass
