"""Safe terminal text and human-readable media metadata."""
import re


def clean(text):
    return ''.join(c if c.isprintable() else ' ' for c in str(text))


def description(text):
    import html
    return clean(html.unescape(re.sub(r'<[^>]*>', ' ', str(text or ''))))


def timestamp(ticks):
    seconds = max(0, int(ticks or 0) // 10_000_000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'
