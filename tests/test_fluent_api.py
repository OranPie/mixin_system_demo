"""Tests for the fluent builder API on At and Loc."""
from mixpy.model import At, Loc, TYPE, OCCURRENCE, When, OP
from mixpy.location import SliceSpec, NearSpec, AnchorSpec, LineSpec


# ── At static factories ─────────────────────────────────────────────

def test_at_head():
    a = At.head()
    assert a.type == TYPE.HEAD and a.name is None and a.location is None

def test_at_tail():
    a = At.tail()
    assert a.type == TYPE.TAIL

def test_at_invoke():
    a = At.invoke("print")
    assert a.type == TYPE.INVOKE and a.name == "print"

def test_at_invoke_with_selector():
    sel = object()
    a = At.invoke("foo", selector=sel)
    assert a.selector is sel

def test_at_const():
    a = At.const(42)
    assert a.type == TYPE.CONST and a.name == 42

def test_at_parameter():
    a = At.parameter("x")
    assert a.type == TYPE.PARAMETER and a.name == "x"

def test_at_attribute():
    a = At.attribute("hp")
    assert a.type == TYPE.ATTRIBUTE and a.name == "hp"

def test_at_exception():
    a = At.exception()
    assert a.type == TYPE.EXCEPTION

def test_at_yield():
    a = At.yield_()
    assert a.type == TYPE.YIELD

def test_at_factory_with_location():
    loc = Loc(ordinal=2)
    a = At.invoke("f", location=loc)
    assert a.location is loc and a.location.ordinal == 2


# ── At chaining methods ─────────────────────────────────────────────

def test_first():
    a = At.invoke("f").first()
    assert a.location.occurrence == OCCURRENCE.FIRST

def test_last():
    a = At.invoke("f").last()
    assert a.location.occurrence == OCCURRENCE.LAST

def test_nth():
    a = At.invoke("f").nth(3)
    assert a.location.ordinal == 3

def test_where():
    cond = When("args[0]", OP.GT, 10)
    a = At.invoke("f").where(cond)
    assert a.location.condition is cond

def test_at_line():
    a = At.const(0).at_line(42)
    assert a.location.line == LineSpec(lineno=42)

def test_at_line_range():
    a = At.const(0).at_line(10, end_lineno=20)
    assert a.location.line == LineSpec(lineno=10, end_lineno=20)

def test_chaining_preserves_fields():
    cond = When("x", OP.EQ, 1)
    a = At.invoke("print").first().where(cond).nth(2)
    assert a.type == TYPE.INVOKE
    assert a.name == "print"
    assert a.location.ordinal == 2
    assert a.location.condition is cond
    # nth doesn't reset occurrence set earlier via first — it only sets ordinal
    assert a.location.occurrence == OCCURRENCE.FIRST

def test_chaining_does_not_mutate_original():
    a = At.invoke("f")
    b = a.first()
    assert a.location is None
    assert b.location.occurrence == OCCURRENCE.FIRST


# ── Loc static factories ────────────────────────────────────────────

def test_loc_between():
    f = At.invoke("a")
    t = At.invoke("b")
    loc = Loc.between(f, t, include_from=True)
    assert loc.slice == SliceSpec(from_anchor=f, to_anchor=t,
                                  include_from=True, include_to=False)

def test_loc_after():
    anchor = At.invoke("a")
    loc = Loc.after(anchor, inclusive=True)
    assert loc.slice.from_anchor is anchor
    assert loc.slice.to_anchor is None
    assert loc.slice.include_from is True

def test_loc_before():
    anchor = At.invoke("b")
    loc = Loc.before(anchor)
    assert loc.slice.to_anchor is anchor
    assert loc.slice.from_anchor is None
    assert loc.slice.include_to is False

def test_loc_within():
    anchor = At.invoke("x")
    loc = Loc.within(5, of=anchor)
    assert loc.near == NearSpec(anchor=anchor, max_distance=5)

def test_loc_relative_to():
    anchor = At.invoke("y")
    loc = Loc.relative_to(anchor, offset=1, inclusive=True)
    assert loc.anchor == AnchorSpec(anchor=anchor, offset=1, inclusive=True)


# ── Integration: factories + chaining ────────────────────────────────

def test_invoke_with_loc_factory():
    anchor = At.invoke("setup")
    a = At.invoke("run", location=Loc.after(anchor)).first()
    assert a.location.slice.from_anchor is anchor
    assert a.location.occurrence == OCCURRENCE.FIRST
