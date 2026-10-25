# Development

Python 3.10+; no third-party Python runtime dependencies.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_release.py
python3 -m jelly_cli --doctor
```

Real window tests need mpv, ffmpeg, Xvfb, xauth and xdotool. Tests skip them if unavailable. Run with a temporary XDG_CONFIG_HOME when experimenting with accounts. Never commit credentials, session files or private media.

The app is split into terminal flows (`cli.py`), API access (`client.py`), player control (`playback.py`), ordered reports (`reporting.py`), and profile preferences (`settings.py`). Keep network mutations explicit and do not turn read retries into repeated POST/DELETE requests. Credentials must stay out of process arguments and logs.

For a release, update `jelly_cli/__init__.py` and `install.sh` together, update release notes and run checks. The package metadata reads the module version. The build refuses mismatched installer versions. Deploy new version directories; never overwrite published release contents. A matching `vX.Y.Z` tag runs CI and creates a draft GitHub release for review.
