from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_root_tool(wrapper_file: str, module_name: str) -> ModuleType:
    wrapper_path = Path(wrapper_file).resolve()
    repo_root = wrapper_path.parents[3]
    root_tool = repo_root / "tools" / wrapper_path.name
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    spec = importlib.util.spec_from_file_location(f"_aicrm_root_tools_{wrapper_path.stem}", root_tool)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load root tool: {root_tool}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if module_name != "__main__":
        sys.modules[module_name] = module
    return module
