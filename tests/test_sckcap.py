import os
import unittest

from tvcast.cast import sckcap


class TestFitSize(unittest.TestCase):
    def test_wide_display_limited_by_height(self):
        self.assertEqual(sckcap.fit_size(3024, 1964, 1280, 720), (1108, 720))

    def test_16_9_display_fills(self):
        self.assertEqual(sckcap.fit_size(1920, 1080, 1280, 720), (1280, 720))

    def test_ultrawide_limited_by_width(self):
        w, h = sckcap.fit_size(3440, 1440, 1280, 720)
        self.assertEqual(w, 1280)
        self.assertLess(h, 720)

    def test_dimensions_are_even(self):
        w, h = sckcap.fit_size(1512, 982, 1280, 720)
        self.assertEqual((w % 2, h % 2), (0, 0))
        self.assertLessEqual(h, 720)
        self.assertLessEqual(w, 1280)


class TestPaths(unittest.TestCase):
    def test_source_exists(self):
        self.assertTrue(os.path.exists(sckcap.source_path()))
        self.assertTrue(sckcap.source_path().endswith("main.swift"))

    def test_cache_dir_is_under_user_caches(self):
        self.assertIn("Caches", sckcap.cache_dir())

    def test_helper_binary_name_tracks_source_digest(self):
        a = sckcap.helper_path_for(b"source one")
        b = sckcap.helper_path_for(b"source two")
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.basename(a).startswith("sckcap-"))


if __name__ == "__main__":
    unittest.main()
