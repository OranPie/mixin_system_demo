from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Dict

from .location import SliceSpec, NearSpec, AnchorSpec
from .selector import NameSelector, QualifiedSelector, ConstSelector, AttrSelector, CallSelector

class TYPE(str, Enum):
    HEAD = "HEAD"
    TAIL = "TAIL"
    INVOKE = "INVOKE"
    CONST = "CONST"
    ATTRIBUTE = "ATTRIBUTE"
    PARAMETER = "PARAMETER"

class OP(str, Enum):
    EQ="EQ"; NE="NE"; GT="GT"; LT="LT"; GE="GE"; LE="LE"
    IN="IN"; NOT_IN="NOT_IN"
    IS_NONE="IS_NONE"; NOT_NONE="NOT_NONE"
    MATCH="MATCH"
    AND="AND"; OR="OR"; NOT="NOT"
    ISINSTANCE="ISINSTANCE"

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

    def __post_init__(self):
        occ = self.occurrence
        if not isinstance(occ, OCCURRENCE):
            raise TypeError("occurrence must be an OCCURRENCE enum value.")

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
