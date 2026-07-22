#!/usr/bin/env bash
set -e

# Try pip install --user first (works on most systems)
if pip install --user . 2>/dev/null; then
    echo "Installed to ~/.local"
    echo "Run: nontonaja 'query'"
    exit 0
fi

# Fallback: create venv (for PEP 668 systems like Arch/Artix)
VENV_DIR=".venv"
echo "Creating venv..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install . -q

echo ""
echo "Done! Run with:"
echo "  source $VENV_DIR/bin/activate && nontonaja 'query'"
echo "  # or: $VENV_DIR/bin/python -m nontonaja 'query'"
