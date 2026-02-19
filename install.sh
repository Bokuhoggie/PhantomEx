#!/usr/bin/env bash
# PhantomEx install — symlinks the CLI to /usr/local/bin so you can run:
#   phantomex          (to start)
#   phantomex stop     (to stop)
#
# Run once from the PhantomEx directory:
#   chmod +x install.sh && ./install.sh

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLI="$ROOT/bin/phantomex"
TARGET="/usr/local/bin/phantomex"

if [[ ! -f "$CLI" ]]; then
  echo "Error: $CLI not found" >&2
  exit 1
fi

# Make executable
chmod +x "$CLI"

# Symlink (requires sudo)
if [[ -L "$TARGET" || -f "$TARGET" ]]; then
  sudo rm -f "$TARGET"
fi
sudo ln -s "$CLI" "$TARGET"

echo ""
echo "✓ Installed: phantomex → $CLI"
echo ""
echo "Run 'phantomex' to start the server."
echo "Run 'phantomex stop' to stop it."
echo ""
