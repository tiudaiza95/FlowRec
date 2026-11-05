"""Windows desktop integration: Single instance mutex, high DPI, and system tray."""
import ctypes
from pathlib import Path
from PIL import Image
import pystray


def set_high_dpi_aware():
    """Enable clean, stable System High-DPI awareness on Windows without DWM drag stutter."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class SingleInstance:
    """Ensures only one instance of the application runs at any time."""

    def __init__(self, app_id="Local\\ProScreenRecorder.Instance"):
        self.app_id = app_id
        self.mutex = None
        self.already_running = False

        self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, self.app_id)
        last_error = ctypes.windll.kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if last_error == ERROR_ALREADY_EXISTS:
            self.already_running = True

    def close(self):
        if self.mutex:
            ctypes.windll.kernel32.CloseHandle(self.mutex)
            self.mutex = None


def create_wakeup_event(event_name="Local\\ProScreenRecorder.Wakeup"):
    """Create a Windows named event for restoring a backgrounded instance."""
    return ctypes.windll.kernel32.CreateEventW(None, False, False, event_name)


def signal_existing_instance(event_name="Local\\ProScreenRecorder.Wakeup"):
    """Signal the running instance to wake up and restore its window."""
    EVENT_MODIFY_STATE = 0x0002
    h_event = ctypes.windll.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, event_name)
    if h_event:
        ctypes.windll.kernel32.SetEvent(h_event)
        ctypes.windll.kernel32.CloseHandle(h_event)
        return True
    return False


def set_dark_titlebar(window):
    """Enable Windows 10/11 native dark mode for title bar."""
    try:
        window.update_idletasks()
        hwnd_client = window.winfo_id()
        top_hwnd = ctypes.windll.user32.GetAncestor(hwnd_client, 2) or hwnd_client
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(top_hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def play_sound_cue(cue_type="start"):
    """Play subtle professional audio cues for recording events."""
    import threading
    def _run():
        try:
            import winsound
            if cue_type == "start":
                winsound.Beep(988, 70)
                winsound.Beep(1318, 110)
            elif cue_type == "stop":
                winsound.Beep(1175, 70)
                winsound.Beep(659, 120)
            elif cue_type == "pause":
                winsound.Beep(880, 80)
            elif cue_type == "resume":
                winsound.Beep(1046, 80)
            elif cue_type == "tray":
                winsound.Beep(1046, 50)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def create_tray(icon_path: Path, on_open, on_toggle_record, on_toggle_pause, on_open_library, on_open_desktop, on_quit):
    """Creates a system tray icon with rich menu options."""
    try:
        img = Image.open(icon_path)
    except Exception:
        img = Image.new("RGBA", (32, 32), (239, 68, 68, 255))

    menu = pystray.Menu(
        pystray.MenuItem("🎥 Mở giao diện", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔴 Bắt đầu / Dừng quay (F9)", on_toggle_record),
        pystray.MenuItem("⏸ Tạm dừng / Tiếp tục (F10)", on_toggle_pause),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📹 Thư viện video", on_open_library),
        pystray.MenuItem("📁 Mở Desktop", on_open_desktop),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Thoát hoàn toàn", on_quit)
    )

    tray = pystray.Icon("ProScreenRecorder", img, "Pro Screen Recorder", menu)
    return tray


WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_from_capture(window):
    """
    Exclude a Tkinter / CustomTkinter window from Windows screen capture.
    The window remains visible and interactive to the user on screen,
    but is 100% invisible in the recorded video.
    """
    try:
        window.update_idletasks()
        hwnd_client = window.winfo_id()
        GA_ROOT = 2
        hwnd_top = ctypes.windll.user32.GetAncestor(hwnd_client, GA_ROOT)
        if not hwnd_top:
            hwnd_top = hwnd_client
        res = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd_top, WDA_EXCLUDEFROMCAPTURE)
        return bool(res)
    except Exception:
        return False

