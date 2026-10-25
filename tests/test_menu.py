"""Optional real fzf keyboard smoke test, enabled in CI."""
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import sys
import termios
import time
import unittest


class MenuTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('fzf'), 'fzf required for interactive menu test')
    def test_search_and_select(self):
        root = Path(__file__).resolve().parents[1]
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(root)
            os.environ['TERM'] = 'xterm-256color'
            os.execv(sys.executable, [sys.executable, '-c', "from jelly_cli.cli import choose; print('SELECTED=' + str(choose('Library', ['First movie', 'Unique movie'])))"])
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
        output, selected, accepted = b'', False, False
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if select.select([fd], [], [], .1)[0]:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    output += chunk
                    if b'\x1b[6n' in chunk:
                        os.write(fd, b'\x1b[1;1R')
                    if not selected and b'First movie' in output:
                        os.write(fd, b'Unique')
                        selected = True
                    if selected and not accepted and b'1/2' in re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', chunk):
                        os.write(fd, b'\r')
                        accepted = True
                    if b'SELECTED=1' in output:
                        break
            self.assertIn(b'SELECTED=1', output, output[-1500:])
        finally:
            finished, _ = os.waitpid(pid, os.WNOHANG)
            if not finished:
                os.kill(pid, signal.SIGTERM)
                os.waitpid(pid, 0)
            os.close(fd)
