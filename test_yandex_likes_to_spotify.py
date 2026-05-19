#!/usr/bin/env python3
import unittest

from yandex_likes_to_spotify import duration_score, normalize, token_overlap


class MatchingHelpersTest(unittest.TestCase):
    def test_normalize_removes_noise(self):
        self.assertEqual(normalize("Song Title (Remastered 2024) [Explicit]"), "song title")

    def test_token_overlap_exact(self):
        self.assertEqual(token_overlap("Artist Track", "artist track"), 1.0)

    def test_token_overlap_partial(self):
        self.assertGreater(token_overlap("artist track", "artist other track"), 0.5)

    def test_duration_score_inside_tolerance(self):
        self.assertEqual(duration_score(180_000, 183_000, 4_000), 1.0)

    def test_duration_score_missing_duration(self):
        self.assertEqual(duration_score(None, 183_000, 4_000), 0.0)


if __name__ == "__main__":
    unittest.main()
