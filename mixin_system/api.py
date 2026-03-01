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


def configure(*, debug: bool | None = None, trace: bool | None = None, source_dump_dir: str | None = None) -> None:
    """Set lightweight runtime options for the mixin system.

    Parameters
    ----------
    debug:
        When ``True`` sets ``MIXIN_DEBUG=True`` which causes each weaved module
        to be written as human-readable Python source to *source_dump_dir*
        (default ``.weaved/``).
    trace:
        When ``True`` enables per-injector trace logging to ``stderr``.
    source_dump_dir:
        Directory for source ejection output.  Defaults to ``.weaved/`` when
        debug is enabled.  Pass an empty string to reset to the default.
    """
    if debug is not None:
        os.environ["MIXIN_DEBUG"] = "True" if debug else "False"
    if trace is not None:
        os.environ["MIXIN_TRACE"] = "True" if trace else "False"
    if source_dump_dir is not None:
        from .debug import set_dump_dir
        set_dump_dir(source_dump_dir if source_dump_dir else None)


def init(*, debug: bool | None = None) -> None:
    """Install import hook and freeze registry."""
    configure(debug=debug)
    install_builtin_handlers()
    install_import_hook()
    REGISTRY.freeze()


def mixin(target: str | type | list, *, priority: int = 100):
    # Support a list of targets: register the same patch class against each one.
    if isinstance(target, list):
        resolved_targets = [target_path(t) for t in target]
    else:
        resolved_targets = [target_path(target)]
    mixin_priority = int(priority)

    def deco(cls):
        cls.__mixin_target__ = resolved_targets[0] if len(resolved_targets) == 1 else resolved_targets
        cls.__mixin_priority__ = mixin_priority
        for resolved_target in resolved_targets:
            try:
                REGISTRY.register_mixin(resolved_target, cls, priority=mixin_priority)
            except RuntimeError as exc:
                _ensure_registration_allowed(exc)

            # scan methods: @inject-decorated ones become injector callbacks;
            # plain (non-dunder) methods are injected as new class members.
            for attr_name, attr in cls.__dict__.items():
                spec = getattr(attr, "__inject_spec__", None)
                if spec:
                    resolved = replace(spec, mixin_cls=cls, mixin_priority=mixin_priority)
                    try:
                        REGISTRY.register_injector(resolved_target, resolved)
                    except RuntimeError as exc:
                        _ensure_registration_allowed(exc)
                elif not attr_name.startswith("_") and callable(attr):
                    # Structural injection: add the plain method to the target class.
                    try:
                        REGISTRY.register_class_member(resolved_target, attr_name, attr)
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


def at_exception(*, location: Loc | None = None) -> At:
    return At(type=TYPE.EXCEPTION, name=None, location=location)


def at_yield(*, location: Loc | None = None) -> At:
    """Return an :class:`~mixin_system.At` descriptor for YIELD injection points."""
    return At(type=TYPE.YIELD, name=None, location=location)


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


def inject_exception(
    method: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_exception(location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )


def inject_yield(
    method: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    """Shorthand for :func:`inject` with ``at=at_yield(...)``."""
    return inject(
        method=method,
        at=at_yield(location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )


# ---------------------------------------------------------------------------
# Hot-reloading / Dynamic Unpatching
# ---------------------------------------------------------------------------

def unregister_injector(target: str, method: str, callback: Callable) -> bool:
    """Remove *callback* from the live injector registry.

    Temporarily unfreezes the registry, removes the callback, and refreezes.
    Returns ``True`` if anything was removed.

    Call :func:`reload_target` afterwards to re-import the target module with
    the updated injector set.
    """
    was_frozen = REGISTRY._frozen
    REGISTRY.unfreeze()
    try:
        return REGISTRY.unregister_injector(target, method, callback)
    finally:
        if was_frozen:
            REGISTRY.freeze()


def reload_target(module_name: str) -> None:
    """Force the target module to be re-imported through the mixin import hook.

    This re-weaves the module's AST against the current registry state,
    picking up any changes made by :func:`unregister_injector`.
    """
    import importlib
    import sys

    mod = sys.modules.get(module_name)
    if mod is None:
        raise ValueError(f"Module {module_name!r} is not currently loaded.")
    # Remove from sys.modules so the next import goes through MixinLoader.
    sys.modules.pop(module_name)
    importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Type-stub generation
# ---------------------------------------------------------------------------

def generate_stubs(output_dir: str = ".") -> None:
    """Generate ``.pyi`` stub files that expose injected hooks for IDE support.

    For each target module a single stub file is written to *output_dir*
    containing a ``# mixin-injected`` comment for every registered injector,
    making it discoverable by static analysis tools.
    """
    import pathlib
    import textwrap

    out_path = pathlib.Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Group injectors by their target module
    by_module: dict[str, list[tuple[str, str, object]]] = {}
    for (target, method), specs in REGISTRY.iter_injectors():
        # Derive module path: everything before the last component (class name)
        # or the target itself for module-level targets.
        parts = target.rsplit(".", 1)
        module_part = parts[0] if len(parts) > 1 else target
        for spec in specs:
            by_module.setdefault(module_part, []).append((target, method, spec))

    for module, entries in by_module.items():
        stub_file = out_path / f"{module.replace('.', '_')}.pyi"
        lines = [
            f"# Auto-generated stub for mixin injectors targeting {module}\n",
            "# Do not edit – regenerate with mixin_system.generate_stubs()\n",
            "from typing import Any\n\n",
        ]
        seen_classes: set[str] = set()
        for target, method, spec in entries:
            cls_name = target.split(".")[-1] if "." in target else None
            cb_name = getattr(spec.callback, "__qualname__", str(spec.callback))
            comment = f"# mixin-injected [{spec.at.type.value}] by {cb_name}"
            if cls_name and cls_name not in seen_classes:
                lines.append(f"class {cls_name}:\n")
                seen_classes.add(cls_name)
            indent = "    " if cls_name else ""
            lines.append(f"{indent}def {method}(self, *args: Any, **kwargs: Any) -> Any: ...  {comment}\n")
        stub_file.write_text("".join(lines), encoding="utf-8")


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


def at_exception(*, location: Loc | None = None) -> At:
    return At(type=TYPE.EXCEPTION, name=None, location=location)


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


def inject_exception(
    method: str,
    *,
    location: Loc | None = None,
    priority: int = 100,
    require: int | None = None,
    expect: int | None = None,
    policy: POLICY = POLICY.ERROR,
):
    return inject(
        method=method,
        at=at_exception(location=location),
        priority=priority,
        require=require,
        expect=expect,
        policy=policy,
    )
