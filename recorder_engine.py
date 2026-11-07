"""High-Performance Screen Recorder Engine for Windows."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime

from audio_manager import AudioManager
from settings import Settings

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32
winmm = ctypes.windll.winmm
k32 = ctypes.windll.kernel32
try:
    k32.GetCurrentThread.restype = wintypes.HANDLE
    k32.SetThreadPriority.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetThreadPriority.restype = wintypes.BOOL
except Exception:
    pass


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def ensure_input_desktop():
    """Ensure the calling thread is attached to the active input desktop."""
    try:
        hdesk = u32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            u32.SetThreadDesktop(hdesk)
    except Exception:
        pass


class POINT(ctypes.Structure):
    _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('hCursor', wintypes.HANDLE),
        ('ptScreenPos', POINT)
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]


class CursorRenderer:
    """Pro mouse cursor renderer with 100% reliable positioning, highlight halo, and click ripples."""

    def __init__(self):
        self.h_arrow = u32.LoadCursorW(0, 32512)
        # BGR: Gold/Yellow halo (0x0000E5FF)
        self.pen_halo = g32.CreatePen(0, 3, 0x0000E5FF)
        self.pen_lclick = g32.CreatePen(0, 3, 0x000000EF) # Red ripple
        self.pen_rclick = g32.CreatePen(0, 3, 0x00F87138) # Sky blue ripple
        self.brush_null = g32.GetStockObject(5) # NULL_BRUSH
        self.active_ripples = []
        self._was_l_down = False
        self._was_r_down = False
        # Pre-allocated structures to avoid per-frame garbage collection
        self._pt = POINT()
        self._ci = CURSORINFO()
        self._ci.cbSize = ctypes.sizeof(CURSORINFO)

    def draw(self, hdc_mem, left, top, show_cursor, halo, click_ripple, excluded_rect):
        if not show_cursor:
            return

        if not u32.GetCursorPos(ctypes.byref(self._pt)):
            return

        cur_x = self._pt.x - left
        cur_y = self._pt.y - top

        # Exclude if inside floating bar
        if excluded_rect:
            rx, ry, rw, rh = excluded_rect
            if rx <= self._pt.x <= rx + rw and ry <= self._pt.y <= ry + rh:
                return

        # Check clicks
        if click_ripple:
            l_down = bool(u32.GetAsyncKeyState(0x01) & 0x8000)
            r_down = bool(u32.GetAsyncKeyState(0x02) & 0x8000)
            if l_down and not self._was_l_down:
                self.active_ripples.append([cur_x, cur_y, 6, self.pen_lclick])
            if r_down and not self._was_r_down:
                self.active_ripples.append([cur_x, cur_y, 6, self.pen_rclick])
            self._was_l_down = l_down
            self._was_r_down = r_down

        # Draw ripples
        if self.active_ripples:
            old_brush = g32.SelectObject(hdc_mem, self.brush_null)
            next_ripples = []
            for r in self.active_ripples:
                rx, ry, radius, pen = r
                old_pen = g32.SelectObject(hdc_mem, pen)
                g32.Ellipse(hdc_mem, rx - radius, ry - radius, rx + radius, ry + radius)
                g32.SelectObject(hdc_mem, old_pen)
                if radius < 24:
                    r[2] += 4
                    next_ripples.append(r)
            self.active_ripples = next_ripples
            g32.SelectObject(hdc_mem, old_brush)

        # Draw halo (golden highlight circle around cursor)
        if halo:
            old_brush = g32.SelectObject(hdc_mem, self.brush_null)
            old_pen = g32.SelectObject(hdc_mem, self.pen_halo)
            g32.Ellipse(hdc_mem, cur_x - 18, cur_y - 18, cur_x + 18, cur_y + 18)
            g32.SelectObject(hdc_mem, old_pen)
            g32.SelectObject(hdc_mem, old_brush)

        # Draw actual cursor icon (query current cursor or fallback to arrow)
        h_cur = None
        if u32.GetCursorInfo(ctypes.byref(self._ci)) and self._ci.hCursor:
            h_cur = self._ci.hCursor
        if not h_cur:
            h_cur = self.h_arrow

        u32.DrawIconEx(hdc_mem, cur_x, cur_y, h_cur, 0, 0, 0, 0, 3)

    def close(self):
        try:
            g32.DeleteObject(self.pen_halo)
            g32.DeleteObject(self.pen_lclick)
            g32.DeleteObject(self.pen_rclick)
        except Exception:
            pass


def find_ffmpeg():
    """Find FFmpeg binary path."""
    candidates = [
        Path(__file__).parent / "tools" / "ffmpeg.exe",
        Path(__file__).parent.parent / "tools" / "ffmpeg.exe",
        Path("C:/Users/Admin/AppData/Local/Programs/Ghi Âm Zalo PC/tools/ffmpeg.exe"),
        Path("C:/Users/Admin/AppData/Local/Programs/Ghi Âm Zalo PC/Source/tools/ffmpeg.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    # Check winget packages
    winget_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    for p in winget_dir.glob("**/ffmpeg.exe"):
        if p.is_file():
            return str(p)

    return "ffmpeg"


_CACHED_ENCODER = None


def detect_best_encoder(ffmpeg_path):
    """Test if h264_mf (hardware accelerated) works, otherwise fallback to libx264. Cached for zero startup lag."""
    global _CACHED_ENCODER
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER

    try:
        cmd = [
            ffmpeg_path, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", "64x64",
            "-pix_fmt", "bgra",
            "-r", "10",
            "-i", "-",
            "-c:v", "h264_mf",
            "-pix_fmt", "nv12",
            "-f", "null", "-"
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW
        )
        dummy_frame = b"\x00" * (64 * 64 * 4)
        proc.stdin.write(dummy_frame)
        proc.stdin.close()
        proc.wait(timeout=2.0)
        if proc.returncode == 0:
            _CACHED_ENCODER = "h264_mf"
            return "h264_mf"
    except Exception:
        pass
    _CACHED_ENCODER = "libx264"
    return "libx264"


class MasterClock:
    """High-precision monotonic master wall-clock with pause/resume support for 100% accurate A/V synchronization."""

    def __init__(self):
        self._t0 = 0.0
        self._paused_duration = 0.0
        self._pause_start = 0.0
        self._is_running = False
        self._is_paused = False
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            self._t0 = time.perf_counter()
            self._paused_duration = 0.0
            self._pause_start = 0.0
            self._is_running = True
            self._is_paused = False

    def now(self) -> float:
        """Returns the real elapsed wall-clock seconds since start, excluding paused time."""
        with self._lock:
            if not self._is_running:
                return getattr(self, "_stopped_time", 0.0)
            if self._is_paused:
                return max(0.0, self._pause_start - self._t0 - self._paused_duration)
            return max(0.0, time.perf_counter() - self._t0 - self._paused_duration)

    def pause(self):
        with self._lock:
            if self._is_running and not self._is_paused:
                self._pause_start = time.perf_counter()
                self._is_paused = True

    def resume(self):
        with self._lock:
            if self._is_running and self._is_paused:
                self._paused_duration += (time.perf_counter() - self._pause_start)
                self._is_paused = False

    def stop(self) -> float:
        with self._lock:
            if self._is_running:
                self._stopped_time = self.now()
                self._is_running = False
                self._is_paused = False
            return getattr(self, "_stopped_time", 0.0)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused


class RecorderEngine:
    def __init__(self, settings: Settings, on_update_callback=None):
        self.settings = settings
        self.on_update = on_update_callback
        self.ffmpeg_path = find_ffmpeg()
        self.audio_mgr = AudioManager()

        self.state = "idle"  # idle, recording, paused, stopping
        self.start_time = 0.0
        self.paused_duration = 0.0
        self.pause_start = 0.0
        self.frames_captured = 0
        self.frames_written = 0
        self.current_fps = 0.0

        self.master_clock = None
        self._ready_event = None
        self._record_thread = None
        self._writer_thread = None
        self._stats_thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._frame_pool = None
        self._work_queue = None
        self.last_sync_stats = None

        self.temp_video_path = None
        self.temp_audio_path = None
        self.final_output_path = None

        # Capture geometry
        self.capture_region = None  # None for full screen, or (left, top, width, height)
        self._excluded_rect_provider = None

    def recover_orphaned_recordings(self):
        """Auto-recovers any leftover ~temp_v_*.mp4 files from previous interrupted sessions."""
        try:
            out_dir = Path(self.settings.output_dir)
            if not out_dir.is_dir():
                return []
            recovered = []
            for temp_v in list(out_dir.glob("~temp_v_*.mp4")):
                try:
                    if time.time() - temp_v.stat().st_mtime > 10:
                        stem = temp_v.stem.replace("~temp_v_", "")
                        rec_path = out_dir / f"FLOWREC_{stem}.mp4"
                        if not rec_path.exists():
                            try:
                                temp_v.replace(rec_path)
                            except Exception:
                                shutil.move(str(temp_v), str(rec_path))
                            recovered.append(str(rec_path))
                except Exception:
                    pass
            return recovered
        except Exception:
            return []

    def set_excluded_rect_provider(self, provider):
        self._excluded_rect_provider = provider

    def set_region(self, region):
        """Set custom region: (left, top, width, height) or None for full screen."""
        if region:
            left, top, w, h = region
            # FFmpeg requires even dimensions (divisible by 2)
            w = (w // 2) * 2
            h = (h // 2) * 2
            self.capture_region = (left, top, max(2, w), max(2, h))
        else:
            self.capture_region = None

    def start(self):
        if self.state != "idle":
            return False

        ensure_input_desktop()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(self.settings.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        self.temp_video_path = out_dir / f"~temp_v_{timestamp}.mp4"
        self.temp_audio_path = out_dir / f"~temp_a_{timestamp}.wav"
        self.final_output_path = out_dir / f"FLOWREC_{timestamp}.mp4"

        # Determine geometry
        screen_w = u32.GetSystemMetrics(0)
        screen_h = u32.GetSystemMetrics(1)
        if self.capture_region:
            left, top, width, height = self.capture_region
        else:
            left, top = 0, 0
            width, height = screen_w, screen_h

        # Ensure width and height are even
        width = (width // 2) * 2
        height = (height // 2) * 2

        # Check resolution scaling preset
        out_w, out_h = width, height
        preset = getattr(self.settings, "resolution_preset", "Native")
        if preset == "720p" and (width > 1280 or height > 720):
            scale = min(1280 / width, 720 / height)
            out_w = (int(width * scale) // 2) * 2
            out_h = (int(height * scale) // 2) * 2
        elif preset == "1080p" and (width > 1920 or height > 1080):
            scale = min(1920 / width, 1080 / height)
            out_w = (int(width * scale) // 2) * 2
            out_h = (int(height * scale) // 2) * 2

        scale_filter = ["-vf", f"scale={out_w}:{out_h}"] if (out_w != width or out_h != height) else []

        # Detect encoder
        encoder = self.settings.encoder
        if encoder == "auto":
            encoder = detect_best_encoder(self.ffmpeg_path)

        fps = self.settings.fps
        bitrate = self.settings.get_bitrate()

        # Encoder flags
        extra_enc_flags = []
        if encoder == "h264_mf":
            extra_enc_flags = ["-scenario", "display_remoting", "-rate_control", "ld_vbr"]
        elif encoder == "libx264":
            extra_enc_flags = ["-preset", "ultrafast", "-tune", "zerolatency"]

        video_cmd = [
            self.ffmpeg_path, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgra",
            "-r", str(fps),
            "-i", "-",
            *scale_filter,
            "-c:v", encoder,
            *extra_enc_flags,
            "-b:v", bitrate,
            "-pix_fmt", "nv12" if encoder == "h264_mf" else "yuv420p",
            str(self.temp_video_path)
        ]

        try:
            v_proc = subprocess.Popen(
                video_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                bufsize=10485760,  # 10 MB OS pipe buffer
                creationflags=NO_WINDOW
            )
        except Exception as e:
            raise RuntimeError(f"Failed to launch FFmpeg: {e}")

        # Initialize MasterClock and synchronization primitives
        self.master_clock = MasterClock()
        self._ready_event = threading.Event()
        self._stop_event.clear()
        self._pause_event.clear()

        # Decoupled frame memory pool (6 reusable buffers)
        frame_bytes = width * height * 4
        self._frame_pool = queue.Queue()
        for _ in range(6):
            self._frame_pool.put(bytearray(frame_bytes))
        self._work_queue = queue.Queue(maxsize=6)

        # Start Audio if Mic or Speaker is enabled
        has_audio = False
        rec_mic = bool(self.settings.record_mic)
        rec_spk = bool(getattr(self.settings, "record_speaker", False))
        if rec_mic or rec_spk:
            try:
                mic_vol = getattr(self.settings, "mic_volume", 1.0)
                self.audio_mgr.start_recording(
                    record_mic=rec_mic,
                    mic_index=self.settings.mic_device_index,
                    mic_volume=mic_vol,
                    record_speaker=rec_spk,
                    speaker_index=getattr(self.settings, "speaker_device_index", None),
                    master_clock=self.master_clock,
                    ready_event=self._ready_event,
                    sample_rate=48000
                )
                has_audio = True
            except Exception as e:
                print(f"Warning: Failed to start audio recording: {e}")

        self.frames_captured = 0
        self.frames_written = 0

        # Dedicated background pipe writer thread with CFR Wall-Clock frame pacing
        self._writer_thread = threading.Thread(
            target=self._pipe_writer_loop,
            args=(v_proc, fps),
            daemon=True
        )
        self._writer_thread.start()

        # High-priority frame grabber thread
        self._record_thread = threading.Thread(
            target=self._capture_loop,
            args=(left, top, width, height, fps, frame_bytes),
            daemon=True
        )
        self._record_thread.start()

        # Stats thread
        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True)
        self._stats_thread.start()

        # Synchronized launch: start master clock and trigger all threads simultaneously (t = 0.0)
        self.master_clock.start()
        self.start_time = self.master_clock._t0
        self.paused_duration = 0.0
        self.pause_start = 0.0
        self._ready_event.set()
        self.state = "recording"
        return True

    def _pipe_writer_loop(self, v_proc, fps):
        """Asynchronously writes captured frames to FFmpeg stdin with strict 1:1 wall-clock CFR pacing and duplication."""
        try:
            self._ready_event.wait()
            target_interval = 1.0 / fps
            actual_frames_written = 0
            last_frame_bytes = None

            while not self._stop_event.is_set():
                if self._pause_event.is_set():
                    time.sleep(0.02)
                    continue

                elapsed = self.master_clock.now()
                expected_frames = int(round(elapsed * fps))

                if actual_frames_written < expected_frames:
                    # Retrieve new frame if available
                    if not self._work_queue.empty():
                        try:
                            buf = self._work_queue.get_nowait()
                            last_frame_bytes = bytes(buf)
                            if self._frame_pool is not None:
                                try:
                                    self._frame_pool.put_nowait(buf)
                                except Exception:
                                    pass
                        except queue.Empty:
                            pass

                    if last_frame_bytes is not None:
                        try:
                            v_proc.stdin.write(last_frame_bytes)
                            actual_frames_written += 1
                            self.frames_written = actual_frames_written
                        except (BrokenPipeError, OSError, ValueError):
                            break
                    else:
                        time.sleep(0.001)

                else:
                    # On schedule: sleep precisely until next frame boundary
                    next_frame_t = (actual_frames_written + 1) * target_interval
                    wait_t = next_frame_t - self.master_clock.now()
                    if wait_t > 0.002:
                        time.sleep(wait_t - 0.001)
                    elif wait_t <= 0:
                        time.sleep(0.0005)

        finally:
            # Stopping phase: ensure actual_frames_written matches final_expected_frames exactly
            final_elapsed = self.master_clock.now() if self.master_clock else 0.0
            final_expected_frames = int(round(final_elapsed * fps))

            # Drain any remaining captured frames in work_queue
            while not self._work_queue.empty() and actual_frames_written < final_expected_frames:
                try:
                    buf = self._work_queue.get_nowait()
                    last_frame_bytes = bytes(buf)
                    v_proc.stdin.write(last_frame_bytes)
                    actual_frames_written += 1
                    self.frames_written = actual_frames_written
                except Exception:
                    break

            # If capture was under-sampled (due to CPU/GPU lag), duplicate last frame to guarantee 1:1 CFR
            if last_frame_bytes is not None:
                while actual_frames_written < final_expected_frames:
                    try:
                        v_proc.stdin.write(last_frame_bytes)
                        actual_frames_written += 1
                        self.frames_written = actual_frames_written
                    except Exception:
                        break

            # Drain and clear queue
            while not self._work_queue.empty():
                try:
                    self._work_queue.get_nowait()
                except Exception:
                    break

            try:
                v_proc.stdin.close()
                v_proc.wait(timeout=10.0)
            except Exception:
                pass

    def _capture_loop(self, left, top, width, height, fps, frame_bytes):
        """High-efficiency screen capture loop running with 1ms timer precision."""
        ensure_input_desktop()

        try:
            winmm.timeBeginPeriod(1)
        except Exception:
            pass

        try:
            k32.SetThreadPriority(k32.GetCurrentThread(), 1)  # THREAD_PRIORITY_ABOVE_NORMAL
        except Exception:
            pass

        hdc_screen = u32.GetDC(0)
        hdc_mem = g32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = -height  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        p_bits = ctypes.c_void_p()
        hbm = g32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(p_bits), 0, 0)
        g32.SelectObject(hdc_mem, hbm)

        cursor_renderer = CursorRenderer()
        target_interval = 1.0 / fps
        record_cursor = self.settings.record_cursor
        mouse_halo = getattr(self.settings, "mouse_halo", True)
        mouse_click_ripple = getattr(self.settings, "mouse_click_ripple", True)

        self._ready_event.wait()
        capture_count = 0

        try:
            while not self._stop_event.is_set():
                if self._pause_event.is_set():
                    time.sleep(0.02)
                    continue

                # Pacing to capture at the target frame rate
                target_t = capture_count * target_interval
                wait_t = target_t - self.master_clock.now()
                if wait_t > 0.002:
                    time.sleep(wait_t - 0.001)
                while self.master_clock.now() < target_t and not self._stop_event.is_set():
                    time.sleep(0.0002)

                if self._stop_event.is_set():
                    break

                # Pure SRCCOPY (0x00CC0020) is hardware-accelerated by DWM
                g32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, 0x00CC0020)

                # Draw mouse cursor with halo & click ripple effects
                if record_cursor:
                    ex_rect = self._excluded_rect_provider() if self._excluded_rect_provider else None
                    cursor_renderer.draw(
                        hdc_mem, left, top,
                        show_cursor=True,
                        halo=mouse_halo,
                        click_ripple=mouse_click_ripple,
                        excluded_rect=ex_rect
                    )

                # Acquire reusable buffer
                try:
                    buf = self._frame_pool.get_nowait()
                except queue.Empty:
                    try:
                        buf = self._work_queue.get_nowait()
                    except queue.Empty:
                        buf = bytearray(frame_bytes)

                c_buf = (ctypes.c_char * frame_bytes).from_buffer(buf)
                ctypes.memmove(c_buf, p_bits, frame_bytes)

                try:
                    self._work_queue.put_nowait(buf)
                except queue.Full:
                    try:
                        old = self._work_queue.get_nowait()
                        self._frame_pool.put_nowait(old)
                    except Exception:
                        pass
                    try:
                        self._work_queue.put_nowait(buf)
                    except Exception:
                        pass

                capture_count += 1
                self.frames_captured = capture_count

        finally:
            try:
                winmm.timeEndPeriod(1)
            except Exception:
                pass

            cursor_renderer.close()
            g32.DeleteObject(hbm)
            g32.DeleteDC(hdc_mem)
            u32.ReleaseDC(0, hdc_screen)

    def _stats_loop(self):
        last_frame_count = 0
        last_calc_time = time.perf_counter()
        last_disk_check_time = 0.0
        cached_size_bytes = 0

        while not self._stop_event.is_set():
            time.sleep(0.2)
            now = time.perf_counter()

            if self.master_clock and self.master_clock.is_running:
                elapsed = self.master_clock.now()
            else:
                elapsed = 0.0

            # Calculate live FPS
            dt = now - last_calc_time
            if dt >= 0.5:
                df = self.frames_captured - last_frame_count
                self.current_fps = max(0.0, df / dt)
                last_frame_count = self.frames_captured
                last_calc_time = now

            # Query disk file size and monitor free disk space every 1.5s
            low_disk = False
            if now - last_disk_check_time >= 1.5:
                last_disk_check_time = now
                if self.temp_video_path and self.temp_video_path.is_file():
                    try:
                        cached_size_bytes = self.temp_video_path.stat().st_size
                    except Exception:
                        pass
                try:
                    free_bytes = shutil.disk_usage(str(self.settings.output_dir)).free
                    if free_bytes < 150 * 1024 * 1024:
                        low_disk = True
                except Exception:
                    pass

            mic_rms = self.audio_mgr.current_rms if (self.settings.record_mic or getattr(self.settings, "record_speaker", False)) else 0.0

            if self.on_update:
                self.on_update({
                    "state": self.state,
                    "elapsed": max(0.0, elapsed),
                    "fps": round(self.current_fps, 1),
                    "size_bytes": cached_size_bytes,
                    "mic_rms": mic_rms,
                    "low_disk": low_disk
                })

    def pause(self):
        if self.state == "recording":
            self.state = "paused"
            if self.master_clock:
                self.master_clock.pause()
            self._pause_event.set()
            self.audio_mgr.pause()
            return True
        return False

    def resume(self):
        if self.state == "paused":
            if self.master_clock:
                self.master_clock.resume()
            self.state = "recording"
            self._pause_event.clear()
            self.audio_mgr.resume()
            return True
        return False

    def stop(self):
        if self.state not in ("recording", "paused"):
            return None

        self.state = "stopping"
        # Freeze MasterClock immediately at user-click moment
        real_elapsed = self.master_clock.stop() if self.master_clock else 0.0
        self._stop_event.set()
        self._pause_event.clear()

        # Stop frame capture first so no new frames are queued
        if self._record_thread:
            self._record_thread.join(timeout=3.0)
            self._record_thread = None

        # Wait for pipe writer thread to finish CFR pacing and closing FFmpeg
        if self._writer_thread:
            self._writer_thread.join(timeout=10.0)
            self._writer_thread = None

        if self._stats_thread:
            self._stats_thread.join(timeout=2.0)
            self._stats_thread = None

        # Stop audio
        has_audio = False
        should_audio = self.settings.record_mic or getattr(self.settings, "record_speaker", False)
        if should_audio and self.temp_audio_path:
            try:
                has_audio = self.audio_mgr.stop_and_save(self.temp_audio_path)
            except Exception as e:
                print(f"Error stopping audio: {e}")
                has_audio = False

        # Compute telemetry & verification stats
        fps = self.settings.fps
        video_duration = (self.frames_written / fps) if getattr(self, "frames_written", 0) > 0 else 0.0
        audio_duration = 0.0
        total_audio_samples = getattr(self.audio_mgr, "total_samples_recorded", 0)
        audio_sr = getattr(self.audio_mgr, "sample_rate", 48000)
        if has_audio and total_audio_samples > 0 and audio_sr > 0:
            audio_duration = total_audio_samples / audio_sr

        diff_v_clock = abs(video_duration - real_elapsed)
        diff_a_clock = abs(audio_duration - real_elapsed) if has_audio else 0.0
        diff_v_a = abs(video_duration - audio_duration) if has_audio else 0.0

        print("\n" + "=" * 65)
        print("[FlowRec Master Clock & A/V Sync Telemetry]")
        print(f"  * Real Elapsed Time (MasterClock) : {real_elapsed:.4f} s")
        print(f"  * Video Duration ({self.frames_written} frames @ {fps} fps): {video_duration:.4f} s (Error: {diff_v_clock*1000:.1f} ms)")
        if has_audio:
            print(f"  * Audio Duration ({total_audio_samples} samples @ {audio_sr} Hz): {audio_duration:.4f} s (Error: {diff_a_clock*1000:.1f} ms)")
            print(f"  * Cumulative A/V Drift (Video vs Audio): {diff_v_a*1000:.2f} ms")
            print(f"  * Sync Verification Status: {'PASS (< 50ms)' if diff_v_a < 0.05 else 'WARN (> 50ms)'}")
        else:
            print(f"  * Audio Track: Disabled")
            print(f"  * Video Clock Status: {'PASS (< 50ms)' if diff_v_clock < 0.05 else 'WARN (> 50ms)'}")
        print("=" * 65 + "\n")

        self.last_sync_stats = {
            "real_elapsed": real_elapsed,
            "video_duration": video_duration,
            "audio_duration": audio_duration,
            "diff_v_clock": diff_v_clock,
            "diff_a_clock": diff_a_clock,
            "diff_v_a": diff_v_a,
            "pass_sync": (diff_v_a < 0.05) if has_audio else (diff_v_clock < 0.05)
        }

        # Mux video and audio
        final_file = self._mux_recording(has_audio)
        self.state = "idle"
        return final_file

    def _mux_recording(self, has_audio):
        if not self.temp_video_path or not self.temp_video_path.is_file():
            self._clean_temp_files()
            return None

        final_path = self.final_output_path

        # If no audio was recorded, instantly rename/replace temp video file
        if not has_audio or not self.temp_audio_path or not self.temp_audio_path.is_file():
            try:
                os.replace(str(self.temp_video_path), str(final_path))
                self._clean_temp_files()
                return str(final_path)
            except Exception:
                try:
                    shutil.move(str(self.temp_video_path), str(final_path))
                    self._clean_temp_files()
                    return str(final_path)
                except Exception:
                    pass

        mux_cmd = [
            self.ffmpeg_path, "-y",
            "-i", str(self.temp_video_path),
            "-i", str(self.temp_audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-movflags", "+faststart",
            str(final_path)
        ]

        try:
            subprocess.run(
                mux_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30.0,
                creationflags=NO_WINDOW
            )
            self._clean_temp_files()
            if final_path.is_file():
                return str(final_path)
        except Exception as e:
            print(f"Error during muxing: {e}")
            if self.temp_video_path.is_file():
                try:
                    shutil.move(str(self.temp_video_path), str(final_path))
                    return str(final_path)
                except Exception:
                    pass
        return None

    def _clean_temp_files(self):
        try:
            if self.temp_video_path and self.temp_video_path.is_file():
                self.temp_video_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if self.temp_audio_path and self.temp_audio_path.is_file():
                self.temp_audio_path.unlink(missing_ok=True)
        except Exception:
            pass
