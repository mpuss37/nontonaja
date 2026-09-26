#!/usr/bin/env bash
# Install nontonaja on Android Termux
set -e

echo "==> Updating Termux packages..."
pkg update -y && pkg upgrade -y

echo "==> Installing dependencies..."
pkg install -y python mpv ffmpeg fzf

echo "==> Grant storage access (run termux-setup-storage prompt manually if not done):"
termux-setup-storage 2>/dev/null || true

echo "==> Installing nontonaja..."
pip install --break-system-packages .

echo ""
echo "Done! Run:"
echo "  nontonaja 'spider man'"
echo ""
echo "Notes:"
echo "  - Video plays in the current terminal as ASCII color blocks (--vo=tct)."
echo "    Quit mpv with 'q' to return to the menu."
echo "  - The stock Termux mpv.conf disables video (vid=no); nontonaja"
echo "    overrides it automatically, no config changes needed."
echo "  - Use the F-Droid Termux build; the Play Store one is unmaintained."
echo "  - Run 'nontonaja --diag' first to check DNS/HTTP connectivity"
echo "  - Downloads go to current dir by default; use -o ~/storage/shared/Movies"