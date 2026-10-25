import json
import threading
import unittest
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from jelly_cli.client import Client, normalize_url


class Handler(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, body, self.headers.get('Authorization')))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'AccessToken': 'secret', 'User': {'Id': 'user1'}}).encode())
    def do_GET(self):
        self.calls.append((self.path, None, self.headers.get('Authorization')))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"Items": [], "TotalRecordCount": 0}')


class ClientTests(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(normalize_url(' localhost:8096/jellyfin/ '), 'http://localhost:8096/jellyfin')
        for bad in ('', 'file:///tmp/a', 'https://user:pass@host', 'http://host?q=1'):
            with self.assertRaises(ValueError):
                normalize_url(bad)

    def test_subtitle_urls_and_stream_metadata(self):
        client = Client('https://media.example/jellyfin', 'test')
        client.token = 'secret'
        streams = client.subtitle_streams('item', {'Id': 'source', 'MediaStreams': [
            {'Type': 'Audio', 'Index': 0},
            {'Type': 'Subtitle', 'Index': 1, 'IsExternal': False, 'Codec': 'pgssub'},
            {'Type': 'Subtitle', 'Index': 2, 'IsExternal': True, 'Codec': 'subrip'},
            {'Type': 'Subtitle', 'Index': 3, 'IsExternal': True, 'Codec': 'ass'},
        ]})
        self.assertEqual(len(streams), 3)
        self.assertNotIn('Url', streams[0])
        self.assertEqual(streams[1]['Url'], 'https://media.example/jellyfin/Videos/item/source/Subtitles/2/Stream.srt')
        self.assertTrue(streams[2]['Url'].endswith('Stream.ass'))
        self.assertNotIn('secret', str(streams))

    def test_login_base_path_and_search_encoding(self):
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = Client(f'http://127.0.0.1:{server.server_port}/jellyfin', 'test-device')
            client.login('neo', 'password')
            client.items(SearchTerm='a & b', Recursive='true')
            self.assertEqual(Handler.calls[-2][0], '/jellyfin/Users/AuthenticateByName')
            self.assertEqual(Handler.calls[-2][1], {'Username': 'neo', 'Pw': 'password'})
            self.assertIn('SearchTerm=a+%26+b', Handler.calls[-1][0])
            self.assertIn('Token="secret"', Handler.calls[-1][2])
            self.assertNotIn('secret', Handler.calls[-1][0])
            client.resume_items(StartIndex=200)
            path, _, auth = Handler.calls[-1]
            parsed = urlsplit(path)
            self.assertEqual(parsed.path, '/jellyfin/Users/user1/Items/Resume')
            params = parse_qs(parsed.query)
            self.assertEqual(params['StartIndex'], ['200'])
            self.assertEqual(params['IncludeItemTypes'], ['Movie,Episode'])
            self.assertEqual(params['EnableUserData'], ['true'])
            self.assertEqual(params['EnableImages'], ['false'])
            self.assertIn('Token="secret"', auth)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
