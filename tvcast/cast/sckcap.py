"""Build and locate the ScreenCaptureKit helper that gives us video plus system audio.

The helper is a single Swift file shipped with the package. It is compiled with `swiftc`
into the user's cache directory the first time it is needed, keyed by a digest of the
source so upgrades rebuild automatically.
"""
import ctypes
import hashlib
import os
import platform
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def source_path():
    return os.path.join(os.path.dirname(HERE), "helpers", "sckcap", "main.swift")


def cache_dir():
    return os.path.expanduser("~/Library/Caches/tvcast")


def helper_path_for(source_bytes):
    digest = hashlib.sha256(source_bytes).hexdigest()[:12]
    return os.path.join(cache_dir(), f"sckcap-{digest}")


def supported():
    """ScreenCaptureKit audio capture needs macOS 13 or newer."""
    if platform.system() != "Darwin":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return False
    return major >= 13


def fit_size(display_w, display_h, max_w, max_h):
    """Largest even-sized box with the display's aspect that fits inside max_w x max_h."""
    scale = min(max_w / display_w, max_h / display_h)
    w = int(display_w * scale) // 2 * 2
    h = int(display_h * scale) // 2 * 2
    return w, h


def display_size():
    cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
    cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
    cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
    cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
    d = cg.CGMainDisplayID()
    return int(cg.CGDisplayPixelsWide(d)), int(cg.CGDisplayPixelsHigh(d))


def ensure_helper(log=lambda m: None):
    """Path to a built helper, compiling it if needed. None when it cannot be provided."""
    if not supported():
        return None
    src = source_path()
    if not os.path.exists(src):
        return None
    with open(src, "rb") as f:
        out = helper_path_for(f.read())
    if os.path.exists(out):
        return out
    swiftc = shutil.which("swiftc")
    if not swiftc:
        log("swiftc not found; run `xcode-select --install` to enable system audio capture")
        return None
    os.makedirs(cache_dir(), exist_ok=True)
    log("→ building the ScreenCaptureKit helper (first run only)…")
    try:
        proc = subprocess.run([swiftc, "-O", "-o", out, src], capture_output=True, text=True,
                              timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"helper build failed: {e}")
        return None
    if proc.returncode != 0:
        log("helper build failed:\n" + proc.stderr[-2000:])
        return None
    return out
