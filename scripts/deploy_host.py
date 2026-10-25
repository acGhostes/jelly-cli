"""Run on the Ubuntu host: sudo python3 /home/nick/code/jelly-cli/scripts/deploy_host.py."""
import hashlib
import json
import re
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROUTE = '''    # jelly-cli release downloads
    handle_path /jelly-cli/releases/* {
        root * /var/www/jelly-cli/releases
        file_server
    }

'''
ANCHOR = '    handle /jelly-cli {'


def add_route(original):
    if ROUTE in original:
        return original
    if '/jelly-cli/releases' in original:
        raise RuntimeError('A release route already exists; review it before deploying.')
    if original.count(ANCHOR) != 1:
        raise RuntimeError('Expected exactly one existing jelly-cli installer route; no config changed.')
    return original.replace(ANCHOR, ROUTE + ANCHOR, 1)


def atomic_write(path, data, mode=0o644):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run this on the Ubuntu host with sudo.')
    config = Path('/etc/caddy/Caddyfile')
    web = Path('/var/www/jelly-cli')
    dist = Path(__file__).resolve().parents[1] / 'dist'
    version = json.loads((dist / 'manifest.json').read_text())['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise RuntimeError('Invalid release version.')
    original = config.read_bytes()
    updated = add_route(original.decode()).encode()
    # Verify every asset before writing any host files.
    files = []
    for arch in ('x86_64', 'aarch64', 'armv7'):
        asset = dist / 'releases' / version / f'jelly-cli-linux-{arch}.pyz'
        checksum = asset.with_suffix('.pyz.sha256')
        if hashlib.sha256(asset.read_bytes()).hexdigest() != checksum.read_text().split()[0]:
            raise RuntimeError(f'Checksum mismatch: {asset.name}')
        files.extend((asset, checksum))
    for source in files:
        target = web / source.relative_to(dist)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError('Published release differs: bump the version before deploying.')
    installer = (dist / 'install.sh').read_bytes()
    subprocess.run(['sh', '-n', str(dist / 'install.sh')], check=True)
    # Caddy must accept the candidate before replacing its live configuration.
    with tempfile.NamedTemporaryFile(dir=config.parent, prefix='.jelly-cli-', suffix='.caddy') as candidate:
        candidate.write(updated)
        candidate.flush()
        subprocess.run(['caddy', 'validate', '--config', candidate.name, '--adapter', 'caddyfile'], check=True)
    stamp = str(time.time_ns())
    backup = config.with_name('Caddyfile.before-jelly-cli-' + stamp)
    shutil.copy2(config, backup)
    old_installer = (web / 'install.sh').read_bytes() if (web / 'install.sh').exists() else None
    if old_installer is not None:
        atomic_write(web / ('install.sh.backup-' + stamp), old_installer)
    for source in files:
        target = web / source.relative_to(dist)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        atomic_write(target, source.read_bytes())
    try:
        if updated != original:
            atomic_write(config, updated, config.stat().st_mode & 0o777)
            subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
        atomic_write(web / 'install.sh', installer)
    except Exception:
        if updated != original:
            shutil.copy2(backup, config)
            subprocess.run(['systemctl', 'reload', 'caddy'], check=False)
        if old_installer is not None:
            atomic_write(web / 'install.sh', old_installer)
        raise
    print('Deployed installer and release files. Existing reverse proxies preserved.')
    print('Caddy backup:', backup)
    print('Verify: curl -fsSL https://saltvaultvideo.com/jelly-cli | head -n 8')
    print(f'Verify: curl -f https://saltvaultvideo.com/jelly-cli/releases/{version}/jelly-cli-linux-x86_64.pyz.sha256')


if __name__ == '__main__':
    main()
