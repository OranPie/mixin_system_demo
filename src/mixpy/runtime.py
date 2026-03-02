from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import asyncio
import os
import time
from .model import TYPE, When, OP

@dataclass
class CallbackInfo:
    type: TYPE
    target: str
    method: str
    at_name: Any
    trace_id: str
    _cancelled: bool = False
    _result: Any = None
    _value_set: bool = False
    _new_value: Any = None

    _ctx: Optional[Dict[str, Any]] = None
    _call_original: Optional[Callable[..., Any]] = None
    _call_args: Optional[List[Any]] = None
    _call_kwargs: Optional[Dict[str, Any]] = None
    _original_called: bool = False
    _original_result: Any = None

    def cancel(self, result: Any = None) -> None:
        self._cancelled = True
        self._result = result

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def result(self) -> Any:
        return self._result

    def set_value(self, new_val: Any) -> None:
        self._value_set = True
        self._new_value = new_val

    def set_return_value(self, new_val: Any) -> None:
        """Mutate the return value without cancelling subsequent injectors."""
        self.set_value(new_val)

    def get_value(self) -> Any:
        if self._ctx and "value" in self._ctx:
            return self._ctx["value"]
        return None

    @property
    def value_set(self) -> bool:
        return self._value_set

    @property
    def new_value(self) -> Any:
        return self._new_value

    def get_context(self) -> Dict[str, Any]:
        return dict(self._ctx or {})

    def get_locals(self) -> Dict[str, Any]:
        if self._ctx and "locals" in self._ctx and isinstance(self._ctx["locals"], dict):
            return dict(self._ctx["locals"])
        return {}

    @property
    def parameter_name(self) -> Optional[str]:
        if self._ctx and self._ctx.get("param") is not None:
            return str(self._ctx["param"])
        return None

    def get_parameter(self) -> Any:
        return self.get_value()

    def set_parameter(self, new_val: Any) -> None:
        self.set_value(new_val)

    def get_call_args(self) -> tuple[List[Any], Dict[str, Any]]:
        if self._call_args is None or self._call_kwargs is None:
            raise RuntimeError("call arguments are only available for INVOKE injection points.")
        return list(self._call_args), dict(self._call_kwargs)

    def set_call_args(self, *args: Any, **kwargs: Any) -> None:
        if not self._call_original:
            raise RuntimeError("set_call_args is only available for INVOKE injection points.")
        self._call_args = list(args)
        self._call_kwargs = dict(kwargs)
        if self._ctx is not None:
            self._ctx["args"] = list(args)
            self._ctx["kwargs"] = dict(kwargs)
            self._ctx["call_args"] = list(args)
            self._ctx["call_kwargs"] = dict(kwargs)

    def call_original(self, *args: Any, **kwargs: Any) -> Any:
        if not self._call_original:
            raise RuntimeError("call_original is not available for this injection point.")
        if args or kwargs:
            self.set_call_args(*args, **kwargs)
        call_args = list(self._call_args or [])
        call_kwargs = dict(self._call_kwargs or {})
        result = self._call_original(*call_args, **call_kwargs)
        self._original_called = True
        self._original_result = result
        return result

# ---------------- Condition DSL evaluation ----------------

def _eval_when(cond: Optional[When], ctx: Dict[str, Any]) -> bool:
    if cond is None:
        return True
    if cond.op == OP.AND:
        return all(_eval_when(c, ctx) for c in cond.right)
    if cond.op == OP.OR:
        return any(_eval_when(c, ctx) for c in cond.right)
    if cond.op == OP.NOT:
        return not _eval_when(cond.right, ctx)

    left_val = _resolve_path(ctx, cond.left)
    op = cond.op
    right = cond.right
    if op == OP.EQ: return left_val == right
    if op == OP.NE: return left_val != right
    if op == OP.GT: return left_val > right
    if op == OP.LT: return left_val < right
    if op == OP.GE: return left_val >= right
    if op == OP.LE: return left_val <= right
    if op == OP.IN: return left_val in right
    if op == OP.NOT_IN: return left_val not in right
    if op == OP.IS_NONE: return left_val is None
    if op == OP.NOT_NONE: return left_val is not None
    if op == OP.ISINSTANCE: return isinstance(left_val, right)
    if op == OP.MATCH:
        import re
        return re.search(str(right), str(left_val)) is not None
    if op == OP.LEN_EQ: return len(left_val) == right
    if op == OP.LEN_GT: return len(left_val) > right
    if op == OP.LEN_LT: return len(left_val) < right
    raise ValueError(f"Unsupported OP: {op}")

def _resolve_path(ctx: Dict[str, Any], path: str) -> Any:
    # supports dotted names and simple [index] for list access like args[0]
    if path in ctx:
        return ctx[path]
    cur: Any = ctx
    import re
    tokens = re.split(r'\.(?![^\[]*\])', path)
    for t in tokens:
        m = re.fullmatch(r'(\w+)(\[(\d+)\])?', t)
        if not m:
            return None
        key = m.group(1)
        idx = m.group(3)
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
        if idx is not None and cur is not None:
            try:
                cur = cur[int(idx)]
            except Exception:
                return None
    return cur

# ---------------- Context normalization ----------------

def _normalize_ctx(ci: CallbackInfo, ctx: Dict[str, Any], *, self_obj: Any, args: List[Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ctx or {})
    out.setdefault("type", ci.type.value)
    out.setdefault("target", ci.target)
    out.setdefault("method", ci.method)
    out.setdefault("at", ci.at_name)
    out.setdefault("self", self_obj)
    out.setdefault("args", list(args))
    out.setdefault("kwargs", dict(kwargs))
    out.setdefault("locals", out.get("locals", {}))
    return out


def merge_kwargs(*maps: Any) -> Dict[str, Any]:
    """Best-effort merge for call-site kwargs.

    Used to preserve `**mapping` keys for INVOKE dispatch + ctx.
    Raises TypeError on duplicate keys (closer to Python call semantics).
    """
    out: Dict[str, Any] = {}
    for m in maps:
        if m is None:
            continue
        d = dict(m)
        for k, v in d.items():
            if k in out:
                raise TypeError(f"multiple values for keyword argument '{k}'")
            out[k] = v
    return out

# ---------------- Dispatch ----------------

def dispatch_injectors(injectors: List[Callable], ci: CallbackInfo, ctx: Dict[str, Any], *cb_args, **cb_kwargs):
    """Call injectors with signature: (self_obj, ci, *args, **kwargs)."""
    self_obj = cb_args[0] if cb_args else None
    rest = list(cb_args[1:]) if len(cb_args) > 1 else []
    ctx2 = _normalize_ctx(ci, ctx, self_obj=self_obj, args=rest, kwargs=dict(cb_kwargs))
    ci._ctx = ctx2

    _trace = os.getenv("MIXIN_TRACE") == "True"

    for cb in injectors:
        args_for_cb = list(rest)
        kwargs_for_cb = dict(cb_kwargs)
        if ci.type == TYPE.INVOKE and ci._call_args is not None and ci._call_kwargs is not None:
            args_for_cb = list(ci._call_args)
            kwargs_for_cb = dict(ci._call_kwargs)
            ci._ctx["args"] = list(args_for_cb)
            ci._ctx["kwargs"] = dict(kwargs_for_cb)
            ci._ctx["call_args"] = list(args_for_cb)
            ci._ctx["call_kwargs"] = dict(kwargs_for_cb)

        if _trace:
            from .debug import log_trace, log_cancel
            log_trace(ci.target, ci.method, ci.type.value, ci.at_name,
                      getattr(cb, "__qualname__", str(cb)), ci.trace_id)

        cb(self_obj, ci, *args_for_cb, **kwargs_for_cb)
        if ci.is_cancelled:
            if _trace:
                from .debug import log_cancel
                log_cancel(ci.result)
            return ci.result
    return None


async def async_dispatch_injectors(injectors: List[Callable], ci: CallbackInfo, ctx: Dict[str, Any], *cb_args, **cb_kwargs):
    """Async variant of :func:`dispatch_injectors`.

    Awaits callbacks that return coroutines, enabling ``async def`` callbacks
    inside ``async def`` target methods.
    """
    self_obj = cb_args[0] if cb_args else None
    rest = list(cb_args[1:]) if len(cb_args) > 1 else []
    ctx2 = _normalize_ctx(ci, ctx, self_obj=self_obj, args=rest, kwargs=dict(cb_kwargs))
    ci._ctx = ctx2

    _trace = os.getenv("MIXIN_TRACE") == "True"

    for cb in injectors:
        args_for_cb = list(rest)
        kwargs_for_cb = dict(cb_kwargs)
        if ci.type == TYPE.INVOKE and ci._call_args is not None and ci._call_kwargs is not None:
            args_for_cb = list(ci._call_args)
            kwargs_for_cb = dict(ci._call_kwargs)
            ci._ctx["args"] = list(args_for_cb)
            ci._ctx["kwargs"] = dict(kwargs_for_cb)
            ci._ctx["call_args"] = list(args_for_cb)
            ci._ctx["call_kwargs"] = dict(kwargs_for_cb)

        if _trace:
            from .debug import log_trace, log_cancel
            log_trace(ci.target, ci.method, ci.type.value, ci.at_name,
                      getattr(cb, "__qualname__", str(cb)), ci.trace_id)

        result = cb(self_obj, ci, *args_for_cb, **kwargs_for_cb)
        if asyncio.iscoroutine(result):
            await result
        if ci.is_cancelled:
            if _trace:
                from .debug import log_cancel
                log_cancel(ci.result)
            return ci.result
    return None

# ---------------- Expression-level helpers ----------------

def eval_const(inj_map, target: str, method: str, at_name: str, self_obj, const_value):
    key = (target, method, "CONST", str(at_name))
    injectors = inj_map.get(key, [])
    ci = CallbackInfo(type=TYPE.CONST, target=target, method=method, at_name=str(at_name), trace_id=str(time.time_ns()))
    ctx = {"value": const_value, "const_value": const_value}
    dispatch_injectors(injectors, ci, ctx, self_obj)
    if ci.is_cancelled:
        return ci.result
    if ci.value_set:
        return ci.new_value
    return const_value

def eval_invoke(inj_map, target: str, method: str, at_name: str, self_obj, call_original, args_list, kwargs_dict):
    key = (target, method, "INVOKE", str(at_name))
    injectors = inj_map.get(key, [])
    ci = CallbackInfo(type=TYPE.INVOKE, target=target, method=method, at_name=str(at_name), trace_id=str(time.time_ns()))
    ci._call_original = call_original
    ci._call_args = list(args_list)
    ci._call_kwargs = dict(kwargs_dict)
    ctx = {"args": list(args_list), "kwargs": dict(kwargs_dict), "call_args": list(args_list), "call_kwargs": dict(kwargs_dict)}
    dispatch_injectors(injectors, ci, ctx, self_obj, *args_list, **kwargs_dict)
    if ci.is_cancelled:
        return ci.result
    if ci._original_called:
        return ci._original_result
    return ci.call_original()

def eval_attr_write(inj_map, target: str, method: str, at_name: str, self_obj, new_value):
    key = (target, method, "ATTRIBUTE", str(at_name))
    injectors = inj_map.get(key, [])
    ci = CallbackInfo(type=TYPE.ATTRIBUTE, target=target, method=method, at_name=str(at_name), trace_id=str(time.time_ns()))
    ctx = {"value": new_value, "attr": str(at_name)}
    dispatch_injectors(injectors, ci, ctx, self_obj, new_value)
    if ci.is_cancelled:
        return ci.result
    if ci.value_set:
        return ci.new_value
    return new_value


def eval_yield(inj_map, target: str, method: str, at_name: str, self_obj, yield_value):
    """Runtime helper for YIELD injection points.

    Replaces the yielded value after running callbacks; callbacks use
    ``ci.set_value(x)`` to mutate the value or ``ci.cancel(result=x)`` to
    substitute an entirely different value (the generator will yield that
    instead).
    """
    key = (target, method, "YIELD", str(at_name))
    injectors = inj_map.get(key, [])
    if not injectors:
        return yield_value
    ci = CallbackInfo(type=TYPE.YIELD, target=target, method=method, at_name=str(at_name), trace_id=str(time.time_ns()))
    ctx = {"value": yield_value, "yield_value": yield_value}
    dispatch_injectors(injectors, ci, ctx, self_obj, yield_value)
    if ci.is_cancelled:
        return ci.result
    if ci.value_set:
        return ci.new_value
    return yield_value
