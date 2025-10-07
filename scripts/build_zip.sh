#!/usr/bin/env bash
set -eu
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
OUT_DIR="$ROOT_DIR/dist"
ZIP="$OUT_DIR/lambda.zip"

mkdir -p "$OUT_DIR"
rm -f "$ZIP"

cd "$ROOT_DIR"

# Package only the Python package at archive root (no external deps). Lambda provides boto3.
(cd src && zip -r9 "$ZIP" backlog_bot -x "**/__pycache__/*" >/dev/null)
echo "Built: $ZIP"
