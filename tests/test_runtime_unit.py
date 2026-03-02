from types import SimpleNamespace

import pytest

from mixpy.model import OP, TYPE, When
from mixpy.runtime import (
    CallbackInfo,
    _eval_when,
    _resolve_path,
    dispatch_injectors,
    eval_invoke,
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


def test_eval_when_len_operators():
    ctx = {"args": [1, 2, 3], "tags": ["a"]}
    assert _eval_when(When("args", OP.LEN_EQ, 3), ctx)
    assert _eval_when(When("args", OP.LEN_GT, 2), ctx)
    assert _eval_when(When("args", OP.LEN_LT, 5), ctx)
    assert not _eval_when(When("args", OP.LEN_EQ, 2), ctx)
    assert not _eval_when(When("tags", OP.LEN_GT, 2), ctx)


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


def test_callbackinfo_parameter_helpers_map_to_value_mutation():
    ci = CallbackInfo(type=TYPE.PARAMETER, target="t", method="set_health", at_name="value", trace_id="p1")
    ci._ctx = {"param": "value", "value": -5}

    assert ci.parameter_name == "value"
    assert ci.get_parameter() == -5
    ci.set_parameter(0)
    assert ci.value_set
    assert ci.new_value == 0


def test_eval_invoke_supports_overriding_call_args():
    seen = []

    def original(*args, **kwargs):
        seen.append((args, kwargs))
        return int(args[0]) * int(kwargs["scale"])

    def rewrite_call(self_obj, ci, x, **kwargs):
        ci.set_call_args(x + 1, scale=kwargs["scale"] + 2)

    inj_map = {("pkg.Player", "update", "INVOKE", "self.physics2"): [rewrite_call]}
    result = eval_invoke(
        inj_map,
        "pkg.Player",
        "update",
        "self.physics2",
        object(),
        original,
        [2],
        {"scale": 3},
    )

    assert result == 15
    assert seen == [((3,), {"scale": 5})]


def test_eval_invoke_reuses_result_if_injector_calls_original():
    call_count = {"n": 0}

    def original(*args, **kwargs):
        call_count["n"] += 1
        return int(args[0]) * int(kwargs["scale"])

    def call_now(self_obj, ci, x, **kwargs):
        assert ci.call_original(x + 5, scale=kwargs["scale"] + 1) == 28

    inj_map = {("pkg.Player", "update", "INVOKE", "self.physics2"): [call_now]}
    result = eval_invoke(
        inj_map,
        "pkg.Player",
        "update",
        "self.physics2",
        object(),
        original,
        [2],
        {"scale": 3},
    )

    assert result == 28
    assert call_count["n"] == 1


def test_eval_invoke_updated_args_flow_to_later_injectors():
    seen_second = []

    def original(*args, **kwargs):
        return int(args[0]) + int(kwargs["scale"])

    def first(self_obj, ci, x, **kwargs):
        ci.set_call_args(10, scale=20)

    def second(self_obj, ci, x, **kwargs):
        seen_second.append((x, kwargs["scale"]))

    inj_map = {("pkg.Player", "update", "INVOKE", "self.physics2"): [first, second]}
    result = eval_invoke(
        inj_map,
        "pkg.Player",
        "update",
        "self.physics2",
        object(),
        original,
        [2],
        {"scale": 3},
    )

    assert result == 30
    assert seen_second == [(10, 20)]

def test_dispatch_injectors_trace_mode_logs_to_stderr(capsys, monkeypatch):
    monkeypatch.setenv("MIXIN_TRACE", "True")
    monkeypatch.setenv("MIXPY_LOG_LEVEL", "DEBUG")

    def cb(self_obj, ci, value):
        ci.cancel(result=42)

    ci = CallbackInfo(type=TYPE.HEAD, target="pkg.Player", method="update", at_name="HEAD", trace_id="t99")
    dispatch_injectors([cb], ci, {}, object(), 5)

    captured = capsys.readouterr()
    assert "[mixpy:DEBUG]" in captured.err
    assert "pkg.Player" in captured.err
    assert "cancelled" in captured.err
