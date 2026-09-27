# nontonaja

Terminal CLI to search, stream, and download movies & TV series with `mpv` + `ffmpeg`.

## Dependencies

Install these first:

- **Python** ≥ 3.10
- **mpv** – video player
- **ffmpeg** – download & mux video + subtitles
- **fzf** – interactive picker menus (optional; falls back to numbered prompt)

### OS packages

**Arch / Artix**
```bash
sudo pacman -S mpv ffmpeg fzf python python-pip
```

**Debian / Ubuntu**
```bash
sudo apt install mpv ffmpeg fzf python3 python3-pip python3-venv
```

**Fedora**
```bash
sudo dnf install mpv ffmpeg fzf python3 python3-pip
```

**macOS (Homebrew)**
```bash
brew install mpv ffmpeg fzf python
```

**Android Termux**
```bash
bash setup-termux.sh          # installs everything + sets up storage
```
or manually:
```bash
pkg update && pkg upgrade
pkg install python mpv ffmpeg fzf python-pip
pip install --break-system-packages .
termux-setup-storage
```
> **External player (Android):** if a video player is installed, the film
> opens there automatically at full resolution — subtitles are only available
> in terminal mode. Force terminal playback with
> `NONTONAJA_NO_EXTERNAL_PLAYER=1`.
>
> **Use `mpv-android` — other players (VLC, MX Player, Visha, ...) may
> stall mid-playback** because the obfuscated HLS segments from these CDNs are
> not handled well by them. `mpv-android` plays them smoothly.
>
> - **Google Play:** https://play.google.com/store/apps/details?id=is.xyz.mpv
> - **F-Droid:** https://f-droid.org/packages/is.xyz.mpv/
>
> Install one of the above and set it as the default handler, or open the
> stream URL manually in `mpv-android`.
>
> **Terminal playback** renders ASCII color blocks (`--vo=tct`); quit with
> mpv's `q`, then the menu returns. Keys: `SPACE` pause, `←`/`→`
> seek 10s, `↑`/`↓` volume. The stock Termux `mpv.conf` ships `vid=no`
> (video decode disabled → audio-only playback); nontonaja always passes
> `--vid=auto` on the command line to override it. For a sharper picture use
> Termux fullscreen + landscape + a smaller font — terminal cells are the
> resolution limit, not the stream. Override the renderer with
> `NONTONAJA_MPV_VO` (e.g. `kitty` on supported terminals).
> Note: the Play Store Termux build is unmaintained; use the F-Droid version.

## Install

Pick one:

```bash
# 1. pip (simplest)
pip install --user --break-system-packages .
nontonaja "spider man"

# 2. setup.sh (creates virtualenv)
bash setup.sh
source .venv/bin/activate
nontonaja "spider man"

# 3. pipx (isolated)
pip install --user pipx
pipx install .
nontonaja "spider man"

# 4. Termux (Android)
bash setup-termux.sh
```

## Usage

```bash
# Search & play
nontonaja "spider man"
nontonaja "the 100"

# Pick quality
nontonaja -q 720 "spider man"
nontonaja -q 1080 "avengers"

# Download
nontonaja -d "spider man"

# Download to folder
nontonaja -d -o ~/Videos "spider man"
nontonaja -o ~/Downloads "avengers"

# Check connectivity (DNS, HTTP, proxy) for each source
nontonaja --diag
```

### Flags

| Flag | Description |
|------|-------------|
| `-q`, `--quality` | Preferred quality: `480`, `720`, `1080` |
| `-d`, `--download` | Download mode instead of streaming |
| `-o`, `--output` | Output directory for downloads (default: current dir) |
| `--diag` | Run connectivity diagnostics |

## How it works

1. Search **LK21, FlixHQ, and IDLIX** in parallel (results merged and de-duplicated).
2. Pick title. For TV series use **arrow keys navigation**:
   - `←`/`→` to change season/episode
   - `Enter` to confirm selection
   - `q` to cancel
3. Pick source + quality:
   - `1` 480p – LK21 (P2P) + subtitles
   - `2` 720p – FlixHQ (M3U8) + subtitles
   - `3` 1080p – FlixHQ (M3U8) + subtitles
4. Pick action:
   - `1` Stream – play in `mpv`
   - `2` Download – save as `.mkv` via `ffmpeg`
   - `3` Stream & Download – both
   - `4` Change Quality / Source – switch without restart
   - `5` Change Season / Episode – series only; switch episode instantly
   - `6` Exit

> Type `q` to quit at any movie list.

Notes:
- Sources auto-fallback: if title unavailable on chosen source, tries others.
- IDLIX enforces 15s server unlock wait before playback; countdown shown. Unlock token cached for instant replay.
- Local HTTP proxy rewrites HLS segments (obfuscated `.pict` extensions) for `mpv`/`ffmpeg` compatibility.
- **On Android, use `mpv-android` as the external player** (see the Termux note
  above). Other players can stall mid-playback on these obfuscated segments.

## Configuration

Create `~/.config/nontonaja/config.toml`:

```toml
subs_language = "English"
# download = "."
# proxy = "socks5://127.0.0.1:1080"   # used only if proxy reachable
# mirrors = { flixhq = "https://flixhq.example", lk21 = "https://lk21.example" }
```

Keys:

| Key | Description |
|-----|-------------|
| `subs_language` | Preferred subtitle language |
| `download` | Default download directory |
| `proxy` | SOCKS/HTTP proxy. Auto-skipped with warning if unreachable |
| `mirrors` | Override base URL per source |

Proxy also set via `NONTONAJA_PROXY` or `ALL_PROXY` env vars.

### Environment variables

| Variable | Description |
|----------|-------------|
| `NONTONAJA_NO_EXTERNAL_PLAYER` | Set to `1` to force terminal (ASCII) playback instead of an external player |
| `NONTONAJA_MPV_VO` | Override the mpv video output (e.g. `kitty`, `tct`) |
| `NONTONAJA_PROXY` / `ALL_PROXY` | SOCKS/HTTP proxy |
| `NONTONAJA_DEBUG_PROXY` | Set to `1` to print HLS proxy logs (playlist refresh, segment fetches) for troubleshooting |

## Features

- **Parallel search** across 3 providers with deduplication
- **Arrow-key navigation** for season/episode selection
- **Token caching** for IDLIX auth (skip 15s unlock on replay)
- **Auto-fallback** between sources when content unavailable
- **Local HLS proxy** for obfuscated segment compatibility
- **mpv-android friendly** — recommended player for smooth Android playback
- **Subtitle integration** with downloads via ffmpeg
- **Quality selection** with provider-specific options

## License

MIT
