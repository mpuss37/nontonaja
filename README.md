# nontonaja

Search, stream, and download movies & TV series from your terminal using
`mpv` + `ffmpeg`.

## Requirements

Install these first:

| Tool | Why |
|------|-----|
| **Python** 3.10+ | runs the app |
| **mpv** | plays the video |
| **ffmpeg** | downloads & merges subtitles |
| **fzf** | nicer picker menus (optional) |

## Install

### Linux

```bash
# 1. Install the system packages (pick your distro)

# Debian / Ubuntu
sudo apt install mpv ffmpeg fzf python3 python3-pip python3-venv

# Arch / Artix
sudo pacman -S mpv ffmpeg fzf python python-pip

# Fedora
sudo dnf install mpv ffmpeg fzf python3 python3-pip

# macOS (Homebrew)
brew install mpv ffmpeg fzf python

# 2. Download the app and install it
git clone https://github.com/mpuss37/nontonaja.git
cd nontonaja
pip install --user --break-system-packages .
```

### Android (Termux)

```bash
# 1. Install Termux from F-Droid (the Play Store build is outdated)
#    https://f-droid.org/packages/com.termux/

# 2. Download the app and run the setup script
git clone https://github.com/mpuss37/nontonaja.git
cd nontonaja
bash setup-termux.sh
```

`setup-termux.sh` installs all packages and the app for you.

> **Player on Android:** install **mpv-android** and it will open
> automatically at full resolution. Other players (VLC, MX Player, ...) can
> stall mid-playback, so use mpv-android.
> - Google Play: https://play.google.com/store/apps/details?id=is.xyz.mpv
> - F-Droid: https://f-droid.org/packages/is.xyz.mpv/
>
> No external player? It plays inside the Termux terminal instead.

## Usage

```bash
nontonaja "spider man"          # search and play
nontonaja "the 100"             # TV series (pick season/episode with arrows)
nontonaja -q 720 "avengers"     # choose quality (480 / 720 / 1080)
nontonaja -d "spider man"       # download instead of streaming
nontonaja -d -o ~/Videos "iron man"   # download to a folder
nontonaja --diag                # troubleshoot connectivity
```

### Flags

| Flag | Description |
|------|-------------|
| `-q`, `--quality` | Preferred quality: `480`, `720`, `1080` |
| `-d`, `--download` | Download instead of streaming |
| `-o`, `--output` | Output folder for downloads (default: current folder) |
| `--diag` | Check DNS/HTTP connectivity |

### While playing

| Key | Action |
|-----|--------|
| `Space` | pause |
| `←` / `→` | seek 10s |
| `↑` / `↓` | volume |
| `q` | quit |

## How it works

1. Search all providers in parallel (results merged and de-duplicated).
2. Pick a title. For series, use `←`/`→` to pick season/episode, `Enter` to confirm.
3. Pick source + quality: `1` 480p · `2` 720p · `3` 1080p.
4. Pick an action: stream, download, both, change quality/source, change episode, or exit.

Notes:
- If a title is missing on the chosen source, it automatically tries the others.
- Some sources require a short unlock wait before playback; the unlock is
  cached so replays start instantly.
- A small local proxy rewrites the video segments so `mpv`/`ffmpeg` accept them.

## Configuration

Optional. Create `~/.config/nontonaja/config.toml`:

```toml
subs_language = "English"
# download = "."
# proxy = "socks5://127.0.0.1:1080"
# mirrors = { source1 = "https://example.com", source2 = "https://example.org" }
```

| Key | Description |
|-----|-------------|
| `subs_language` | Preferred subtitle language |
| `download` | Default download folder |
| `proxy` | SOCKS/HTTP proxy (skipped with a warning if unreachable) |
| `mirrors` | Override base URL per source |

### Environment variables

| Variable | Description |
|----------|-------------|
| `NONTONAJA_NO_EXTERNAL_PLAYER=1` | Force terminal (ASCII) playback |
| `NONTONAJA_MPV_VO` | Override the mpv video output (e.g. `kitty`, `tct`) |
| `NONTONAJA_PROXY` / `ALL_PROXY` | SOCKS/HTTP proxy |
| `NONTONAJA_DEBUG_PROXY=1` | Print proxy logs (troubleshooting) |

## License

MIT
