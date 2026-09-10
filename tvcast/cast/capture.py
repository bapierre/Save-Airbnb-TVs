"""Run the process pipeline that produces a live MPEG-TS byte stream."""
import os
import shutil
import subprocess
import tempfile

from . import ffmpeg as ff


class Capture:
    """A running pipeline. `read()` yields MPEG-TS bytes; `stop()` kills every process."""

    def __init__(self, procs, stdout):
        self.procs = procs
        self.stdout = stdout

    def read(self, n):
        return self.stdout.read(n)

    def stop(self):
        for p in self.procs:
            try:
                p.kill()
            except OSError:
                pass
        for p in self.procs:
            try:
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            self.stdout.close()
        except OSError:
            pass


def start_ffmpeg(argv, stdin=None, extra_procs=()):
    proc = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=0)
    return Capture(list(extra_procs) + [proc], proc.stdout)


def make_avfoundation_factory(ffmpeg, screen, audio, spec):
    """Screen straight from ffmpeg's avfoundation input; audio from a loopback device if given."""
    argv = ff.build_argv(ffmpeg, ff.avfoundation_inputs(screen, audio, spec.fps), spec,
                         has_audio=audio is not None)

    def factory():
        return start_ffmpeg(argv)

    factory.description = (f"avfoundation screen {screen}, "
                           f"audio {'device ' + str(audio) if audio is not None else 'none'}")
    return factory


def make_sck_factory(ffmpeg, helper, spec, capture_size):
    """ScreenCaptureKit helper feeds NV12 video on ffmpeg's stdin and system audio on a fifo."""
    cw, ch = capture_size

    def factory():
        tmp = tempfile.mkdtemp(prefix="tvcast-")
        fifo = os.path.join(tmp, "audio.fifo")
        os.mkfifo(fifo)
        helper_proc = subprocess.Popen(
            [helper, "--width", str(cw), "--height", str(ch), "--fps", str(spec.fps),
             "--audio-fifo", fifo],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        argv = ff.build_argv(ffmpeg, ff.rawpipe_inputs(cw, ch, spec.fps, fifo), spec,
                             has_audio=True)
        cap = start_ffmpeg(argv, stdin=helper_proc.stdout, extra_procs=[helper_proc])
        helper_proc.stdout.close()  # ffmpeg owns the read end now
        orig_stop = cap.stop

        def stop():
            orig_stop()
            shutil.rmtree(tmp, ignore_errors=True)

        cap.stop = stop
        return cap

    factory.description = f"ScreenCaptureKit {cw}x{ch} with system audio"
    return factory
