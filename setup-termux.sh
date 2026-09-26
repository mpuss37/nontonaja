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
echo "  - Video renders in mpv. On weak phones add: mpv --vo=tct (recommended) or --vo=tty"
echo "  - Run 'nontonaja --diag' first to check DNS/HTTP connectivity"
echo "  - Downloads go to current dir by default; use -o ~/storage/shared/Movies"