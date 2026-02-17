from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from .model import At
from .errors import MixinMatchError

@dataclass
class InjectorSpec:
    mixin_cls: type
    callback: Callable
    method: str
    at: At
    priority: int = 100
    require: Optional[int] = None
    expect: Optional[int] = None
    policy: str = "ERROR"   # placeholder

class Registry:
    def __init__(self) -> None:
        self._targets: Dict[str, List[type]] = {}
        self._injectors: Dict[Tuple[str,str], List[InjectorSpec]] = {}  # (target, method) -> injectors
        self._frozen = False

    def register_mixin(self, target: str, mixin_cls: type) -> None:
        if self._frozen:
            raise RuntimeError("Registry is frozen; register mixins before init() completes.")
        self._targets.setdefault(target, []).append(mixin_cls)

    def register_injector(self, target: str, spec: InjectorSpec) -> None:
        if self._frozen:
            raise RuntimeError("Registry is frozen; register injectors before init() completes.")
        key = (target, spec.method)
        self._injectors.setdefault(key, []).append(spec)
        self._injectors[key].sort(key=lambda s: (s.priority, s.callback.__qualname__))

    def get_injectors(self, target: str, method: str) -> List[InjectorSpec]:
        return list(self._injectors.get((target, method), []))

    def freeze(self) -> None:
        self._frozen = True

REGISTRY = Registry()
