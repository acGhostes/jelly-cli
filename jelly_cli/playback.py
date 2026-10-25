"""Windowed mpv playback and ordered Jellyfin session reporting."""
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .reporting import PlaybackReports
from .settings import load_settings
from .text import clean

def play(client, item, restart=False):
    settings = load_settings()
    media = client.playback(item)
    position = 0 if restart else (item.get('UserData') or {}).get('PlaybackPositionTicks', 0) / 10_000_000
    state = dict(PositionTicks=int(position * 10_000_000), IsPaused=False, CanSeek=True, PlayMethod='DirectStream')
    report_errors = []
    reports = PlaybackReports(client, item['Id'], media['source_id'], media['session_id'],
                              report_errors.append, lambda _: None)
    failed = False
    loaded = False
    completed = False
    duration = 0.0
    print('Playing in mpv — close the window or press Q to return.')
    with tempfile.TemporaryDirectory(prefix='jelly-cli-') as directory:
        ipc = str(Path(directory) / 'mpv.sock')
        process = subprocess.Popen(['mpv', '--no-config', '--load-scripts=no', '--idle=yes',
                                    '--keep-open=no', '--terminal=no', '--input-terminal=no', '--hwdec=auto-safe',
                                    '--sub-visibility=' + ('yes' if settings['subtitles'] else 'no'),
                                    '--fullscreen=' + ('yes' if settings['fullscreen'] else 'no'),
                                    '--volume=' + str(settings['volume']),
                                    '--alang=' + settings['audio_language'], '--slang=' + settings['subtitle_language'],
                                    '--input-ipc-server=' + ipc,
                                    '--start=' + str(position)], stdout=None, stderr=subprocess.DEVNULL)
        connection = socket.socket(socket.AF_UNIX)
        def command(*args):
            connection.sendall(json.dumps({'command': args}).encode() + b'\n')
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    connection.connect(ipc)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('mpv failed to start its control socket.')
                    time.sleep(.05)
            connection.settimeout(.5)
            command('set_property', 'http-header-fields', ['Authorization: ' + client.authorization])
            command('set_property', 'force-media-title', clean(item.get('Name', 'jelly-cli')))
            for index, name in enumerate(('time-pos', 'pause', 'duration')):
                command('observe_property', index, name)
            command('loadfile', media['url'])
            buffer = b''
            last_report = time.monotonic()
            deadline = last_report + 45
            finished = False
            while not finished:
                try:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
                except socket.timeout:
                    pass
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    event = json.loads(line)
                    if event.get('event') == 'file-loaded':
                        loaded = True
                        reports.start(dict(state))
                        subtitles = media['subtitles']
                        selected = next((sub for sub in subtitles if sub.get('Index') == media.get('default_subtitle')), None)
                        preferred = settings['subtitle_language'].lower().split(',')
                        selected = next((sub for sub in subtitles if sub.get('Url') and str(sub.get('Language', '')).lower() in preferred and sub.get('Language')), selected)
                        if selected is None and not any(not sub.get('Url') for sub in subtitles):
                            selected = next(iter(subtitles), None)
                        for subtitle in subtitles:
                            if subtitle.get('Url'):
                                command('sub-add', subtitle['Url'], 'select' if subtitle is selected else 'auto')
                    elif event.get('event') == 'property-change' and event.get('data') is not None:
                        if event.get('name') == 'time-pos':
                            state['PositionTicks'] = int(max(0, event['data']) * 10_000_000)
                        elif event.get('name') == 'duration':
                            duration = max(0.0, float(event['data']))
                        elif event.get('name') == 'pause':
                            state['IsPaused'] = bool(event['data'])
                            reports.progress(dict(state))
                    elif event.get('event') == 'end-file':
                        failed = event.get('reason') == 'error'
                        completed = event.get('reason') == 'eof'
                        if event.get('reason') == 'eof' and duration:
                            state['PositionTicks'] = int(duration * 10_000_000)
                        finished = True
                if time.monotonic() - last_report >= 10:
                    reports.progress(dict(state))
                    last_report = time.monotonic()
                if not loaded and time.monotonic() > deadline:
                    raise RuntimeError('Timed out opening the media stream.')
                if process.poll() is not None:
                    failed = process.returncode != 0
                    break
            if failed or not loaded:
                raise RuntimeError('mpv could not play this media. Check server access and codec support.')
        except Exception:
            failed = True
            raise
        finally:
            connection.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reports.stop(dict(state), failed=failed)
            reports.executor.shutdown(wait=True)
            for error in dict.fromkeys(report_errors):
                print('Watch progress: ' + error, file=sys.stderr)
    return completed

