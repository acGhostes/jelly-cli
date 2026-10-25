"""Small Jellyfin HTTP client. Used by terminal browsing and playback."""
import json
import uuid
import time
from . import __version__
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


def normalize_url(value):
    value = value.strip().rstrip('/')
    if '://' not in value:
        value = 'http://' + value
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Enter an HTTP(S) server address, optionally with a base path.')
    return value



class ClientError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        old, new = urlsplit(request.full_url), urlsplit(newurl)
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            raise ClientError('Server redirected to another address. Use the final Jellyfin URL in --setup.')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, address, device_id):
        self.address = normalize_url(address)
        self.device_id = device_id
        self.token = ''
        self.user_id = ''
        self.opener = build_opener(SameOriginRedirect())

    @property
    def authorization(self):
        base = f'MediaBrowser Client="jelly-cli", Device="Terminal", DeviceId="{self.device_id}", Version="{__version__}"'
        return base + (f', Token="{self.token}"' if self.token else '')

    def url(self, path, params=None):
        return self.address + '/' + path.lstrip('/') + ('?' + urlencode(params) if params else '')

    def request(self, path, params=None, body=None, raw=False, method=None):
        method = method or ('POST' if body is not None else 'GET')
        request = Request(self.url(path, params), method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'Authorization': self.authorization, 'Content-Type': 'application/json'})
        for attempt in range(2 if method == 'GET' else 1):
            try:
                with self.opener.open(request, timeout=10) as response:
                    data = response.read()
                    try:
                        return data if raw else (json.loads(data) if data else {})
                    except (ValueError, UnicodeDecodeError):
                        raise ClientError('Server returned an invalid response. Check its URL and reverse-proxy base path.') from None
            except HTTPError as exc:
                if method == 'GET' and attempt == 0 and exc.code in (502, 503, 504):
                    exc.close()
                    time.sleep(.25)
                    continue
                messages = {401: 'Login rejected or session expired. Sign in again with --setup.',
                            403: 'Your Jellyfin account does not have access to this resource.',
                            404: 'Resource not found. Check the server address and base path.'}
                status = exc.code
                exc.close()
                raise ClientError(messages.get(status, f'Jellyfin returned HTTP {status}.'), status) from None
            except (URLError, TimeoutError):
                if method == 'GET' and attempt == 0:
                    time.sleep(.25)
                    continue
                raise ClientError('Cannot reach Jellyfin. Check the address, network, and server.') from None

    def login(self, username, password):
        result = self.request('Users/AuthenticateByName', body={'Username': username, 'Pw': password})
        self.token, self.user_id = result['AccessToken'], result['User']['Id']
        return self

    def items(self, **params):
        options = {'Limit': 200, 'EnableUserData': 'true', 'EnableImages': 'false', 'Fields': 'RunTimeTicks', 'SortBy': 'SortName', 'SortOrder': 'Ascending'}
        options.update(params)
        return self.request(f'Users/{self.user_id}/Items', options)

    def resume_items(self, **params):
        options = {'Limit': 200, 'EnableUserData': 'true', 'EnableImages': 'false',
                   'IncludeItemTypes': 'Movie,Episode', 'EnableTotalRecordCount': 'true'}
        options.update(params)
        # This route remains compatible with older supported Jellyfin servers.
        return self.request(f'Users/{self.user_id}/Items/Resume', options)

    def next_up(self, **params):
        return self.request('Shows/NextUp', dict(UserId=self.user_id, Limit=200,
                            EnableImages='false', EnableUserData='true', **params))

    def favorite(self, item_id, enabled):
        return self.request(f'Users/{self.user_id}/FavoriteItems/{item_id}',
                            method='POST' if enabled else 'DELETE')

    def watched(self, item_id, enabled):
        return self.request(f'Users/{self.user_id}/PlayedItems/{item_id}',
                            method='POST' if enabled else 'DELETE')

    def next_episode(self, item):
        if item.get('Type') != 'Episode' or not item.get('SeriesId'):
            return None
        result = self.request(f"Shows/{item['SeriesId']}/Episodes", {
            'UserId': self.user_id, 'StartItemId': item['Id'], 'Limit': 2, 'EnableUserData': 'true'})
        episodes = result.get('Items', [])
        # Do not jump backwards if the server did not return the requested start item.
        if not episodes or episodes[0]['Id'] != item['Id']:
            return None
        return next((entry for entry in episodes[1:] if entry['Id'] != item['Id']), None)

    def detail(self, item_id):
        return self.request(f'Users/{self.user_id}/Items/{item_id}')

    def playback(self, item):
        result = self.request(f'Items/{item["Id"]}/PlaybackInfo', {'UserId': self.user_id})
        sources = result.get('MediaSources', [])
        if not sources:
            raise RuntimeError('No playable media source is available.')
        source = next((entry for entry in sources if entry.get('Id')), None)
        if source is None:
            raise ClientError('No valid media source is available.')
        return {'url': self.url(f'Videos/{item["Id"]}/stream', {'Static': 'true', 'MediaSourceId': source['Id']}),
                'source_id': source['Id'], 'session_id': result.get('PlaySessionId') or uuid.uuid4().hex,
                'subtitles': self.subtitle_streams(item['Id'], source),
                'default_subtitle': source.get('DefaultSubtitleStreamIndex')}

    def subtitle_streams(self, item_id, source):
        result = []
        for stream in source.get('MediaStreams') or []:
            if stream.get('Type') != 'Subtitle':
                continue
            entry = dict(stream)
            if stream.get('IsExternal'):
                codec = str(stream.get('Codec') or 'srt').lower()
                extension = {'subrip': 'srt', 'webvtt': 'vtt', 'mov_text': 'srt'}.get(codec, codec)
                if extension not in ('srt', 'ass', 'ssa', 'vtt', 'sup', 'sub'):
                    extension = 'srt'
                entry['Url'] = self.url(f"Videos/{item_id}/{source['Id']}/Subtitles/{stream['Index']}/Stream.{extension}")
            result.append(entry)
        return result
