#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.bun/bin:$HOME/.cargo/bin:$PATH"

PORT="${PORT:-4173}"

if [[ ! -f "$ROOT_DIR/apps/web/src/wasm/telemetry_core_bg.wasm" ]]; then
  echo "Building Rust WASM core..."
  (cd "$ROOT_DIR/crates/telemetry-core" && wasm-pack build --target web --release --out-dir ../../apps/web/src/wasm)
fi

if [[ ! -d "$ROOT_DIR/apps/web/node_modules" ]]; then
  echo "Installing frontend dependencies with bun..."
  (cd "$ROOT_DIR/apps/web" && bun install)
fi

NEEDS_BUILD=0
if [[ ! -d "$ROOT_DIR/apps/web/dist" || "${1:-}" == "--rebuild" ]]; then
  NEEDS_BUILD=1
elif [[ -n "$(find "$ROOT_DIR/apps/web/src" "$ROOT_DIR/apps/web/index.html" -newer "$ROOT_DIR/apps/web/dist/index.html" -print -quit 2>/dev/null)" ]]; then
  NEEDS_BUILD=1
fi

if [[ "$NEEDS_BUILD" -eq 1 ]]; then
  echo "Building static PWA bundle..."
  (cd "$ROOT_DIR/apps/web" && bun run build)
fi

echo ""
echo "=================================================="
echo "  SZenergy Pro Analyser (Web/WASM PWA)"
echo "  URL: http://localhost:${PORT}/"
echo "  Press Ctrl+C to stop."
echo "=================================================="
echo ""

cd "$ROOT_DIR/apps/web"
exec bun --bun vite preview --port "$PORT" --strictPort --host
