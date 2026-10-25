import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from jelly_cli import cli
from jelly_cli.client import Client


class TerminalTests(unittest.TestCase):
    def test_saved_token_permissions_and_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config' / 'session.json'
            client = Client('https://example.com/jellyfin', 'device')
            client.token, client.user_id = 'secret-token', 'user'
            cli.save_session(path, client, 'name')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn('password', path.read_text())
            with patch.object(Client, 'request', return_value={}) as request, patch('builtins.input') as prompt:
                restored = cli.connect(path)
                self.assertEqual(restored.token, 'secret-token')
                request.assert_called_once_with('Users/Me')
                prompt.assert_not_called()

    def test_corrupt_session_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            path.write_text('bad json')
            def login(client, username, password):
                client.token, client.user_id = 'new-token', 'user'
            with patch('builtins.input', side_effect=['https://example.com', 'name']), patch('getpass.getpass', return_value='password'), patch.object(Client, 'login', login):
                cli.connect(path, setup=True)
            self.assertEqual(json.loads(path.read_text())['token'], 'new-token')

    def test_pagination_and_identity(self):
        fetch = Mock(side_effect=[{'Items': [{'Id': 'a', 'Name': 'Same'}], 'TotalRecordCount': 201},
                                  {'Items': [{'Id': 'b', 'Name': 'Same'}], 'TotalRecordCount': 201}])
        with patch.object(cli, 'choose', side_effect=[1, 0]):
            self.assertEqual(cli.select_page('Movies', fetch)['Id'], 'b')
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [0, 200])

    def test_menu_cancellation_and_control_characters(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 130, '')) as run:
            self.assertIsNone(cli.choose('Search', ['title\n\x1b[31m']))
            self.assertNotIn('\x1b', run.call_args.kwargs['input'])

    def test_replay_and_next_episode(self):
        client = Mock()
        item = {'Id': 'one', 'Type': 'Episode', 'SeriesId': 'show'}
        client.detail.side_effect = [item, item, {'Id': 'two', 'Type': 'Episode', 'SeriesId': 'show'}]
        client.next_episode.return_value = {'Id': 'two', 'Type': 'Episode', 'SeriesId': 'show'}
        with patch.object(cli, 'details', return_value='resume'), patch.object(cli, 'choose', side_effect=[1, 0, 2]), patch.object(cli, 'play', return_value=False) as play:
            cli.watch(client, item)
        self.assertEqual([call.kwargs['restart'] for call in play.call_args_list], [False, True, False])
        self.assertEqual(play.call_args.args[1]['Id'], 'two')

    @unittest.skipUnless(shutil.which('mpv'), 'mpv required')
    def test_real_mpv_reports_and_private_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / 'sample.wav'
            with wave.open(str(media), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b'\0\0' * 8000)
            client = Mock()
            client.authorization = 'secret-token'
            client.playback.return_value = dict(url=str(media), source_id='source', session_id='session', subtitles=[])
            original = subprocess.Popen
            commands = []
            def launch(args, **kwargs):
                commands.append(args)
                return original(args + ['--vo=null', '--ao=null'], **kwargs)
            with patch.dict(os.environ, {'JELLY_CLI_VIDEO': 'tct'}), patch('subprocess.Popen', side_effect=launch):
                cli.play(client, {'Id': 'movie', 'Name': 'Movie'})
            self.assertNotIn('secret-token', repr(commands))
            self.assertFalse(any(arg.startswith('--vo=') for args in commands for arg in args))
            self.assertIn('--input-terminal=no', commands[0])
            reports = client.request.call_args_list
            self.assertEqual(reports[0].args[0], 'Sessions/Playing')
            self.assertEqual(reports[-1].args[0], 'Sessions/Playing/Stopped')
            self.assertGreater(reports[-1].kwargs['body']['PositionTicks'], 0)
            socket_arg = next(arg for args in commands for arg in args if arg.startswith('--input-ipc-server='))
            self.assertFalse(Path(socket_arg.split('=', 1)[1]).parent.exists())


if __name__ == '__main__':
    unittest.main()
