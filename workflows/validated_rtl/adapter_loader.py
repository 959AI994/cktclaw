"""Robust loader for deps/verilog-generator/integration/verilog_adapter.py."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class VerilogAdapterLoadResult:
    ok: bool
    module: ModuleType | None
    vg_root: Path
    adapter_path: Path
    error: str = ""

    @property
    def hint(self) -> str:
        if self.ok:
            return ""
        return (
            f"Set VERILOG_GENERATOR_ROOT={self.vg_root} and run setup.sh if missing. "
            f"Expected adapter at {self.adapter_path}."
        )


def get_verilog_generator_root() -> Path:
    from cktclaw.skills.deps_roots import get_verilog_generator_root as _root

    return _root().resolve()


def get_adapter_path(vg_root: Path | None = None) -> Path:
    root = (vg_root or get_verilog_generator_root()).resolve()
    return root / "integration" / "verilog_adapter.py"


def _ensure_runtime_on_path(vg_root: Path) -> None:
    root_str = str(vg_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def load_verilog_adapter(*, vg_root: Path | None = None) -> VerilogAdapterLoadResult:
    """Load verilog_adapter from an absolute file path (avoids integration namespace clashes)."""
    root = (vg_root or get_verilog_generator_root()).resolve()
    adapter_path = get_adapter_path(root)
    if not adapter_path.is_file():
        return VerilogAdapterLoadResult(
            ok=False,
            module=None,
            vg_root=root,
            adapter_path=adapter_path,
            error=f"verilog_adapter not found at {adapter_path}",
        )
    _ensure_runtime_on_path(root)
    module_name = "cktclaw_verilog_adapter"
    try:
        spec = importlib.util.spec_from_file_location(module_name, adapter_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not create module spec for {adapter_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return VerilogAdapterLoadResult(
            ok=True,
            module=module,
            vg_root=root,
            adapter_path=adapter_path,
        )
    except Exception as exc:
        return VerilogAdapterLoadResult(
            ok=False,
            module=None,
            vg_root=root,
            adapter_path=adapter_path,
            error=str(exc),
        )


def ensure_verilog_adapter_available() -> VerilogAdapterLoadResult:
    """Preflight helper used during skill registration."""
    return load_verilog_adapter()


def get_adapter_functions(result: VerilogAdapterLoadResult) -> dict[str, Any]:
    if not result.ok or result.module is None:
        raise RuntimeError(result.error or "verilog_adapter unavailable")
    module = result.module
    return {
        "route_verilog_request": module.route_verilog_request,
        "run_verilog_workflow": module.run_verilog_workflow,
        "validate_verilog_artifacts": module.validate_verilog_artifacts,
        "verify_existing_verilog": module.verify_existing_verilog,
    }
