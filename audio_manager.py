"""Audio Manager: Device enumeration, live microphone recording, and VU meter."""
import math
import struct
import threading
import time
import wave
from pathlib import Path
import numpy as np
import pyaudiowpatch as pyaudio


class AudioManager:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.recording = False
        self.paused = False
        self._thread = None
        self._stop_event = threading.Event()
        self.current_rms = 0.0  # Normalized 0.0 - 1.0 for UI VU meter
        self.frames = []
        self.sample_rate = 44100
        self.channels = 1
        self.stream = None

        # Live microphone test & monitor state
        self.is_testing = False
        self.is_sample_testing = False
        self._test_thread = None
        self._test_stop_event = threading.Event()
        self._test_stream = None
        self._test_out_stream = None
        self.test_volume = 1.0
        self.test_live_playback = False
        self.test_rms = 0.0

    def list_microphones(self):
        devices = []
        try:
            count = self.pa.get_device_count()
            for i in range(count):
                info = self.pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and not info.get("isLoopbackDevice", False):
                    devices.append({
                        "index": i,
                        "name": info.get("name", f"Microphone {i}"),
                        "channels": min(2, info.get("maxInputChannels", 1)),
                        "default_rate": int(info.get("defaultSampleRate", 44100))
                    })
        except Exception:
            pass
        return devices

    def list_speakers(self):
        devices = []
        try:
            for loopback in self.pa.get_loopback_device_info_generator():
                devices.append({
                    "index": loopback["index"],
                    "name": loopback["name"],
                    "channels": loopback["maxInputChannels"],
                    "default_rate": int(loopback["defaultSampleRate"])
                })
        except Exception:
            pass
        return devices

    def start_recording(self, mic_index=None, sample_rate=44100, volume=1.0):
        self.stop_test_monitor()
        self.frames = []
        self.current_rms = 0.0
        self.paused = False
        self.volume = volume
        self._stop_event.clear()

        try:
            if mic_index is None:
                default_info = self.pa.get_default_input_device_info()
                mic_index = default_info["index"]
                self.sample_rate = int(default_info.get("defaultSampleRate", sample_rate))
                self.channels = min(2, default_info.get("maxInputChannels", 1))
            else:
                info = self.pa.get_device_info_by_index(mic_index)
                self.sample_rate = int(info.get("defaultSampleRate", sample_rate))
                self.channels = min(2, info.get("maxInputChannels", 1))

            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=mic_index,
                frames_per_buffer=1024
            )
        except Exception as e:
            self.stream = None
            raise RuntimeError(f"Cannot initialize microphone: {e}")

        self.recording = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def _record_loop(self):
        chunk_count = 0
        vol = getattr(self, "volume", 1.0)
        has_custom_vol = vol != 1.0

        while not self._stop_event.is_set():
            if self.paused:
                self.current_rms = 0.0
                time.sleep(0.05)
                continue
            try:
                data = self.stream.read(1024, exception_on_overflow=False)
                if has_custom_vol:
                    try:
                        arr = np.frombuffer(data, dtype=np.int16)
                        data = np.clip(arr * vol, -32768, 32767).astype(np.int16).tobytes()
                    except Exception:
                        pass
                self.frames.append(data)

                # Vectorized RMS calculated once every 4 chunks (~10 Hz) to eliminate CPU overhead
                chunk_count += 1
                if chunk_count % 4 == 0:
                    self._calculate_rms_fast(data)
            except Exception:
                break
        self.current_rms = 0.0

    def _calculate_rms(self, data):
        """Public/test-compatible RMS calculation."""
        self._calculate_rms_fast(data)

    def _calculate_rms_fast(self, data):
        try:
            if not data:
                self.current_rms = 0.0
                return
            arr = np.frombuffer(data, dtype=np.int16)
            if len(arr) == 0:
                self.current_rms = 0.0
                return
            mean_sq = float(np.mean(arr.astype(np.float32) ** 2))
            rms = math.sqrt(mean_sq)
            if rms > 10.0:
                norm = min(1.0, math.log10(rms) / 4.2)
                self.current_rms = max(0.0, norm)
            else:
                self.current_rms = 0.0
        except Exception:
            self.current_rms = 0.0

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop_and_save(self, wav_path):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        self.recording = False
        self.paused = False
        self.current_rms = 0.0

        if not self.frames:
            return False

        try:
            wf = wave.open(str(wav_path), "wb")
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # paInt16
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(self.frames))
            wf.close()
            return True
        except Exception:
            return False

    # --- Live Microphone Test & Monitor Features ---

    def start_test_monitor(self, mic_index=None, volume=1.0, live_playback=False, on_rms=None):
        """Starts live, non-recording mic monitor to visualize audio levels & test sound."""
        if self.recording:
            return False

        self.stop_test_monitor()
        self.test_volume = volume
        self.test_live_playback = live_playback
        self._test_stop_event.clear()

        try:
            if mic_index is None:
                default_info = self.pa.get_default_input_device_info()
                dev_idx = default_info["index"]
                rate = int(default_info.get("defaultSampleRate", 44100))
                channels = min(2, default_info.get("maxInputChannels", 1))
            else:
                info = self.pa.get_device_info_by_index(mic_index)
                dev_idx = mic_index
                rate = int(info.get("defaultSampleRate", 44100))
                channels = min(2, info.get("maxInputChannels", 1))

            self._test_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev_idx,
                frames_per_buffer=1024
            )

            if live_playback:
                try:
                    self._test_out_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        output=True
                    )
                except Exception:
                    self._test_out_stream = None
            else:
                self._test_out_stream = None

        except Exception as e:
            self._cleanup_test_streams()
            raise RuntimeError(f"Không thể khởi động kiểm tra Micro: {e}")

        self.is_testing = True
        self._test_thread = threading.Thread(
            target=self._test_monitor_loop,
            args=(on_rms, channels, rate),
            daemon=True
        )
        self._test_thread.start()
        return True

    def _test_monitor_loop(self, on_rms, channels, rate):
        """Continuously reads audio, calculates RMS and optionally mirrors to speakers."""
        while not self._test_stop_event.is_set():
            try:
                if not self._test_stream:
                    break
                data = self._test_stream.read(1024, exception_on_overflow=False)
                vol = getattr(self, "test_volume", 1.0)
                if vol != 1.0:
                    try:
                        arr = np.frombuffer(data, dtype=np.int16)
                        data = np.clip(arr * vol, -32768, 32767).astype(np.int16).tobytes()
                    except Exception:
                        pass

                arr = np.frombuffer(data, dtype=np.int16)
                if len(arr) > 0:
                    mean_sq = float(np.mean(arr.astype(np.float32) ** 2))
                    rms = math.sqrt(mean_sq)
                    norm = min(1.0, math.log10(rms) / 4.2) if rms > 10.0 else 0.0
                else:
                    norm = 0.0

                self.test_rms = norm
                if on_rms:
                    on_rms(norm)

                if self.test_live_playback and self._test_out_stream:
                    try:
                        self._test_out_stream.write(data)
                    except Exception:
                        pass
            except Exception:
                break

        self.test_rms = 0.0
        if on_rms:
            on_rms(0.0)

    def set_test_volume(self, volume: float):
        """Live updates volume gain for test monitor."""
        self.test_volume = max(0.1, float(volume))

    def set_test_live_playback(self, enable: bool, mic_index=None):
        """Dynamically enables or disables live playback to speakers."""
        self.test_live_playback = bool(enable)
        if not self.is_testing:
            return

        if self.test_live_playback:
            if not self._test_out_stream:
                try:
                    if mic_index is None:
                        info = self.pa.get_default_input_device_info()
                    else:
                        info = self.pa.get_device_info_by_index(mic_index)
                    rate = int(info.get("defaultSampleRate", 44100))
                    channels = min(2, info.get("maxInputChannels", 1))
                    self._test_out_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        output=True
                    )
                except Exception:
                    self._test_out_stream = None
        else:
            if self._test_out_stream:
                try:
                    self._test_out_stream.stop_stream()
                    self._test_out_stream.close()
                except Exception:
                    pass
                self._test_out_stream = None

    def stop_test_monitor(self):
        """Safely stops live test monitor and releases audio device."""
        self._test_stop_event.set()
        if self._test_thread:
            self._test_thread.join(timeout=1.0)
            self._test_thread = None
        self._cleanup_test_streams()
        self.is_testing = False
        self.is_sample_testing = False
        self.test_rms = 0.0

    def _cleanup_test_streams(self):
        if self._test_stream:
            try:
                self._test_stream.stop_stream()
                self._test_stream.close()
            except Exception:
                pass
            self._test_stream = None
        if self._test_out_stream:
            try:
                self._test_out_stream.stop_stream()
                self._test_out_stream.close()
            except Exception:
                pass
            self._test_out_stream = None

    def test_record_and_playback_sample(self, mic_index=None, volume=1.0, duration=3.0, on_progress=None, on_finish=None):
        """Records a 3-second audio sample, then plays it back immediately through speakers.
        Provides a realistic, echo-free test of speech clarity and volume level.
        """
        if self.recording:
            return False

        self.stop_test_monitor()
        self._test_stop_event.clear()
        self.is_sample_testing = True

        def _worker():
            frames = []
            in_stream = None
            out_stream = None
            try:
                if mic_index is None:
                    default_info = self.pa.get_default_input_device_info()
                    dev_idx = default_info["index"]
                    rate = int(default_info.get("defaultSampleRate", 44100))
                    channels = min(2, default_info.get("maxInputChannels", 1))
                else:
                    info = self.pa.get_device_info_by_index(mic_index)
                    dev_idx = mic_index
                    rate = int(info.get("defaultSampleRate", 44100))
                    channels = min(2, info.get("maxInputChannels", 1))

                # Phase 1: Record 3 seconds
                in_stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=rate,
                    input=True,
                    input_device_index=dev_idx,
                    frames_per_buffer=1024
                )
                start_t = time.perf_counter()
                while not self._test_stop_event.is_set():
                    elapsed = time.perf_counter() - start_t
                    if elapsed >= duration:
                        break
                    data = in_stream.read(1024, exception_on_overflow=False)
                    if volume != 1.0:
                        try:
                            arr = np.frombuffer(data, dtype=np.int16)
                            data = np.clip(arr * volume, -32768, 32767).astype(np.int16).tobytes()
                        except Exception:
                            pass
                    frames.append(data)

                    # Calculate live RMS for meter
                    arr = np.frombuffer(data, dtype=np.int16)
                    mean_sq = float(np.mean(arr.astype(np.float32) ** 2)) if len(arr) > 0 else 0.0
                    rms = math.sqrt(mean_sq)
                    norm = min(1.0, math.log10(rms) / 4.2) if rms > 10.0 else 0.0
                    self.test_rms = norm

                    if on_progress:
                        remaining = max(0.0, duration - elapsed)
                        on_progress("recording", remaining, norm)

                in_stream.stop_stream()
                in_stream.close()
                in_stream = None

                if self._test_stop_event.is_set() or not frames:
                    self.is_sample_testing = False
                    if on_finish:
                        try:
                            on_finish(False, "Đã hủy")
                        except Exception:
                            pass
                    return

                # Phase 2: Playback sample
                out_stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=rate,
                    output=True
                )
                total_frames = len(frames)
                for idx, chunk in enumerate(frames):
                    if self._test_stop_event.is_set():
                        break
                    out_stream.write(chunk)
                    if on_progress and idx % 4 == 0:
                        arr = np.frombuffer(chunk, dtype=np.int16)
                        mean_sq = float(np.mean(arr.astype(np.float32) ** 2)) if len(arr) > 0 else 0.0
                        rms = math.sqrt(mean_sq)
                        norm = min(1.0, math.log10(rms) / 4.2) if rms > 10.0 else 0.0
                        self.test_rms = norm
                        remaining = max(0.0, (total_frames - idx) * 1024 / rate)
                        try:
                            on_progress("playing", remaining, norm)
                        except Exception:
                            pass

                out_stream.stop_stream()
                out_stream.close()
                out_stream = None

                self.is_sample_testing = False
                self.test_rms = 0.0
                if on_finish:
                    try:
                        on_finish(True, "Kiểm tra hoàn tất")
                    except Exception:
                        pass

            except Exception as e:
                if in_stream:
                    try:
                        in_stream.stop_stream()
                        in_stream.close()
                    except Exception:
                        pass
                if out_stream:
                    try:
                        out_stream.stop_stream()
                        out_stream.close()
                    except Exception:
                        pass
                self.is_sample_testing = False
                self.test_rms = 0.0
                if on_finish:
                    try:
                        on_finish(False, str(e))
                    except Exception:
                        pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True

    def close(self):
        self.stop_test_monitor()
        if self.recording:
            self.stop_and_save(Path.home() / "temp_abort.wav")
        try:
            self.pa.terminate()
        except Exception:
            pass
