import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile


class ReleaseTests(unittest.TestCase):
    def test_reproducible_archive_and_no_private_files(self):
        root = Path(__file__).resolve().parents[1]
        build = [sys.executable, 'scripts/build_release.py']
        subprocess.run(build, cwd=root, check=True, capture_output=True)
        first = (root / 'dist/jelly-cli.pyz').read_bytes()
        subprocess.run(build, cwd=root, check=True, capture_output=True)
        self.assertEqual(first, (root / 'dist/jelly-cli.pyz').read_bytes())
        with zipfile.ZipFile(root / 'dist/jelly-cli.pyz') as archive:
            self.assertIn('jelly_cli/playback.py', archive.namelist())
            self.assertFalse(any('session' in name or '__pycache__' in name or '.venv' in name for name in archive.namelist()))
        output = subprocess.run([sys.executable, 'dist/jelly-cli.pyz', '--version'], cwd=root, check=True, capture_output=True, text=True)
        self.assertEqual(output.stdout.strip(), 'jelly-cli 1.0.1')
