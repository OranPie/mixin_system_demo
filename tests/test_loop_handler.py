"""Tests for the LOOP injection handler."""

import ast
import textwrap
import types
import time

from mixpy.model import At, TYPE
from mixpy.handlers import Match
from mixpy.registry import InjectorSpec
from mixpy.builtin_handlers import LoopHandler
from mixpy.ast_index import ASTIndex
from mixpy.runtime import CallbackInfo, dispatch_injectors
import mixpy.runtime as mixpy_runtime
import mixpy.model as mixpy_model


def _parse_fn(src: str) -> ast.FunctionDef:
    mod = ast.parse(textwrap.dedent(src))
    return mod.body[0]


def _compile_and_run(fn_node: ast.FunctionDef, injectors_map: dict, **extra_globals):
    """Compile a modified FunctionDef, inject runtime globals, execute and return the namespace."""
    mod = ast.Module(body=[fn_node], type_ignores=[])
    ast.fix_missing_locations(mod)
    code = compile(mod, "<test>", "exec")
    ns = {
        "__mixin_injectors__": injectors_map,
        "mixpy_runtime": mixpy_runtime,
        "mixpy_model": mixpy_model,
    }
    ns.update(extra_globals)
    exec(code, ns)
    return ns


# ---- find() tests ----

def test_find_for_loop():
    fn = _parse_fn("""
    def f():
        for item in items:
            pass
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP))
    assert len(matches) == 1


def test_find_while_loop():
    fn = _parse_fn("""
    def f():
        while True:
            pass
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP))
    assert len(matches) == 1


def test_find_multiple_loops():
    fn = _parse_fn("""
    def f():
        for x in xs:
            pass
        while True:
            break
        for y in ys:
            pass
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP))
    assert len(matches) == 3


def test_find_by_name_for():
    fn = _parse_fn("""
    def f():
        for item in items:
            pass
        for other in others:
            pass
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP, name="item"))
    assert len(matches) == 1


def test_find_by_name_while():
    fn = _parse_fn("""
    def f():
        for item in items:
            pass
        while True:
            break
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP, name="while"))
    assert len(matches) == 1


def test_find_with_index():
    fn = _parse_fn("""
    def f():
        for item in items:
            pass
        while True:
            break
    """)
    handler = LoopHandler()
    idx = ASTIndex(fn)
    matches = handler.find(fn, At(type=TYPE.LOOP), index=idx)
    assert len(matches) == 2


def test_find_nested_loops():
    fn = _parse_fn("""
    def f():
        for i in range(10):
            for j in range(10):
                pass
    """)
    handler = LoopHandler()
    matches = handler.find(fn, At(type=TYPE.LOOP))
    assert len(matches) == 2


# ---- instrument() + execution tests ----

def test_loop_entry_exit_called():
    fn = _parse_fn("""
    def f(self):
        result = []
        for item in [1, 2, 3]:
            result.append(item)
        return result
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)
    assert len(matches) == 1

    events = []

    def cb(self_obj, ci):
        events.append(ci.get_context()["event"])

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "LOOP")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    result = ns["f"](None)

    assert result == [1, 2, 3]
    assert events == ["entry", "exit"]


def test_loop_cancel_skips_loop():
    fn = _parse_fn("""
    def f(self):
        result = []
        for item in [1, 2, 3]:
            result.append(item)
        return result
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)

    events = []

    def cb(self_obj, ci):
        ev = ci.get_context()["event"]
        events.append(ev)
        if ev == "entry":
            ci.cancel()

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "LOOP")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    result = ns["f"](None)

    assert result == []
    # Only entry is called; exit is not called because loop was skipped
    assert events == ["entry"]


def test_loop_context_has_loop_type():
    fn = _parse_fn("""
    def f(self):
        for x in [1]:
            pass
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)

    contexts = []

    def cb(self_obj, ci):
        ctx = ci.get_context()
        contexts.append({"event": ctx["event"], "loop_type": ctx["loop_type"], "loop_var": ctx["loop_var"]})

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "LOOP")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    ns["f"](None)

    assert contexts[0] == {"event": "entry", "loop_type": "for", "loop_var": "x"}
    assert contexts[1] == {"event": "exit", "loop_type": "for", "loop_var": "x"}


def test_while_loop_entry_exit():
    fn = _parse_fn("""
    def f(self):
        count = 0
        while count < 3:
            count += 1
        return count
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP, name="while")
    matches = handler.find(fn, at)
    assert len(matches) == 1

    events = []

    def cb(self_obj, ci):
        ctx = ci.get_context()
        events.append(ctx["event"])

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "while")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    result = ns["f"](None)

    assert result == 3
    assert events == ["entry", "exit"]


def test_exit_called_on_break():
    """Exit callback should fire even when the loop ends via break (try/finally)."""
    fn = _parse_fn("""
    def f(self):
        for item in [1, 2, 3]:
            if item == 2:
                break
        return item
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)

    events = []

    def cb(self_obj, ci):
        events.append(ci.get_context()["event"])

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "LOOP")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    result = ns["f"](None)

    assert result == 2
    assert events == ["entry", "exit"]


def test_nested_loops_unique_vars():
    """Nested loops should get unique variable names and both fire callbacks."""
    fn = _parse_fn("""
    def f(self):
        result = []
        for i in [1, 2]:
            for j in [10, 20]:
                result.append(i + j)
        return result
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)
    assert len(matches) == 2

    events = []

    def cb(self_obj, ci):
        ctx = ci.get_context()
        events.append((ctx["event"], ctx["loop_var"]))

    spec = InjectorSpec(mixin_cls=object, callback=cb, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    key = ("test_mod.TestCls", "f", "LOOP", "LOOP")
    inj_map = {key: [cb]}
    ns = _compile_and_run(fn, inj_map)
    result = ns["f"](None)

    assert result == [11, 21, 12, 22]
    # Outer loop: entry, inner loop: entry+exit (per outer iteration × 2), outer loop: exit
    assert ("entry", "i") in events
    assert ("exit", "i") in events
    assert ("entry", "j") in events
    assert ("exit", "j") in events


def test_no_injectors_noop():
    """When injector map has no entries for the key, loop executes normally."""
    fn = _parse_fn("""
    def f(self):
        result = []
        for item in [1, 2, 3]:
            result.append(item)
        return result
    """)
    handler = LoopHandler()
    at = At(type=TYPE.LOOP)
    matches = handler.find(fn, at)
    spec = InjectorSpec(mixin_cls=object, callback=lambda s, ci: None, method="f", at=at)
    handler.instrument(fn, matches, [spec], "test_mod.TestCls")

    ns = _compile_and_run(fn, {})  # empty injector map
    result = ns["f"](None)
    assert result == [1, 2, 3]


def test_loop_name_property():
    handler = LoopHandler()

    for_node = ast.parse("for item in items: pass").body[0]
    assert handler._loop_name(for_node) == "item"

    while_node = ast.parse("while True: pass").body[0]
    assert handler._loop_name(while_node) == "while"

    tuple_for = ast.parse("for a, b in items: pass").body[0]
    assert handler._loop_name(tuple_for) == "for"
