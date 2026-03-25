"""Tests for new selector types (ArgRegex, ArgTypeCheck, ArgExpr, And/Or/NotPattern,
WildcardSelector) and the fluent API on At / Loc."""

from __future__ import annotations

import ast

import pytest

from mixpy.selector import (
    ArgAny,
    ArgConst,
    ArgRegex,
    ArgTypeCheck,
    ArgExpr,
    AndPattern,
    OrPattern,
    NotPattern,
    WildcardSelector,
    QualifiedSelector,
    CallSelector,
    ARGS_MODE,
)
from mixpy.model import At, Loc, When, OP, TYPE, OCCURRENCE
from mixpy.location import SliceSpec, NearSpec, AnchorSpec, LineSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _const(value):
    """Create an ast.Constant node."""
    return ast.Constant(value=value)


def _name(id_):
    """Create an ast.Name node."""
    return ast.Name(id=id_, ctx=ast.Load())


# ===========================================================================
# ArgRegex
# ===========================================================================

class TestArgRegex:
    def test_match_string_constant(self):
        pat = ArgRegex(pattern=r"^hello")
        assert pat.match(_const("hello world")) is True

    def test_non_match_string(self):
        pat = ArgRegex(pattern=r"^hello")
        assert pat.match(_const("goodbye")) is False

    def test_non_string_constant_int(self):
        pat = ArgRegex(pattern=r"\d+")
        assert pat.match(_const(42)) is False

    def test_non_constant_node(self):
        pat = ArgRegex(pattern=r".*")
        assert pat.match(_name("x")) is False


# ===========================================================================
# ArgTypeCheck
# ===========================================================================

class TestArgTypeCheck:
    def test_match_int(self):
        assert ArgTypeCheck(type_name="int").match(_const(7)) is True

    def test_match_str(self):
        assert ArgTypeCheck(type_name="str").match(_const("abc")) is True

    def test_match_float(self):
        assert ArgTypeCheck(type_name="float").match(_const(3.14)) is True

    def test_match_bool(self):
        assert ArgTypeCheck(type_name="bool").match(_const(True)) is True

    def test_match_none(self):
        assert ArgTypeCheck(type_name="NoneType").match(_const(None)) is True

    def test_non_match_type(self):
        assert ArgTypeCheck(type_name="str").match(_const(99)) is False

    def test_non_constant_node(self):
        assert ArgTypeCheck(type_name="str").match(_name("x")) is False


# ===========================================================================
# ArgExpr
# ===========================================================================

class TestArgExpr:
    def test_positive_int_match(self):
        pat = ArgExpr(code="isinstance(node, ast.Constant) and node.value > 0")
        assert pat.match(_const(5)) is True

    def test_negative_int_non_match(self):
        pat = ArgExpr(code="isinstance(node, ast.Constant) and node.value > 0")
        assert pat.match(_const(-3)) is False

    def test_non_constant_node(self):
        pat = ArgExpr(code="isinstance(node, ast.Constant) and node.value > 0")
        assert pat.match(_name("x")) is False

    def test_string_length(self):
        pat = ArgExpr(code="isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 3")
        assert pat.match(_const("abcd")) is True
        assert pat.match(_const("ab")) is False


# ===========================================================================
# AndPattern
# ===========================================================================

class TestAndPattern:
    def test_both_match(self):
        p = AndPattern(patterns=(ArgTypeCheck(type_name="int"), ArgExpr(code="node.value > 0")))
        assert p.match(_const(5)) is True

    def test_one_fails(self):
        p = AndPattern(patterns=(ArgTypeCheck(type_name="int"), ArgExpr(code="node.value > 0")))
        assert p.match(_const(-1)) is False

    def test_empty_patterns_vacuous_truth(self):
        p = AndPattern(patterns=())
        assert p.match(_const("anything")) is True


# ===========================================================================
# OrPattern
# ===========================================================================

class TestOrPattern:
    def test_one_matches(self):
        p = OrPattern(patterns=(ArgTypeCheck(type_name="int"), ArgTypeCheck(type_name="str")))
        assert p.match(_const(42)) is True

    def test_none_match(self):
        p = OrPattern(patterns=(ArgTypeCheck(type_name="int"), ArgTypeCheck(type_name="str")))
        assert p.match(_const(3.14)) is False

    def test_empty_patterns(self):
        p = OrPattern(patterns=())
        assert p.match(_const("anything")) is False


# ===========================================================================
# NotPattern
# ===========================================================================

class TestNotPattern:
    def test_inner_matches_returns_false(self):
        p = NotPattern(pattern=ArgTypeCheck(type_name="int"))
        assert p.match(_const(1)) is False

    def test_inner_does_not_match_returns_true(self):
        p = NotPattern(pattern=ArgTypeCheck(type_name="int"))
        assert p.match(_const("hello")) is True


# ===========================================================================
# WildcardSelector
# ===========================================================================

class TestWildcardSelector:
    def test_calc_star_matches_calc_physics(self):
        ws = WildcardSelector.of("self.calc_*")
        assert ws.matches("self.calc_physics") is True

    def test_calc_star_matches_calc_damage(self):
        ws = WildcardSelector.of("self.calc_*")
        assert ws.matches("self.calc_damage") is True

    def test_calc_star_no_match_process_data(self):
        ws = WildcardSelector.of("self.calc_*")
        assert ws.matches("self.process_data") is False

    def test_star_dot_process(self):
        ws = WildcardSelector.of("*.process")
        assert ws.matches("obj.process") is True

    def test_star_dot_process_no_match(self):
        ws = WildcardSelector.of("*.process")
        assert ws.matches("obj.execute") is False

    def test_of_factory(self):
        ws = WildcardSelector.of("foo.*")
        assert isinstance(ws, WildcardSelector)
        assert ws.pattern == "foo.*"


# ===========================================================================
# CallSelector with WildcardSelector
# ===========================================================================

class TestCallSelectorWithWildcard:
    def test_wildcard_func_match(self):
        cs = CallSelector(func=WildcardSelector.of("self.calc_*"))
        assert cs.match(func_parts=("self", "calc_damage"), args_nodes=[], kwargs_nodes={}) is True

    def test_wildcard_func_non_match(self):
        cs = CallSelector(func=WildcardSelector.of("self.calc_*"))
        assert cs.match(func_parts=("self", "process_data"), args_nodes=[], kwargs_nodes={}) is False

    def test_wildcard_func_none_parts(self):
        cs = CallSelector(func=WildcardSelector.of("self.calc_*"))
        assert cs.match(func_parts=None, args_nodes=[], kwargs_nodes={}) is False

    def test_wildcard_with_args(self):
        cs = CallSelector(
            func=WildcardSelector.of("self.calc_*"),
            args=(ArgConst(value=10),),
            args_mode=ARGS_MODE.PREFIX,
        )
        assert cs.match(
            func_parts=("self", "calc_physics"),
            args_nodes=[_const(10), _const(20)],
            kwargs_nodes={},
        ) is True

    def test_qualified_selector_still_works(self):
        cs = CallSelector(func=QualifiedSelector.of("self", "attack"))
        assert cs.match(func_parts=("self", "attack"), args_nodes=[], kwargs_nodes={}) is True
        assert cs.match(func_parts=("self", "defend"), args_nodes=[], kwargs_nodes={}) is False


# ===========================================================================
# At factory methods
# ===========================================================================

class TestAtFactories:
    def test_head(self):
        a = At.head()
        assert a.type == TYPE.HEAD
        assert a.name is None
        assert a.location is None

    def test_tail(self):
        a = At.tail()
        assert a.type == TYPE.TAIL

    def test_invoke(self):
        a = At.invoke("print")
        assert a.type == TYPE.INVOKE
        assert a.name == "print"

    def test_const(self):
        a = At.const(42)
        assert a.type == TYPE.CONST
        assert a.name == 42

    def test_parameter(self):
        a = At.parameter("x")
        assert a.type == TYPE.PARAMETER
        assert a.name == "x"

    def test_attribute(self):
        a = At.attribute("hp")
        assert a.type == TYPE.ATTRIBUTE
        assert a.name == "hp"

    def test_exception(self):
        a = At.exception()
        assert a.type == TYPE.EXCEPTION
        assert a.name is None

    def test_yield(self):
        a = At.yield_()
        assert a.type == TYPE.YIELD
        assert a.name is None


# ===========================================================================
# At chaining methods
# ===========================================================================

class TestAtChaining:
    def test_first(self):
        a = At.invoke("print").first()
        assert a.location.occurrence == OCCURRENCE.FIRST
        assert a.type == TYPE.INVOKE
        assert a.name == "print"

    def test_last(self):
        a = At.invoke("print").last()
        assert a.location.occurrence == OCCURRENCE.LAST

    def test_nth(self):
        a = At.invoke("print").nth(2)
        assert a.location.ordinal == 2

    def test_where(self):
        cond = When("x", OP.GT, 0)
        a = At.invoke("print").where(cond)
        assert a.location.condition is cond
        assert a.condition is cond

    def test_at_line(self):
        a = At.invoke("print").at_line(42)
        assert a.location.line == LineSpec(lineno=42)

    def test_at_line_range(self):
        a = At.invoke("print").at_line(10, end_lineno=20)
        assert a.location.line == LineSpec(lineno=10, end_lineno=20)

    def test_chain_where_and_first(self):
        cond = When("x", OP.GT, 0)
        a = At.invoke("print").where(cond).first()
        assert a.location.condition is cond
        assert a.location.occurrence == OCCURRENCE.FIRST
        assert a.name == "print"

    def test_chain_nth_and_where(self):
        cond = When("y", OP.EQ, 5)
        a = At.const(99).nth(1).where(cond)
        assert a.location.ordinal == 1
        assert a.location.condition is cond
        assert a.name == 99

    def test_chain_at_line_and_last(self):
        a = At.attribute("hp").at_line(50).last()
        assert a.location.line == LineSpec(lineno=50)
        assert a.location.occurrence == OCCURRENCE.LAST

    def test_with_location(self):
        loc = Loc(ordinal=3)
        a = At.invoke("foo").with_location(loc)
        assert a.location is loc
        assert a.location.ordinal == 3


# ===========================================================================
# Loc factory methods
# ===========================================================================

class TestLocFactories:
    def test_between(self):
        a1 = At.invoke("start")
        a2 = At.invoke("end")
        loc = Loc.between(a1, a2)
        assert loc.slice is not None
        assert loc.slice.from_anchor is a1
        assert loc.slice.to_anchor is a2
        assert loc.slice.include_from is False
        assert loc.slice.include_to is False

    def test_between_inclusive(self):
        a1 = At.invoke("start")
        a2 = At.invoke("end")
        loc = Loc.between(a1, a2, include_from=True, include_to=True)
        assert loc.slice.include_from is True
        assert loc.slice.include_to is True

    def test_after(self):
        anchor = At.invoke("checkpoint")
        loc = Loc.after(anchor)
        assert loc.slice is not None
        assert loc.slice.from_anchor is anchor
        assert loc.slice.to_anchor is None

    def test_after_inclusive(self):
        anchor = At.invoke("checkpoint")
        loc = Loc.after(anchor, inclusive=True)
        assert loc.slice.include_from is True

    def test_before(self):
        anchor = At.invoke("checkpoint")
        loc = Loc.before(anchor)
        assert loc.slice is not None
        assert loc.slice.to_anchor is anchor
        assert loc.slice.from_anchor is None

    def test_before_inclusive(self):
        anchor = At.invoke("checkpoint")
        loc = Loc.before(anchor, inclusive=True)
        assert loc.slice.include_to is True

    def test_within(self):
        anchor = At.invoke("target")
        loc = Loc.within(3, of=anchor)
        assert loc.near is not None
        assert loc.near.anchor is anchor
        assert loc.near.max_distance == 3

    def test_relative_to(self):
        anchor = At.invoke("ref")
        loc = Loc.relative_to(anchor, offset=1)
        assert loc.anchor is not None
        assert loc.anchor.anchor is anchor
        assert loc.anchor.offset == 1
        assert loc.anchor.inclusive is False

    def test_relative_to_inclusive(self):
        anchor = At.invoke("ref")
        loc = Loc.relative_to(anchor, offset=-1, inclusive=True)
        assert loc.anchor.offset == -1
        assert loc.anchor.inclusive is True


# ===========================================================================
# Composite / integration-style tests
# ===========================================================================

class TestComposite:
    def test_and_or_not_composition(self):
        """Compose And(Or(int, str), Not(bool))."""
        p = AndPattern(patterns=(
            OrPattern(patterns=(ArgTypeCheck(type_name="int"), ArgTypeCheck(type_name="str"))),
            NotPattern(pattern=ArgTypeCheck(type_name="bool")),
        ))
        assert p.match(_const(42)) is True
        assert p.match(_const("hi")) is True
        # bool is a subclass of int in Python, but type(True).__name__ == "bool"
        assert p.match(_const(True)) is False
        assert p.match(_const(3.14)) is False

    def test_at_invoke_with_full_loc(self):
        """Build a fully-specified At via chaining and verify all fields."""
        cond = When("args[0]", OP.GT, 10)
        a = At.invoke("calculate").where(cond).first().at_line(100)
        assert a.type == TYPE.INVOKE
        assert a.name == "calculate"
        assert a.location.occurrence == OCCURRENCE.FIRST
        assert a.location.condition is cond
        assert a.location.line.lineno == 100

    def test_loc_between_used_in_at(self):
        """Attach a Loc.between to an At via with_location."""
        a1 = At.invoke("setup")
        a2 = At.invoke("teardown")
        loc = Loc.between(a1, a2, include_from=True)
        target = At.const(0).with_location(loc)
        assert target.location.slice.from_anchor.name == "setup"
        assert target.location.slice.to_anchor.name == "teardown"
        assert target.location.slice.include_from is True
