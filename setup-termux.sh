#!/usr/bin/env bash
# Install nontonaja on Android Termux
set -e

echo "==> Updating Termux packages..."
pkg update -y && pkg upgrade -y

echo "==> Installing dependencies..."
pkg install -y python mpv ffmpeg fzf

echo "==> Grant storage access (run termux-setup-storage prompt manually if not done):"
termux-setup-storage 2>/dev/null || true

echo "==> Enabling external-app access (needed to open video in a new Termux window)..."
PROPS="$HOME/.termux/termux.properties"
mkdir -p "$HOME/.termux"
if ! grep -q '^allow-external-apps=true' "$PROPS" 2>/dev/null; then
    printf '\nallow-external-apps=true\n' >> "$PROPS"
fi

echo "==> Installing nontonaja..."
pip install --break-system-packages .

echo ""
echo "Done! Run:"
echo "  nontonaja 'spider man'"
echo ""
echo "Notes:"
echo "  - Video opens in a NEW Termux window (ASCII --vo=tct) and closes with mpv 'q'."
echo "    If no window appears: enable Termux -> Settings -> Allow external apps,"
echo "    then fully restart Termux. Fallback plays in the current terminal."
echo "  - Use the F-Droid Termux build; the Play Store one is unmaintained."
echo "  - Run 'nontonaja --diag' first to check DNS/HTTP connectivity"
echo "  - Downloads go to current dir by default; use -o ~/storage/shared/Movies"