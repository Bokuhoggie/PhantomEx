#!/usr/bin/env bash
# PhantomEx dev launcher
# Usage: ./start.sh [--build]
#   --build   rebuild the frontend before starting (needed after frontend changes)

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ── Colors ────────────────────────────────────────────────────────────────────
GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'; RST='\033[0m'
log()  { echo -e "${CYN}[phantomex]${RST} $*"; }
ok()   { echo -e "${GRN}[phantomex]${RST} $*"; }
warn() { echo -e "${YEL}[phantomex]${RST} $*"; }

# ── Args ──────────────────────────────────────────────────────────────────────
BUILD=false
for arg in "$@"; do
  [[ "$arg" == "--build" ]] && BUILD=true
done

# ── Checks ────────────────────────────────────────────────────────────────────
command -v python3 &>/dev/null || { echo "python3 not found"; exit 1; }
command -v npm &>/dev/null    || { echo "npm not found"; exit 1; }

# ── Python venv ───────────────────────────────────────────────────────────────
if [[ ! -d "$ROOT/venv" ]]; then
  log "Creating Python virtual environment..."
  python3 -m venv "$ROOT/venv"
fi

log "Installing/updating Python dependencies..."
"$ROOT/venv/bin/pip" install -q -r "$BACKEND/requirements.txt"

# ── Frontend ──────────────────────────────────────────────────────────────────
if [[ ! -d "$FRONTEND/node_modules" ]]; then
  log "Installing frontend dependencies..."
  npm --prefix "$FRONTEND" install
fi

if $BUILD || [[ ! -d "$FRONTEND/dist" ]]; then
  log "Building frontend..."
  npm --prefix "$FRONTEND" run build
  ok "Frontend built."
fi

# ── Start ─────────────────────────────────────────────────────────────────────
PORT="${PHANTOMEX_PORT:-8000}"
ok "Starting PhantomEx on http://localhost:$PORT"
warn "Press Ctrl+C to stop."
echo ""

cd "$BACKEND"
exec "$ROOT/venv/bin/uvicorn" main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload
