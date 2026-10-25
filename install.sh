#!/bin/sh
set -eu
# Usage: sh install.sh [--install-deps] [--github-auth] [--uninstall]
base_url='https://github.com/acGhostes/jelly-cli/releases/download'
github_auth=no
install_deps=no
release_version='1.0.1'
uninstall=no
while [ "$#" -gt 0 ]; do
    case "$1" in
        --base-url) [ "$#" -ge 2 ] || exit 2; base_url=$2; shift 2 ;;
        --github-auth) github_auth=yes; shift ;;
        --install-deps) install_deps=yes; shift ;;
        --uninstall) uninstall=yes; shift ;;
        *) echo 'Usage: install.sh [--install-deps] [--github-auth] [--base-url HTTPS_RELEASE_ROOT] [--uninstall]' >&2; exit 2 ;;
    esac
done
if [ "$uninstall" = no ]; then
    case "$base_url" in https://?*) ;; *) echo 'Provide --base-url with your HTTPS release directory.' >&2; exit 2 ;; esac
fi
if [ "$uninstall" = no ]; then
    case "$(uname -s)" in Linux) ;; *) echo 'This installer supports Linux only.' >&2; exit 1 ;; esac
    case "$(uname -m)" in
        x86_64|amd64|aarch64|arm64|armv7l|armv7) ;;
        *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 1 ;;
    esac
fi
run_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}
if [ "$install_deps" = yes ] && [ "$uninstall" = no ]; then
    if command -v apt-get >/dev/null 2>&1; then
        run_root apt-get update
        run_root apt-get install -y python3 fzf mpv curl
    elif command -v pacman >/dev/null 2>&1; then
        run_root pacman -Syu --needed python fzf mpv curl
    elif command -v dnf >/dev/null 2>&1; then
        run_root dnf install -y python3 fzf mpv curl
    else
        echo 'Install Python 3.10+, fzf, mpv and curl using your package manager, then rerun.' >&2
        exit 1
    fi
fi
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.10+ first (or use --install-deps).' >&2; exit 1; }
python3 - "$base_url" "$uninstall" "$release_version" "$github_auth" <<'PY'
import hashlib
import os
import platform
from pathlib import Path
import shlex
import shutil
import sys
import subprocess
import tempfile
import urllib.request
import zipfile

if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10+ is required.')
base, uninstall, version, github_auth = sys.argv[1:]
root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'jelly-cli'
bin_dir = Path(os.environ.get('JELLY_CLI_BIN_DIR', Path.home() / '.local/bin'))
launcher = bin_dir / 'jelly-cli'
marker = '# jelly-cli managed launcher'
if launcher.exists() and marker not in launcher.read_text():
    raise SystemExit(f'Refusing to replace an unrelated command: {launcher}')
if uninstall == 'yes':
    if launcher.exists():
        launcher.unlink()
    archive = root / 'jelly-cli.pyz'
    if archive.exists():
        archive.unlink()
    print('jelly-cli removed. Saved Jellyfin login preserved.')
    raise SystemExit(0)
if platform.system() != 'Linux':
    raise SystemExit('This installer supports Linux only.')
architectures = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'aarch64', 'arm64': 'aarch64', 'armv7l': 'armv7', 'armv7': 'armv7'}
architecture = architectures.get(platform.machine().lower())
if not architecture:
    raise SystemExit('Unsupported Linux architecture: ' + platform.machine())
asset = f'v{version}/jelly-cli-linux-{architecture}.pyz'
print(f'Installing jelly-cli {version} for Linux {architecture}')
for dependency in ('fzf', 'mpv'):
    if not shutil.which(dependency):
        raise SystemExit(f'Missing {dependency}. Rerun with --install-deps or install it using your package manager.')
class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Refusing a non-HTTPS redirect.')
        return super().redirect_request(request, fp, code, msg, headers, newurl)
opener = urllib.request.build_opener(HTTPSOnly())
def fetch(name):
    if github_auth == 'yes':
        if not shutil.which('gh'):
            raise ValueError('Install GitHub CLI and run gh auth login before using --github-auth.')
        result = subprocess.run(['gh', 'release', 'download', 'v' + version,
                                 '--repo', 'acGhostes/jelly-cli', '--pattern', name.rsplit('/', 1)[-1],
                                 '--output', '-'], capture_output=True, timeout=120)
        if result.returncode:
            raise ValueError('GitHub download failed. Check gh auth status and access to the published release.')
        return result.stdout
    with opener.open(base.rstrip('/') + '/' + name, timeout=60) as response:
        return response.read()
try:
    checksum = fetch(asset + '.sha256').decode().split()[0]
    payload = fetch(asset)
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise ValueError('Release checksum does not match. Existing installation preserved.')
    root.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        staged = Path(directory) / 'release.pyz'
        staged.write_bytes(payload)
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip() or '__main__.py' not in archive.namelist():
                raise ValueError('Invalid release archive.')
        # Never extract the downloaded archive; Python runs it directly.
        script = Path(directory) / 'launcher'
        script.write_text('#!/bin/sh\n' + marker + '\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(root / 'jelly-cli.pyz')) + ' "$@"\n')
        script.chmod(0o755)
        # Stage within bin_dir too so custom paths can reside on another filesystem.
        fd, name = tempfile.mkstemp(dir=bin_dir, prefix='.jelly-cli-')
        try:
            with os.fdopen(fd, 'w') as output:
                output.write(script.read_text())
            os.chmod(name, 0o755)
            destination = root / 'jelly-cli.pyz'
            previous = destination.read_bytes() if destination.exists() else None
            os.replace(staged, destination)
            try:
                os.replace(name, launcher)
            except OSError:
                if previous is None:
                    destination.unlink()
                else:
                    staged.write_bytes(previous)
                    os.replace(staged, destination)
                raise
        finally:
            if os.path.exists(name):
                os.unlink(name)
except Exception as exc:
    raise SystemExit(f'Installation failed: {exc}')
print(f'Installed {launcher}')
if str(bin_dir) not in os.environ.get('PATH', '').split(os.pathsep):
    print('Add this to your shell profile, then open a new terminal:')
    print('export PATH=' + shlex.quote(str(bin_dir)) + ':"$PATH"')
print('Run: jelly-cli')
PY
