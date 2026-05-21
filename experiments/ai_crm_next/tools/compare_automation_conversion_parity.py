#!/usr/bin/env python
from __future__ import annotations

try:
    from ._root_tool_wrapper import load_root_tool
except ImportError:  # pragma: no cover - script execution path
    from _root_tool_wrapper import load_root_tool

_ROOT_TOOL = load_root_tool(__file__, __name__)

if __name__ == "__main__":
    raise SystemExit(_ROOT_TOOL.main())
