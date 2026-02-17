from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Any
import importlib
import sys

from .registry import REGISTRY, InjectorSpec
from .hook import install_import_hook
from .builtin_handlers import install_builtin_handlers

def init() -> None:
    """Install import hook and freeze registry."""
    install_builtin_handlers()
    install_import_hook()
    # Freeze registry to ensure deterministic runtime
    REGISTRY.freeze()

def mixin(target: str):
    def deco(cls):
        cls.__mixin_target__ = target
        REGISTRY.register_mixin(target, cls)
        # scan methods for inject metadata (populated by @inject)
        for name, attr in cls.__dict__.items():
            spec = getattr(attr, "__inject_spec__", None)
            if spec:
                REGISTRY.register_injector(target, spec)
        return cls
    return deco

def inject(method: str, at, priority: int = 100, require: int | None = None, expect: int | None = None, policy: str = "ERROR"):
    def deco(fn: Callable):
        # The runtime callback signature used by handlers is (ci, *args, **kwargs)
        spec = InjectorSpec(mixin_cls=None, callback=fn, method=method, at=at, priority=priority, require=require, expect=expect, policy=policy)
        fn.__inject_spec__ = spec
        return fn
    return deco
