from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

# ---- Common name selectors ----

@dataclass(frozen=True)
class NameSelector:
    name: str

@dataclass(frozen=True)
class QualifiedSelector:
    parts: Tuple[str, ...]

    @staticmethod
    def of(*parts: str) -> "QualifiedSelector":
        return QualifiedSelector(parts=tuple(parts))

    def as_dotted(self) -> str:
        return ".".join(self.parts)

# ---- CONST selectors ----

@dataclass(frozen=True)
class ConstSelector:
    value: Any
    type_name: Optional[str] = None  # e.g. "int","float","str","bool"

# ---- Attribute selectors ----

@dataclass(frozen=True)
class AttrSelector:
    parts: Tuple[str, ...]

    @staticmethod
    def of(*parts: str) -> "AttrSelector":
        return AttrSelector(parts=tuple(parts))

    def as_dotted(self) -> str:
        return ".".join(self.parts)

# ---- INVOKE selectors (args/kwargs pattern) ----

class ARGS_MODE(str, Enum):
    PREFIX = "PREFIX"
    EXACT = "EXACT"

class KW_MODE(str, Enum):
    SUBSET = "SUBSET"
    EXACT = "EXACT"

class STARSTAR_POLICY(str, Enum):
    FAIL = "FAIL"
    IGNORE = "IGNORE"
    ASSUME_MATCH = "ASSUME_MATCH"

class ArgPattern:
    def match(self, node) -> bool:
        raise NotImplementedError

@dataclass(frozen=True)
class ArgAny(ArgPattern):
    def match(self, node) -> bool:
        return True

@dataclass(frozen=True)
class ArgConst(ArgPattern):
    value: Any
    def match(self, node) -> bool:
        import ast
        return isinstance(node, ast.Constant) and node.value == self.value

@dataclass(frozen=True)
class ArgName(ArgPattern):
    name: str
    def match(self, node) -> bool:
        import ast
        return isinstance(node, ast.Name) and node.id == self.name

@dataclass(frozen=True)
class ArgAttr(ArgPattern):
    parts: Tuple[str, ...]
    @staticmethod
    def of(*parts: str) -> "ArgAttr":
        return ArgAttr(parts=tuple(parts))
    def match(self, node) -> bool:
        import ast
        if isinstance(node, ast.Name):
            return (node.id,) == self.parts
        if not isinstance(node, ast.Attribute):
            return False
        parts=[]
        cur=node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur=cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return tuple(reversed(parts)) == self.parts
        return False

@dataclass(frozen=True)
class KwPattern:
    items: Tuple[Tuple[str, ArgPattern], ...]
    mode: KW_MODE = KW_MODE.SUBSET

    @staticmethod
    def subset(**patterns: ArgPattern) -> "KwPattern":
        return KwPattern(items=tuple(sorted(patterns.items(), key=lambda kv: kv[0])), mode=KW_MODE.SUBSET)

    @staticmethod
    def exact(**patterns: ArgPattern) -> "KwPattern":
        return KwPattern(items=tuple(sorted(patterns.items(), key=lambda kv: kv[0])), mode=KW_MODE.EXACT)

    def as_dict(self) -> Dict[str, ArgPattern]:
        return dict(self.items)

    def __post_init__(self):
        mode = self.mode
        if not isinstance(mode, KW_MODE):
            raise TypeError("KwPattern.mode must be a KW_MODE enum value.")

@dataclass(frozen=True)
class CallSelector:
    """Match a call site structurally (AST-level), with deterministic handling of **kwargs.

    `starstar_policy` governs unresolved `**expr` keywords:

    - FAIL (default): if any unresolved **kwargs exists, the selector does not match.
    - IGNORE: allow unresolved **kwargs, but they do NOT satisfy missing required keys.
              For EXACT, "exact" is enforced on *known keys only* (explicit + resolvable dict literals).
    - ASSUME_MATCH: allow unresolved **kwargs. For SUBSET, missing required keys may be assumed present.
                    For EXACT, behaves like IGNORE (exact on known keys).
    """
    func: Optional[QualifiedSelector] = None
    args: Tuple[ArgPattern, ...] = ()
    args_mode: ARGS_MODE = ARGS_MODE.PREFIX
    kwargs: Optional[KwPattern] = None
    starstar_policy: STARSTAR_POLICY = STARSTAR_POLICY.FAIL

    def __post_init__(self):
        args_mode = self.args_mode
        if not isinstance(args_mode, ARGS_MODE):
            raise TypeError("args_mode must be an ARGS_MODE enum value.")
        starstar_policy = self.starstar_policy
        if not isinstance(starstar_policy, STARSTAR_POLICY):
            raise TypeError("starstar_policy must be a STARSTAR_POLICY enum value.")

    def match(
        self,
        func_parts: Optional[Tuple[str, ...]],
        args_nodes: Sequence,
        kwargs_nodes: Dict[str, Any],
        *,
        has_unresolved_starstar: bool = False,
    ) -> bool:
        # func
        if self.func is not None:
            if func_parts != self.func.parts:
                return False

        # args
        mode = self.args_mode
        if mode == ARGS_MODE.EXACT:
            if len(args_nodes) != len(self.args):
                return False
        if len(args_nodes) < len(self.args):
            return False
        for pat, node in zip(self.args, args_nodes):
            if not pat.match(node):
                return False

        # kwargs / **kwargs
        starstar_policy = self.starstar_policy
        if has_unresolved_starstar and starstar_policy == STARSTAR_POLICY.FAIL:
            return False

        if self.kwargs is not None:
            kwmode = self.kwargs.mode
            pats = self.kwargs.as_dict()

            missing = [k for k in pats.keys() if k not in kwargs_nodes]
            if missing:
                if has_unresolved_starstar and starstar_policy == STARSTAR_POLICY.ASSUME_MATCH and kwmode == KW_MODE.SUBSET:
                    missing = []
                else:
                    return False

            for k, pat in pats.items():
                if k in kwargs_nodes and not pat.match(kwargs_nodes[k]):
                    return False

            if kwmode == KW_MODE.EXACT:
                if set(kwargs_nodes.keys()) != set(pats.keys()):
                    return False

        return True
