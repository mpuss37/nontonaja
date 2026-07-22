# nontonaja

CLI media streaming tool. Cari film, pilih source, putar langsung lewat terminal.

## Instalasi

```bash
# Option 1: pipx (recommended)
pip install --user --break-system-packages .
nontonaja "spider man"

# Option 2: setup.sh
bash setup.sh
source .venv/bin/activate
nontonaja "spider man"

# Option 3: pipx via pacman (Arch/Artix)
sudo pacman -S python-pipx
pipx install .
nontonaja "spider man"
```

### System Dependencies

| Package | Fungsi |
|---------|--------|
| `mpv` | Player utama |
| `ffmpeg` | Download |

## Cara Pakai

```bash
# Search & play
nontonaja "spider man"
nontonaja "avengers"
nontonaja "batman"

# Download
nontonaja -d "spider man"
nontonaja -d /path/to/dir "spider man"
```

### Flow

```
1. Search film dari LK21 + FlixHQ (merged, deduplicated)
2. Pilih film dari daftar
3. Pilih source:
   1. 480p   — LK21 P2P + subtitle
   2. 720p   — FlixHQ M3U8 + IDLIX sub Indo
   3. 1080p  — FlixHQ M3U8 + IDLIX sub Indo
4. Stream ready → putar via mpv
```

### Source Comparison

| Opsi | Video Source | Quality | Subtitle |
|------|-------------|---------|----------|
| 1 | LK21 (P2P) | 480p | LK21 |
| 2 | FlixHQ (M3U8) | 720p | FlixHQ + IDLIX sub Indo |
| 3 | FlixHQ (M3U8) | 1080p | FlixHQ + IDLIX sub Indo |

## Struktur Project

```
nontonaja/
├── pyproject.toml
├── setup.sh
├── README.md
├── scraping-flow.md
└── src/nontonaja/
    ├── __main__.py
    ├── cli.py               # Entry point + main flow
    ├── config.py            # Config loading
    ├── download.py          # FFmpeg download
    ├── proxy.py             # Local HTTP proxy (IDLIX HLS rewrite)
    ├── quality.py           # M3U8 quality selection
    └── providers/
        ├── lk21.py          # LK21 scraper + JSON API
        ├── flixhq.py        # FlixHQ scraper
        └── idlix.py         # IDLIX API (pentos claim/redeem)
```

## Config

Buatan `~/.config/nontonaja/config.toml` (opsional):

```toml
subs_language = "English"
# download = "."
```

## Lisensi

MIT
