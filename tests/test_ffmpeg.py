import unittest

from tvcast.cast import ffmpeg as ff

LIST_OUTPUT = """[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Camera
[AVFoundation indev @ 0x1] [4] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x1] [1] BlackHole 2ch
"""


class TestDevices(unittest.TestCase):
    def test_parse_devices(self):
        d = ff.parse_devices(LIST_OUTPUT)
        self.assertEqual(d["video"], [(0, "MacBook Pro Camera"), (4, "Capture screen 0")])
        self.assertEqual(d["audio"], [(0, "MacBook Pro Microphone"), (1, "BlackHole 2ch")])

    def test_screen_and_audio_lookup(self):
        d = ff.parse_devices(LIST_OUTPUT)
        self.assertEqual(ff.screen_index(d), 4)
        self.assertEqual(ff.find_audio_device(d, "blackhole"), 1)
        self.assertIsNone(ff.find_audio_device(d, "loopback"))

    def test_empty_output(self):
        self.assertEqual(ff.parse_devices(""), {"video": [], "audio": []})
        self.assertIsNone(ff.screen_index({"video": [], "audio": []}))


class TestArgv(unittest.TestCase):
    def test_avfoundation_video_only(self):
        argv = ff.build_argv("ffmpeg", ff.avfoundation_inputs(4, None, 30), ff.VideoSpec(), False)
        self.assertEqual(argv[0], "ffmpeg")
        self.assertIn("4:none", argv)
        self.assertIn("h264_videotoolbox", argv)
        self.assertIn("-nostdin", argv)
        self.assertIn("-an", argv)
        self.assertNotIn("aac", argv)
        self.assertEqual(argv[-2:], ["mpegts", "-"])

    def test_avfoundation_with_audio(self):
        argv = ff.build_argv("ffmpeg", ff.avfoundation_inputs(4, 1, 30), ff.VideoSpec(), True)
        self.assertIn("4:1", argv)
        self.assertIn("aac", argv)
        self.assertIn("-ac", argv)
        self.assertNotIn("-an", argv)

    def test_rawpipe_inputs(self):
        inputs = ff.rawpipe_inputs(1280, 832, 30, "/tmp/a.fifo")
        self.assertIn("rawvideo", inputs)
        self.assertIn("1280x832", inputs)
        self.assertIn("pipe:0", inputs)
        self.assertIn("/tmp/a.fifo", inputs)
        self.assertIn("f32le", inputs)
        argv = ff.build_argv("ffmpeg", inputs, ff.VideoSpec(), True)
        self.assertNotIn("-nostdin", argv)  # stdin carries the video

    def test_rawpipe_without_audio(self):
        inputs = ff.rawpipe_inputs(1280, 832, 30, None)
        self.assertNotIn("f32le", inputs)

    def test_fit_filter_pads_to_16_9(self):
        f = ff.fit_filter(ff.VideoSpec(width=1280, height=720))
        self.assertIn("scale=1280:720:force_original_aspect_ratio=decrease", f)
        self.assertIn("pad=1280:720:(ow-iw)/2:(oh-ih)/2", f)

    def test_spec_values_flow_into_argv(self):
        spec = ff.VideoSpec(width=1920, height=1080, fps=25, bitrate="8M")
        argv = ff.build_argv("ffmpeg", ff.avfoundation_inputs(4, None, spec.fps), spec, False)
        self.assertIn("8M", argv)
        self.assertEqual(argv[argv.index("-g") + 1], "25")
        self.assertEqual(argv[argv.index("-framerate") + 1], "25")


if __name__ == "__main__":
    unittest.main()
