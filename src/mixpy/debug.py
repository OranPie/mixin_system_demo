from __future__ import annotations
import os
import ast
import pathlib
import sys
import time

_dump_dir: str | None = None

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"
_CYAN    = "\033[36m"
_YELLOW  = "\033[33m"
_GREEN   = "\033[32m"
_RED     = "\033[31m"
_MAGENTA = "\033[35m"

def _colour_enabled() -> bool:
    return bool(
        os.getenv("FORCE_COLOR")
        or (hasattr(sys.stderr, "isatty") and sys.stderr.isatty())
    )


def _c(text: str, *codes: str) -> str:
    if not _colour_enabled():
        return text
    return "".join(codes) + text + _RESET


# ---------------------------------------------------------------------------
# Log-level helpers
# ---------------------------------------------------------------------------

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_LEVEL_COLOURS = {
    "DEBUG": _DIM,
    "INFO":  _GREEN,
    "WARN":  _YELLOW,
    "ERROR": _RED,
}


def _current_level() -> int:
    raw = os.getenv("MIXPY_LOG_LEVEL", "WARN").upper()
    return _LEVELS.get(raw, _LEVELS["WARN"])


def log(level: str, message: str, *, stream=None) -> None:
    """Emit a structured log line to *stream* (default: ``sys.stderr``)."""
    if _LEVELS.get(level.upper(), 0) < _current_level():
        return
    if stream is None:
        stream = sys.stderr
    ts = time.strftime("%H:%M:%S")
    colour = _LEVEL_COLOURS.get(level.upper(), "")
    prefix = _c(f"[mixpy:{level.upper()}]", colour, _BOLD)
    print(f"{prefix} {_c(ts, _DIM)} {message}", file=stream)


def log_trace(target: str, method: str, type_val: str, at_name: str, cb_qualname: str, trace_id: str) -> None:
    """Emit a TRACE-level injector invocation line."""
    msg = (
        f"{_c(target, _CYAN)}.{_c(method, _BOLD)}"
        f" [{_c(type_val, _MAGENTA)}:{_c(str(at_name), _YELLOW)}]"
        f" cb={_c(cb_qualname, _DIM)}"
        f" trace_id={trace_id}"
    )
    log("DEBUG", msg)


def log_cancel(result: object) -> None:
    """Emit a TRACE-level cancellation line."""
    log("DEBUG", f"  {_c('↳ cancelled', _YELLOW)} result={result!r}")


# ---------------------------------------------------------------------------
# Dump helpers
# ---------------------------------------------------------------------------

def set_dump_dir(directory: str | None) -> None:
    """Set (or clear) the directory used by :func:`maybe_dump`."""
    global _dump_dir
    _dump_dir = directory


def maybe_dump(module_name: str, tree: ast.AST) -> None:
    if os.getenv("MIXIN_DEBUG") != "True":
        return
    out_path = _dump_dir or os.getenv("MIXIN_DUMP_DIR") or ".weaved"
    out_dir = pathlib.Path(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        src = ast.unparse(tree)
    except Exception:
        src = "<unparse failed>"

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    version = _get_version()
    header = (
        f"# MixPy v{version} — auto-generated weaved source\n"
        f"# Module  : {module_name}\n"
        f"# Generated: {ts}\n"
        f"# Do not edit — this file is overwritten on each import.\n"
        f"{'#' * 72}\n\n"
    )
    out_file = out_dir / f"{module_name.replace('.', '_')}.py"
    out_file.write_text(header + src, encoding="utf-8")
    log("INFO", f"AST dump written → {out_file}")


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("mixpy")
    except Exception:
        return "dev"

