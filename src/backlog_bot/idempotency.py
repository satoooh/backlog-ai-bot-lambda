"""
Simple idempotency guard using S3.

Stores a tiny marker object per processed comment id.
"""

from __future__ import annotations

import importlib


def _boto3():
    # Allow tests to monkeypatch module-level `boto3` symbol.
    return globals().get("boto3") or importlib.import_module("boto3")


def s3_record_if_new(bucket: str, key: str) -> bool:
    """Return True if recorded now (i.e., first time), False if already exists."""
    s3 = _boto3().client("s3")
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return False
    except Exception:
        pass
    s3.put_object(Bucket=bucket, Key=key, Body=b"1")
    return True
