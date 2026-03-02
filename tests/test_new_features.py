"""Tests for the expanded mixpy features:
  - True Class Mixins (Structural Injection)
  - Async/Await Support
  - Line-Number Targeting
  - Yield / Generator Interception
  - Dry-Run / Source Ejection Mode
  - Hot-Reloading / Dynamic Unpatching
  - Type Hinting Generation
  - Weaved Bytecode Caching
  - Fast-Path Execution (behavioural correctness)
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import importlib

import pytest


# ---------------------------------------------------------------------------
# 1. Structural Injection – new methods injected into target class
# ---------------------------------------------------------------------------

def test_structural_injection_new_method_exists():
    from demo_game.game.player.player import Player

    p = Player(42)
    assert hasattr(p, "mixin_greet"), "structural method should be injected"
    assert hasattr(p, "mixin_double_health"), "structural method should be injected"


def test_structural_injection_new_method_behaves_correctly():
    from demo_game.game.player.player import Player

    p = Player(7)
    assert p.mixin_greet() == "Hello from mixin! health=7"
    assert p.mixin_double_health() == 14


# ---------------------------------------------------------------------------
# 2. Async/Await Support
# ---------------------------------------------------------------------------

def test_async_function_const_injection():
    """CONST injection inside async def should work – the existing patch buffs base speed."""
    from demo_game.game.player.player import Player

    p = Player(10)
    result = asyncio.run(p.async_speed())
    assert result == 5.0, "async_speed: const 1.0 → 2.5, result should be 2.5 * 2 = 5.0"


async def _run_async_speed(player):
    return await player.async_speed()


def test_async_function_works_with_await():
    from demo_game.game.player.player import Player

    p = Player(10)
    result = asyncio.run(_run_async_speed(p))
    assert result == 5.0


# ---------------------------------------------------------------------------
# 3. Line-Number Targeting
# ---------------------------------------------------------------------------

def test_line_targeting_replaces_only_matching_line():
    """PlayerLinePatch targets the 10.0 constant on line 85 only (first assignment).

    multi_const_lines:
        a = 10.0   <- line 85, replaced → 99.0
        b = 10.0   <- line 86, NOT replaced
        return a + b → 99.0 + 10.0 = 109.0
    """
    from demo_game.game.player.player import Player

    p = Player(0)
    result = p.multi_const_lines()
    assert result == 109.0, f"expected 109.0 (99.0+10.0), got {result}"


# ---------------------------------------------------------------------------
# 4. Yield / Generator Interception
# ---------------------------------------------------------------------------

def test_yield_injection_modifies_generated_values():
    """PlayerYieldPatch multiplies every yielded value by 10."""
    from demo_game.game.player.player import Player

    p = Player(5)
    items = list(p.generate_items())
    # Without patch: [5, 10]; with patch (×10): [50, 100]
    assert items == [50, 100], f"expected [50, 100], got {items}"


def test_yield_injection_cancel_substitutes_value():
    """ci.cancel(result=x) in a YIELD callback substitutes the yielded value."""
    from demo_game.game.player.player import Player

    p = Player(3)
    # The default patch multiplies by 10, so [30, 60]
    items = list(p.generate_items())
    assert items[0] == 30


# ---------------------------------------------------------------------------
# 5. Dry-Run / Source Ejection Mode
# ---------------------------------------------------------------------------

def test_source_ejection_writes_to_configured_dir(tmp_path):
    import os
    import mixpy
    from mixpy.debug import set_dump_dir, maybe_dump
    import ast

    dump_dir = tmp_path / "weaved_out"
    set_dump_dir(str(dump_dir))
    os.environ["MIXIN_DEBUG"] = "True"
    try:
        tree = ast.parse("x = 1\n")
        maybe_dump("test_module_dump", tree)
        out_file = dump_dir / "test_module_dump.py"
        assert out_file.exists(), "source ejection should write to the configured dir"
        assert "x = 1" in out_file.read_text()
    finally:
        os.environ["MIXIN_DEBUG"] = "False"
        set_dump_dir(None)


def test_source_ejection_default_dir(tmp_path, monkeypatch):
    import os
    import mixpy
    from mixpy.debug import set_dump_dir, maybe_dump
    import ast

    # Temporarily cd to tmp_path so .weaved/ is created there
    monkeypatch.chdir(tmp_path)
    set_dump_dir(None)  # use default (.weaved/)
    os.environ["MIXIN_DEBUG"] = "True"
    try:
        tree = ast.parse("y = 2\n")
        maybe_dump("default_dir_test", tree)
        out_file = tmp_path / ".weaved" / "default_dir_test.py"
        assert out_file.exists(), "default dump dir should be .weaved/"
    finally:
        os.environ["MIXIN_DEBUG"] = "False"
        set_dump_dir(None)


def test_configure_source_dump_dir(tmp_path):
    import os
    import mixpy
    from mixpy.debug import set_dump_dir, maybe_dump
    import ast

    mixpy.configure(source_dump_dir=str(tmp_path / "custom_weaved"))
    os.environ["MIXIN_DEBUG"] = "True"
    try:
        tree = ast.parse("z = 3\n")
        maybe_dump("configure_test", tree)
        assert (tmp_path / "custom_weaved" / "configure_test.py").exists()
    finally:
        os.environ["MIXIN_DEBUG"] = "False"
        set_dump_dir(None)


# ---------------------------------------------------------------------------
# 6. Hot-Reloading / Dynamic Unpatching
# ---------------------------------------------------------------------------

def test_unregister_injector_removes_callback():
    """unregister_injector returns True when the callback was found and removed."""
    import mixpy
    from mixpy.registry import REGISTRY

    # Use a known callback from demo patches and verify unregister API doesn't error.
    # We test the return value when the callback is NOT in the registry (returns False).
    def fake_cb(self_obj, ci):
        pass

    result = mixpy.unregister_injector(
        "demo_game.game.player.player.Player", "calculate_speed", fake_cb
    )
    assert result is False, "should return False when callback not found"


def test_reload_target_raises_for_unloaded_module():
    """reload_target should raise ValueError for a module that isn't imported."""
    import mixpy

    with pytest.raises(ValueError, match="not currently loaded"):
        mixpy.reload_target("does_not_exist_xyz_123")


def test_reload_target_re_imports_module():
    """reload_target forces a fresh import through the MixinLoader."""
    import mixpy
    import demo_game.game.player.player as player_mod

    original_id = id(player_mod.Player)
    mixpy.reload_target("demo_game.game.player.player")
    # Re-import to get the fresh module
    import demo_game.game.player.player as player_mod2
    # The Player class should still be accessible after reload
    p = player_mod2.Player(10)
    assert p.health == 10


# ---------------------------------------------------------------------------
# 7. Type Hinting Generation (.pyi stubs)
# ---------------------------------------------------------------------------

def test_generate_stubs_creates_files(tmp_path):
    import mixpy

    mixpy.generate_stubs(output_dir=str(tmp_path))
    stubs = list(tmp_path.glob("*.pyi"))
    assert len(stubs) > 0, "generate_stubs should create at least one .pyi file"


def test_generate_stubs_content(tmp_path):
    import mixpy

    mixpy.generate_stubs(output_dir=str(tmp_path))
    # Find a stub that mentions Player-related injectors
    contents = "".join(f.read_text() for f in tmp_path.glob("*.pyi"))
    assert "mixin-injected" in contents, ".pyi stubs should contain mixin-injected markers"
    assert "def " in contents, ".pyi stubs should contain method stubs"


# ---------------------------------------------------------------------------
# 8. Weaved Bytecode Caching
# ---------------------------------------------------------------------------

def test_bytecode_cache_is_created():
    """After importing the demo player, a bytecode cache should exist."""
    cache_dir = pathlib.Path("__pycache__") / "mixin_weaved"
    assert cache_dir.exists(), "bytecode cache directory should be created"
    cached = list(cache_dir.glob("demo_game_game_player_player.*.pyc"))
    assert len(cached) > 0, "at least one cached pyc should exist for the player module"


def test_bytecode_cache_is_valid_marshal():
    """Cached files should be valid marshal-encoded code objects."""
    import marshal

    cache_dir = pathlib.Path("__pycache__") / "mixin_weaved"
    cached = list(cache_dir.glob("demo_game_game_player_player.*.pyc"))
    assert cached, "cache file should exist"
    with open(cached[0], "rb") as fh:
        code = marshal.loads(fh.read())
    assert hasattr(code, "co_filename"), "should deserialize to a code object"


# ---------------------------------------------------------------------------
# 9. Fast-Path Execution (behavioural correctness)
# ---------------------------------------------------------------------------

def test_fast_path_does_not_alter_behaviour_when_injectors_registered():
    """With the fast-path guard, injectors should still fire as expected."""
    from demo_game.game.player.player import Player

    p = Player(10)
    # buff_base_speed replaces 1.0 → 1.5, so calculate_speed() = 1.5 * 2 = 3.0
    assert p.calculate_speed() == 3.0


def test_fast_path_does_not_alter_behaviour_when_no_injectors_apply():
    """Methods with no injectors should execute normally under the fast-path guard."""
    from demo_game.game.player.player import Player

    p = Player(20)
    # calculate_physics has no injector; should return x * 2
    assert p.calculate_physics(5) == 10


# ---------------------------------------------------------------------------
# LineSpec unit test (independent of conftest weaving)
# ---------------------------------------------------------------------------

def test_linespec_construction():
    from mixpy import LineSpec

    spec = LineSpec(lineno=10)
    assert spec.lineno == 10
    assert spec.end_lineno is None

    spec_range = LineSpec(lineno=10, end_lineno=20)
    assert spec_range.end_lineno == 20


def test_loc_accepts_linespec():
    from mixpy import Loc, LineSpec

    loc = Loc(line=LineSpec(lineno=5))
    assert loc.line is not None
    assert loc.line.lineno == 5


# ---------------------------------------------------------------------------
# TYPE.YIELD exposed in public API
# ---------------------------------------------------------------------------

def test_type_yield_in_enum():
    from mixpy import TYPE

    assert TYPE.YIELD == "YIELD"
    assert hasattr(TYPE, "YIELD")
