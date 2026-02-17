"""mixin_system: import-time AST mixin injection framework (demo).

This is a runnable reference implementation intended for iteration.
"""

from .api import (
    configure,
    init,
    inject,
    inject_attribute,
    inject_const,
    inject_head,
    inject_invoke,
    inject_parameter,
    inject_tail,
    mixin,
    at_attribute,
    at_const,
    at_head,
    at_invoke,
    at_parameter,
    at_tail,
    target_path,
)
from .model import At, TYPE, OP, Loc, When, POLICY, OCCURRENCE
from .errors import MixinConflictError, MixinMatchError

from .selector import (
    NameSelector, QualifiedSelector, ConstSelector, AttrSelector,
    CallSelector, ArgAny, ArgConst, ArgName, ArgAttr, KwPattern,
    ARGS_MODE, KW_MODE, STARSTAR_POLICY
)
from .location import SliceSpec, NearSpec, AnchorSpec

__all__ = [
    "configure","init","mixin","inject","target_path",
    "at_head","at_tail","at_parameter","at_const","at_invoke","at_attribute",
    "inject_head","inject_tail","inject_parameter","inject_const","inject_invoke","inject_attribute",
    "At","TYPE","OP","POLICY","OCCURRENCE","Loc","When",
    "NameSelector","QualifiedSelector","ConstSelector","AttrSelector",
    "CallSelector","ArgAny","ArgConst","ArgName","ArgAttr","KwPattern",
    "ARGS_MODE","KW_MODE","STARSTAR_POLICY",
    "SliceSpec","NearSpec","AnchorSpec",
    "MixinConflictError","MixinMatchError",
]
