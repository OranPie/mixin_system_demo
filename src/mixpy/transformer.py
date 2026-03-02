from __future__ import annotations
import ast
import warnings
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
        warnings.warn(msg, stacklevel=2)

    def _handle_count_mismatch(self, *, kind: str, spec: InjectorSpec, matched: int, expected: int, target: str, method: str) -> None:
        pol = self._policy(spec)
        cb_name = getattr(spec.callback, "__qualname__", str(spec.callback))
        mixin_name = getattr(spec.mixin_cls, "__qualname__", None) if spec.mixin_cls else None
        mixin_hint = f" (mixin={mixin_name})" if mixin_name else ""
        msg = (
            f"[mixpy] {kind} mismatch for '{target}.{method}'{mixin_hint}\n"
            f"  injector : {cb_name}\n"
            f"  matched  : {matched}  (expected {kind}={expected})\n"
            f"  at       : {spec.at!r}\n"
            f"  Tip: Check that the method signature and injection type match the target source."
        )
        if kind == "require":
            # Policy hierarchy for require:
            #   STRICT / ERROR → raise MixinMatchError
            #   WARN           → emit warning
            #   IGNORE         → silent
            if pol in (POLICY.STRICT, POLICY.ERROR):
                raise MixinMatchError(msg)
            if pol == POLICY.WARN:
                self._warn(msg)
            return

        # kind == "expect"
        # Policy hierarchy for expect:
        #   STRICT → raise MixinMatchError (stricter than ERROR)
        #   ERROR / WARN → emit warning
        #   IGNORE → silent
        if pol == POLICY.STRICT:
            raise MixinMatchError(msg)
        if pol in (POLICY.ERROR, POLICY.WARN):
            self._warn(msg)

    def _instrument_method(self, item: ast.FunctionDef, target: str) -> None:
        """Apply all registered injectors to a single method node (FunctionDef or AsyncFunctionDef)."""
        injectors = REGISTRY.get_injectors(target, item.name)
        if not injectors:
            return
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

    def visit_ClassDef(self, node: ast.ClassDef):
        # Determine fully qualified target for this class: module.ClassName
        target = f"{self.module_name}.{node.name}"
        # Apply injectors per method (sync and async)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._instrument_method(item, target)
        return node

    def visit_Module(self, node: ast.Module):
        # Instrument module-level functions; target = module name itself.
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._instrument_method(item, self.module_name)
        self.generic_visit(node)
        return node
