from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Callable

from .builtin_handlers import install_builtin_handlers
from .hook import install_import_hook
from .model import At, Loc, POLICY, TYPE
from .registry import InjectorSpec, REGISTRY


def target_path(target: str | type) -> str:
    """Resolve a mixin target into a fully qualified class path."""
    if isinstance(target, str):
        resolved = target.strip()
        if not resolved:
            raise ValueError("target must be a non-empty string or a class object.")
        return resolved
    if isinstance(target, type):
        return f"{target.__module__}.{target.__qualname__}"
    raise TypeError("target must be a non-empty string or a class object.")


def _ensure_registration_allowed(exc: RuntimeError) -> None:
    msg = str(exc)
    if "frozen" in msg.lower():
        raise RuntimeError(
            "Registry is frozen. Import and register patch modules before calling mixin_system.init()."
        ) from exc
    raise exc


def configure(*, debug: bool | None = None) -> None:
    """Set lightweight runtime options for the mixin system."""
    if debug is not None:
        os.environ["MIXIN_DEBUG"] = "True" if debug else "False"


def init(*, debug: bool | None = None) -> None:
    """Install import hook and freeze registry."""
    configure(debug=debug)
    install_builtin_handlers()
    install_import_hook()
    REGISTRY.freeze()


def mixin(target: str | type, *, priority: int = 100):
    resolved_target = target_path(target)
    mixin_priority = int(priority)

    def deco(cls):
        cls.__mixin_target__ = resolved_target
        cls.__mixin_priority__ = mixin_priority
        try:
            REGISTRY.register_mixin(resolved_target, cls, priority=mixin_priority)
        except RuntimeError as exc:
            _ensure_registration_allowed(exc)

        # scan methods for inject metadata (populated by @inject)
        for _, attr in cls.__dict__.items():
            spec = getattr(attr, "__inject_spec__", None)
            if spec:
                resolved = replace(spec, mixin_cls=cls, mixin_priority=mixin_priority)
                try:
                    REGISTRY.register_injector(resolved_target, resolved)
                except RuntimeError as exc:
                    _ensure_registration_allowed(exc)
        return cls

    return deco


def inject(
    method: str,
    at: At,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    if not isinstance(method, str) or not method.strip():
        raise ValueError("method must be a non-empty string.")
    if not isinstance(at, At):
        raise TypeError("at must be an At(...) instance.")
    if not isinstance(policy, POLICY):
        raise TypeError("policy must be a POLICY enum value.")

    def deco(fn: Callable):
        # The runtime callback signature used by handlers is (ci, *args, **kwargs)
        spec = InjectorSpec(
            mixin_cls=None,
            callback=fn,
            method=method.strip(),
            at=at,
            priority=priority,
            require=require,
            expect=expect,
            policy=policy,
        )
        fn.__inject_spec__ = spec
        return fn

    return deco


def at_head(*, location: Loc | None = None) -> At:
    return At(type=TYPE.HEAD, name=None, location=location)


def at_tail(*, location: Loc | None = None) -> At:
    return At(type=TYPE.TAIL, name=None, location=location)


def at_parameter(name: str, *, location: Loc | None = None) -> At:
    return At(type=TYPE.PARAMETER, name=name, location=location)


def at_const(value: Any, *, location: Loc | None = None) -> At:
    return At(type=TYPE.CONST, name=value, location=location)


def at_invoke(name: str, *, selector: Any = None, location: Loc | None = None) -> At:
    return At(type=TYPE.INVOKE, name=name, selector=selector, location=location)


def at_attribute(name: str, *, location: Loc | None = None) -> At:
    return At(type=TYPE.ATTRIBUTE, name=name, location=location)


def inject_head(
    method: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(method=method, at=at_head(location=location), priority=priority, require=require, expect=expect, policy=policy)


def inject_tail(
    method: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(method=method, at=at_tail(location=location), priority=priority, require=require, expect=expect, policy=policy)


def inject_parameter(
    method: str,
    name: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_parameter(name=name, location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )


def inject_const(
    method: str,
    value: Any,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_const(value=value, location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )


def inject_invoke(
    method: str,
    name: str,
    *,
    selector: Any = None,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_invoke(name=name, selector=selector, location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )


def inject_attribute(
    method: str,
    name: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_attribute(name=name, location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )
