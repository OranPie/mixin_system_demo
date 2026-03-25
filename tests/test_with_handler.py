"""Unit tests for TYPE.WITH injection point (WithHandler)."""

import ast
import textwrap

from mixpy.model import At, TYPE
from mixpy.builtin_handlers import WithHandler
from mixpy.ast_index import ASTIndex
from mixpy.registry import InjectorSpec


def _parse_fn(src: str) -> ast.FunctionDef:
    """Parse a single function definition from source text."""
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found in source")


def _dummy_cb(self_obj, ci):
    pass


# ---------------------------------------------------------------------------
# find() tests
# ---------------------------------------------------------------------------


class TestWithHandlerFind:
    handler = WithHandler()

    def test_find_with_open(self):
        fn = _parse_fn("""
        def foo():
            with open("f") as fh:
                pass
        """)
        at = At(type=TYPE.WITH, name="open")
        matches = self.handler.find(fn, at)
        assert len(matches) == 1
        assert isinstance(matches[0].node, ast.With)

    def test_find_with_name_expr(self):
        fn = _parse_fn("""
        def foo():
            with ctx_mgr:
                pass
        """)
        at = At(type=TYPE.WITH, name="ctx_mgr")
        matches = self.handler.find(fn, at)
        assert len(matches) == 1

    def test_find_no_match(self):
        fn = _parse_fn("""
        def foo():
            with open("f") as fh:
                pass
        """)
        at = At(type=TYPE.WITH, name="nonexistent")
        matches = self.handler.find(fn, at)
        assert len(matches) == 0

    def test_find_dotted_attr(self):
        fn = _parse_fn("""
        def foo():
            with some.module.ctx() as c:
                pass
        """)
        at = At(type=TYPE.WITH, name="some.module.ctx")
        matches = self.handler.find(fn, at)
        assert len(matches) == 1

    def test_find_multiple_withs(self):
        fn = _parse_fn("""
        def foo():
            with open("a") as a:
                pass
            with open("b") as b:
                pass
        """)
        at = At(type=TYPE.WITH, name="open")
        matches = self.handler.find(fn, at)
        assert len(matches) == 2

    def test_find_async_with(self):
        fn = _parse_fn("""
        async def foo():
            async with aopen("f") as fh:
                pass
        """)
        at = At(type=TYPE.WITH, name="aopen")
        matches = self.handler.find(fn, at)
        assert len(matches) == 1
        assert isinstance(matches[0].node, ast.AsyncWith)

    def test_find_uses_index(self):
        fn = _parse_fn("""
        def foo():
            with open("f") as fh:
                pass
        """)
        idx = ASTIndex(fn)
        at = At(type=TYPE.WITH, name="open")
        matches = self.handler.find(fn, at, index=idx)
        assert len(matches) == 1

    def test_find_as_variable_fallback(self):
        """When context_expr is complex, fall back to the 'as' variable name."""
        fn = _parse_fn("""
        def foo():
            with (lambda: mgr)() as fh:
                pass
        """)
        at = At(type=TYPE.WITH, name="fh")
        matches = self.handler.find(fn, at)
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# instrument() tests
# ---------------------------------------------------------------------------


class TestWithHandlerInstrument:
    handler = WithHandler()

    def _instrument(self, src: str, at_name: str = "open") -> ast.FunctionDef:
        fn = _parse_fn(src)
        at = At(type=TYPE.WITH, name=at_name)
        matches = self.handler.find(fn, at)
        spec = InjectorSpec(mixin_cls=object, callback=_dummy_cb, method=fn.name, at=at)
        self.handler.instrument(fn, matches, [spec], "test.Target")
        ast.fix_missing_locations(fn)
        return fn

    def test_instrument_basic(self):
        fn = self._instrument("""
        def foo(self):
            with open("f") as fh:
                x = 1
        """)
        # Should have: inj_assign, enter_if, guard_if
        assert len(fn.body) == 3
        src = ast.unparse(fn)
        assert "_mixin_inj_with_0" in src
        assert "_mixin_ci_with_enter_0" in src
        assert "_mixin_ci_with_exit_0" in src

    def test_instrument_preserves_original_with(self):
        fn = self._instrument("""
        def foo(self):
            with open("f") as fh:
                x = 1
        """)
        src = ast.unparse(fn)
        assert 'open("f")' in src or "open('f')" in src

    def test_instrument_multiple_withs_unique_vars(self):
        fn = self._instrument("""
        def foo(self):
            with open("a") as a:
                pass
            with open("b") as b:
                pass
        """)
        src = ast.unparse(fn)
        assert "_mixin_inj_with_0" in src
        assert "_mixin_inj_with_1" in src

    def test_instrument_compiles(self):
        fn = self._instrument("""
        def foo(self):
            with open("f") as fh:
                x = 1
        """)
        module = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(module)
        code = compile(module, "<test>", "exec")
        assert code is not None

    def test_instrument_nested_with_in_if(self):
        fn = self._instrument("""
        def foo(self):
            if True:
                with open("f") as fh:
                    pass
        """)
        src = ast.unparse(fn)
        assert "_mixin_inj_with_0" in src
