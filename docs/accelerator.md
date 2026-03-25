# C Extension Accelerator

## Overview

mixpy includes an optional C extension (`_accel`) that accelerates runtime hot paths:
- **Path resolution** — `fast_resolve_path()` replaces regex-based Python implementation
- **Condition evaluation** — `fast_eval_when()` for `When` conditions
- **Kwargs merging** — `fast_merge_kwargs()` for INVOKE dispatch

## Installation

### Pure Python (default)
```bash
pip install mixpy
```
No compilation needed. All features work via pure Python.

### With C Accelerator
```bash
MIXPY_BUILD_ACCEL=1 pip install mixpy
# or from source:
MIXPY_BUILD_ACCEL=1 python setup.py build_ext --inplace
```

### Checking Acceleration Status
```python
from mixpy._dispatch import ACCEL_AVAILABLE
print(f"C accelerator: {'enabled' if ACCEL_AVAILABLE else 'disabled'}")
```

## Architecture

The dual-path pattern in `_dispatch.py` tries the C extension first:
```python
try:
    from ._accel import fast_resolve_path, fast_eval_when, fast_merge_kwargs
    ACCEL_AVAILABLE = True
except ImportError:
    # Pure Python fallback
    ACCEL_AVAILABLE = False
```

When the C extension is not available, `_dispatch.py` imports equivalent
functions from the pure-Python `runtime.py` module and adapts their
signatures where needed.

## Performance

The C extension accelerates:

| Function | Speedup | Description |
|----------|---------|-------------|
| `fast_resolve_path` | ~3-5× | Path resolution without regex |
| `fast_eval_when` | ~2-3× | Condition evaluation |
| `fast_merge_kwargs` | ~2× | Dict merging |

Note: These are the runtime hot paths. The AST transformation (compile-time)
is not affected since it runs only once per module import.

## Accelerated Functions

### `fast_resolve_path(ctx_dict, path_str)`
Resolves dotted paths (with optional `[index]` notation) against a context dict.
Uses a fast C loop instead of per-call regex compilation. Falls back to direct
dict key lookup for simple (non-dotted) keys.

### `fast_eval_when(left, op_str, right, ctx_dict)`
Evaluates a single leaf `When` condition. Handles all comparison and membership
operators (`EQ`, `NE`, `GT`, `LT`, `GE`, `LE`, `IN`, `NOT_IN`, `IS_NONE`,
`NOT_NONE`, `LEN_EQ`, `LEN_GT`, `LEN_LT`). Logical combinators (`AND`, `OR`,
`NOT`) are still evaluated in Python since they require recursive dispatch.

### `fast_merge_kwargs(*maps)`
Merges N dictionaries into one, raising `TypeError` on duplicate keys. Skips
`None` arguments. This matches Python's call semantics more closely than a
naive `dict.update()`.
