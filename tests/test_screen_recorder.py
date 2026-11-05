"""Unit tests for Pro Screen Recorder."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import Settings
from recorder_engine import find_ffmpeg, detect_best_encoder, RecorderEngine
from audio_manager import AudioManager
from desktop_support import (
    SingleInstance, exclude_from_capture,
    create_wakeup_event, signal_existing_instance
)
from hotkey_manager import HotkeyManager, KEY_MAP


class TestSettings(unittest.TestCase):
    def test_default_values(self):
        s = Settings()
        self.assertIn(s.fps, (30, 60))
        self.assertEqual(s.get_bitrate(), "6M")
        self.assertTrue(s.record_cursor)
        self.assertTrue(s.record_mic)

    def test_bitrate_mapping(self):
        s = Settings()
        s.quality = "Standard"
        self.assertEqual(s.get_bitrate(), "3M")
        s.quality = "Ultra"
        self.assertEqual(s.get_bitrate(), "12M")


class TestFFmpegDetection(unittest.TestCase):
    def test_find_ffmpeg(self):
        path = find_ffmpeg()
        self.assertTrue(len(path) > 0)

    def test_detect_best_encoder(self):
        path = find_ffmpeg()
        enc = detect_best_encoder(path)
        self.assertIn(enc, ("h264_mf", "libx264"))


class TestAudioManager(unittest.TestCase):
    def test_device_enumeration(self):
        mgr = AudioManager()
        try:
            mics = mgr.list_microphones()
            self.assertIsInstance(mics, list)
            # Should have at least one mic on this machine (Microphone 2- ME6S)
            self.assertGreater(len(mics), 0)
        finally:
            mgr.close()

    def test_rms_calculation(self):
        mgr = AudioManager()
        try:
            # Silence
            silence = b"\x00" * 2048
            mgr._calculate_rms(silence)
            self.assertEqual(mgr.current_rms, 0.0)

            # Loud tone (full amplitude)
            import struct
            loud_samples = [30000 if i % 2 == 0 else -30000 for i in range(1024)]
            loud_bytes = struct.pack(f"{len(loud_samples)}h", *loud_samples)
            mgr._calculate_rms(loud_bytes)
            self.assertGreater(mgr.current_rms, 0.5)
        finally:
            mgr.close()

    def test_mic_test_monitor(self):
        import time
        mgr = AudioManager()
        try:
            rms_vals = []
            ok = mgr.start_test_monitor(volume=1.5, on_rms=lambda r: rms_vals.append(r))
            self.assertTrue(ok)
            self.assertTrue(mgr.is_testing)
            mgr.set_test_volume(1.8)
            self.assertEqual(mgr.test_volume, 1.8)
            time.sleep(0.2)
            mgr.stop_test_monitor()
            self.assertFalse(mgr.is_testing)
        finally:
            mgr.close()

    def test_mic_sample_test(self):
        import time
        mgr = AudioManager()
        try:
            done = [False]
            def on_finish(ok, msg):
                done[0] = True
            ok = mgr.test_record_and_playback_sample(duration=0.3, on_finish=on_finish)
            self.assertTrue(ok)
            t0 = time.time()
            while not done[0] and time.time() - t0 < 3.0:
                time.sleep(0.05)
            self.assertTrue(done[0])
        finally:
            mgr.close()


class TestRecorderEngine(unittest.TestCase):
    def test_region_formatting(self):
        s = Settings()
        engine = RecorderEngine(s)
        try:
            # Odd dimensions must be rounded to even
            engine.set_region((10, 20, 1001, 799))
            self.assertEqual(engine.capture_region, (10, 20, 1000, 798))

            engine.set_region(None)
            self.assertIsNone(engine.capture_region)
        finally:
            engine.audio_mgr.close()

    def test_state_flow(self):
        s = Settings()
        engine = RecorderEngine(s)
        try:
            self.assertEqual(engine.state, "idle")
            # Should return False if not recording
            self.assertFalse(engine.pause())
            self.assertFalse(engine.resume())
            self.assertIsNone(engine.stop())
        finally:
            engine.audio_mgr.close()

    def test_live_recording_cycle(self):
        import time
        s = Settings()
        s.record_mic = False
        s.fps = 30
        engine = RecorderEngine(s)
        # Small region for fast unit test
        engine.set_region((0, 0, 320, 240))
        try:
            ok = engine.start()
            self.assertTrue(ok)
            self.assertEqual(engine.state, "recording")
            time.sleep(0.3)
            self.assertTrue(engine.pause())
            self.assertEqual(engine.state, "paused")
            time.sleep(0.1)
            self.assertTrue(engine.resume())
            self.assertEqual(engine.state, "recording")
            time.sleep(0.2)
            out = engine.stop()
            self.assertIsNotNone(out)
            self.assertTrue(Path(out).is_file())
            Path(out).unlink(missing_ok=True)
        finally:
            engine.audio_mgr.close()


    def test_recover_orphaned_recordings(self):
        import tempfile, time
        with tempfile.TemporaryDirectory() as td:
            s = Settings()
            s.output_dir = td
            engine = RecorderEngine(s)
            temp_v = Path(td) / "~temp_v_20261105_120000.mp4"
            temp_v.write_bytes(b"\x00" * 100)
            os.utime(str(temp_v), (time.time() - 30, time.time() - 30))
            recovered = engine.recover_orphaned_recordings()
            self.assertEqual(len(recovered), 1)
            self.assertTrue(Path(td, "REC_20261105_120000.mp4").is_file())
            self.assertFalse(temp_v.exists())


class TestSingleInstance(unittest.TestCase):
    def test_single_instance(self):
        lock1 = SingleInstance("Local\\TestMutexUnique.Instance")
        self.assertFalse(lock1.already_running)
        lock2 = SingleInstance("Local\\TestMutexUnique.Instance")
        self.assertTrue(lock2.already_running)
        lock2.close()
        lock1.close()

    def test_exclude_from_capture_safe(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            res = exclude_from_capture(root)
            self.assertIsInstance(res, bool)
        finally:
            root.destroy()

    def test_wakeup_signaling(self):
        import ctypes
        k32 = ctypes.windll.kernel32
        event_name = "Local\\TestWakeupEventUnique"
        h_ev = create_wakeup_event(event_name)
        self.assertIsNotNone(h_ev)
        self.assertNotEqual(h_ev, 0)
        try:
            # Initially not signaled
            self.assertEqual(k32.WaitForSingleObject(h_ev, 0), 258)  # WAIT_TIMEOUT
            # Signal from another "process"
            ok = signal_existing_instance(event_name)
            self.assertTrue(ok)
            # Now signaled
            self.assertEqual(k32.WaitForSingleObject(h_ev, 0), 0)    # WAIT_OBJECT_0
        finally:
            k32.CloseHandle(h_ev)


class TestHotkeyManager(unittest.TestCase):
    def test_hotkey_manager_config(self):
        hm = HotkeyManager(key_record="F7", key_pause="F8")
        self.assertEqual(hm.key_record, "F7")
        self.assertEqual(hm.key_pause, "F8")
        self.assertEqual(KEY_MAP.get(hm.key_record), 0x76)
        self.assertEqual(KEY_MAP.get(hm.key_pause), 0x77)
        hm.update_keys(key_record="f9", key_pause="f10")
        self.assertEqual(hm.key_record, "F9")
        self.assertEqual(hm.key_pause, "F10")


if __name__ == "__main__":
    unittest.main()
