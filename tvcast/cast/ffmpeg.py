"""Locate ffmpeg, enumerate avfoundation devices, build the capture command.

Everything here is a pure function over strings so it can be tested without ffmpeg.
"""
import re
import shutil
import subprocess
from dataclasses import dataclass

CANDIDATES = ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
INSTALL_HINT = "ffmpeg not found. Install it with: brew install ffmpeg"

DEVICE_RE = re.compile(r"\[AVFoundation indev @ [^\]]+\] \[(\d+)\] (.+)")


@dataclass
class VideoSpec:
    width: int = 1280
    height: int = 720
    fps: int = 30
    bitrate: str = "3M"


def find_ffmpeg():
    for c in CANDIDATES:
        path = shutil.which(c)
        if path:
            return path
    return None


def parse_devices(text):
    """Parse `ffmpeg -f avfoundation -list_devices true -i ""` output."""
    devices = {"video": [], "audio": []}
    section = None
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            section = "video"
            continue
        if "AVFoundation audio devices" in line:
            section = "audio"
            continue
        m = DEVICE_RE.search(line)
        if m and section:
            devices[section].append((int(m.group(1)), m.group(2).strip()))
    return devices


def list_devices(ffmpeg):
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-f", "avfoundation",
                               "-list_devices", "true", "-i", ""],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return {"video": [], "audio": []}
    return parse_devices(proc.stderr + proc.stdout)


def screen_index(devices):
    for idx, name in devices["video"]:
        if name.lower().startswith("capture screen"):
            return idx
    return None


def find_audio_device(devices, needle):
    needle = needle.lower()
    for idx, name in devices["audio"]:
        if needle in name.lower():
            return idx
    return None


def avfoundation_inputs(screen, audio, fps):
    """Screen (and optionally an audio device) straight from avfoundation."""
    return ["-f", "avfoundation", "-framerate", str(fps), "-pixel_format", "nv12",
            "-capture_cursor", "1",
            "-i", f"{screen}:{audio if audio is not None else 'none'}"]


# Raw inputs need no format analysis. Without these, ffmpeg sits on the PCM input for
# several seconds "estimating" it, and the TV gives up waiting for the first byte.
NO_PROBE = ["-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer"]


def rawpipe_inputs(width, height, fps, audio_fifo):
    """NV12 frames on stdin (from the ScreenCaptureKit helper) plus float PCM on a fifo."""
    args = NO_PROBE + ["-f", "rawvideo", "-pix_fmt", "nv12", "-video_size", f"{width}x{height}",
                       "-framerate", str(fps), "-thread_queue_size", "64", "-i", "pipe:0"]
    if audio_fifo:
        args += NO_PROBE + ["-f", "f32le", "-ar", "48000", "-ac", "2",
                            "-thread_queue_size", "1024", "-i", audio_fifo]
    return args


def fit_filter(spec):
    """Scale to fit inside the target, pad to exactly the target (16:9 for TVs)."""
    w, h = spec.width, spec.height
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=nv12")


def build_argv(ffmpeg, inputs, spec, has_audio):
    argv = [ffmpeg, "-hide_banner", "-loglevel", "warning"]
    if "pipe:0" not in inputs:
        argv.append("-nostdin")
    argv += inputs
    # maxrate/bufsize cap the encoder's bursts to the target rate over a 1 s window.
    # Uncapped, motion spikes to 2-3x the average and stall TVs on busy Wi-Fi.
    argv += ["-vf", fit_filter(spec),
             "-c:v", "h264_videotoolbox", "-b:v", spec.bitrate,
             "-maxrate", spec.bitrate, "-bufsize", spec.bitrate,
             "-g", str(spec.fps), "-bf", "0", "-realtime", "1"]
    if has_audio:
        argv += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    else:
        argv += ["-an"]
    # Emit TS packets the instant they are ready and never hold frames back to reorder,
    # so nothing waits on our side of the wire. The TV's own prebuffer dominates latency.
    argv += ["-muxdelay", "0", "-muxpreload", "0", "-max_delay", "0", "-flush_packets", "1",
             "-f", "mpegts", "-"]
    return argv
