# nontonaja

CLI media streaming tool. Cari film, pilih source, putar langsung lewat terminal.

## Instalasi

```bash
git clone https://github.com/mpuss37/nontonaja.git
cd nontonaja
python -m venv .venv
.venv/bin/pip install -e .

# Optional: install chromium untuk search lebih lengkap
.venv/bin/playwright install chromium
```

### Dependencies

| Package | Fungsi |
|---------|--------|
| `mpv` | Player utama |
| `fzf` | Selection menu |
| `ffmpeg` | Download |
| `chromium` | Search (playwright, optional) |

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
1. Search film dari multiple source (digabung)
2. Pilih film dari daftar
3. Pilih source:
   1. 480p (sub-indo)
   2. 720p+ (nonsub)
4. Putar via mpv dengan upscaling (gpu-next + high-quality)
```

## Sumber

| Source | Quality | Subtitle | Kecepatan |
|--------|---------|----------|-----------|
| P2P | 480p | Ya | Cepat |
| Multi-source | 720p-1080p | Ya | Sedang |

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
    │   ├── flixhq.py         # Web scraper
    │   └── lk21.py           # P2P stream provider
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
