import hashlib
import io
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / 'install.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, 'scripts/build_release.py'], cwd=ROOT, check=True, capture_output=True)
        cls.archive = (ROOT / 'dist/jelly-cli.pyz').read_bytes()

    def install(self, base, bad=False, uninstall=False, auth=False):
        def download(url, timeout):
            expected = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64', 'armv7l': 'armv7'}[platform.machine().lower()]
            self.assertIn(f'/releases/download/v1.0.1/jelly-cli-linux-{expected}.pyz', url)
            if url.endswith('.sha256'):
                return io.BytesIO((('0' * 64 if bad else hashlib.sha256(self.archive).hexdigest()) + '  jelly-cli.pyz\n').encode())
            return io.BytesIO(self.archive)
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(base / 'data'), 'JELLY_CLI_BIN_DIR': str(base / 'bin')}), patch.object(sys, 'argv', ['install', 'https://github.com/acGhostes/jelly-cli/releases/download', 'yes' if uninstall else 'no', '1.0.1', 'yes' if auth else 'no']), patch('shutil.which', return_value='/usr/bin/tool'), patch('urllib.request.OpenerDirector.open', side_effect=download):
            exec(compile(INSTALLER, 'install.sh', 'exec'), {'__name__': '__main__'})

    def test_install_update_checksum_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='jelly install ') as directory:
            base = Path(directory)
            self.install(base)
            launcher = base / 'bin/jelly-cli'
            result = subprocess.run([str(launcher), '--version'], check=True, capture_output=True, text=True)
            self.assertIn('jelly-cli 1.0.1', result.stdout)
            self.install(base)
            previous = (base / 'data/jelly-cli/jelly-cli.pyz').read_bytes()
            with self.assertRaisesRegex(SystemExit, 'checksum'):
                self.install(base, bad=True)
            self.assertEqual((base / 'data/jelly-cli/jelly-cli.pyz').read_bytes(), previous)
            with self.assertRaises(SystemExit) as stopped:
                self.install(base, uninstall=True)
            self.assertEqual(stopped.exception.code, 0)
            self.assertFalse(launcher.exists())
            self.assertFalse((base / 'data/jelly-cli/jelly-cli.pyz').exists())

    def test_launcher_failure_rolls_back_existing_app(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.install(base)
            installed = base / 'data/jelly-cli/jelly-cli.pyz'
            installed.write_bytes(b'previous-installation')
            original = os.replace
            def replace(source, target):
                if Path(target) == base / 'bin/jelly-cli':
                    raise OSError('simulated launcher failure')
                return original(source, target)
            with patch('os.replace', side_effect=replace), self.assertRaisesRegex(SystemExit, 'launcher failure'):
                self.install(base)
            self.assertEqual(installed.read_bytes(), b'previous-installation')

    def test_does_not_overwrite_unrelated_command(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'bin').mkdir()
            (base / 'bin/jelly-cli').write_text('another application')
            with self.assertRaisesRegex(SystemExit, 'unrelated'):
                self.install(base)
            self.assertEqual((base / 'bin/jelly-cli').read_text(), 'another application')

    def test_architecture_selection(self):
        for machine, expected in [('x86_64', 'x86_64'), ('arm64', 'aarch64'), ('aarch64', 'aarch64'), ('armv7l', 'armv7')]:
            with self.subTest(machine=machine), tempfile.TemporaryDirectory() as directory, patch('platform.machine', return_value=machine), patch('platform.system', return_value='Linux'):
                self.install(Path(directory))
                self.assertTrue((ROOT / f'dist/releases/1.0.1/jelly-cli-linux-{expected}.pyz').exists())
        with tempfile.TemporaryDirectory() as directory, patch('platform.machine', return_value='mips'):
            with self.assertRaisesRegex(SystemExit, 'Unsupported Linux architecture'):
                self.install(Path(directory))

    def test_authenticated_download(self):
        def download(command, **kwargs):
            self.assertEqual(command[:6], ['gh', 'release', 'download', 'v1.0.1', '--repo', 'acGhostes/jelly-cli'])
            self.assertEqual(command[-2:], ['--output', '-'])
            asset = command[7]
            payload = ((hashlib.sha256(self.archive).hexdigest() + '  release.pyz\n').encode()
                       if asset.endswith('.sha256') else self.archive)
            return subprocess.CompletedProcess(command, 0, stdout=payload)
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.run', side_effect=download) as calls:
            base = Path(directory)
            self.install(base, auth=True)
            self.assertEqual(calls.call_count, 2)
            self.assertEqual((base / 'data/jelly-cli/jelly-cli.pyz').read_bytes(), self.archive)

    def test_shell_syntax(self):
        subprocess.run(['sh', '-n', str(ROOT / 'install.sh')], check=True)
