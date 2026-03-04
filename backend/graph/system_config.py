"""SystemConfigStore — JSON-file persistence for system-level node configuration."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "system_config.json"


class SystemConfigStore:
    """Thread-safe JSON store for system-scope config values.

    Atomic writes via NamedTemporaryFile + os.replace.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if not self._path.exists():
                return {}
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)

    def save(self, data: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(self._path.parent),
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            )
            try:
                json.dump(data, fd, ensure_ascii=False, indent=2)
                fd.flush()
                os.fsync(fd.fileno())
                fd.close()
                os.replace(fd.name, str(self._path))
            except BaseException:
                fd.close()
                try:
                    os.unlink(fd.name)
                except OSError:
                    pass
                raise

    def get_node(self, node_name: str) -> dict[str, Any]:
        return self.load().get(node_name, {})


# Module-level singleton
system_config_store = SystemConfigStore()
