#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.bun/bin:$HOME/.cargo/bin:$PATH"

BRANCH="${PAGES_BRANCH:-pages}"
REMOTE="${PAGES_REMOTE:-origin}"
DO_PUSH=1

for arg in "$@"; do
  case "$arg" in
    --no-push)
      DO_PUSH=0
      ;;
    -h|--help)
      echo "Usage: $0 [--no-push]"
      echo "Builds the WASM core and web PWA, commits dist/ to '$BRANCH', and pushes to '$REMOTE'."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

for cmd in git cargo wasm-pack bun; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

cd "$ROOT_DIR"
SRC_REV="$(git rev-parse --short HEAD 2>/dev/null || echo "workspace")"

echo "[1/4] Building Rust WASM core..."
(
  cd "$ROOT_DIR/crates/telemetry-core"
  wasm-pack build --target web --release --out-dir ../../apps/web/src/wasm
)

echo "[2/4] Building frontend PWA bundle..."
if [[ ! -d "$ROOT_DIR/apps/web/node_modules" ]]; then
  (cd "$ROOT_DIR/apps/web" && bun install)
fi
(
  cd "$ROOT_DIR/apps/web"
  bun run build
)

echo "[3/4] Updating '$BRANCH' branch in isolated worktree..."
WORKTREE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/szenergy-pages.XXXXXX")"
cleanup() {
  if git -C "$ROOT_DIR" worktree list --porcelain | grep -Fq "worktree $WORKTREE_DIR"; then
    git -C "$ROOT_DIR" worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE_DIR" "$BRANCH"
elif git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
  git fetch "$REMOTE" "$BRANCH:$BRANCH"
  git worktree add "$WORKTREE_DIR" "$BRANCH"
else
  git worktree add --detach "$WORKTREE_DIR" HEAD
  (
    cd "$WORKTREE_DIR"
    git checkout --orphan "$BRANCH"
    git rm -rf . >/dev/null 2>&1 || true
  )
fi

(
  cd "$WORKTREE_DIR"
  # Remove previously tracked files so stale hashed assets don't accumulate
  git rm -rf --ignore-unmatch . >/dev/null 2>&1 || true
  cp -a "$ROOT_DIR/apps/web/dist/." .
  touch .nojekyll
  cat << 'EOF' > .gitignore
# Ignore workspace source/build/sample dirs when checking out `pages` locally
/apps/
/crates/
/target/
/samples/
/sample_data/
node_modules/
*.tsbuildinfo
.DS_Store
Thumbs.db
EOF

  git add -A
  if git diff --cached --quiet; then
    echo "No asset changes to commit on '$BRANCH'."
  else
    git commit -m "Deploy SZenergy Pro Analyser ($SRC_REV)"
  fi
)

if [[ "$DO_PUSH" -eq 1 ]]; then
  echo "[4/4] Pushing '$BRANCH' to '$REMOTE'..."
  git push -u "$REMOTE" "$BRANCH"
else
  echo "[4/4] Skipping push (--no-push)."
fi

echo "Done."
