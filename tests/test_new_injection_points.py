"""Tests for new injection point TYPE values and their API helpers."""
from __future__ import annotations

import pytest

from mixpy.model import TYPE, At, Loc
from mixpy.api import (
    at_attr_read,
    at_await,
    at_loop,
    at_subscript,
    at_with,
    inject_attr_read,
    inject_await,
    inject_loop,
    inject_subscript,
    inject_with,
)


# ---------------------------------------------------------------------------
# TYPE enum membership
# ---------------------------------------------------------------------------

class TestTypeEnum:
    """Verify the five new TYPE values exist with correct string values."""

    def test_attr_read_exists(self):
        assert TYPE.ATTR_READ == "ATTR_READ"

    def test_loop_exists(self):
        assert TYPE.LOOP == "LOOP"

    def test_with_exists(self):
        assert TYPE.WITH == "WITH"

    def test_await_exists(self):
        assert TYPE.AWAIT == "AWAIT"

    def test_subscript_exists(self):
        assert TYPE.SUBSCRIPT == "SUBSCRIPT"

    def test_all_new_types_are_type_instances(self):
        for member in (TYPE.ATTR_READ, TYPE.LOOP, TYPE.WITH, TYPE.AWAIT, TYPE.SUBSCRIPT):
            assert isinstance(member, TYPE)


# ---------------------------------------------------------------------------
# at_* factory functions
# ---------------------------------------------------------------------------

class TestAtAttrRead:
    def test_returns_at_with_correct_type(self):
        at = at_attr_read("hp")
        assert isinstance(at, At)
        assert at.type is TYPE.ATTR_READ

    def test_name_stored(self):
        at = at_attr_read("hp")
        assert at.name == "hp"

    def test_location_default_none(self):
        at = at_attr_read("hp")
        assert at.location is None

    def test_location_passed_through(self):
        loc = Loc(ordinal=0)
        at = at_attr_read("mana", location=loc)
        assert at.location is loc


class TestAtLoop:
    def test_returns_at_with_correct_type(self):
        at = at_loop("item")
        assert isinstance(at, At)
        assert at.type is TYPE.LOOP

    def test_name_stored(self):
        at = at_loop("item")
        assert at.name == "item"

    def test_no_name_defaults_none(self):
        at = at_loop()
        assert at.name is None

    def test_location_default_none(self):
        at = at_loop()
        assert at.location is None

    def test_location_passed_through(self):
        loc = Loc(ordinal=1)
        at = at_loop("x", location=loc)
        assert at.location is loc


class TestAtWith:
    def test_returns_at_with_correct_type(self):
        at = at_with("open")
        assert isinstance(at, At)
        assert at.type is TYPE.WITH

    def test_name_stored(self):
        at = at_with("open")
        assert at.name == "open"

    def test_location_default_none(self):
        at = at_with("open")
        assert at.location is None

    def test_location_passed_through(self):
        loc = Loc(ordinal=2)
        at = at_with("lock", location=loc)
        assert at.location is loc


class TestAtAwait:
    def test_returns_at_with_correct_type(self):
        at = at_await("fetch")
        assert isinstance(at, At)
        assert at.type is TYPE.AWAIT

    def test_name_stored(self):
        at = at_await("fetch")
        assert at.name == "fetch"

    def test_location_default_none(self):
        at = at_await("fetch")
        assert at.location is None

    def test_location_passed_through(self):
        loc = Loc(ordinal=0)
        at = at_await("send", location=loc)
        assert at.location is loc


class TestAtSubscript:
    def test_returns_at_with_correct_type(self):
        at = at_subscript("data")
        assert isinstance(at, At)
        assert at.type is TYPE.SUBSCRIPT

    def test_name_stored(self):
        at = at_subscript("data")
        assert at.name == "data"

    def test_location_default_none(self):
        at = at_subscript("data")
        assert at.location is None

    def test_location_passed_through(self):
        loc = Loc(ordinal=3)
        at = at_subscript("cache", location=loc)
        assert at.location is loc


# ---------------------------------------------------------------------------
# inject_* shorthand decorators (return decorator callables)
# ---------------------------------------------------------------------------

class TestInjectHelpers:
    """Each inject_* helper should return a decorator (callable)."""

    def test_inject_attr_read_returns_decorator(self):
        dec = inject_attr_read("some_method", "hp")
        assert callable(dec)

    def test_inject_subscript_returns_decorator(self):
        dec = inject_subscript("some_method", "data")
        assert callable(dec)

    def test_inject_loop_returns_decorator(self):
        dec = inject_loop("some_method", "item")
        assert callable(dec)

    def test_inject_loop_no_name(self):
        dec = inject_loop("some_method")
        assert callable(dec)

    def test_inject_with_returns_decorator(self):
        dec = inject_with("some_method", "open")
        assert callable(dec)

    def test_inject_await_returns_decorator(self):
        dec = inject_await("some_method", "fetch")
        assert callable(dec)


# ---------------------------------------------------------------------------
# __init__.py exports — importability from top-level `mixpy` package
# ---------------------------------------------------------------------------

class TestMixpyExports:
    """Verify all new symbols are importable from ``mixpy``."""

    def test_at_attr_read_importable(self):
        from mixpy import at_attr_read as fn
        assert callable(fn)

    def test_at_loop_importable(self):
        from mixpy import at_loop as fn
        assert callable(fn)

    def test_at_with_importable(self):
        from mixpy import at_with as fn
        assert callable(fn)

    def test_at_await_importable(self):
        from mixpy import at_await as fn
        assert callable(fn)

    def test_at_subscript_importable(self):
        from mixpy import at_subscript as fn
        assert callable(fn)

    def test_inject_attr_read_importable(self):
        from mixpy import inject_attr_read as fn
        assert callable(fn)

    def test_inject_subscript_importable(self):
        from mixpy import inject_subscript as fn
        assert callable(fn)

    def test_inject_loop_importable(self):
        from mixpy import inject_loop as fn
        assert callable(fn)

    def test_inject_with_importable(self):
        from mixpy import inject_with as fn
        assert callable(fn)

    def test_inject_await_importable(self):
        from mixpy import inject_await as fn
        assert callable(fn)

    def test_monkey_patch_hook_importable(self):
        from mixpy import MonkeyPatchHook
        assert MonkeyPatchHook is not None

    def test_settrace_hook_importable(self):
        from mixpy import SettraceHook
        assert SettraceHook is not None

    def test_hook_strategy_importable(self):
        from mixpy import HookStrategy
        assert HookStrategy is not None

    def test_hook_registry_importable(self):
        from mixpy import HookRegistry
        assert HookRegistry is not None

    def test_type_has_new_members(self):
        from mixpy import TYPE
        new_names = {"ATTR_READ", "LOOP", "WITH", "AWAIT", "SUBSCRIPT"}
        actual = {m.name for m in TYPE}
        assert new_names.issubset(actual)
