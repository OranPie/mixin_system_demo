from types import SimpleNamespace

import pytest

from mixin_system.model import OP, TYPE, When
from mixin_system.runtime import (
    CallbackInfo,
    _eval_when,
    _resolve_path,
    dispatch_injectors,
    merge_kwargs,
)


def test_resolve_path_supports_dict_attribute_and_index():
    ctx = {
        "args": [10, 20],
        "obj": SimpleNamespace(inner=SimpleNamespace(value=42)),
        "kwargs": {"scale": 3},
    }

    assert _resolve_path(ctx, "args[1]") == 20
    assert _resolve_path(ctx, "obj.inner.value") == 42
    assert _resolve_path(ctx, "kwargs.scale") == 3
    assert _resolve_path(ctx, "args[9]") is None


def test_eval_when_handles_composed_boolean_expressions():
    ctx = {"x": 10, "tags": {"alpha", "beta"}, "probe": "alpha", "name": "player_1"}
    cond = When.and_(
        When("x", OP.GT, 3),
        When("probe", OP.IN, ctx["tags"]),
        When.not_(When("name", OP.MATCH, r"npc")),
    )

    assert _eval_when(cond, ctx)


def test_merge_kwargs_raises_on_duplicate_keys():
    with pytest.raises(TypeError, match="multiple values for keyword argument 'scale'"):
        merge_kwargs({"scale": 2}, {"scale": 3})


def test_dispatch_injectors_sets_context_and_stops_after_cancel():
    calls = []

    def first(self_obj, ci, value, **kwargs):
        calls.append((self_obj, value, kwargs.get("scale"), ci.get_context()["target"]))
        ci.cancel(result=999)

    def second(self_obj, ci, value, **kwargs):
        calls.append(("second", value, kwargs))

    ci = CallbackInfo(type=TYPE.HEAD, target="pkg.mod.Player", method="update", at_name="HEAD", trace_id="t1")
    result = dispatch_injectors([first, second], ci, {"locals": {"x": 1}}, object(), 5, scale=7)

    assert result == 999
    assert len(calls) == 1
    assert calls[0][1:] == (5, 7, "pkg.mod.Player")


def test_callbackinfo_call_original_raises_when_missing():
    ci = CallbackInfo(type=TYPE.INVOKE, target="t", method="m", at_name="x", trace_id="1")
    with pytest.raises(RuntimeError, match="call_original is not available"):
        ci.call_original()
