"""Build reproducible, static-hostable releases with no third-party build tools."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / 'jelly_cli/__init__.py').read_text())[1]


def write_zip(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def build():
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    installer = (ROOT / 'install.sh').read_text()
    if f"release_version='{VERSION}'" not in installer:
        raise SystemExit('Update install.sh release_version to match jelly_cli.__version__.')
    files = {str(path.relative_to(ROOT)): path.read_bytes() for path in (ROOT / 'jelly_cli').glob('*.py')}
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    files['__main__.py'] = b'from jelly_cli.cli import main\nraise SystemExit(main())\n'
    archive = out / 'jelly-cli.pyz'
    write_zip(archive, files)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / 'jelly-cli.pyz.sha256').write_text(digest + '  jelly-cli.pyz\n')
    shutil.copy2(ROOT / 'install.sh', out / 'install.sh')
    release = out / 'releases' / VERSION
    release.mkdir(parents=True, exist_ok=True)
    bundle = {'install.sh': installer.encode()}
    assets = {}
    for architecture in ('x86_64', 'aarch64', 'armv7'):
        name = f'jelly-cli-linux-{architecture}.pyz'
        target = release / name
        shutil.copy2(archive, target)
        checksum = target.with_suffix('.pyz.sha256')
        checksum.write_text(digest + '  ' + name + '\n')
        assets[name] = digest
        for path in (target, checksum):
            bundle[str(path.relative_to(out))] = path.read_bytes()
    manifest = json.dumps({'version': VERSION, 'assets': assets}, indent=2, sort_keys=True).encode() + b'\n'
    (out / 'manifest.json').write_bytes(manifest)
    bundle['manifest.json'] = manifest
    write_zip(out / 'jelly-cli-hosting.zip', bundle)
    print(f'Built jelly-cli {VERSION}: {out / "jelly-cli-hosting.zip"}')


if __name__ == '__main__':
    build()
