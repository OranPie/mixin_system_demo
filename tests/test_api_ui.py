import os

import pytest

from mixpy import api
from mixpy.model import OCCURRENCE, POLICY, TYPE, Loc


class _FakeRegistry:
    def __init__(self):
        self.mixins = []
        self.injectors = []
        self.freeze_calls = 0

    def register_mixin(self, target, cls, priority=100):
        self.mixins.append((target, cls, priority))

    def register_injector(self, target, spec):
        self.injectors.append((target, spec))

    def freeze(self):
        self.freeze_calls += 1


def test_target_path_accepts_string_and_type():
    class Target:
        pass

    assert api.target_path("pkg.mod.Player") == "pkg.mod.Player"
    assert api.target_path(Target) == f"{Target.__module__}.{Target.__qualname__}"


def test_target_path_rejects_invalid_values():
    with pytest.raises(ValueError, match="non-empty"):
        api.target_path("   ")
    with pytest.raises(TypeError, match="string or a class"):
        api.target_path(123)


def test_inject_validates_method_and_at():
    with pytest.raises(ValueError, match="non-empty"):
        api.inject(method="", at=api.at_head())
    with pytest.raises(TypeError, match=r"At\(\.\.\.\)"):
        api.inject(method="run", at="HEAD")
    with pytest.raises(TypeError, match="POLICY enum"):
        api.inject(method="run", at=api.at_head(), policy="ERROR")

    @api.inject_head(method="tick", policy=POLICY.WARN)
    def _ok(self, ci):
        return None

    assert _ok.__inject_spec__.policy == POLICY.WARN


def test_at_helpers_build_expected_types():
    assert api.at_head().type == TYPE.HEAD
    assert api.at_tail().type == TYPE.TAIL
    assert api.at_parameter("value").type == TYPE.PARAMETER
    assert api.at_const(1.0).type == TYPE.CONST
    assert api.at_invoke("self.fn").type == TYPE.INVOKE
    assert api.at_attribute("self.health").type == TYPE.ATTRIBUTE

    with pytest.raises(TypeError, match="OCCURRENCE enum"):
        Loc(occurrence="FIRST")
    assert Loc(occurrence=OCCURRENCE.FIRST).occurrence == OCCURRENCE.FIRST


def test_inject_shortcut_builders_attach_specs():
    @api.inject_head(method="tick")
    def head(self, ci):
        return None

    @api.inject_parameter(method="set_health", name="value")
    def param(self, ci, value):
        return None

    assert head.__inject_spec__.at.type == TYPE.HEAD
    assert param.__inject_spec__.at.type == TYPE.PARAMETER
    assert param.__inject_spec__.at.name == "value"


def test_mixin_accepts_type_target_and_registers(monkeypatch):
    fake = _FakeRegistry()
    monkeypatch.setattr(api, "REGISTRY", fake)

    class Target:
        pass

    @api.mixin(Target)
    class Patch:
        @api.inject_const(method="calculate_speed", value=1.0)
        def inject_const(self, ci):
            ci.set_value(2.0)

    expected_target = f"{Target.__module__}.{Target.__qualname__}"
    assert Patch.__mixin_target__ == expected_target
    assert fake.mixins[0][0] == expected_target
    assert fake.injectors[0][0] == expected_target
    assert fake.injectors[0][1].at.type == TYPE.CONST
    assert fake.injectors[0][1].mixin_priority == 100


def test_mixin_priority_is_forwarded_to_registry_and_injectors(monkeypatch):
    fake = _FakeRegistry()
    monkeypatch.setattr(api, "REGISTRY", fake)

    @api.mixin("pkg.mod.Target", priority=5)
    class Patch:
        @api.inject_head(method="tick")
        def on_tick(self, ci):
            return None

    assert fake.mixins[0] == ("pkg.mod.Target", Patch, 5)
    assert fake.injectors[0][1].mixin_priority == 5


def test_mixin_frozen_error_message_is_actionable(monkeypatch):
    class _FrozenRegistry(_FakeRegistry):
        def register_mixin(self, target, cls, priority=100):
            raise RuntimeError("Registry is frozen; register mixins before init() completes.")

    monkeypatch.setattr(api, "REGISTRY", _FrozenRegistry())

    with pytest.raises(RuntimeError, match=r"before calling mixpy.init\(\)"):
        @api.mixin("pkg.mod.Target")
        class Patch:
            pass


def test_configure_and_init_debug_path(monkeypatch):
    fake = _FakeRegistry()
    calls = {"handlers": 0, "hook": 0}

    monkeypatch.setattr(api, "REGISTRY", fake)
    monkeypatch.setattr(api, "install_builtin_handlers", lambda: calls.__setitem__("handlers", calls["handlers"] + 1))
    monkeypatch.setattr(api, "install_import_hook", lambda: calls.__setitem__("hook", calls["hook"] + 1))

    api.configure(debug=False)
    assert os.environ["MIXIN_DEBUG"] == "False"

    api.init(debug=True)
    assert os.environ["MIXIN_DEBUG"] == "True"
    assert calls == {"handlers": 1, "hook": 1}
    assert fake.freeze_calls == 1
