# 🎥 FlowRec - Smooth, Featherlight Screen Recorder for Windows

<p align="center">
  <img src="assets/icon.ico" width="80" height="80" alt="FlowRec Logo">
</p>

<p align="center">
  <b>High-performance, GPU-accelerated, distraction-free screen & audio recorder.</b><br>
  Built natively for Windows with zero bloat, instant startup, and buttery-smooth 60/144 FPS capture.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-blue?style=flat-square&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python Version">
  <img src="https://img.shields.io/badge/Capture-Direct%20GPU%20DWM-emerald?style=flat-square" alt="Capture">
  <img src="https://img.shields.io/badge/License-MIT-purple?style=flat-square" alt="License">
</p>

---

## ✨ Why FlowRec?

Most modern screen recorders are either bloated (100MB+ installers, electron engines eating 400MB RAM) or overly complex (OBS Studio). **FlowRec** was engineered from the ground up for creators, developers, educators, and gamers who need:
- **Instant startup** (< 0.5s).
- **Featherlight footprint** (< 50MB RAM idle, low CPU consumption).
- **Rock-solid hardware dragging** without micro-stutters or drift.
- **Crystal-clear microphone boost & live monitoring**.
- **Complete privacy**: 100% local, no account required, no telemetry, zero watermarks.

---

## 🚀 Key Features

### 🎬 High-Performance Capture Engine
- **Direct DWM GPU Acceleration:** Captures frame buffers with sub-millisecond BitBlt memory copies, completely bypassing slow GDI composition locks.
- **Decoupled Asynchronous Pipe Writer:** Video capture and FFmpeg disk encoding run on separate threads with a bounded frame-pool queue, guaranteeing zero dropped frames even during heavy disk I/O.
- **Hardware Encoders:** Automatically picks the fastest available encoder on your system (`h264_mf` via Media Foundation on NVIDIA/Intel/AMD, falling back cleanly to `libx264`).
- **Resolution Scaling:** Select between **Native (Crisp 1:1)**, **1080p Full HD**, or **720p HD** on the fly.
- **Custom Region Selector:** Interactive crosshair selector with automatic even-dimension alignment (required by H.264 codecs).

### 🎙️ Studio Audio Intelligence
- **Real-Time VU Meter:** Live audio visualizer bar reacting instantly to your speech.
- **Microphone Boost (100% – 200%):** Amplify quiet USB or headset microphones with clean digital gain and clipping protection.
- **Live Sound Monitor:** Listen to your microphone through your headphones in real-time before recording.
- **3-Second Voice Test:** One-click automated record & playback test to verify your mic clarity before important sessions.

### 🖱️ Smart Cursor Effects
- **Hardware Cursor Capture:** Uses `GetCursorPos` and `GetCursorInfo` to guarantee cursor visibility across all displays and applications.
- **Mouse Highlight Halo:** Subtle golden halo following your pointer so viewers can easily track tutorials.
- **Animated Click Ripples:**
  - 🔴 **Left Click:** Dynamic pulsing ruby ripple.
  - 🔵 **Right Click:** Sleek cobalt ripple.

### 🪄 Stealth Floating Bar
- **Invisible during recording:** Uses Windows `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`. The floating bar is fully interactive on your screen, but **100% invisible in the recorded video output**.
- **Compact Controls:** Real-time elapsed timer, pulse recording dot, mini VU meter, Pause/Resume, Stop, and Restore buttons.

### ⚡ Seamless Windows Desktop Integration
- **Tray Mode:** Minimizes to the Windows taskbar notification area with a rich context menu.
- **Global Hotkeys:**
  - `F9`: Start / Stop recording instantly from any game or app.
  - `F10`: Pause / Resume recording.
- **Per-Monitor V2 DPI Aware:** Native hardware cursor tracking on high-DPI displays (100%, 125%, 150%) and gaming mice (up to 1000Hz polling rate) with zero lag or drifting.
- **Auto-Recovery Guard:** Temp files are safely recovered and finalized even if the computer crashes or loses power.

---

## 📊 Feature Comparison

| Feature | **FlowRec** | OBS Studio | Bandicam (Free) | Windows Snipping Tool |
| :--- | :---: | :---: | :---: | :---: |
| **Startup Time** | **< 0.5 sec** | 3 - 5 sec | 2 - 3 sec | 2 - 4 sec |
| **Idle RAM Usage** | **~45 MB** | ~250 MB | ~90 MB | ~110 MB |
| **Watermark** | **None (100% Free)** | None | Yes (Watermarked) | None |
| **Mic Live Monitor & 3s Test** | **Built-in** | Manual filters | No | No |
| **Stealth Toolbar (Hidden in Video)** | **Yes (`WDA`)** | Manual crop | No | No |
| **Cursor Halo & Click Ripple** | **Built-in** | Needs Plugin | Paid Only | No |
| **Portable & Open Source** | **Yes (MIT)** | Yes | No (Closed) | No (Closed) |

---

## 🛠️ Installation & Getting Started

### Prerequisites
- Windows 10 or Windows 11 (64-bit)
- Python 3.10+ (Recommended Python 3.12, 3.13, or 3.14)
- FFmpeg (FlowRec automatically detects local FFmpeg or system PATH)

### Quick Start
```bash
# 1. Clone the repository
git clone https://github.com/tiudaiza95/flowrec.git
cd flowrec

# 2. Install required dependencies
pip install -r requirements.txt

# 3. Launch FlowRec
python main.py
```

Or simply double-click `run.bat` or the **FlowRec** shortcut on your Desktop!

---

## ⌨️ Default Keyboard Shortcuts

| Shortcut | Action | Scope |
| :---: | :--- | :--- |
| `F9` | **Start / Stop Recording** | Global (Works anywhere) |
| `F10` | **Pause / Resume Recording** | Global (Works anywhere) |
| `Space` | **Start Immediately** | During Countdown overlay |
| `Escape` | **Cancel Countdown / Selection** | During Countdown / Area Select |

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    UI[FlowRecApp / Tk GUI] -->|Control| Engine[RecorderEngine]
    Engine -->|Screen Capture GDI/DWM| CapThread[_capture_loop]
    CapThread -->|Shared Frame Pool| WorkQueue[_work_queue]
    WorkQueue -->|Async Stdin Write| PipeWriter[_pipe_writer_loop]
    PipeWriter -->|Video Feed| FFmpeg[FFmpeg h264_mf]

    AudioMgr[AudioManager WASAPI] -->|Mic Audio| AudioThread[_record_thread]
    AudioThread -->|PCM Wave| WAV[~temp_a.wav]

    Engine -->|Stop & Mux| Muxer[_mux_recording]
    FFmpeg -->|Raw MP4| TempV[~temp_v.mp4]
    TempV & WAV --> Muxer
    Muxer -->|Stream Copy & FastStart| FinalVideo[FLOWREC_YYYYMMDD_HHMMSS.mp4]
```

---

## 🇻🇳 Tiếng Việt (Tóm tắt nhanh)

**FlowRec** là phần mềm quay màn hình thế hệ mới siêu nhẹ cho máy tính Windows:
- **Tốc độ:** Khởi động tức thì, tối ưu GPU phần cứng, kéo thả cửa sổ đầm chắc bám chuột 1:1.
- **Âm thanh:** Tăng cường âm lượng Micro lên đến 200%, có bộ đo sóng âm thời gian thực và tính năng ghi & nghe lại 3 giây kiểm tra trước khi quay.
- **Con trỏ:** Vòng hào quang vàng và hiệu ứng sóng nước nhấp chuột trái/phải chuyên nghiệp.
- **Tàng hình thanh công cụ:** Thanh điều khiển nổi trên màn hình nhưng hoàn toàn vô hình trong video xuất ra.
- **Phím tắt toàn cầu:** Nhấn `F9` để Bắt đầu/Dừng quay, `F10` để Tạm dừng/Tiếp tục ở bất cứ đâu.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). Built with ❤️ for content creators and power users worldwide.
