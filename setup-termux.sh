#!/usr/bin/env bash
# Install nontonaja on Android Termux
set -e

echo "==> Updating Termux packages..."
pkg update -y && pkg upgrade -y

echo "==> Installing dependencies..."
pkg install -y python mpv ffmpeg fzf

echo "==> Installing nontonaja..."
pip install --force-reinstall --no-cache-dir --break-system-packages .

echo ""
echo "Done! Run:"
echo "  nontonaja 'spider man'"
echo ""
echo "Notes:"
echo "  - Films open in mpv-android at full resolution when installed (best);"
echo "    other players (VLC/MX/Visha) may stall on some streams. Otherwise"
echo "    ASCII playback in this terminal (--vo=tct, quit with 'q')."
echo "  - mpv-android: https://play.google.com/store/apps/details?id=is.xyz.mpv"
echo "  - Subtitles only work in terminal mode: NONTONAJA_NO_EXTERNAL_PLAYER=1"
echo "  - The stock Termux mpv.conf disables video (vid=no); nontonaja"
echo "    overrides it automatically, no config changes needed."
echo "  - Use the F-Droid Termux build; the Play Store one is unmaintained."
echo "  - Run 'nontonaja --diag' first to check DNS/HTTP connectivity"
echo "  - Downloads go to current dir by default; use -o ~/storage/shared/Movies"
echo "  - For storage access (downloads to shared storage), run once manually:"
echo "      termux-setup-storage"
echo "    (it shows an Android permission dialog that needs a tap)"