# GitHub Releases

GitHub is the distribution source. No Caddy configuration, personal domain or Ubuntu-host deployment is needed for new installs.

## Build and release

1. Update `jelly_cli/__init__.py` and `install.sh` to the same new version.
2. Update release notes, run tests and build:

   ```sh
   python3 -m unittest discover -s tests -v
   python3 scripts/build_release.py
   ```

3. Commit and push the changes. Tag that commit `vX.Y.Z` and push the tag.
4. The release workflow tests, builds, and uploads a draft GitHub release.
5. After successful checks, publish the draft. The `releases/latest/download/install.sh` URL then serves the published installer.

Each installer downloads from `https://github.com/acGhostes/jelly-cli/releases/download/vVERSION/ASSET`. Assets include x86-64, ARM64 and ARMv7 Python archives and SHA-256 files. The executable payload is portable Python; dependencies are system-managed. Never replace a published version's contents.

## Public installation

```sh
curl --proto '=https' --proto-redir '=https' -fsSL https://github.com/acGhostes/jelly-cli/releases/latest/download/install.sh -o /tmp/jelly-cli-install.sh
sh /tmp/jelly-cli-install.sh --install-deps
jelly-cli
```

Anonymous installation requires the repository to be public. A private repository can publish releases, but users must authenticate with an account that has access:

```sh
gh auth login
gh release download --repo acGhostes/jelly-cli --pattern install.sh --output /tmp/jelly-cli-install.sh --clobber
sh /tmp/jelly-cli-install.sh --install-deps --github-auth
```

## Former hosting setup

Existing personal-domain installations continue to run. To update, use the GitHub installer above; it preserves their login and settings. No server change is needed. The old `scripts/deploy_host.py` remains available for maintaining historical self-hosted releases, but is not part of the GitHub installation path. It does not need to be run for this release.
