from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Dict

from .location import SliceSpec, NearSpec, AnchorSpec, LineSpec
from .selector import NameSelector, QualifiedSelector, ConstSelector, AttrSelector, CallSelector

class TYPE(str, Enum):
    HEAD = "HEAD"
    TAIL = "TAIL"
    INVOKE = "INVOKE"
    CONST = "CONST"
    ATTRIBUTE = "ATTRIBUTE"
    PARAMETER = "PARAMETER"
    EXCEPTION = "EXCEPTION"
    YIELD = "YIELD"
    WITH = "WITH"
    ATTR_READ = "ATTR_READ"
    AWAIT = "AWAIT"
    SUBSCRIPT = "SUBSCRIPT"

class OP(str, Enum):
    EQ="EQ"; NE="NE"; GT="GT"; LT="LT"; GE="GE"; LE="LE"
    IN="IN"; NOT_IN="NOT_IN"
    IS_NONE="IS_NONE"; NOT_NONE="NOT_NONE"
    MATCH="MATCH"
    AND="AND"; OR="OR"; NOT="NOT"
    ISINSTANCE="ISINSTANCE"
    LEN_EQ="LEN_EQ"; LEN_GT="LEN_GT"; LEN_LT="LEN_LT"

class POLICY(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    IGNORE = "IGNORE"
    STRICT = "STRICT"

class OCCURRENCE(str, Enum):
    ALL = "ALL"
    FIRST = "FIRST"
    LAST = "LAST"

@dataclass(frozen=True)
class When:
    """Safe condition DSL node."""
    left: str
    op: OP
    right: Any = None

    @staticmethod
    def and_(*conds: 'When') -> 'When':
        return When(left="__and__", op=OP.AND, right=list(conds))

    @staticmethod
    def or_(*conds: 'When') -> 'When':
        return When(left="__or__", op=OP.OR, right=list(conds))

    @staticmethod
    def not_(cond: 'When') -> 'When':
        return When(left="__not__", op=OP.NOT, right=cond)

@dataclass(frozen=True)
class Loc:
    """Location constraints (extensible)."""
    ordinal: Optional[int] = None           # match the Nth occurrence (0-based)
    occurrence: OCCURRENCE = OCCURRENCE.ALL
    condition: Optional[When] = None        # runtime condition (checked by wrapper)
    slice: Optional[SliceSpec] = None       # limit to region between anchors
    near: Optional[NearSpec] = None         # limit to neighborhood of anchor (statement distance)
    anchor: Optional[AnchorSpec] = None     # select relative to anchor
    line: Optional[LineSpec] = None         # filter by source line number

    def __post_init__(self):
        occ = self.occurrence
        if not isinstance(occ, OCCURRENCE):
            raise TypeError("occurrence must be an OCCURRENCE enum value.")

    # -- Fluent static factories ------------------------------------------------

    @staticmethod
    def between(from_anchor: 'At', to_anchor: 'At',
                include_from: bool = False, include_to: bool = False) -> 'Loc':
        """Create a Loc with a slice between two anchors."""
        return Loc(slice=SliceSpec(from_anchor=from_anchor, to_anchor=to_anchor,
                                   include_from=include_from, include_to=include_to))

    @staticmethod
    def after(anchor: 'At', inclusive: bool = False) -> 'Loc':
        """Create a Loc for everything after an anchor."""
        return Loc(slice=SliceSpec(from_anchor=anchor, include_from=inclusive))

    @staticmethod
    def before(anchor: 'At', inclusive: bool = False) -> 'Loc':
        """Create a Loc for everything before an anchor."""
        return Loc(slice=SliceSpec(to_anchor=anchor, include_to=inclusive))

    @staticmethod
    def within(distance: int, of: 'At') -> 'Loc':
        """Create a Loc for matches near an anchor within statement distance."""
        return Loc(near=NearSpec(anchor=of, max_distance=distance))

    @staticmethod
    def relative_to(anchor: 'At', offset: int = 0, inclusive: bool = False) -> 'Loc':
        """Create a Loc for a match relative to an anchor."""
        return Loc(anchor=AnchorSpec(anchor=anchor, offset=offset, inclusive=inclusive))

@dataclass(frozen=True)
class At:
    type: TYPE
    name: Any = None        # string for invoke/attribute, literal for const, arg name for parameter
    selector: Any = None    # structured selector (CallSelector / etc.)
    location: Optional[Loc] = None

    def with_location(self, loc: Loc) -> 'At':
        return At(type=self.type, name=self.name, selector=self.selector, location=loc)

    @property
    def condition(self) -> Optional[When]:
        return self.location.condition if self.location else None

    # -- Fluent static factories ------------------------------------------------

    @staticmethod
    def head(location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.HEAD, location=location)

    @staticmethod
    def tail(location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.TAIL, location=location)

    @staticmethod
    def invoke(name: str, selector: Any = None, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.INVOKE, name=name, selector=selector, location=location)

    @staticmethod
    def const(value: Any, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.CONST, name=value, location=location)

    @staticmethod
    def parameter(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.PARAMETER, name=name, location=location)

    @staticmethod
    def attribute(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.ATTRIBUTE, name=name, location=location)

    @staticmethod
    def exception(location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.EXCEPTION, location=location)

    @staticmethod
    def yield_(location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.YIELD, location=location)

    @staticmethod
    def with_(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.WITH, name=name, location=location)

    @staticmethod
    def attr_read(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.ATTR_READ, name=name, location=location)

    @staticmethod
    def await_(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.AWAIT, name=name, location=location)

    @staticmethod
    def subscript(name: str, location: Optional[Loc] = None) -> 'At':
        return At(type=TYPE.SUBSCRIPT, name=name, location=location)

    # -- Chaining methods -------------------------------------------------------

    def where(self, condition: When) -> 'At':
        """Add a runtime condition."""
        loc = self.location or Loc()
        new_loc = Loc(ordinal=loc.ordinal, occurrence=loc.occurrence, condition=condition,
                      slice=loc.slice, near=loc.near, anchor=loc.anchor, line=loc.line)
        return self.with_location(new_loc)

    def first(self) -> 'At':
        """Select only the first match."""
        loc = self.location or Loc()
        new_loc = Loc(ordinal=loc.ordinal, occurrence=OCCURRENCE.FIRST, condition=loc.condition,
                      slice=loc.slice, near=loc.near, anchor=loc.anchor, line=loc.line)
        return self.with_location(new_loc)

    def last(self) -> 'At':
        """Select only the last match."""
        loc = self.location or Loc()
        new_loc = Loc(ordinal=loc.ordinal, occurrence=OCCURRENCE.LAST, condition=loc.condition,
                      slice=loc.slice, near=loc.near, anchor=loc.anchor, line=loc.line)
        return self.with_location(new_loc)

    def nth(self, n: int) -> 'At':
        """Select the Nth match (0-based)."""
        loc = self.location or Loc()
        new_loc = Loc(ordinal=n, occurrence=loc.occurrence, condition=loc.condition,
                      slice=loc.slice, near=loc.near, anchor=loc.anchor, line=loc.line)
        return self.with_location(new_loc)

    def at_line(self, lineno: int, end_lineno: Optional[int] = None) -> 'At':
        """Filter by source line number."""
        loc = self.location or Loc()
        new_loc = Loc(ordinal=loc.ordinal, occurrence=loc.occurrence, condition=loc.condition,
                      slice=loc.slice, near=loc.near, anchor=loc.anchor,
                      line=LineSpec(lineno=lineno, end_lineno=end_lineno))
        return self.with_location(new_loc)
