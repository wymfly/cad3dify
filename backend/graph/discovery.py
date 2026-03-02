"""Auto-discover and import all node modules under backend/graph/nodes/.

Calling discover_nodes() triggers the import of every .py file in the
nodes package, which in turn fires @register_node decorators.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_discovered = False
_discovery_lock = __import__("threading").Lock()


def discover_nodes() -> None:
    """Import all node modules to trigger @register_node decorators.

    Idempotent: subsequent calls are no-ops.  Thread-safe via lock.
    """
    global _discovered
    with _discovery_lock:
        if _discovered:
            return

        nodes_dir = Path(__file__).parent / "nodes"
        if not nodes_dir.is_dir():
            logger.warning("Nodes directory not found: %s", nodes_dir)
            _discovered = True
            return

        for py_file in sorted(nodes_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"backend.graph.nodes.{py_file.stem}"
            try:
                importlib.import_module(module_name)
                logger.debug("Discovered node module: %s", module_name)
            except Exception as exc:
                logger.error("Failed to import node module %s: %s", module_name, exc)

        _discovered = True


def reset_discovery() -> None:
    """Reset discovery state (for testing only)."""
    global _discovered
    _discovered = False
