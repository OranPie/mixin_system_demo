from __future__ import annotations
import ast
from typing import Any, Dict, List, Tuple, Optional
from .model import TYPE, At, POLICY
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

    def _policy(self, spec: InjectorSpec) -> POLICY:
        pol = spec.policy
        if isinstance(pol, POLICY):
            return pol
        raise TypeError(f"Injector policy must be POLICY enum, got {type(pol).__name__}")

    def _warn(self, msg: str) -> None:
        print(f"[mixin warn] {msg}")

    def _handle_count_mismatch(self, *, kind: str, spec: InjectorSpec, matched: int, expected: int, target: str, method: str) -> None:
        pol = self._policy(spec)
        msg = (
            f"{kind} mismatch for {target}.{method} {spec.callback.__qualname__}: "
            f"matched {matched} != {kind} {expected}"
        )
        if kind == "require":
            if pol in (POLICY.ERROR, POLICY.STRICT):
                raise MixinMatchError(msg)
            if pol == POLICY.WARN:
                self._warn(msg)
            return

        # kind == "expect"
        if pol == POLICY.STRICT:
            raise MixinMatchError(msg)
        if pol in (POLICY.ERROR, POLICY.WARN):
            self._warn(msg)

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
                            self._handle_count_mismatch(
                                kind="require",
                                spec=spec,
                                matched=len(matches),
                                expected=spec.require,
                                target=target,
                                method=item.name,
                            )
                        if spec.expect is not None and len(matches) != spec.expect:
                            self._handle_count_mismatch(
                                kind="expect",
                                spec=spec,
                                matched=len(matches),
                                expected=spec.expect,
                                target=target,
                                method=item.name,
                            )
                    handler.instrument(item, matches, specs, target)
        return node
