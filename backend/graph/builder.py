"""Re-export wrapper for backward compatibility.

The actual builder code has moved to builder_legacy.py.
Import from backend.graph.builder_legacy directly for new code.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "backend.graph.builder is deprecated. "
    "Use backend.graph.builder_legacy for the legacy builder, "
    "or backend.graph.builder_new for the new builder.",
    DeprecationWarning,
    stacklevel=2,
)

from backend.graph.builder_legacy import (  # noqa: F401, E402
    build_graph,
    get_compiled_graph,
)
