from __future__ import annotations
import ast
from typing import Dict, List, Optional, Tuple

from .model import At, Loc, OCCURRENCE
from .handlers import get_handler
from .location import SliceSpec, NearSpec, AnchorSpec, LineSpec

def _dotted_name_from_attribute(n: ast.AST):
    if isinstance(n, ast.Name):
        return (n.id,)
    if isinstance(n, ast.Attribute):
        parts=[]
        cur=n
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur=cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return tuple(reversed(parts))
    return None

def _build_parent_map(root: ast.AST) -> Dict[int, ast.AST]:
    parents: Dict[int, ast.AST] = {}
    for parent in ast.walk(root):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents

def _enclosing_stmt(node: ast.AST, parents: Dict[int, ast.AST]) -> Optional[ast.stmt]:
    cur = node
    while True:
        if isinstance(cur, ast.stmt) and not isinstance(cur, ast.FunctionDef):
            return cur
        p = parents.get(id(cur))
        if p is None:
            return None
        cur = p

def _iter_stmts_in_order(fn: ast.FunctionDef) -> List[ast.stmt]:
    out: List[ast.stmt] = []
    def walk_block(stmts: List[ast.stmt]):
        for s in stmts:
            out.append(s)
            for field in ("body", "orelse", "finalbody"):
                blk = getattr(s, field, None)
                if isinstance(blk, list) and blk and all(isinstance(x, ast.stmt) for x in blk):
                    walk_block(blk)
            if isinstance(s, ast.Try):
                for h in s.handlers:
                    walk_block(h.body)
                    walk_block(h.orelse)
                walk_block(s.finalbody)
    walk_block(fn.body)
    return out

def _stmt_index(fn: ast.FunctionDef) -> Dict[int, int]:
    stmts = _iter_stmts_in_order(fn)
    return {id(s): i for i, s in enumerate(stmts)}

def _dfs_preorder(root: ast.AST) -> List[ast.AST]:
    out: List[ast.AST] = []
    stack: List[ast.AST] = [root]
    while stack:
        node = stack.pop()
        out.append(node)
        children = list(ast.iter_child_nodes(node))
        stack.extend(reversed(children))
    return out

def _intra_index(stmt: ast.stmt) -> Dict[int, int]:
    nodes = _dfs_preorder(stmt)
    return {id(n): i for i, n in enumerate(nodes)}

def _order_key(fn: ast.FunctionDef, node: ast.AST, parents: Dict[int, ast.AST], stmt_idx: Dict[int, int]) -> Tuple[int, int]:
    stmt = _enclosing_stmt(node, parents)
    if stmt is None:
        return (-1, -1)
    si = stmt_idx.get(id(stmt), -1)
    intra = _intra_index(stmt)
    ii = intra.get(id(node), intra.get(id(stmt), 0))
    return (si, ii)

def _find_matches_raw(fn: ast.FunctionDef, at: At):
    handler = get_handler(at.type)
    return handler.find(fn, at)

def _anchor_pos(fn: ast.FunctionDef, parents: Dict[int, ast.AST], stmt_idx: Dict[int, int], anchor_at: At) -> Optional[Tuple[int, int]]:
    raw = _find_matches_raw(fn, anchor_at)
    matches = apply_location(fn, raw, anchor_at)
    if not matches:
        return None
    keys = sorted(_order_key(fn, m.node, parents, stmt_idx) for m in matches)
    return keys[0] if keys else None

def apply_location(fn: ast.FunctionDef, matches, at: At):
    loc: Optional[Loc] = at.location
    if not loc:
        return matches

    parents = _build_parent_map(fn)
    stmt_idx = _stmt_index(fn)

    def key(m):
        return _order_key(fn, m.node, parents, stmt_idx)

    matches_sorted = sorted(matches, key=key)

    # slice filter (supports one-sided)
    if loc.slice:
        s: SliceSpec = loc.slice
        start = _anchor_pos(fn, parents, stmt_idx, s.from_anchor) if s.from_anchor else None
        end = _anchor_pos(fn, parents, stmt_idx, s.to_anchor) if s.to_anchor else None

        def ge(a,b): return a[0] > b[0] or (a[0]==b[0] and a[1] >= b[1])
        def gt(a,b): return a[0] > b[0] or (a[0]==b[0] and a[1] > b[1])
        def le(a,b): return a[0] < b[0] or (a[0]==b[0] and a[1] <= b[1])
        def lt(a,b): return a[0] < b[0] or (a[0]==b[0] and a[1] < b[1])

        def in_range(k):
            if start is not None:
                if s.include_from:
                    if not ge(k, start): return False
                else:
                    if not gt(k, start): return False
            if end is not None:
                if s.include_to:
                    if not le(k, end): return False
                else:
                    if not lt(k, end): return False
            return True

        matches_sorted = [m for m in matches_sorted if in_range(key(m))]

    # near filter (statement distance)
    if loc.near:
        n: NearSpec = loc.near
        apos = _anchor_pos(fn, parents, stmt_idx, n.anchor)
        if apos is None:
            matches_sorted = []
        else:
            a_stmt = apos[0]
            matches_sorted = [m for m in matches_sorted if abs(key(m)[0] - a_stmt) <= n.max_distance]

    # anchor-relative selection
    if loc.anchor:
        a: AnchorSpec = loc.anchor
        apos = _anchor_pos(fn, parents, stmt_idx, a.anchor)
        if apos is None:
            matches_sorted = []
        else:
            items = [(key(m), m) for m in matches_sorted]
            items.sort(key=lambda t: t[0])

            def gt_(x,y): return x[0] > y[0] or (x[0]==y[0] and x[1] > y[1])
            def ge_(x,y): return x[0] > y[0] or (x[0]==y[0] and x[1] >= y[1])
            def lt_(x,y): return x[0] < y[0] or (x[0]==y[0] and x[1] < y[1])
            def le_(x,y): return x[0] < y[0] or (x[0]==y[0] and x[1] <= y[1])

            if a.offset >= 0:
                cand = [t for t in items if (ge_(t[0], apos) if a.inclusive else gt_(t[0], apos))]
                pick = a.offset
            else:
                cand = [t for t in items if (le_(t[0], apos) if a.inclusive else lt_(t[0], apos))]
                cand = list(reversed(cand))
                pick = (-a.offset) - 1
            matches_sorted = [cand[pick][1]] if 0 <= pick < len(cand) else []

    # line-number filter: applied before occurrence/ordinal so those selectors
    # pick from the line-restricted candidate set.
    if loc.line:
        ln: LineSpec = loc.line

        def _in_line(m) -> bool:
            node_lineno = getattr(m.node, "lineno", None)
            if node_lineno is None:
                return False
            if ln.end_lineno is None:
                return node_lineno == ln.lineno
            return ln.lineno <= node_lineno <= ln.end_lineno

        matches_sorted = [m for m in matches_sorted if _in_line(m)]

    occ = loc.occurrence
    if occ == OCCURRENCE.FIRST:
        matches_sorted = matches_sorted[:1]
    elif occ == OCCURRENCE.LAST:
        matches_sorted = matches_sorted[-1:] if matches_sorted else []

    if loc.ordinal is not None:
        matches_sorted = [matches_sorted[loc.ordinal]] if 0 <= loc.ordinal < len(matches_sorted) else []

    return matches_sorted
