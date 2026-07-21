# nontonaja

CLI media streaming tool. Cari film, pilih source, putar langsung lewat terminal.

## Instalasi

```bash
git clone https://github.com/mpuss37/nontonaja.git
cd nontonaja
python -m venv .venv
.venv/bin/pip install -e .

# Install playwright untuk LK21
.venv/bin/playwright install chromium
```

### Dependencies

| Package | Fungsi |
|---------|--------|
| `mpv` | Player utama |
| `fzf` | Selection menu |
| `ffmpeg` | Download |
| `chromium` | LK21 search (playwright) |

## Cara Pakai

```bash
# Search & play
nontonaja spider-man
nontonaja avengers
nontonaja batman

# Pilih quality
nontonaja -q 1080 spider-man

# Download
nontonaja -d "spider-man"
nontonaja -d /path/to/dir "spider-man"
```

### Flow

```
1. Search film dari LK21 + FlixHQ (digabung)
2. Pilih film dari daftar
3. Pilih source:
   1. 480p (sub-indo)   → LK21 P2P
   2. 720p+ (nonsub)    → FlixHQ
4. Putar via mpv
```

## Sumber

| Source | Quality | Subtitle | Kecepatan |
|--------|---------|----------|-----------|
| LK21 (P2P) | 480p | Ya | Cepat |
| FlixHQ | Multi (720p-1080p) | Ya | Sedang |

## Struktur Project

```
nontonaja/
├── pyproject.toml
├── config.example.toml
├── README.md
└── src/nontonaja/
    ├── __main__.py
    ├── cli.py               # Entry point + main flow
    ├── config.py             # Config loading
    ├── dependencies.py       # Cek mpv/fzf/ffmpeg
    ├── download.py           # FFmpeg download
    ├── history.py            # Watch history
    ├── launcher.py           # fzf/rofi wrapper
    ├── quality.py            # M3U8 quality selection
    ├── providers/
    │   ├── flixhq.py         # FlixHQ scraper
    │   ├── lk21.py           # LK21 scraper + P2P
    │   ├── browser.py        # Playwright wrapper
    │   └── decoder.py        # Stream decoder
    └── players/
        ├── mpv.py
        ├── vlc.py
        └── celluloid.py
```

## Config

Buat `~/.config/nontonaja/config.toml`:

```toml
player = "mpv"        # mpv, vlc, celluloid
download = "."        # default download dir
history = false       # simpan watch history
```

## Lisensi

MIT
