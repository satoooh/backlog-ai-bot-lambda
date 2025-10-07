#!/usr/bin/env bash
set -eu
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
OUT_DIR="$ROOT_DIR/dist"
ZIP="$OUT_DIR/lambda.zip"

mkdir -p "$OUT_DIR"
rm -f "$ZIP"

cd "$ROOT_DIR"

# Package only source (no external deps). Lambda provides boto3.
zip -r9 "$ZIP" src >/dev/null
echo "Built: $ZIP"

