from __future__ import annotations
from typing import Any, Callable, Dict, List, Tuple
import mixin_system.runtime as mixin_system_runtime
import mixin_system.model as mixin_system_model

def ensure_module_globals(globals_dict: Dict[str, Any]) -> None:
    # runtime + model shortcuts
    globals_dict.setdefault("mixin_system_runtime", mixin_system_runtime)
    globals_dict.setdefault("mixin_system_model", mixin_system_model)

    # injector mapping: key=(target, method, type_name, at_name) -> [callables...]
    globals_dict.setdefault("__mixin_injectors__", {})

    # helpers
    globals_dict.setdefault("__mixin_invoke__", _mixin_invoke_wrapper)
    globals_dict.setdefault("__mixin_attr_write__", _mixin_attr_write_wrapper)

def _mixin_invoke_wrapper(call_original: Callable[[], Any], pre_stmts_ignored):
    # pre_stmts are inserted as statements inline in transformed AST, so ignored here.
    return call_original()

def _mixin_attr_write_wrapper(orig_value: Any, pre_stmts_ignored):
    # AST inserts pre statements inline; helper just returns the (possibly already replaced) value
    return orig_value
