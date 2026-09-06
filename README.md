# nontonaja

## Prasyarat

Sebelum menginstall nontonaja, pastikan dependensi sistem berikut sudah terinstall:

### Arch / Artix Linux

```bash
sudo pacman -S mpv ffmpeg fzf python python-pip
```

### Debian / Ubuntu

```bash
sudo apt install mpv ffmpeg fzf python3 python3-pip python3-venv
```

### Fedora

```bash
sudo dnf install mpv ffmpeg fzf python3 python3-pip
```

### macOS (Homebrew)

```bash
brew install mpv ffmpeg fzf python
```

| Dependensi | Fungsi | Wajib? |
|------------|--------|--------|
| `python` >= 3.10 | Runtime | Ya |
| `mpv` | Memutar video di terminal | Ya |
| `ffmpeg` | Download & multiplexing video + subtitle | Ya |
| `fzf` | Interactive fuzzy search menu (ala ani-cli) | Opsional (fallback ke prompt angka) |

## Instalasi

Setelah semua dependensi terinstall, pilih salah satu cara berikut:

```bash
# Cara 1: pip (recommended)
pip install --user --break-system-packages .
nontonaja "spider man"

# Cara 2: setup.sh (auto venv)
bash setup.sh
source .venv/bin/activate
nontonaja "spider man"

# Cara 3: pipx (isolated environment)
sudo pacman -S python-pipx   # atau: pip install --user pipx
pipx install .
nontonaja "spider man"
```

## Cara Pakai

```bash
# Cari dan putar film
nontonaja "spider man"
nontonaja "avengers"

# Pilih quality
nontonaja -q 720 "spider man"
nontonaja -q 1080 "avengers"

# Mode download
nontonaja -d "spider man"

# Download ke direktori tertentu
nontonaja -d -o ~/Videos "spider man"
nontonaja -o ~/Videos "spider man"
```

### Flow

```
1. Cari film dari LK21 + FlixHQ + IDLIX (merged, deduplicated, diurutkan berdasarkan relevansi)
2. Pilih film dari daftar hasil
3. Pilih source & quality:
   1. 480p   — LK21 P2P + subtitle
   2. 720p   — FlixHQ M3U8 + IDLIX sub Indo
   3. 1080p  — FlixHQ M3U8 + IDLIX sub Indo
4. Pilih action:
   1. Stream   — Putar langsung via mpv
   2. Download — Download via ffmpeg (.mkv)
   3. Stream & Download — Keduanya sekaligus
   4. Change Quality / Source — Ganti quality/source tanpa restart
   5. Exit
```

### Perbandingan Source

| Opsi | Video Source | Quality | Subtitle |
|------|-------------|---------|----------|
| 1 | LK21 (P2P) | 480p | LK21 |
| 2 | FlixHQ (M3U8) | 720p | FlixHQ + IDLIX sub Indo |
| 3 | FlixHQ (M3U8) | 1080p | FlixHQ + IDLIX sub Indo |

## Config

Buat `~/.config/nontonaja/config.toml` (opsional):

```toml
subs_language = "English"
# download = "."
```

## Lisensi

MIT
