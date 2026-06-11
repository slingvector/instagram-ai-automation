#!/usr/bin/env bash
# Download required font assets for the Media Factory.
# Run this after cloning: ./scripts/setup_fonts.sh

set -euo pipefail

FONTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/fonts"
mkdir -p "$FONTS_DIR"

NOTO_URL="https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf"
NOTO_FILE="$FONTS_DIR/NotoColorEmoji.ttf"

if [ -f "$NOTO_FILE" ]; then
    echo "✅ NotoColorEmoji.ttf already exists — skipping download."
else
    echo "⬇️  Downloading NotoColorEmoji.ttf..."
    curl -fSL "$NOTO_URL" -o "$NOTO_FILE"
    echo "✅ Downloaded to $NOTO_FILE"
fi

echo "Font setup complete."
