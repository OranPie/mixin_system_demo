from __future__ import annotations
import ast
from typing import Any, Dict, List, Tuple, Optional
from .model import TYPE, At
from .registry import REGISTRY, InjectorSpec
from .handlers import get_handler
from .errors import MixinMatchError
from .location_utils import apply_location

def transform_module(source: str, filename: str, module_name: str) -> ast.Module:
    tree = ast.parse(source, filename=filename)
    return tree

class MixinTransformer(ast.NodeTransformer):
    def __init__(self, module_name: str, debug: bool = False):
        self.module_name = module_name
        self.debug = debug
        super().__init__()

    def visit_ClassDef(self, node: ast.ClassDef):
        # Determine fully qualified target for this class: module.ClassName
        target = f"{self.module_name}.{node.name}"
        # Apply injectors per method
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                injectors = REGISTRY.get_injectors(target, item.name)
                if not injectors:
                    continue
                # Group by At (type+name+selector+location) for batching
                by_at: Dict[At, List[InjectorSpec]] = {}
                for spec in injectors:
                    by_at.setdefault(spec.at, []).append(spec)
                for at, specs in by_at.items():
                    handler = get_handler(at.type)
                    matches = apply_location(item, handler.find(item, at), at)
                    # enforce require/expect for each spec (simple: same match count)
                    for spec in specs:
                        if spec.require is not None and len(matches) != spec.require:
                            raise MixinMatchError(f"Require failed for {target}.{item.name} {spec.callback.__qualname__}: matched {len(matches)} != require {spec.require}")
                        if spec.expect is not None and len(matches) != spec.expect and self.debug:
                            print(f"[mixin warn] Expect mismatch for {target}.{item.name} {spec.callback.__qualname__}: matched {len(matches)} != expect {spec.expect}")
                    handler.instrument(item, matches, specs, target)
        return node
