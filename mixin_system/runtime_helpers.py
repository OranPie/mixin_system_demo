from __future__ import annotations
from typing import Any, Callable, List
import ast as _ast

def __mixin_expr__(stmts: list, orig):
    # stmts is actually an AST list when executed? No—this helper is called at runtime.
    # In our demo we pass pre-built statements inside a lambda and execute them via exec would be unsafe.
    # So this helper is only a placeholder; transformer avoids using this in the demo runtime.
    return orig

def __mixin_invoke__(call_original: Callable[[], Any], pre_stmts: list):
    # pre_stmts are executed inline by AST, not passed here in this demo.
    return call_original()

def __mixin_attr_write__(orig_value: Any, pre_stmts: list):
    return orig_value
