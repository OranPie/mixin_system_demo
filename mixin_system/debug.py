from __future__ import annotations
import os, ast, pathlib

def maybe_dump(module_name: str, tree: ast.AST) -> None:
    if os.getenv("MIXIN_DEBUG") != "True":
        return
    out_dir = pathlib.Path("__pycache__") / "mixin_dump"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        src = ast.unparse(tree)
    except Exception:
        src = "<unparse failed>"
    (out_dir / f"{module_name.replace('.', '_')}.py").write_text(src, encoding="utf-8")
