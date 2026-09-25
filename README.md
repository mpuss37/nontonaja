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

## Features

- **Parallel search** across 3 providers with deduplication
- **Arrow-key navigation** for season/episode selection
- **Token caching** for IDLIX auth (skip 15s unlock on replay)
- **Auto-fallback** between sources when content unavailable
- **Local HLS proxy** for obfuscated segment compatibility
- **Subtitle integration** with downloads via ffmpeg
- **Quality selection** with provider-specific options

## License

MIT
