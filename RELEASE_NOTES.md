jelly-cli 1.0 keeps browsing in your terminal and plays your Jellyfin library in a normal mpv window.

- Continue Watching, Next Up, favorites, recently added, movies, TV and search.
- Media details with Resume, Start Over, favorite and watched-state controls.
- Separate server/account profiles with saved login and playback preferences.
- Fullscreen, starting volume, audio/subtitle languages and optional episode autoplay.
- Playback start/progress/stop reporting, resume and full-duration EOF reporting.
- Bounded read retries, recovery menus, image-free lists and cached page navigation.
- Reproducible checksum-verified releases and dependency diagnostics.

Install using the README. Existing default-profile logins are retained. Requires Linux, Python 3.10+, fzf, mpv, and a graphical session for video. Direct streaming only; server transcoding, downloads and native Windows support are not implemented. Tests cover local HTTP fixtures and real mpv under Xvfb; live-server/GPU testing remains environment-dependent.
