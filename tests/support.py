"""Shared accounting and loading helpers for the standard-library test suite."""
from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path
from types import ModuleType

COUNTS: Counter[str] = Counter()


def record(kind: str, amount: int) -> None:
    if type(amount) is not int or amount < 0:
        raise ValueError("test accounting must be a nonnegative integer")
    COUNTS[kind] += amount


def load_script(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
