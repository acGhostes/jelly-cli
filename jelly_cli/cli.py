"""Terminal Jellyfin browser: Python standard library, fzf, and mpv."""
import argparse
from collections import OrderedDict
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import textwrap
import platform

from . import __version__

from .client import Client, ClientError
from .playback import play
from .settings import load_settings, save_settings, profile_path, atomic_json
from .text import clean, description, timestamp


def config_path():
    return profile_path('session.json')


def save_session(path, client, username):
    atomic_json(path, dict(address=client.address, device_id=client.device_id,
                           token=client.token, user_id=client.user_id, username=username))


def connect(path, setup=False):
    saved = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            if not isinstance(saved, dict):
                raise ValueError()
        except (ValueError, OSError):
            if not setup:
                raise RuntimeError('Cannot read saved session. Run jelly-cli --setup to replace it.') from None
            saved = {}
    if saved and not setup:
        try:
            client = Client(saved['address'], saved['device_id'])
            client.token, client.user_id = saved['token'], saved['user_id']
        except (KeyError, ValueError):
            raise RuntimeError('Invalid saved session. Run jelly-cli --setup.') from None
        try:
            client.request('Users/Me')
            return client
        except RuntimeError as exc:
            if not (isinstance(exc, ClientError) and exc.status == 401):
                raise
            print('Your saved login has expired. Sign in again.')
    address = input(f"Jellyfin server [{saved.get('address', '')}]: ").strip() or saved.get('address', '')
    username = input(f"Username [{saved.get('username', '')}]: ").strip() or saved.get('username', '')
    client = Client(address, saved.get('device_id') or uuid.uuid4().hex)
    client.login(username, getpass.getpass('Password: '))
    save_session(path, client, username)
    print('Login saved. Your password is not stored.')
    return client


def choose(prompt, entries, header='Type to filter · Enter selects · Esc goes back'):
    """Return an index, retaining identity even when titles are identical."""
    if not entries:
        print('No results.')
        return None
    result = subprocess.run(['fzf', '--reverse', '--cycle', '--no-multi', '--delimiter=\t',
                             '--with-nth=2..', '--prompt=' + clean(prompt) + ' > ',
                             '--header=' + clean(header), '--border=rounded', '--height=80%', '--layout=reverse',
                             '--info=inline', '--color=fg+:white,bg+:24,hl:cyan,hl+:cyan,pointer:cyan'],
                            input='\n'.join(f'{i}\t{clean(label)}' for i, label in enumerate(entries)),
                            text=True, stdout=subprocess.PIPE,
                            env={**os.environ, 'FZF_DEFAULT_OPTS': '', 'FZF_DEFAULT_OPTS_FILE': ''})
    if result.returncode in (1, 130):
        return None
    if result.returncode:
        raise RuntimeError('fzf could not open the terminal menu.')
    return int(result.stdout.split('\t', 1)[0])


def label(item):
    data = item.get('UserData') or {}
    mark = 'X' if data.get('Played') else '~' if data.get('PlaybackPositionTicks') else ' '
    title = item.get('Name', 'Untitled')
    if item.get('Type') == 'Episode':
        title = f"{item.get('SeriesName', '')} S{(item.get('ParentIndexNumber') or 0):02}E{(item.get('IndexNumber') or 0):02} — {title}"
    year = f" ({item['ProductionYear']})" if item.get('ProductionYear') else ''
    duration = f" · {int(item['RunTimeTicks']) // 600_000_000} min" if item.get('RunTimeTicks') else ''
    resume = f" · {timestamp(data.get('PlaybackPositionTicks'))}" if data.get('PlaybackPositionTicks') else ''
    favorite = ' ♥' if data.get('IsFavorite') else ''
    return f'[{mark}] {title}{year}{duration}{resume}{favorite}'


def select_page(prompt, fetch):
    offset = 0
    pages = OrderedDict()
    while True:
        if offset not in pages:
            pages[offset] = fetch(offset)
            if len(pages) > 8:
                pages.popitem(last=False)
        pages.move_to_end(offset)
        result = pages[offset]
        items = result.get('Items', [])
        labels = [label(item) for item in items]
        more = bool(items) and offset + len(items) < result.get('TotalRecordCount', offset + len(items))
        actions = (['Next page'] if more else []) + (['Previous page'] if offset else [])
        selected = choose(prompt, labels + actions)
        if selected is None:
            return None
        if selected < len(items):
            return items[selected]
        offset += 200 if actions[selected - len(items)] == 'Next page' else -200


def settings_menu():
    while True:
        settings = load_settings()
        actions = [f"Fullscreen: {'on' if settings['fullscreen'] else 'off'}",
                   f"Autoplay next episode: {'on' if settings['autoplay'] else 'off'}",
                   f"Subtitles: {'on' if settings['subtitles'] else 'off'}",
                   f"Audio language: {settings['audio_language'] or 'server default'}",
                   f"Subtitle language: {settings['subtitle_language'] or 'server default'}",
                   f"Starting volume: {settings['volume']}%", 'Back']
        choice = choose('Preferences', actions)
        if choice is None or choice == 6:
            return
        if choice < 3:
            key = ('fullscreen', 'autoplay', 'subtitles')[choice]
            settings[key] = not settings[key]
        elif choice < 5:
            key = ('audio_language', 'subtitle_language')[choice - 3]
            settings[key] = input('Language codes, e.g. eng,jpn (blank for default): ').strip()
        else:
            try:
                settings['volume'] = int(input('Starting volume (0–100): '))
            except ValueError:
                print('Enter a number from 0 to 100.')
                continue
        try:
            save_settings(settings)
        except ValueError as error:
            print(str(error))


def details(client, item):
    """Return a playback choice; remote mutations only happen on explicit selection."""
    while True:
        data = item.get('UserData') or {}
        print('\n' + clean(label(item)))
        overview = description(item.get('Overview'))
        if overview:
            print(textwrap.fill(overview[:1800], width=min(100, shutil.get_terminal_size().columns)))
        actions = [('resume', 'Resume at ' + timestamp(data['PlaybackPositionTicks']))] if data.get('PlaybackPositionTicks') else []
        actions += [('start', 'Start over' if actions else 'Play'),
                    ('favorite', 'Remove favorite' if data.get('IsFavorite') else 'Add to favorites'),
                    ('watched', 'Mark unwatched' if data.get('Played') else 'Mark watched'), ('back', 'Back')]
        selected = choose('Watch', [label for _, label in actions])
        if selected is None or actions[selected][0] == 'back':
            return None
        action = actions[selected][0]
        if action in ('resume', 'start'):
            return action
        if action == 'favorite':
            client.favorite(item['Id'], not data.get('IsFavorite'))
        elif action == 'watched':
            client.watched(item['Id'], not data.get('Played'))
        item = client.detail(item['Id'])


def watch(client, item):
    restart = False
    show_details = True
    while item:
        if item.get('Type') in ('Series', 'Season'):
            selected = select_page(item['Name'], lambda start: client.items(
                ParentId=item['Id'], StartIndex=start, SortBy='ParentIndexNumber,IndexNumber,SortName'))
            if selected:
                watch(client, selected)
                continue
            return
        item = client.detail(item['Id'])
        if show_details:
            action = details(client, item)
            if action is None:
                return
            restart = action == 'start'
        completed = play(client, item, restart=restart)
        restart, show_details = False, False
        if completed and load_settings()['autoplay']:
            following = client.next_episode(item)
            if following:
                item = following
                continue
        actions = ['Replay', 'Back']
        if item.get('Type') == 'Episode' and item.get('SeriesId'):
            actions.insert(0, 'Next episode')
        choice = choose('Finished' if completed else 'Stopped', actions)
        if choice is None or actions[choice] == 'Back':
            return
        if actions[choice] == 'Replay':
            restart = True
            continue
        item = client.next_episode(item)
        if not item:
            print('No next episode available.')


def doctor():
    print(f'jelly-cli {__version__} · Python {platform.python_version()} · {platform.system()} {platform.machine()}')
    missing = []
    for program in ('fzf', 'mpv'):
        path = shutil.which(program)
        print(f"{program}: {path or 'missing'}")
        if not path:
            missing.append(program)
    print('Graphical session: ' + ('available' if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY') else 'not detected'))
    print('Profile: ' + os.environ.get('JELLY_CLI_PROFILE', 'default'))
    print('Saved login: ' + ('present' if config_path().exists() else 'not configured'))
    print('Preferences: ' + str(profile_path('settings.json')))
    return 1 if missing else 0


def browse(client, initial=None, query=''):
    mode = initial
    while True:
        try:
            if mode is None:
                actions = ['Continue watching', 'Next up', 'Search', 'Movies', 'TV shows',
                           'Recently added', 'Favorites', 'Preferences', 'Quit']
                selected = choose('jelly-cli', actions, 'Your library · [X] watched · [~] in progress · Esc quits')
                if selected is None or actions[selected] == 'Quit':
                    return
                mode = actions[selected]
            if mode == 'Preferences':
                settings_menu()
                mode = None
                continue
            if mode == 'Search':
                query = query or input('Search Jellyfin: ').strip()
                if not query:
                    mode = None
                    continue
                fetch = lambda start: client.items(SearchTerm=query, Recursive='true', IncludeItemTypes='Movie,Series,Episode', StartIndex=start)
            elif mode == 'Continue watching':
                fetch = lambda start: client.resume_items(StartIndex=start)
            elif mode == 'Next up':
                fetch = lambda start: client.next_up(StartIndex=start)
            else:
                options = dict(Recursive='true', IncludeItemTypes='Movie' if mode == 'Movies' else 'Series' if mode == 'TV shows' else 'Movie,Series,Episode')
                if mode == 'Favorites':
                    options['Filters'] = 'IsFavorite'
                elif mode == 'Recently added':
                    options.update(SortBy='DateCreated', SortOrder='Descending')
                fetch = lambda start: client.items(StartIndex=start, **options)
            print('Loading ' + mode.lower() + '…', flush=True)
            item = select_page(mode, fetch)
            if item:
                watch(client, item)
                # Stay in the same section and fetch fresh watch state after playback.
                continue
            query, mode = '', None
        except (ClientError, RuntimeError, OSError, ValueError) as error:
            print('jelly-cli: ' + str(error), file=sys.stderr)
            if isinstance(error, ClientError) and error.status == 401:
                raise
            choice = choose('Connection or playback problem', ['Try again', 'Home', 'Quit'])
            if choice is None or choice == 2:
                return
            if choice == 1:
                query, mode = '', None


def main(argv=None):
    parser = argparse.ArgumentParser(description='Browse your Jellyfin server with fzf and watch with mpv.')
    parser.add_argument('--version', action='version', version='jelly-cli ' + __version__)
    parser.add_argument('query', nargs='*', help='search your library')
    parser.add_argument('--profile', default=os.environ.get('JELLY_CLI_PROFILE', 'default'), help='separate server/account profile')
    parser.add_argument('--doctor', action='store_true', help='show dependency and session diagnostics without secrets')
    parser.add_argument('--settings', action='store_true', help='edit playback preferences')
    parser.add_argument('--reset-settings', action='store_true', help='reset this profile’s playback preferences')
    parser.add_argument('--next-up', action='store_true', help='open next unwatched episodes')
    parser.add_argument('--setup', action='store_true', help='change server or sign in again')
    parser.add_argument('-c', '--continue', dest='resume', action='store_true', help='continue watching')
    parser.add_argument('--logout', action='store_true', help='revoke and forget the saved session')
    args = parser.parse_args(argv)
    try:
        os.environ['JELLY_CLI_PROFILE'] = args.profile
        path = config_path()
        if args.doctor:
            return doctor()
        if args.reset_settings:
            from .settings import DEFAULTS
            save_settings(DEFAULTS)
            print('Preferences reset.')
            return 0
        if args.logout:
            if path.exists():
                data = json.loads(path.read_text())
                client = Client(data['address'], data['device_id'])
                client.token = data['token']
                try:
                    client.request('Sessions/Logout', body={})
                finally:
                    path.unlink()
            print('Saved login removed.')
            return 0
        for dependency in ('fzf', 'mpv'):
            if not shutil.which(dependency):
                raise RuntimeError(f'Install {dependency} with your package manager first.')
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError('Run jelly-cli in an interactive terminal.')
        if args.settings:
            settings_menu()
            return 0
        client = connect(path, args.setup)
        query = ' '.join(args.query)
        mode = 'Continue watching' if args.resume else 'Next up' if args.next_up else 'Search' if query else None
        browse(client, mode, query)
        return 0
    except (KeyboardInterrupt, EOFError):
        print()
        return 0
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print('jelly-cli: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
