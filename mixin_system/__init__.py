"""mixin_system: import-time AST mixin injection framework (demo).

This is a runnable reference implementation intended for iteration.
"""

from .api import (
    configure,
    init,
    inject,
    inject_attribute,
    inject_const,
    inject_exception,
    inject_head,
    inject_invoke,
    inject_parameter,
    inject_tail,
    inject_yield,
    mixin,
    at_attribute,
    at_const,
    at_exception,
    at_head,
    at_invoke,
    at_parameter,
    at_tail,
    at_yield,
    target_path,
    unregister_injector,
    reload_target,
    generate_stubs,
)
from .model import At, TYPE, OP, Loc, When, POLICY, OCCURRENCE
from .errors import MixinConflictError, MixinMatchError

from .selector import (
    NameSelector, QualifiedSelector, ConstSelector, AttrSelector,
    CallSelector, ArgAny, ArgConst, ArgName, ArgAttr, KwPattern,
    ARGS_MODE, KW_MODE, STARSTAR_POLICY
)
from .location import SliceSpec, NearSpec, AnchorSpec, LineSpec

__all__ = [
    "configure","init","mixin","inject","target_path",
    "at_head","at_tail","at_parameter","at_const","at_invoke","at_attribute","at_exception","at_yield",
    "inject_head","inject_tail","inject_parameter","inject_const","inject_invoke","inject_attribute","inject_exception","inject_yield",
    "unregister_injector","reload_target","generate_stubs",
    "At","TYPE","OP","POLICY","OCCURRENCE","Loc","When",
    "NameSelector","QualifiedSelector","ConstSelector","AttrSelector",
    "CallSelector","ArgAny","ArgConst","ArgName","ArgAttr","KwPattern",
    "ARGS_MODE","KW_MODE","STARSTAR_POLICY",
    "SliceSpec","NearSpec","AnchorSpec","LineSpec",
    "MixinConflictError","MixinMatchError",
]
