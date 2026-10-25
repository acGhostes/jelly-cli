"""Small, atomic, per-profile settings; existing default sessions stay compatible."""
import json
import os
from pathlib import Path
import re
import tempfile

DEFAULTS = {'fullscreen': False, 'autoplay': False, 'subtitles': True,
            'audio_language': '', 'subtitle_language': '', 'volume': 100}


def profile_path(filename):
    root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'jelly-cli'
    profile = os.environ.get('JELLY_CLI_PROFILE', 'default')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', profile):
        raise ValueError('Profile names must be 1–40 letters, numbers, underscores or hyphens.')
    return (root if profile == 'default' else root / 'profiles' / profile) / filename


def atomic_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.jelly-cli-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_settings():
    path = profile_path('settings.json')
    if not path.exists():
        return dict(DEFAULTS)
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError()
        return validate(value)
    except (ValueError, TypeError) as error:
        raise RuntimeError(f'Invalid preferences in {path}. Run jelly-cli --reset-settings.') from error


def validate(value):
    settings = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        option = value.get(key, default)
        if type(option) is not type(default):
            raise ValueError(f'Invalid {key}')
        settings[key] = option
    if not 0 <= settings['volume'] <= 100:
        raise ValueError('Volume must be 0–100.')
    for name in ('audio_language', 'subtitle_language'):
        if not re.fullmatch(r'[a-zA-Z0-9,-]{0,60}', settings[name]):
            raise ValueError('Use language codes such as eng,jpn.')
    return settings


def save_settings(settings):
    atomic_json(profile_path('settings.json'), validate(settings))
