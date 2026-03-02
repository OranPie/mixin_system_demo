from __future__ import annotations
from typing import Any, Callable, Dict, List, Tuple

from .registry import REGISTRY, InjectorSpec
from .runtime import _eval_when

def build_injector_map(module_name: str) -> Dict[Tuple[str,str,str,str], List[Callable]]:
    """Build mapping used by transformed modules.

    key = (target, method, type_name, at_name_str) -> [callables...]
    Only includes targets within the given module.

    Note: we wrap callbacks to enforce per-injector Condition (When DSL) at runtime.
    """
    out: Dict[Tuple[str,str,str,str], List[Callable]] = {}

    for (target, method), specs in REGISTRY.iter_injectors():  # type: ignore[attr-defined]
        if not (target == module_name or target.startswith(module_name + ".")):
            continue
        for spec in specs:
            canon_name = spec.at.name if spec.at.name is not None else spec.at.type.value
            key = (target, method, spec.at.type.value, str(canon_name))

            cond = spec.at.condition
            cb = spec.callback

            if cond is None:
                wrapped = cb
            else:
                def _make_wrapper(cb, cond):
                    def _wrapped(self_obj, ci, *args, **kwargs):
                        if _eval_when(cond, ci.get_context()):
                            return cb(self_obj, ci, *args, **kwargs)
                        return None
                    _wrapped.__name__ = getattr(cb, "__name__", "wrapped_injector")
                    _wrapped.__qualname__ = getattr(cb, "__qualname__", "wrapped_injector")
                    return _wrapped
                wrapped = _make_wrapper(cb, cond)

            out.setdefault(key, []).append(wrapped)
    return out
