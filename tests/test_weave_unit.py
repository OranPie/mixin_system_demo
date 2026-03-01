from mixin_system.model import At, Loc, OP, TYPE, When
from mixin_system.registry import InjectorSpec
from mixin_system.runtime import CallbackInfo
from mixin_system.weave import build_injector_map


def _fake_registry(injectors_dict):
    class FakeRegistry:
        def __init__(self, d):
            self._injectors = d
        def iter_injectors(self):
            yield from self._injectors.items()
    return FakeRegistry(injectors_dict)


def test_build_injector_map_filters_to_requested_module(monkeypatch):
    def cb(self_obj, ci):
        return None

    at = At(type=TYPE.HEAD, name=None)
    spec = InjectorSpec(mixin_cls=object, callback=cb, method="tick", at=at)
    at_param = At(type=TYPE.PARAMETER, name="x")
    spec_mod = InjectorSpec(mixin_cls=object, callback=cb, method="compute", at=at_param)
    fake_registry = _fake_registry({
        ("demo_game.player.Player", "tick"): [spec],
        ("other_game.player.Player", "tick"): [spec],
        ("demo_game.utils", "compute"): [spec_mod],  # module-level function target
    })

    monkeypatch.setattr("mixin_system.weave.REGISTRY", fake_registry)

    inj_map = build_injector_map("demo_game")

    assert ("demo_game.player.Player", "tick", "HEAD", "HEAD") in inj_map
    assert ("other_game.player.Player", "tick", "HEAD", "HEAD") not in inj_map
    # module-level target (target == module_name) must be included
    assert ("demo_game.utils", "compute", "PARAMETER", "x") in inj_map


def test_build_injector_map_wraps_condition_and_preserves_callback_name(monkeypatch):
    calls = []

    def conditional_cb(self_obj, ci, value):
        calls.append(value)

    at = At(type=TYPE.PARAMETER, name="value", location=Loc(condition=When("value", OP.GT, 0)))
    spec = InjectorSpec(mixin_cls=object, callback=conditional_cb, method="set_value", at=at)
    fake_registry = _fake_registry({("demo_game.player.Player", "set_value"): [spec]})

    monkeypatch.setattr("mixin_system.weave.REGISTRY", fake_registry)

    inj_map = build_injector_map("demo_game")
    wrapped = inj_map[("demo_game.player.Player", "set_value", "PARAMETER", "value")][0]

    assert wrapped.__name__ == conditional_cb.__name__

    ci = CallbackInfo(type=TYPE.PARAMETER, target="demo_game.player.Player", method="set_value", at_name="value", trace_id="t")
    ci._ctx = {"value": 5}
    wrapped(None, ci, 5)
    ci._ctx = {"value": -1}
    wrapped(None, ci, -1)

    assert calls == [5]
