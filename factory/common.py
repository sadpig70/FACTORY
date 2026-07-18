"""Shared primitives: root resolution, atomic writes, hashing, UTC time.

Mirrors the PAO runtime idioms (atomic temp->fsync->os.replace writes,
content hashing) so Factory state on disk is as crash-safe as the bus it drives.
Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path.home() / ".agents" / "factory"

# Filesystem-safe token for pairing filenames: keep the design's `@` and `__`
# separators, fold everything else that could break a path into `_`.
_UNSAFE = re.compile(r"[^A-Za-z0-9._@-]+")


def resolve_root(value: str | os.PathLike[str] | None) -> Path:
    """FACTORY_ROOT resolution: explicit --root > env FACTORY_ROOT > default."""
    if value:
        return Path(value).expanduser().resolve()
    env_value = os.environ.get("FACTORY_ROOT", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_ROOT.resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_json(path: str | os.PathLike[str]) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write_json(path: str | os.PathLike[str], payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=".factory-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = ""
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return target


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def copy_into(source: str | os.PathLike[str], dest_dir: str | os.PathLike[str]) -> tuple[Path, str]:
    """Copy ``source`` into ``dest_dir`` (created if needed); return (dest, sha256).

    Probe buses are disposable, so verified evidence is copied out of the bus
    into the ledger. The content hash is taken from the copy that now lives in
    the ledger, so a later bus-path rot cannot invalidate it.
    """
    src = Path(source)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    destination = dest / src.name
    shutil.copyfile(src, destination)
    return destination, sha256_file(destination)


def safe_token(value: str) -> str:
    return _UNSAFE.sub("_", value)
