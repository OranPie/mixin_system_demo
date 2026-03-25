"""Tests for MonkeyPatchHook, SettraceHook, and HookRegistry."""
from __future__ import annotations

import sys
import types
import pytest

from mixpy.monkey_patch import MonkeyPatchHook
from mixpy.settrace_hook import SettraceHook
from mixpy.hook_strategy import HookStrategy, HookRegistry
from mixpy.model import TYPE
from mixpy.runtime import CallbackInfo


# ---------------------------------------------------------------------------
# Helper targets for MonkeyPatchHook tests
# ---------------------------------------------------------------------------

# MonkeyPatchHook._resolve_class does importlib.import_module(module_part)
# then getattr(mod, class_name).  We create a synthetic importable module
# so the resolution works without needing `tests` on sys.path as a package.

class _DummyClass:
    """Simple class whose methods we monkey-patch in tests."""

    def greet(self, name: str) -> str:
        return f"hello {name}"

    def add(self, a: int, b: int) -> int:
        return a + b


def _standalone_func(x: int) -> int:
    """Module-level function used by patch_function tests."""
    return x * 2


# Expose helpers via a synthetic module importable by MonkeyPatchHook.
_HELPER_MOD_NAME = "_hook_test_helpers"
_helper_mod = types.ModuleType(_HELPER_MOD_NAME)
_helper_mod._DummyClass = _DummyClass  # type: ignore[attr-defined]
_helper_mod._standalone_func = _standalone_func  # type: ignore[attr-defined]
sys.modules[_HELPER_MOD_NAME] = _helper_mod

_CLASS_FQN = f"{_HELPER_MOD_NAME}._DummyClass"


# ---------------------------------------------------------------------------
# MonkeyPatchHook tests
# ---------------------------------------------------------------------------

class TestMonkeyPatchHookProtocol:
    """HookStrategy protocol compliance."""

    def test_name_attribute(self):
        hook = MonkeyPatchHook()
        assert hook.name == "monkey_patch"

    def test_activate_deactivate_lifecycle(self):
        hook = MonkeyPatchHook()
        assert not hook.is_active
        hook.activate()
        assert hook.is_active
        hook.deactivate()
        assert not hook.is_active

    def test_is_hookstrategy(self):
        hook = MonkeyPatchHook()
        assert isinstance(hook, HookStrategy)


class TestMonkeyPatchMethod:
    """patch_method / unpatch_method for class methods."""

    def setup_method(self):
        self.hook = MonkeyPatchHook()

    def teardown_method(self):
        self.hook.unpatch_all()

    def test_head_callback_runs(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("head")

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, head_cb)
        result = _DummyClass().greet("world")
        assert "head" in calls
        assert result == "hello world"

    def test_tail_callback_runs(self):
        captured: list[dict] = []

        def tail_cb(self_obj, ci: CallbackInfo, *args, **kwargs):
            captured.append(ci.get_context())

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.TAIL, tail_cb)
        result = _DummyClass().greet("world")
        assert result == "hello world"
        assert len(captured) == 1
        assert captured[0]["return_value"] == "hello world"

    def test_head_cancel_replaces_result(self):
        def head_cb(self_obj, ci: CallbackInfo, *args, **kwargs):
            ci.cancel(result="intercepted")

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, head_cb)
        result = _DummyClass().greet("world")
        assert result == "intercepted"

    def test_unpatch_restores_original(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("head")

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, head_cb)
        assert _DummyClass().greet("a") == "hello a"
        assert len(calls) == 1

        self.hook.unpatch_method(fqn, "greet")
        calls.clear()
        assert _DummyClass().greet("b") == "hello b"
        assert len(calls) == 0  # callback no longer fires

    def test_unpatch_all(self):
        def noop(self_obj, ci, *args, **kwargs):
            pass

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, noop)
        self.hook.patch_method(fqn, "add", TYPE.HEAD, noop)
        count = self.hook.unpatch_all()
        assert count == 2

        # Methods should be originals again
        assert _DummyClass().greet("x") == "hello x"
        assert _DummyClass().add(1, 2) == 3

    def test_multiple_callbacks_priority_ordering(self):
        order: list[int] = []

        def cb_low(self_obj, ci, *args, **kwargs):
            order.append(10)

        def cb_high(self_obj, ci, *args, **kwargs):
            order.append(200)

        fqn = _CLASS_FQN
        # Register high-priority first, low second
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, cb_high, priority=200)
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, cb_low, priority=10)

        _DummyClass().greet("x")
        # Lower priority value should run first
        assert order == [10, 200]

    def test_unpatch_method_returns_false_for_unknown(self):
        fqn = _CLASS_FQN
        assert self.hook.unpatch_method(fqn, "nonexistent") is False

    def test_deactivate_unpatches_all(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("hit")

        fqn = _CLASS_FQN
        self.hook.patch_method(fqn, "greet", TYPE.HEAD, head_cb)
        self.hook.activate()
        assert self.hook.is_active

        self.hook.deactivate()
        assert not self.hook.is_active

        calls.clear()
        _DummyClass().greet("z")
        assert len(calls) == 0  # unpatched by deactivate


class TestMonkeyPatchFunction:
    """patch_function / unpatch_function for module-level functions."""

    def setup_method(self):
        self.hook = MonkeyPatchHook()

    def teardown_method(self):
        self.hook.unpatch_all()

    def test_head_callback_on_function(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("head")

        self.hook.patch_function(_HELPER_MOD_NAME, "_standalone_func", TYPE.HEAD, head_cb)
        # After patching, the module attribute is replaced — import it fresh.
        mod = sys.modules[_HELPER_MOD_NAME]
        result = mod._standalone_func(5)
        assert result == 10
        assert "head" in calls

    def test_tail_callback_on_function(self):
        returns: list = []

        def tail_cb(self_obj, ci: CallbackInfo, *args, **kwargs):
            returns.append(ci.get_context().get("return_value"))

        self.hook.patch_function(_HELPER_MOD_NAME, "_standalone_func", TYPE.TAIL, tail_cb)
        mod = sys.modules[_HELPER_MOD_NAME]
        result = mod._standalone_func(7)
        assert result == 14
        assert returns == [14]

    def test_unpatch_function_restores(self):
        def head_cb(self_obj, ci, *args, **kwargs):
            pass

        self.hook.patch_function(_HELPER_MOD_NAME, "_standalone_func", TYPE.HEAD, head_cb)
        self.hook.unpatch_function(_HELPER_MOD_NAME, "_standalone_func")

        # Original should be back — no wrapper
        mod = sys.modules[_HELPER_MOD_NAME]
        fn = mod._standalone_func
        assert not hasattr(fn, "__wrapped__")


# ---------------------------------------------------------------------------
# SettraceHook tests
# ---------------------------------------------------------------------------

def _traced_add(a: int, b: int) -> int:
    return a + b


def _traced_mul(a: int, b: int) -> int:
    return a * b


class TestSettraceHookProtocol:
    """HookStrategy protocol compliance."""

    def test_name_attribute(self):
        hook = SettraceHook()
        assert hook.name == "settrace"

    def test_activate_deactivate(self):
        hook = SettraceHook()
        assert not hook.is_active
        hook.activate()
        assert hook.is_active
        hook.deactivate()
        assert not hook.is_active

    def test_is_hookstrategy(self):
        hook = SettraceHook()
        assert isinstance(hook, HookStrategy)


class TestSettraceHookCallReturn:
    """on_call / on_return functionality."""

    def setup_method(self):
        self.hook = SettraceHook()

    def teardown_method(self):
        self.hook.disable()
        self.hook.clear()

    def test_on_call_fires_callback(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("call")

        self.hook.on_call("_traced_add", head_cb)
        self.hook.enable()
        result = _traced_add(3, 4)
        self.hook.disable()
        assert result == 7
        assert "call" in calls

    def test_on_return_fires_callback(self):
        returns: list = []

        def tail_cb(self_obj, ci: CallbackInfo, *args, **kwargs):
            ctx = ci.get_context()
            returns.append(ctx.get("return_value"))

        self.hook.on_return("_traced_mul", tail_cb)
        self.hook.enable()
        result = _traced_mul(3, 5)
        self.hook.disable()
        assert result == 15
        assert returns == [15]

    def test_remove_hook_stops_callbacks(self):
        calls: list[str] = []

        def head_cb(self_obj, ci, *args, **kwargs):
            calls.append("hit")

        self.hook.on_call("_traced_add", head_cb)
        self.hook.enable()
        _traced_add(1, 1)
        assert len(calls) == 1

        self.hook.remove_hook("_traced_add", TYPE.HEAD, head_cb)
        calls.clear()
        _traced_add(2, 2)
        self.hook.disable()
        assert len(calls) == 0

    def test_remove_hook_all_types(self):
        """remove_hook with no type removes from both call and return."""
        def cb1(self_obj, ci, *args, **kwargs):
            pass

        def cb2(self_obj, ci, *args, **kwargs):
            pass

        self.hook.on_call("_traced_add", cb1)
        self.hook.on_return("_traced_add", cb2)
        removed = self.hook.remove_hook("_traced_add")
        assert removed is True
        assert "_traced_add" not in self.hook._call_hooks
        assert "_traced_add" not in self.hook._return_hooks

    def test_enable_disable_lifecycle(self):
        hook = SettraceHook()
        assert not hook.is_enabled
        hook.enable()
        assert hook.is_enabled
        # Double enable is idempotent
        hook.enable()
        assert hook.is_enabled
        hook.disable()
        assert not hook.is_enabled
        # Double disable is idempotent
        hook.disable()
        assert not hook.is_enabled

    def test_disable_restores_previous_trace(self):
        sentinel_trace = lambda frame, event, arg: None
        sys.settrace(sentinel_trace)
        try:
            hook = SettraceHook()
            hook.enable()
            # While enabled, sys.gettrace() should be our dispatch
            assert sys.gettrace() is not sentinel_trace
            hook.disable()
            # After disable, the sentinel should be restored
            assert sys.gettrace() is sentinel_trace
        finally:
            sys.settrace(None)

    def test_remove_hook_returns_false_for_unknown(self):
        assert self.hook.remove_hook("nonexistent", TYPE.HEAD) is False


# ---------------------------------------------------------------------------
# HookRegistry tests
# ---------------------------------------------------------------------------

class _FakeStrategy:
    """Minimal HookStrategy implementation for registry tests."""
    name: str

    def __init__(self, name: str):
        self.name = name
        self._active = False

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


class TestHookRegistry:
    def setup_method(self):
        self.reg = HookRegistry()

    def test_register_and_contains(self):
        s = _FakeStrategy("alpha")
        self.reg.register(s)
        assert "alpha" in self.reg

    def test_unregister(self):
        s = _FakeStrategy("alpha")
        self.reg.register(s)
        self.reg.unregister("alpha")
        assert "alpha" not in self.reg

    def test_unregister_deactivates_first(self):
        s = _FakeStrategy("alpha")
        self.reg.register(s)
        self.reg.activate("alpha")
        assert s.is_active
        self.reg.unregister("alpha")
        assert not s.is_active

    def test_unregister_unknown_is_noop(self):
        # Should not raise
        self.reg.unregister("nonexistent")

    def test_activate_deactivate(self):
        s = _FakeStrategy("beta")
        self.reg.register(s)
        self.reg.activate("beta")
        assert s.is_active
        self.reg.deactivate("beta")
        assert not s.is_active

    def test_activate_all_deactivate_all(self):
        s1 = _FakeStrategy("s1")
        s2 = _FakeStrategy("s2")
        self.reg.register(s1)
        self.reg.register(s2)

        self.reg.activate_all()
        assert s1.is_active
        assert s2.is_active
        assert set(self.reg.active_strategies) == {"s1", "s2"}

        self.reg.deactivate_all()
        assert not s1.is_active
        assert not s2.is_active
        assert self.reg.active_strategies == []

    def test_active_strategies_property(self):
        s1 = _FakeStrategy("a")
        s2 = _FakeStrategy("b")
        self.reg.register(s1)
        self.reg.register(s2)
        self.reg.activate("a")
        assert self.reg.active_strategies == ["a"]

    def test_registered_strategies_property(self):
        s1 = _FakeStrategy("x")
        s2 = _FakeStrategy("y")
        self.reg.register(s1)
        self.reg.register(s2)
        assert set(self.reg.registered_strategies) == {"x", "y"}

    def test_len(self):
        assert len(self.reg) == 0
        self.reg.register(_FakeStrategy("a"))
        assert len(self.reg) == 1
        self.reg.register(_FakeStrategy("b"))
        assert len(self.reg) == 2

    def test_get_existing(self):
        s = _FakeStrategy("g")
        self.reg.register(s)
        assert self.reg.get("g") is s

    def test_get_missing_raises(self):
        with pytest.raises(KeyError):
            self.reg.get("missing")

    def test_register_rejects_non_strategy(self):
        with pytest.raises(TypeError, match="Expected HookStrategy"):
            self.reg.register("not a strategy")  # type: ignore[arg-type]

    def test_real_hooks_integrate(self):
        """Register real MonkeyPatchHook + SettraceHook."""
        mp = MonkeyPatchHook()
        st = SettraceHook()
        self.reg.register(mp)
        self.reg.register(st)
        assert "monkey_patch" in self.reg
        assert "settrace" in self.reg
        assert len(self.reg) == 2

        self.reg.activate_all()
        assert mp.is_active
        assert st.is_active

        self.reg.deactivate_all()
        assert not mp.is_active
        assert not st.is_active
