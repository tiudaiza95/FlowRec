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
        self.sample_rate = 48000
        self.channels = 2
        self.stream = None
        self.mic_stream = None
        self.spk_stream = None
        self.mic_channels = 1
        self.spk_channels = 2
        self.mic_rate = 48000
        self.spk_rate = 48000
        self.master_clock = None
        self.ready_event = None
        self.total_samples_recorded = 0

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

    def start_recording(
        self,
        mic_index=None,
        sample_rate=48000,
        volume=1.0,
        mic_volume=None,
        record_mic=True,
        record_speaker=False,
        speaker_index=None,
        master_clock=None,
        ready_event=None
    ):
        if mic_volume is not None:
            volume = mic_volume
        self.stop_test_monitor()
        self.frames = []
        self.current_rms = 0.0
        self.paused = False
        self.volume = volume
        self._stop_event.clear()
        self.sample_rate = sample_rate
        self.channels = 2
        self.master_clock = master_clock
        self.ready_event = ready_event
        self.total_samples_recorded = 0
        self.mic_stream = None
        self.spk_stream = None
        self.stream = None

        opened_any = False

        if record_mic:
            try:
                if mic_index is None:
                    default_info = self.pa.get_default_input_device_info()
                    mic_idx = default_info["index"]
                    def_rate = int(default_info.get("defaultSampleRate", sample_rate))
                    max_ch = min(2, default_info.get("maxInputChannels", 1))
                else:
                    try:
                        info = self.pa.get_device_info_by_index(mic_index)
                        mic_idx = mic_index
                        def_rate = int(info.get("defaultSampleRate", sample_rate))
                        max_ch = min(2, info.get("maxInputChannels", 1))
                    except Exception:
                        default_info = self.pa.get_default_input_device_info()
                        mic_idx = default_info["index"]
                        def_rate = int(default_info.get("defaultSampleRate", sample_rate))
                        max_ch = min(2, default_info.get("maxInputChannels", 1))

                try:
                    self.mic_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=max_ch,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=mic_idx,
                        frames_per_buffer=1024
                    )
                    self.mic_rate = self.sample_rate
                    self.mic_channels = max_ch
                except Exception:
                    self.mic_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=max_ch,
                        rate=def_rate,
                        input=True,
                        input_device_index=mic_idx,
                        frames_per_buffer=1024
                    )
                    self.mic_rate = def_rate
                    self.mic_channels = max_ch

                self.stream = self.mic_stream
                opened_any = True
            except Exception as e:
                print(f"Warning: Failed to initialize microphone: {e}")
                self.mic_stream = None

        if record_speaker:
            try:
                if speaker_index is None:
                    spk_info = self.pa.get_default_wasapi_loopback()
                    spk_idx = spk_info["index"]
                    spk_ch = int(spk_info.get("maxInputChannels", 2))
                    spk_def_rate = int(spk_info.get("defaultSampleRate", sample_rate))
                else:
                    try:
                        spk_info = self.pa.get_device_info_by_index(speaker_index)
                        spk_idx = speaker_index
                        spk_ch = int(spk_info.get("maxInputChannels", 2))
                        spk_def_rate = int(spk_info.get("defaultSampleRate", sample_rate))
                    except Exception:
                        spk_info = self.pa.get_default_wasapi_loopback()
                        spk_idx = spk_info["index"]
                        spk_ch = int(spk_info.get("maxInputChannels", 2))
                        spk_def_rate = int(spk_info.get("defaultSampleRate", sample_rate))

                try:
                    self.spk_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=spk_ch,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=spk_idx,
                        frames_per_buffer=1024
                    )
                    self.spk_rate = self.sample_rate
                    self.spk_channels = spk_ch
                except Exception:
                    self.spk_stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=spk_ch,
                        rate=spk_def_rate,
                        input=True,
                        input_device_index=spk_idx,
                        frames_per_buffer=1024
                    )
                    self.spk_rate = spk_def_rate
                    self.spk_channels = spk_ch

                if not self.stream:
                    self.stream = self.spk_stream
                opened_any = True
            except Exception as e:
                print(f"Warning: Failed to initialize speaker loopback: {e}")
                self.spk_stream = None

        if not opened_any:
            raise RuntimeError("Cannot initialize any audio recording device (Mic or Speaker).")

        self.recording = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        return True

    def _record_loop(self):
        if self.ready_event:
            self.ready_event.wait()

        mic_buf = bytearray()
        spk_buf = bytearray()
        total_audio_samples = 0
        RATE = self.sample_rate
        BYTES_PER_STEREO_SAMPLE = 4
        vol = getattr(self, "volume", 1.0)

        def process_raw_chunk(raw, in_channels, in_rate, volume_boost=1.0):
            if not raw:
                return None
            # Ensure byte count aligns to full frame boundaries
            frame_align = in_channels * 2
            remainder = len(raw) % frame_align
            if remainder > 0:
                raw = raw[:-remainder]
            if not raw:
                return None
            arr = np.frombuffer(raw, dtype=np.int16)
            if in_channels == 1:
                arr = np.column_stack((arr, arr))
            else:
                arr = arr.reshape(-1, in_channels)[:, :2]

            if in_rate != RATE and len(arr) > 1:
                target_len = int(round(len(arr) * RATE / in_rate))
                orig_idx = np.linspace(0, len(arr) - 1, len(arr))
                new_idx = np.linspace(0, len(arr) - 1, target_len)
                res = np.empty((target_len, 2), dtype=np.int16)
                res[:, 0] = np.interp(new_idx, orig_idx, arr[:, 0]).astype(np.int16)
                res[:, 1] = np.interp(new_idx, orig_idx, arr[:, 1]).astype(np.int16)
                arr = res

            if volume_boost != 1.0:
                arr = np.clip(arr.astype(np.float32) * volume_boost, -32768, 32767).astype(np.int16)
            return arr

        while not self._stop_event.is_set():
            if self.paused:
                self.current_rms = 0.0
                # Drain hardware streams to prevent buffer overrun and stale audio leak during pause
                if self.mic_stream:
                    try:
                        avail = self.mic_stream.get_read_available()
                        if avail > 0:
                            self.mic_stream.read(avail, exception_on_overflow=False)
                    except Exception:
                        pass
                if self.spk_stream:
                    try:
                        avail = self.spk_stream.get_read_available()
                        if avail > 0:
                            self.spk_stream.read(avail, exception_on_overflow=False)
                    except Exception:
                        pass
                mic_buf.clear()
                spk_buf.clear()
                time.sleep(0.02)
                continue

            if self.mic_stream:
                try:
                    avail = self.mic_stream.get_read_available()
                    if avail > 0:
                        raw = self.mic_stream.read(avail, exception_on_overflow=False)
                        arr = process_raw_chunk(raw, self.mic_channels, self.mic_rate, vol)
                        if arr is not None and len(arr) > 0:
                            mic_buf.extend(arr.tobytes())
                except Exception:
                    pass

            if self.spk_stream:
                try:
                    avail = self.spk_stream.get_read_available()
                    if avail > 0:
                        raw = self.spk_stream.read(avail, exception_on_overflow=False)
                        arr = process_raw_chunk(raw, self.spk_channels, self.spk_rate, 1.0)
                        if arr is not None and len(arr) > 0:
                            spk_buf.extend(arr.tobytes())
                except Exception:
                    pass

            if self.master_clock:
                elapsed = self.master_clock.now()
                target_samples = int(round(elapsed * RATE))
            else:
                target_samples = total_audio_samples + 480

            needed_samples = target_samples - total_audio_samples
            if needed_samples >= 480:
                bytes_needed = needed_samples * BYTES_PER_STEREO_SAMPLE

                if self.mic_stream:
                    if len(mic_buf) >= bytes_needed:
                        m_chunk = bytes(mic_buf[:bytes_needed])
                        del mic_buf[:bytes_needed]
                    else:
                        m_chunk = bytes(mic_buf) + (b"\x00" * (bytes_needed - len(mic_buf)))
                        mic_buf.clear()
                else:
                    m_chunk = None

                if self.spk_stream:
                    if len(spk_buf) >= bytes_needed:
                        s_chunk = bytes(spk_buf[:bytes_needed])
                        del spk_buf[:bytes_needed]
                    else:
                        s_chunk = bytes(spk_buf) + (b"\x00" * (bytes_needed - len(spk_buf)))
                        spk_buf.clear()
                else:
                    s_chunk = None

                if m_chunk and s_chunk:
                    arr_m = np.frombuffer(m_chunk, dtype=np.int16).astype(np.int32)
                    arr_s = np.frombuffer(s_chunk, dtype=np.int16).astype(np.int32)
                    out_chunk = np.clip(arr_m + arr_s, -32768, 32767).astype(np.int16).tobytes()
                    self._calculate_rms_fast(m_chunk)
                elif m_chunk:
                    out_chunk = m_chunk
                    self._calculate_rms_fast(m_chunk)
                elif s_chunk:
                    out_chunk = s_chunk
                    self._calculate_rms_fast(s_chunk)
                else:
                    out_chunk = b"\x00" * bytes_needed

                self.frames.append(out_chunk)
                total_audio_samples += needed_samples
                self.total_samples_recorded = total_audio_samples

                max_slack = int(RATE * BYTES_PER_STEREO_SAMPLE * 0.40)
                if len(mic_buf) > max_slack:
                    del mic_buf[: len(mic_buf) - max_slack]
                if len(spk_buf) > max_slack:
                    del spk_buf[: len(spk_buf) - max_slack]
            else:
                time.sleep(0.005)

        if self.master_clock:
            final_elapsed = self.master_clock.now()
            final_target = int(round(final_elapsed * RATE))
            final_needed = final_target - total_audio_samples
            if final_needed > 0:
                bytes_needed = final_needed * BYTES_PER_STEREO_SAMPLE
                if self.mic_stream and self.spk_stream:
                    m = bytes(mic_buf[:bytes_needed]).ljust(bytes_needed, b"\x00")
                    s = bytes(spk_buf[:bytes_needed]).ljust(bytes_needed, b"\x00")
                    arr_m = np.frombuffer(m, dtype=np.int16).astype(np.int32)
                    arr_s = np.frombuffer(s, dtype=np.int16).astype(np.int32)
                    out_chunk = np.clip(arr_m + arr_s, -32768, 32767).astype(np.int16).tobytes()
                elif self.mic_stream:
                    out_chunk = bytes(mic_buf[:bytes_needed]).ljust(bytes_needed, b"\x00")
                elif self.spk_stream:
                    out_chunk = bytes(spk_buf[:bytes_needed]).ljust(bytes_needed, b"\x00")
                else:
                    out_chunk = b"\x00" * bytes_needed

                self.frames.append(out_chunk)
                total_audio_samples += final_needed
                self.total_samples_recorded = total_audio_samples

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

        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
            except Exception:
                pass
            try:
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None

        if self.spk_stream:
            try:
                self.spk_stream.stop_stream()
            except Exception:
                pass
            try:
                self.spk_stream.close()
            except Exception:
                pass
            self.spk_stream = None

        self.stream = None
        self.recording = False
        self.paused = False
        self.current_rms = 0.0

        if not self.frames:
            return False

        try:
            wav_path = Path(wav_path)
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(b"".join(self.frames))
            return wav_path.is_file() and wav_path.stat().st_size > 44
        except Exception as e:
            print(f"Error saving audio WAV: {e}")
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
                        data = np.clip(arr.astype(np.float32) * float(vol), -32768, 32767).astype(np.int16).tobytes()
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
                            data = np.clip(arr.astype(np.float32) * float(volume), -32768, 32767).astype(np.int16).tobytes()
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
        if self.mic_stream:
            try:
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        if self.spk_stream:
            try:
                self.spk_stream.close()
            except Exception:
                pass
            self.spk_stream = None
        try:
            self.pa.terminate()
        except Exception:
            pass
