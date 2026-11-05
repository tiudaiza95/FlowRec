"""Global Windows Hotkey Manager using native RegisterHotKey API."""
import ctypes
from ctypes import wintypes
import threading

u32 = ctypes.windll.user32

MOD_NONE = 0x0000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

KEY_MAP = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B
}


class HotkeyManager:
    def __init__(self, on_toggle_record=None, on_toggle_pause=None, key_record="F9", key_pause="F10"):
        self.on_toggle_record = on_toggle_record
        self.on_toggle_pause = on_toggle_pause
        self.key_record = key_record.upper() if isinstance(key_record, str) else "F9"
        self.key_pause = key_pause.upper() if isinstance(key_pause, str) else "F10"
        self._thread = None
        self._thread_id = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._msg_loop, daemon=True)
        self._thread.start()

    def update_keys(self, key_record=None, key_pause=None):
        """Update hotkeys dynamically while running."""
        changed = False
        if key_record and key_record.upper() != self.key_record:
            self.key_record = key_record.upper()
            changed = True
        if key_pause and key_pause.upper() != self.key_pause:
            self.key_pause = key_pause.upper()
            changed = True
        if changed and self._running:
            self.stop()
            self.start()

    def _msg_loop(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # Dynamic hotkeys from configuration
        vk_rec = KEY_MAP.get(self.key_record, 0x78)  # F9 default
        vk_pau = KEY_MAP.get(self.key_pause, 0x79)  # F10 default
        u32.RegisterHotKey(0, 101, MOD_NOREPEAT, vk_rec)
        u32.RegisterHotKey(0, 102, MOD_NOREPEAT, vk_pau)

        msg = wintypes.MSG()
        while self._running:
            res = u32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if res <= 0:
                break
            if msg.message == WM_HOTKEY:
                hk_id = msg.wParam
                if hk_id == 101 and self.on_toggle_record:
                    try:
                        self.on_toggle_record()
                    except Exception:
                        pass
                elif hk_id == 102 and self.on_toggle_pause:
                    try:
                        self.on_toggle_pause()
                    except Exception:
                        pass
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

        u32.UnregisterHotKey(0, 101)
        u32.UnregisterHotKey(0, 102)

    def stop(self):
        self._running = False
        if self._thread_id:
            u32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
