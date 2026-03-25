"""Dispatch acceleration layer.

Tries to import C-accelerated versions of hot-path functions.
Falls back to pure-Python implementations transparently.
"""
try:
    from ._accel import fast_resolve_path, fast_eval_when, fast_merge_kwargs
    ACCEL_AVAILABLE = True
except ImportError:
    ACCEL_AVAILABLE = False
    # Fallback: import from pure-Python runtime
    from .runtime import _resolve_path as fast_resolve_path  # type: ignore[attr-defined]
    from .runtime import _eval_when as _py_eval_when
    from .runtime import merge_kwargs as fast_merge_kwargs  # type: ignore[attr-defined]

    def fast_eval_when(left, op, right, ctx):  # type: ignore[misc]
        """Adapter: convert decomposed args to When object for Python path."""
        from .model import When, OP
        cond = When(left=left, op=OP(op), right=right)
        return _py_eval_when(cond, ctx)
