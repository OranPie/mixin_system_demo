from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from .model import At, POLICY
from .errors import MixinMatchError

@dataclass
class InjectorSpec:
    mixin_cls: Optional[type]
    callback: Callable
    method: str
    at: At
    priority: int = 100
    require: Optional[int] = None
    expect: Optional[int] = None
    policy: POLICY = POLICY.ERROR
    mixin_priority: int = 100
    registration_index: int = 0

class Registry:
    def __init__(self) -> None:
        self._targets: Dict[str, List[type]] = {}
        self._target_priorities: Dict[Tuple[str, type], int] = {}
        self._injectors: Dict[Tuple[str,str], List[InjectorSpec]] = {}  # (target, method) -> injectors
        self._frozen = False
        self._next_index = 0

    def register_mixin(self, target: str, mixin_cls: type, priority: int = 100) -> None:
        if self._frozen:
            raise RuntimeError("Registry is frozen; register mixins before init() completes.")
        self._targets.setdefault(target, []).append(mixin_cls)
        self._target_priorities[(target, mixin_cls)] = int(priority)

    def _injector_sort_key(self, spec: InjectorSpec):
        mixin_name = ""
        if spec.mixin_cls is not None:
            mixin_name = f"{spec.mixin_cls.__module__}.{spec.mixin_cls.__qualname__}"
        return (spec.mixin_priority, spec.priority, mixin_name, spec.callback.__qualname__, spec.registration_index)

    def register_injector(self, target: str, spec: InjectorSpec) -> None:
        if self._frozen:
            raise RuntimeError("Registry is frozen; register injectors before init() completes.")
        if spec.mixin_cls is not None:
            spec.mixin_priority = self._target_priorities.get((target, spec.mixin_cls), spec.mixin_priority)
        spec.registration_index = self._next_index
        self._next_index += 1
        key = (target, spec.method)
        self._injectors.setdefault(key, []).append(spec)
        self._injectors[key].sort(key=self._injector_sort_key)

    def get_injectors(self, target: str, method: str) -> List[InjectorSpec]:
        return list(self._injectors.get((target, method), []))

    def freeze(self) -> None:
        self._frozen = True

REGISTRY = Registry()
