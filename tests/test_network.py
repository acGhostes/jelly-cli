import io
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from jelly_cli.client import Client, ClientError


class NetworkTests(unittest.TestCase):
    def test_get_retries_once_but_post_does_not(self):
        client = Client('https://example.org', 'device')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"Items": []}'
        with patch.object(client.opener, 'open', side_effect=[URLError('offline'), response]) as opened, patch('time.sleep'):
            self.assertEqual(client.items(), {'Items': []})
            self.assertEqual(opened.call_count, 2)
        with patch.object(client.opener, 'open', side_effect=URLError('offline')) as opened:
            with self.assertRaises(ClientError):
                client.request('Sessions/Playing', body={})
            self.assertEqual(opened.call_count, 1)

    def test_unauthorized_has_status_and_does_not_retry(self):
        client = Client('https://example.org', 'device')
        error = HTTPError('https://example.org', 401, 'Unauthorized', {}, io.BytesIO(b'private'))
        with patch.object(client.opener, 'open', side_effect=error) as opened:
            with self.assertRaises(ClientError) as caught:
                client.items()
        self.assertEqual(caught.exception.status, 401)
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(opened.call_count, 1)

    def test_html_instead_of_json_has_actionable_error(self):
        client = Client('https://example.org', 'device')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'<html>wrong proxy</html>'
        with patch.object(client.opener, 'open', return_value=response):
            with self.assertRaisesRegex(ClientError, 'reverse-proxy'):
                client.items()
