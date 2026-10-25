"""Exercise actual windowed mpv with resume, subtitles, pause, seek, quit and EOF."""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from unittest.mock import Mock, patch

from jelly_cli.cli import play


def until(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError('Timed out waiting for playback state')


with tempfile.TemporaryDirectory() as directory:
    media = Path(directory) / 'movie.mkv'
    subtitle = Path(directory) / 'movie.srt'
    subtitle.write_text('1\n00:00:00,000 --> 00:00:12,000\nWindow subtitles\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10', '-t', '12', '-c:v', 'mpeg4', str(media)], check=True)
    original = subprocess.Popen
    for end in ('quit', 'eof'):
        calls, paths, errors = [], [], []
        client = Mock()
        client.authorization = 'private-token'
        client.playback.return_value = dict(url=str(media), source_id='source', session_id=end,
            subtitles=[{'Index': 2, 'Url': str(subtitle)}], default_subtitle=2)
        client.request.side_effect = lambda endpoint, body: calls.append((endpoint, body))
        def launch(args, **kwargs):
            if args[0] != 'mpv':
                return original(args, **kwargs)
            paths.append(next(arg.split('=', 1)[1] for arg in args if arg.startswith('--input-ipc-server=')))
            # Xvfb has no GPU/audio hardware; use mpv's real X11 window renderer.
            return original(args + ['--vo=x11', '--ao=null'], **kwargs)
        def run():
            try:
                play(client, {'Id': 'item', 'Name': 'jelly-cli window test', 'UserData': {'PlaybackPositionTicks': 20_000_000}})
            except BaseException as error:
                errors.append(error)
        with patch('subprocess.Popen', side_effect=launch):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            control = socket.socket(socket.AF_UNIX)
            control.settimeout(3)
            try:
                until(lambda: paths and Path(paths[0]).exists())
                control.connect(paths[0])
                stream = control.makefile('rb')
                request_id = 0
                def command(*args):
                    global request_id
                    request_id += 1
                    control.sendall(json.dumps({'command': args, 'request_id': request_id}).encode() + b'\n')
                    while True:
                        response = json.loads(stream.readline())
                        if response.get('request_id') == request_id:
                            assert response['error'] == 'success', response
                            return response.get('data')
                until(lambda: calls and calls[0][0] == 'Sessions/Playing')
                assert calls[0][1]['PositionTicks'] >= 20_000_000
                def visible_window():
                    windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', 'jelly-cli window test'], capture_output=True, text=True)
                    return windows.returncode == 0 and windows.stdout.strip()
                until(visible_window)
                until(lambda: any(t.get('external') and t.get('selected') for t in command('get_property', 'track-list')))
                command('set_property', 'pause', True)
                until(lambda: any(path.endswith('/Progress') and state['IsPaused'] for path, state in calls))
                command('seek', 6, 'absolute+exact')
                until(lambda: command('get_property', 'time-pos') >= 5.9)
                command('set_property', 'pause', False)
                until(lambda: any(path.endswith('/Progress') and not state['IsPaused'] and state['PositionTicks'] >= 59_000_000 for path, state in calls))
                if end == 'quit':
                    command('quit')
                else:
                    command('seek', 11, 'absolute+exact')
                worker.join(10)
                assert not worker.is_alive(), 'Player did not stop'
                assert not errors, errors
                assert calls[-1][0] == 'Sessions/Playing/Stopped', calls
                assert calls[-1][1]['Failed'] is False
                if end == 'quit':
                    assert 59_000_000 <= calls[-1][1]['PositionTicks'] < 120_000_000
                else:
                    assert calls[-1][1]['PositionTicks'] == 120_000_000, calls[-1]
                assert not Path(paths[0]).parent.exists(), 'IPC directory was not cleaned up'
            finally:
                if worker.is_alive():
                    try:
                        control.sendall(b'{"command":["quit"]}\n')
                    except OSError:
                        pass
                    worker.join(5)
                control.close()
print('Windowed playback verified: resume, subtitles, pause, seek, early quit, EOF and reports.')
