# Ubuntu deployment

Public installer: `https://saltvaultvideo.com/jelly-cli`

Existing server installer: `/var/www/jelly-cli/install.sh`

The public endpoint was checked and currently returns the placeholder. The release bundle is ready locally; it has not been deployed.

## Deploy directly from the shared folder

The Docker mount maps `/home/coder/projects` to `/home/nick/code` on the Ubuntu host. The built files are therefore already on the host.

Run in the **Ubuntu host terminal** (`nick@ubuntuserver`):

```sh
sudo python3 /home/nick/code/jelly-cli/scripts/deploy_host.py
```

This verifies release checksums, validates the candidate Caddyfile, backs up the original config and installer, publishes releases, adds only the following route, reloads Caddy only if the release route changed, and replaces the placeholder installer. On failure during config reload or installer replacement it restores the previous config and installer. Existing reverse-proxy text is preserved exactly.

```caddyfile
    handle_path /jelly-cli/releases/* {
        root * /var/www/jelly-cli/releases
        file_server
    }
```

The new route is inserted immediately before the existing `/jelly-cli` handler. It strips `/jelly-cli/releases` from requests before serving the versioned files. All other paths continue through the existing handlers. The script is safe to repeat with identical release files. It rejects changes to an already published version; bump the version for new contents.

After deployment:

```sh
curl -fsSL https://saltvaultvideo.com/jelly-cli | head -n 8
curl -f https://saltvaultvideo.com/jelly-cli/releases/1.0.0/jelly-cli-linux-x86_64.pyz.sha256
curl -I https://saltvaultvideo.com
```

Caddy's actual validation and reload run on the host; they cannot be exercised from this container. The Python tests verify exact preservation of existing configuration and repeat-deployment behavior.

## Replace the placeholder

Upload `dist/jelly-cli-hosting.zip` to the Ubuntu server and extract it into a staging directory. The archive contains `install.sh` and `releases/1.0.0/` with three architecture assets and their checksums.

From that extracted directory, verify and publish the assets **before** replacing the installer:

```sh
(cd releases/1.0.0 && sha256sum -c jelly-cli-linux-x86_64.pyz.sha256 && sha256sum -c jelly-cli-linux-aarch64.pyz.sha256 && sha256sum -c jelly-cli-linux-armv7.pyz.sha256)
sudo install -d -m 755 /var/www/jelly-cli/releases/1.0.0
sudo install -m 644 releases/1.0.0/* /var/www/jelly-cli/releases/1.0.0/
```

Confirm Caddy already serves static release files at this URL, rather than returning HTML or proxying to Jellyfin:

```sh
curl -f https://saltvaultvideo.com/jelly-cli/releases/1.0.0/jelly-cli-linux-x86_64.pyz.sha256
```

The returned checksum must match the staged checksum file. If the current Caddy configuration only handles the exact `/jelly-cli` path, stop here: the release subpath needs a dedicated static-file route before the installer can work. Inspect the existing configuration first; do not replace the site block or its Jellyfin reverse proxy.

Once asset routing works, back up and atomically replace the placeholder:

```sh
sudo cp -p /var/www/jelly-cli/install.sh /var/www/jelly-cli/install.sh.backup
sudo install -m 644 install.sh /var/www/jelly-cli/install.sh.new
sudo mv /var/www/jelly-cli/install.sh.new /var/www/jelly-cli/install.sh
curl -fsSL https://saltvaultvideo.com/jelly-cli | head -n 8
```

Replacing static files needs no Caddy reload. These commands do not modify Caddy configuration or Jellyfin. Future releases should use a new version directory so existing versioned downloads remain immutable.

## User installation

```sh
curl --proto '=https' --proto-redir '=https' -fsSL https://saltvaultvideo.com/jelly-cli -o /tmp/jelly-cli-install.sh
sh /tmp/jelly-cli-install.sh --install-deps
jelly-cli
```

The installer checks Linux and architecture before installing dependencies. It supports x86-64, ARM64 and ARMv7; unsupported platforms receive a clear error. Assets are Python zip applications, identical portable code under architecture-specific filenames. System Python 3.10+, fzf, and mpv are still required. `--install-deps` uses apt/pacman/dnf, including sudo when needed. It installs the application in the invoking user's home directory; do not run the entire installer with sudo unless you intend to install for root.

No desktop launcher is created. If `~/.local/bin` is absent from PATH, follow the installer's printed instruction. Browsing stays in the terminal; playback opens a normal mpv window. ARM download selection is tested via simulation; actual playback testing was performed on Linux x86-64.
