from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union

# ---- Common name selectors ----

@dataclass(frozen=True)
class NameSelector:
    name: str

@dataclass(frozen=True)
class QualifiedSelector:
    parts: Tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, '_compiled_dotted', ".".join(self.parts))

    @staticmethod
    def of(*parts: str) -> "QualifiedSelector":
        return QualifiedSelector(parts=tuple(parts))

    def as_dotted(self) -> str:
        return self._compiled_dotted  # type: ignore[attr-defined]

@dataclass(frozen=True)
class WildcardSelector:
    pattern: str  # glob pattern like "self.calc_*" or "*.process"

    @staticmethod
    def of(pattern: str) -> "WildcardSelector":
        return WildcardSelector(pattern=pattern)

    def matches(self, dotted_name: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(dotted_name, self.pattern)

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
class ArgRegex(ArgPattern):
    pattern: str

    def __post_init__(self):
        object.__setattr__(self, '_compiled_re', re.compile(self.pattern))

    def match(self, node) -> bool:
        import ast
        return isinstance(node, ast.Constant) and isinstance(node.value, str) and self._compiled_re.search(node.value) is not None  # type: ignore[attr-defined]

@dataclass(frozen=True)
class ArgTypeCheck(ArgPattern):
    type_name: str  # "int", "float", "str", "bool", "NoneType"
    def match(self, node) -> bool:
        import ast
        return isinstance(node, ast.Constant) and type(node.value).__name__ == self.type_name

@dataclass(frozen=True)
class ArgExpr(ArgPattern):
    code: str  # e.g. "isinstance(node, ast.Constant) and node.value > 0"
    def match(self, node) -> bool:
        import ast
        return bool(eval(self.code, {"ast": ast, "node": node, "__builtins__": {
            "isinstance": isinstance, "len": len, "str": str, "int": int,
            "float": float, "bool": bool, "type": type, "hasattr": hasattr,
            "getattr": getattr,
        }}))

@dataclass(frozen=True)
class AndPattern(ArgPattern):
    patterns: Tuple[ArgPattern, ...]
    def match(self, node) -> bool:
        return all(p.match(node) for p in self.patterns)

@dataclass(frozen=True)
class OrPattern(ArgPattern):
    patterns: Tuple[ArgPattern, ...]
    def match(self, node) -> bool:
        return any(p.match(node) for p in self.patterns)

@dataclass(frozen=True)
class NotPattern(ArgPattern):
    pattern: ArgPattern
    def match(self, node) -> bool:
        return not self.pattern.match(node)

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
        object.__setattr__(self, '_keys_frozenset', frozenset(k for k, _ in self.items))

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
    func: Optional[Union[QualifiedSelector, WildcardSelector]] = None
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
            if isinstance(self.func, WildcardSelector):
                if func_parts is None or not self.func.matches(".".join(func_parts)):
                    return False
            else:
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
            pat_keys = self.kwargs._keys_frozenset  # type: ignore[attr-defined]

            kw_node_keys = set(kwargs_nodes.keys())
            missing = pat_keys - kw_node_keys
            if missing:
                if has_unresolved_starstar and starstar_policy == STARSTAR_POLICY.ASSUME_MATCH and kwmode == KW_MODE.SUBSET:
                    missing = frozenset()
                else:
                    return False

            for k, pat in pats.items():
                if k in kwargs_nodes and not pat.match(kwargs_nodes[k]):
                    return False

            if kwmode == KW_MODE.EXACT:
                if kw_node_keys != pat_keys:
                    return False

        return True

    def compile(self) -> Callable:
        """Return a pre-optimized match function for repeated use.

        Pre-computes invariants from the selector so that repeated calls avoid
        redundant attribute lookups, dict conversions, and object allocations.
        """
        # Pre-compute func matching invariants
        func_sel = self.func
        if func_sel is not None and isinstance(func_sel, QualifiedSelector):
            func_expected_parts = func_sel.parts
        else:
            func_expected_parts = None
        has_wildcard = func_sel is not None and isinstance(func_sel, WildcardSelector)

        # Pre-compute args invariants
        n_args = len(self.args)
        args_pats = self.args
        exact_args = self.args_mode == ARGS_MODE.EXACT

        # Pre-compute kwargs invariants
        if self.kwargs is not None:
            kw_dict = self.kwargs.as_dict()
            kw_keys = self.kwargs._keys_frozenset  # type: ignore[attr-defined]
            kw_exact = self.kwargs.mode == KW_MODE.EXACT
            kw_items = tuple(kw_dict.items())
        else:
            kw_dict = None
            kw_keys = None
            kw_exact = False
            kw_items = ()

        sp = self.starstar_policy

        def _match(
            func_parts_in: Optional[Tuple[str, ...]],
            args_nodes: Sequence,
            kwargs_nodes: Dict[str, Any],
            *,
            has_unresolved_starstar: bool = False,
        ) -> bool:
            # --- func ---
            if func_expected_parts is not None:
                if func_parts_in != func_expected_parts:
                    return False
            elif has_wildcard:
                if func_parts_in is None or not func_sel.matches(".".join(func_parts_in)):  # type: ignore[union-attr]
                    return False

            # --- args ---
            n_nodes = len(args_nodes)
            if exact_args:
                if n_nodes != n_args:
                    return False
            if n_nodes < n_args:
                return False
            for i in range(n_args):
                if not args_pats[i].match(args_nodes[i]):
                    return False

            # --- starstar gate ---
            if has_unresolved_starstar and sp == STARSTAR_POLICY.FAIL:
                return False

            # --- kwargs ---
            if kw_dict is not None:
                kw_node_keys = set(kwargs_nodes.keys())
                missing = kw_keys - kw_node_keys  # type: ignore[operator]
                if missing:
                    if has_unresolved_starstar and sp == STARSTAR_POLICY.ASSUME_MATCH and not kw_exact:
                        pass  # assume covered
                    else:
                        return False

                for k, pat in kw_items:
                    if k in kwargs_nodes and not pat.match(kwargs_nodes[k]):
                        return False

                if kw_exact:
                    if kw_node_keys != kw_keys:
                        return False

            return True

        return _match
