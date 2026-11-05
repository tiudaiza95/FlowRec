"""Settings manager for FlowRec."""
import json
import os
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path.home() / "Desktop"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlowRec"
CONFIG_FILE = CONFIG_DIR / "config.json"
OLD_CONFIG_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ProScreenRecorder" / "config.json"


class Settings:
    def __init__(self):
        self.output_dir = str(DEFAULT_OUTPUT_DIR)
        self.fps = 30
        self.quality = "High"  # Standard (3 Mbps), High (6 Mbps), Ultra (12 Mbps)
        self.encoder = "auto"   # auto, h264_mf, libx264
        self.record_cursor = True
        self.mouse_halo = True           # Golden highlight halo around mouse
        self.mouse_click_ripple = True   # Animated ripple on left/right click
        self.countdown_seconds = 3       # 3, 5, or 0 (off)
        self.mic_volume = 1.0            # 1.0 = 100%, up to 2.0 = 200% boost
        self.resolution_preset = "Native" # Native, 1080p, 720p
        self.record_mic = True
        self.mic_device_index = None
        self.record_speaker = False
        self.speaker_device_index = None
        self.hotkey_start_stop = "F9"
        self.hotkey_pause_resume = "F10"
        self.minimize_on_start = True
        self.show_floating_bar = True
        self.sound_cues = True           # Subtle audio cues on record/stop/tray
        self.close_to_tray = True        # Closing [X] minimizes to tray
        self.load()

    def get_bitrate(self):
        rates = {"Standard": "3M", "High": "6M", "Ultra": "12M"}
        return rates.get(self.quality, "6M")

    def load(self):
        try:
            cfg_target = CONFIG_FILE if CONFIG_FILE.is_file() else (OLD_CONFIG_FILE if OLD_CONFIG_FILE.is_file() else None)
            if cfg_target and cfg_target.is_file():
                data = json.loads(cfg_target.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
        except Exception:
            pass

        old_default = Path.home() / "Videos" / "ProScreenRecorder"
        if self.output_dir == str(old_default) or "ProScreenRecorder" in self.output_dir:
            self.output_dir = str(DEFAULT_OUTPUT_DIR)

        # Ensure output directory exists
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            self.output_dir = str(DEFAULT_OUTPUT_DIR)
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def save(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "output_dir": self.output_dir,
                "fps": self.fps,
                "quality": self.quality,
                "encoder": self.encoder,
                "record_cursor": self.record_cursor,
                "mouse_halo": self.mouse_halo,
                "mouse_click_ripple": self.mouse_click_ripple,
                "countdown_seconds": self.countdown_seconds,
                "mic_volume": self.mic_volume,
                "resolution_preset": self.resolution_preset,
                "record_mic": self.record_mic,
                "mic_device_index": self.mic_device_index,
                "record_speaker": self.record_speaker,
                "speaker_device_index": self.speaker_device_index,
                "hotkey_start_stop": self.hotkey_start_stop,
                "hotkey_pause_resume": self.hotkey_pause_resume,
                "minimize_on_start": self.minimize_on_start,
                "show_floating_bar": self.show_floating_bar,
                "sound_cues": self.sound_cues,
                "close_to_tray": self.close_to_tray,
            }
            CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
