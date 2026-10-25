# jelly-cli

**Your Jellyfin library. A terminal menu. One good player.**

Search and browse with the keyboard, then watch in a normal mpv window with subtitles, resume and Jellyfin watch tracking. Inspired by ani-cli, built for your own Jellyfin server.

## Install

Linux · Python 3.10+ · fzf · mpv

```sh
curl --proto '=https' --proto-redir '=https' -fsSL https://github.com/acGhostes/jelly-cli/releases/latest/download/install.sh -o /tmp/jelly-cli-install.sh
sh /tmp/jelly-cli-install.sh --install-deps
jelly-cli
```

The first launch asks for your server URL, username and password. Later launches reuse the saved session. Include a reverse-proxy base path if your server uses one.

`--install-deps` uses apt, pacman or dnf to install system dependencies; package availability depends on your repositories. On Arch/CachyOS it performs a full system upgrade. Omit this flag if Python, fzf and mpv are already installed. curl is needed to download the installer. Run the application installer as your normal user; it invokes sudo only for dependency installation.

The launcher installs to `~/.local/bin/jelly-cli`. If that directory is not on PATH, follow the printed shell-profile instruction or run it by full path. App files live in `~/.local/share/jelly-cli`. No desktop launcher is created. The installer chooses x86-64, ARM64 or ARMv7 and verifies its HTTPS download with SHA-256. Assets contain portable Python code; Python and mpv are not bundled.

The public install command requires a public repository and a published release. The installer downloads the matching version's executable and checksum from GitHub Releases; it never contacts the former personal-domain download endpoint.

For private-repository access, install GitHub CLI and authenticate with an account that can read this repository:

```sh
gh auth login
gh release download --repo acGhostes/jelly-cli --pattern install.sh --output /tmp/jelly-cli-install.sh --clobber
sh /tmp/jelly-cli-install.sh --install-deps --github-auth
jelly-cli
```

The GitHub CLI handles authentication; no token is put in the install command. `--base-url` can override the public release-download root for mirrors using `vVERSION/ASSET` paths. `--github-auth` always uses this GitHub repository.

## Daily use

```sh
jelly-cli                         # Home
jelly-cli the expanse              # Search immediately
jelly-cli -c                      # Continue Watching
jelly-cli --next-up                # Next episodes from Jellyfin
jelly-cli --settings               # Playback preferences
jelly-cli --doctor                 # Dependency/session diagnostics
```

Home includes Continue Watching, Next Up, Search, Movies, TV Shows, Recently Added and Favorites. Type to filter a page, use the arrow keys to move, Enter to select and Esc to return. Search queries the server; the menu filter searches the loaded page. Large libraries paginate in batches of 200. Up to eight recently visited pages are reused while navigating a list; returning after playback fetches fresh watch state.

Lists show `[X]` watched, `[~]` in progress, runtime, saved position and a favorite marker when available. Open a movie or episode to read its description and choose Resume, Start Over, Favorite or Mark Watched/Unwatched. Those last two actions update Jellyfin only when explicitly selected. Series open seasons and episodes in order.

After watching, replay, select the next episode, or return to the same library section. Optional autoplay advances **only after natural playback completion**; quitting mpv does not start another episode.

## Playback

| Key in mpv | Action |
| --- | --- |
| Space | Pause/resume |
| Left / Right | Seek |
| F | Fullscreen |
| J / Shift+J | Cycle subtitles |
| V | Toggle subtitles |
| # | Cycle audio tracks |
| 9 / 0 | Volume |
| Q / close window | Return to jelly-cli |

Preferences save fullscreen, autoplay, subtitle visibility, preferred audio/subtitle languages and starting volume. Use language codes such as `eng,jpn`. `jelly-cli --reset-settings` resets preferences without deleting the login.

mpv uses its normal video output and safe automatic hardware decoding. Embedded subtitles and external Jellyfin subtitle tracks are supported. Playback uses a private local IPC socket; tokens are never placed in command arguments. jelly-cli uses its own mpv settings to keep behavior predictable; personal mpv config files/scripts are not loaded.

Run jelly-cli on the PC where you want the video window and sound. A graphical desktop is required for normal playback. Running over SSH does not automatically display video or forward audio to your local machine.

### Watch tracking

jelly-cli sends playback start, periodic position updates, available pause/resume updates, and a final stop report. At natural EOF it reports the full duration. Jellyfin applies its configured watched thresholds, so stopping early does not automatically mark an item watched. Continue Watching and resume use the server's data.

Keep the terminal process running while watching. Network failures, forced termination or power loss can prevent the last report. Errors are shown; reports are not persisted for offline retry. Ordinary read requests retry once on transient network errors; writes are never automatically retried.

## Servers and profiles

```sh
jelly-cli --setup                         # Change the default account/server
jelly-cli --profile family --setup        # A separate account or server
jelly-cli --profile family                # Use it
jelly-cli --profile family --settings     # Its own playback preferences
jelly-cli --profile family --logout       # Revoke and forget that login
```

`JELLY_CLI_PROFILE` also selects a profile. The default profile preserves logins from earlier jelly-cli releases. Preferences and sessions live under `~/.config/jelly-cli`, or `$XDG_CONFIG_HOME/jelly-cli`; named profiles live in `profiles/NAME`. Files are written atomically with owner-only permissions. Passwords are never saved; session tokens are saved unencrypted, so protect your account and backups. Diagnostics do not print tokens or server URLs.

## Updates and removal

Repeat the install command to update. Login and preferences are preserved. A checksum failure leaves the installed release untouched. The checksum detects corruption; it is not a signature protecting against compromise of the hosting server.

```sh
jelly-cli --logout
sh /tmp/jelly-cli-install.sh --uninstall
```

Uninstall preserves profile files; use `--logout` on each profile to revoke its token first. Custom `XDG_DATA_HOME` and `JELLY_CLI_BIN_DIR` are supported; use the same values for updates and removal.

## Scope and troubleshooting

- Direct streaming only. No server transcoding negotiation, offline downloads or native Windows support.
- mpv uses the first valid media source. Multiple-version selection is not implemented.
- Linux x86-64 window playback is tested under Xvfb, including subtitles, resume, pause, seek, early quit and EOF reports. ARM download selection is tested; ARM playback and your GPU/Wayland setup require local verification.
- Live Jellyfin versions, network conditions, permissions and watched thresholds vary. API tests use local HTTP fixtures; a live-server acceptance check is still recommended before publishing a release.
- `jelly-cli --doctor` identifies missing executables and the active profile. `--setup` replaces an expired login; `--reset-settings` repairs preferences.
- Playback/network errors offer Retry, Home or Quit. A 401 requires signing in again.

## Development and releases

```sh
python3 -m jelly_cli
python3 -m unittest discover -s tests -v
python3 scripts/build_release.py
```

No third-party Python runtime dependencies. Integration checks use mpv, ffmpeg, Xvfb, xauth and xdotool; the real menu test additionally uses fzf. Missing integration tools cause explicit skips. GitHub CI installs those tools and runs Python 3.10 and 3.13.

Builds are reproducible and exclude sessions, caches and virtual environments. `dist/jelly-cli-hosting.zip` contains the installer, manifest and versioned architecture assets. See [deployment](DEPLOY.md), [contributing](CONTRIBUTING.md), and [release notes](RELEASE_NOTES.md). Tagging a matching version creates a draft GitHub release after checks pass.

Independent Jellyfin client; not an official Jellyfin product. The menu/player workflow is inspired by [ani-cli](https://github.com/pystardust/ani-cli); its scraper and shell source are not included.

## License

[MIT](LICENSE), copyright 2026 acGhostes.
