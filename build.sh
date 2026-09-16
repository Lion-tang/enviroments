#!/bin/bash
# Enviroments - Build Script (Linux/macOS)
# Prerequisites: Python 3.9+, Node.js, pnpm, and backend/requirements-build.txt

set -e

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "ERROR: Python 3.9 or newer is required." >&2
  exit 1
fi

echo "==> Building frontend..."
cd frontend
pnpm install
pnpm run build
cd ..

echo "==> Building executable..."
cd backend
python3 -m PyInstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build
cd ..

echo ""
echo "========================================"
echo "Build complete!"
echo "Output: dist/Enviroments/"
echo ""
echo "Run: ./dist/Enviroments/Enviroments"
echo "========================================"
