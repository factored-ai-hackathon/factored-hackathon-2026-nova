#!/usr/bin/env bash
# Build the Lambda package: backend/build/lambda.zip (Python 3.12, arm64/Graviton).
# Used by infra/app (first deploy) and .github/workflows/deploy.yml. Run from anywhere.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$BACKEND_DIR/build"
PKG_DIR="$BUILD_DIR/package"

rm -rf "$BUILD_DIR"
mkdir -p "$PKG_DIR"

cd "$BACKEND_DIR"
uv export --frozen --no-dev --no-hashes --no-emit-project -o "$BUILD_DIR/requirements.txt" >/dev/null
# Linux arm64 wheels, whatever the machine building the package. The python3.12 runtime is
# Amazon Linux 2023 (glibc 2.34), so manylinux_2_28 wheels work.
uv pip install --quiet \
  --requirements "$BUILD_DIR/requirements.txt" \
  --target "$PKG_DIR" \
  --python-platform aarch64-manylinux_2_28 \
  --python-version 3.12 \
  --only-binary :all:

cp -r app run.sh "$PKG_DIR/"
find "$PKG_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +

(cd "$PKG_DIR" && zip -qr9 "$BUILD_DIR/lambda.zip" .)
echo "Built $BUILD_DIR/lambda.zip ($(du -h "$BUILD_DIR/lambda.zip" | cut -f1))"
