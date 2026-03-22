#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "Cleaning local Python/cache/test artifacts..."

rm -rf \
  __pycache__ \
  app/__pycache__ \
  tests/unit/__pycache__ \
  tests/integration/__pycache__ \
  .pytest_cache \
  htmlcov

rm -f \
  .coverage \
  coverage.xml \
  cache/music_cache.sqlite3

echo "Done."
