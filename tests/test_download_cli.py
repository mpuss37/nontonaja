import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from nontonaja.cli import _pick_action, _pick_source, build_parser
from nontonaja.download import download, sanitize_filename


class TestDownloadAndCli(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Spider-Man: No Way Home (2021)"), "Spider-Man No Way Home (2021)")
        self.assertEqual(sanitize_filename("Film/Movie: Part 1? *Special*"), "FilmMovie Part 1 Special")
        self.assertEqual(sanitize_filename(""), "video")

    def test_parser_download_flags(self):
        p = build_parser()
        args1 = p.parse_args(["spider man"])
        self.assertFalse(args1.download)
        self.assertIsNone(args1.output)
        self.assertEqual(args1.query, ["spider man"])

        args2 = p.parse_args(["-d", "spider man"])
        self.assertTrue(args2.download)
        self.assertIsNone(args2.output)
        self.assertEqual(args2.query, ["spider man"])

        args3 = p.parse_args(["-d", "-o", "/downloads/movies", "spider man"])
        self.assertTrue(args3.download)
        self.assertEqual(args3.output, "/downloads/movies")
        self.assertEqual(args3.query, ["spider man"])

    def test_pick_action(self):
        with patch("builtins.input", side_effect=[""]):
            self.assertEqual(_pick_action(), "play")

        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(_pick_action(), "play")

        with patch("builtins.input", side_effect=["2"]):
            self.assertEqual(_pick_action(), "download")

        with patch("builtins.input", side_effect=["3"]):
            self.assertEqual(_pick_action(), "both")

        with patch("builtins.input", side_effect=["4"]):
            self.assertEqual(_pick_action(), "exit")

    def test_pick_source(self):
        with patch("builtins.input", side_effect=["1"]):
            src, q = _pick_source()
            self.assertEqual(src, "lk21")
            self.assertIsNone(q)

        with patch("builtins.input", side_effect=["2"]):
            src, q = _pick_source()
            self.assertEqual(src, "flixhq")
            self.assertEqual(q, 720)

        with patch("builtins.input", side_effect=["3"]):
            src, q = _pick_source()
            self.assertEqual(src, "flixhq")
            self.assertEqual(q, 1080)

    def test_download_mock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "mock.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                    "-f", "lavfi", "-i", "anoisesrc=d=1:c=pink:r=44100:a=0.5",
                    "-c:v", "libx264", "-c:a", "aac", video_path,
                ],
                check=True,
                capture_output=True,
            )

            sub_path = os.path.join(tmpdir, "mock.vtt")
            with open(sub_path, "w") as f:
                f.write("WEBVTT\n\n00:00.000 --> 00:01.000\nHello World Subtitle\n")

            out_dir = os.path.join(tmpdir, "downloads")
            download(video_path, out_dir, "My Movie: The Beginning", [sub_path], subtitle_language="Indonesian")

            expected_file = os.path.join(out_dir, "My Movie The Beginning.mkv")
            self.assertTrue(os.path.exists(expected_file))
            self.assertGreater(os.path.getsize(expected_file), 0)

            probe = subprocess.run(["ffprobe", expected_file], capture_output=True, text=True, check=False)
            self.assertIn("Video: h264", probe.stderr)
            self.assertIn("Audio: aac", probe.stderr)
            self.assertIn("Subtitle: subrip", probe.stderr)


if __name__ == "__main__":
    unittest.main()
