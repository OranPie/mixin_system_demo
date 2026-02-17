"""mixin_system: import-time AST mixin injection framework (demo).

This is a runnable reference implementation intended for iteration.
"""

from .api import init, mixin, inject
from .model import At, TYPE, OP, Loc, When
from .errors import MixinConflictError, MixinMatchError

from .selector import (
    NameSelector, QualifiedSelector, ConstSelector, AttrSelector,
    CallSelector, ArgAny, ArgConst, ArgName, ArgAttr, KwPattern
)
from .location import SliceSpec, NearSpec, AnchorSpec

__all__ = [
    "init","mixin","inject",
    "At","TYPE","OP","Loc","When",
    "NameSelector","QualifiedSelector","ConstSelector","AttrSelector",
    "CallSelector","ArgAny","ArgConst","ArgName","ArgAttr","KwPattern",
    "SliceSpec","NearSpec","AnchorSpec",
    "MixinConflictError","MixinMatchError",
]
