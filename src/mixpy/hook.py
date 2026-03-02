from __future__ import annotations
import importlib.abc, importlib.util, importlib.machinery
import sys, os
import types
import ast
import hashlib
import marshal
import pathlib

from .transformer import MixinTransformer
from .debug import maybe_dump
from .bootstrap import ensure_module_globals
from .weave import build_injector_map
from .registry import REGISTRY


def _injectors_fingerprint() -> str:
    """Produce a short hash that changes whenever the registered injectors change."""
    parts = []
    for (target, method), specs in REGISTRY.iter_injectors():
        for s in specs:
            parts.append(f"{target}:{method}:{s.at.type.value}:{s.at.name}:{getattr(s.callback, '__qualname__', '')}")
    return hashlib.md5("\n".join(sorted(parts)).encode()).hexdigest()


def _inject_class_members(module: types.ModuleType) -> None:
    """Set attributes registered as structural class-member injections on the module's classes."""
    mod_name = module.__name__
    for target, members in REGISTRY.iter_class_members():
        if not (target == mod_name or target.startswith(mod_name + ".")):
            continue
        # Resolve the class object within the module
        suffix = target[len(mod_name) + 1:] if target != mod_name else ""
        if not suffix:
            continue
        obj = module
        for part in suffix.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                break
        if obj is None:
            continue
        for name, member in members:
            setattr(obj, name, member)


class MixinLoader(importlib.machinery.SourceFileLoader):
    _CACHE_DIR = pathlib.Path("__pycache__") / "mixin_weaved"

    def get_code(self, fullname):
        path = self.get_filename(fullname)
        source_bytes = self.get_data(path)

        # ---- bytecode cache look-up ----
        src_hash = hashlib.md5(source_bytes).hexdigest()
        inj_hash = _injectors_fingerprint()
        cache_key = f"{src_hash}_{inj_hash}"
        safe_name = fullname.replace(".", "_")
        cache_file = self._CACHE_DIR / f"{safe_name}.{cache_key}.pyc"

        if cache_file.exists():
            try:
                with open(cache_file, "rb") as fh:
                    return marshal.loads(fh.read())
            except Exception:
                pass  # stale / corrupt cache; fall through to recompile

        code = self.source_to_code(source_bytes, path)

        # Write cache
        try:
            self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "wb") as fh:
                fh.write(marshal.dumps(code))
        except Exception:
            pass  # caching is best-effort

        return code

    def source_to_code(self, data, path, *, _optimize=-1):
        source = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        module_name = self.name
        tree = ast.parse(source, filename=path)
        tree = MixinTransformer(module_name=module_name, debug=os.getenv("MIXIN_DEBUG")=="True").visit(tree)
        ast.fix_missing_locations(tree)
        maybe_dump(module_name, tree)
        return compile(tree, path, "exec", dont_inherit=True, optimize=_optimize)

    def exec_module(self, module):
        # Prepare globals required by injected code
        ensure_module_globals(module.__dict__)
        # Build injector mapping for this module (targets within this module)
        inj_map = build_injector_map(module.__name__)
        module.__dict__["__mixin_injectors__"].update(inj_map)
        super().exec_module(module)
        # Structural injection: set new class members after the module is executed
        _inject_class_members(module)


class MixinFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if not spec or not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            return None
        if fullname.startswith("mixpy"):
            return None
        spec.loader = MixinLoader(fullname, spec.origin)
        return spec

_INSTALLED = False

def install_import_hook():
    global _INSTALLED
    if _INSTALLED:
        return
    sys.meta_path.insert(0, MixinFinder())
    _INSTALLED = True
