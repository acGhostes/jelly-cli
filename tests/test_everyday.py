import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from jelly_cli import cli
from jelly_cli.client import Client, ClientError, SameOriginRedirect
from jelly_cli.settings import DEFAULTS, profile_path, save_settings, load_settings
from urllib.request import Request


class EverydayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.directory.name, 'JELLY_CLI_PROFILE': 'default'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def test_profile_isolation_and_settings_validation(self):
        save_settings(dict(DEFAULTS, fullscreen=True, audio_language='eng,jpn'))
        self.assertEqual(profile_path('settings.json').stat().st_mode & 0o777, 0o600)
        with patch.dict(os.environ, {'JELLY_CLI_PROFILE': 'family'}):
            self.assertFalse(load_settings()['fullscreen'])
            save_settings(dict(DEFAULTS, volume=35))
        self.assertTrue(load_settings()['fullscreen'])
        self.assertEqual(load_settings()['volume'], 100)
        with patch.dict(os.environ, {'JELLY_CLI_PROFILE': '../../bad'}), self.assertRaises(ValueError):
            profile_path('session.json')
        with self.assertRaises(ValueError):
            save_settings(dict(DEFAULTS, volume=101))
        profile_path('settings.json').write_text('[]')
        with self.assertRaisesRegex(RuntimeError, 'reset-settings'):
            load_settings()

    def test_resume_start_over_and_explicit_mutations(self):
        item = {'Id': 'movie', 'Name': 'Movie', 'UserData': {'PlaybackPositionTicks': 600_000_000}}
        client = Mock()
        client.detail.return_value = dict(item, UserData={'IsFavorite': True})
        with patch.object(cli, 'choose', side_effect=[2, 0]):
            self.assertEqual(cli.details(client, item), 'start')
        client.favorite.assert_called_once_with('movie', True)
        client.watched.assert_not_called()
        with patch.object(cli, 'choose', return_value=0):
            self.assertEqual(cli.details(client, item), 'resume')
        with patch.object(cli, 'choose', return_value=None):
            self.assertIsNone(cli.details(client, item))

    def test_autoplay_only_after_natural_completion(self):
        save_settings(dict(DEFAULTS, autoplay=True))
        first = {'Id': 'one', 'Type': 'Episode', 'SeriesId': 'show'}
        second = dict(first, Id='two')
        client = Mock()
        client.detail.side_effect = [first, second]
        client.next_episode.return_value = second
        with patch.object(cli, 'details', return_value='resume'), patch.object(cli, 'play', side_effect=[True, False]) as player, patch.object(cli, 'choose', return_value=2):
            cli.watch(client, first)
        self.assertEqual(player.call_count, 2)
        client.next_episode.assert_called_once_with(first)

    def test_page_cache_back_navigation_and_empty_result(self):
        fetch = Mock(side_effect=[{'Items': [{'Id': '1'}], 'TotalRecordCount': 201}, {'Items': [{'Id': '2'}], 'TotalRecordCount': 201}])
        with patch.object(cli, 'choose', side_effect=[1, 1, 0]):
            self.assertEqual(cli.select_page('Movies', fetch)['Id'], '1')
        self.assertEqual(fetch.call_count, 2)
        with patch.object(cli, 'choose', return_value=None) as menu:
            self.assertIsNone(cli.select_page('Empty', lambda _: {'Items': [], 'TotalRecordCount': 100}))
            self.assertEqual(menu.call_args.args[1], [])

    def test_favorite_and_watched_methods_and_next_up(self):
        client = Client('https://example.org/jellyfin', 'device')
        client.user_id = 'user'
        with patch.object(client, 'request', return_value={}) as request:
            client.favorite('movie', False)
            self.assertEqual(request.call_args.kwargs['method'], 'DELETE')
            client.watched('movie', True)
            self.assertEqual(request.call_args.args[0], 'Users/user/PlayedItems/movie')
            self.assertEqual(request.call_args.kwargs['method'], 'POST')
            client.next_up(StartIndex=200)
            self.assertEqual(request.call_args.args[1]['StartIndex'], 200)

    def test_next_episode_never_jumps_backwards(self):
        client = Client('https://example.org', 'device')
        episode = {'Id': 'one', 'Type': 'Episode', 'SeriesId': 'show'}
        with patch.object(client, 'request', return_value={'Items': [{'Id': 'wrong'}, {'Id': 'two'}]}):
            self.assertIsNone(client.next_episode(episode))
        with patch.object(client, 'request', return_value={'Items': [{'Id': 'one'}, {'Id': 'two'}]}):
            self.assertEqual(client.next_episode(episode)['Id'], 'two')

    def test_session_expiry_prompts_but_network_failure_preserves_login(self):
        client = Client('https://example.org', 'device')
        client.token, client.user_id = 'saved-token', 'user'
        path = cli.config_path()
        cli.save_session(path, client, 'nick')
        with patch.object(Client, 'request', side_effect=ClientError('offline')), patch('builtins.input') as prompt:
            with self.assertRaisesRegex(ClientError, 'offline'):
                cli.connect(path)
            prompt.assert_not_called()
        self.assertIn('saved-token', path.read_text())
        with patch.object(Client, 'request', side_effect=[ClientError('expired', 401), {'AccessToken': 'new', 'User': {'Id': 'user'}}]), patch('builtins.input', side_effect=['', '']), patch('getpass.getpass', return_value='pw'):
            self.assertEqual(cli.connect(path).token, 'new')
        self.assertNotIn('pw', path.read_text())

    def test_credentials_not_forwarded_to_another_origin(self):
        handler = SameOriginRedirect()
        request = Request('https://example.org/jellyfin', headers={'Authorization': 'secret'})
        for target in ('https://elsewhere.example/', 'http://example.org/', 'https://example.org:9443/'):
            with self.assertRaises(ClientError):
                handler.redirect_request(request, None, 302, '', {}, target)

    def test_diagnostics_does_not_print_token(self):
        client = Client('https://example.org', 'device')
        client.token, client.user_id = 'private-token', 'user'
        cli.save_session(cli.config_path(), client, 'nick')
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            cli.doctor()
        self.assertNotIn('private-token', output.getvalue())
        self.assertNotIn('https://example.org', output.getvalue())
