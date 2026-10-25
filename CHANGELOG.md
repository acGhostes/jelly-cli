# Changes

## 1.0.0

- New home sections: Next Up, Favorites and Recently Added.
- Media details with Resume/Start Over, favorite and watched-state actions.
- Separate server/account profiles with backwards-compatible default login.
- Saved fullscreen, autoplay, subtitle, language and volume preferences.
- Autoplay advances only after EOF; next-episode lookup cannot silently jump backwards.
- Reuse visited list pages and omit images in API lists; refresh after playback.
- Typed API failures, bounded read retries, recovery menus, and same-origin authorization redirects.
- Secrets-free diagnostics and resettable preferences.
- Reproducible, checksum-verified 1.0 assets, safer update rollback, immutable hosted versions.
- GitHub test matrix and draft-release automation.

## 0.3.0

- Open a normal mpv window with safe automatic hardware decoding.
- Remove terminal video rendering and its graphics/size options.
- Preserve saved login, subtitle support, resume and Jellyfin reporting.
- Report full media duration on EOF so Jellyfin can apply its watched thresholds.
- Test a visible mpv window with resume, subtitles, pause/seek, early quit and EOF reports.

## 0.2.0

- Detect Kitty/Sixel terminal graphics and use pixel output by default.
- Check actual terminal pixel dimensions; require explicit size when unknown instead of accepting a blurry fallback.
- Add --doctor, --video, and --video-size.
- Keep low-resolution blocks available through --video tct only.
- Select default external subtitles and test real Kitty frames with subtitle text.
- Publish a new versioned release directory; retain the deployed 0.1.0 assets.

## 0.1.0

Initial Jellyfin terminal browser, saved login, block-based playback, and hosted installer.
