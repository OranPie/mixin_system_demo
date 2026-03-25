"""mixpy: import-time AST mixin injection framework.

This is a runnable reference implementation intended for iteration.
"""

from .api import (
    configure,
    init,
    inject,
    inject_attribute,
    inject_await,
    inject_const,
    inject_exception,
    inject_head,
    inject_invoke,
    inject_loop,
    inject_parameter,
    inject_tail,
    inject_with,
    inject_yield,
    mixin,
    at_attribute,
    at_await,
    at_const,
    at_exception,
    at_head,
    at_invoke,
    at_loop,
    at_parameter,
    at_tail,
    at_with,
    at_yield,
    target_path,
    unregister_injector,
    reload_target,
    generate_stubs,
)
from .model import At, TYPE, OP, Loc, When, POLICY, OCCURRENCE
from .errors import MixinConflictError, MixinMatchError
from .debug import log

from .selector import (
    NameSelector, QualifiedSelector, WildcardSelector, ConstSelector, AttrSelector,
    CallSelector, ArgAny, ArgConst, ArgName, ArgAttr,
    ArgRegex, ArgTypeCheck, ArgExpr, AndPattern, OrPattern, NotPattern,
    KwPattern, ARGS_MODE, KW_MODE, STARSTAR_POLICY
)
from .location import SliceSpec, NearSpec, AnchorSpec, LineSpec

__version__ = "0.1.0"

__all__ = [
    "configure","init","mixin","inject","target_path","log",
    "at_head","at_tail","at_parameter","at_const","at_invoke","at_attribute","at_exception","at_yield","at_await","at_with","at_loop",
    "inject_head","inject_tail","inject_parameter","inject_const","inject_invoke","inject_attribute","inject_exception","inject_yield","inject_await","inject_with","inject_loop",
    "unregister_injector","reload_target","generate_stubs",
    "At","TYPE","OP","POLICY","OCCURRENCE","Loc","When",
    "NameSelector","QualifiedSelector","WildcardSelector","ConstSelector","AttrSelector",
    "CallSelector","ArgAny","ArgConst","ArgName","ArgAttr",
    "ArgRegex","ArgTypeCheck","ArgExpr","AndPattern","OrPattern","NotPattern",
    "KwPattern",
    "ARGS_MODE","KW_MODE","STARSTAR_POLICY",
    "SliceSpec","NearSpec","AnchorSpec","LineSpec",
    "MixinConflictError","MixinMatchError",
]
