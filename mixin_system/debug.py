from __future__ import annotations
import os, ast, pathlib

_dump_dir: str | None = None


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
    (out_dir / f"{module_name.replace('.', '_')}.py").write_text(src, encoding="utf-8")
