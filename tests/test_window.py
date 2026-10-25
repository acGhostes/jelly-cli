import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


class WindowTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(tool) for tool in ('mpv', 'ffmpeg', 'xvfb-run', 'xdotool')), 'window integration tools required')
    def test_windowed_playback_and_reporting(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['xvfb-run', '-a', sys.executable, 'scripts/check_window_playback.py'], cwd=root,
                                env={**os.environ, 'PYTHONPATH': str(root)}, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
