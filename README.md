# nontonaja

Aplikasi CLI untuk nyari, stream, dan download film langsung di terminal pakai `mpv` + `ffmpeg`.

## Dependensi

Sebelum pakai, instal:

- **Python** ≥ 3.10
- **mpv** – putar video di terminal
- **ffmpeg** – download & gabungin video + subtitle
- **fzf** – cari film pakai menu (opsional, kalo gak ada ada prompt angka)

### OS

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

## Instal

Pilih salah satu:

```bash
# 1. pip (paling gampang)
pip install --user --break-system-packages .
nontonaja "spider man"

# 2. setup.sh (bikin virtualenv)
bash setup.sh
source .venv/bin/activate
nontonaja "spider man"

# 3. pipx (isolasi penuh)
pip install --user pipx
pipx install .
nontonaja "spider man"
```

## Pakai

```bash
# Cari & putar film
nontonaja "spider man"
nontonaja "avengers"

# Cek quality
nontonaja -q 720 "spider man"
nontonaja -q 1080 "avengers"

# Download
nontonaja -d "spider man"

# Download ke folder tertentu
nontonaja -d -o ~/Videos "spider man"
nontonaja -o ~/Downloads "avengers"
```

## Cara Kerja

1. Cari film di **LK21, FlixHQ, IDLIX** (semua digabungin, duplikat dihilangkan)
2. Pilih film yang mau
3. Pilih sumber + quality:
   - `1` 480p – LK21 (P2P) + subtitle
   - `2` 720p – FlixHQ (M3U8) + subtitle Indonesia
   - `3` 1080p – FlixHQ (M3U8) + subtitle Indonesia
4. Pilih aksi:
   - `1` Stream – langsung putar pakai mpv
   - `2` Download – save jadi `.mkv` pakai ffmpeg
   - `3` Stream + Download – keduanya
   - `4` Ganti quality/source – tanpa restart
   - `5` Keluar

## Konfigurasi

Buat file `~/.config/nontonaja/config.toml`:

```toml
subs_language = "English"
# download = "."
```

## Lisensi

MIT