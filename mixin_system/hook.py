from __future__ import annotations
import importlib.abc, importlib.util, importlib.machinery
import sys, os
import types
import ast

from .transformer import MixinTransformer
from .debug import maybe_dump
from .bootstrap import ensure_module_globals
from .weave import build_injector_map

class MixinLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        # Always compile from source so AST weaving is applied on each fresh import.
        # Using default SourceFileLoader.get_code may reuse stale .pyc that predates
        # current weaving logic.
        path = self.get_filename(fullname)
        source = self.get_data(path)
        return self.source_to_code(source, path)

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

class MixinFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if not spec or not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            return None
        if fullname.startswith("mixin_system"):
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
