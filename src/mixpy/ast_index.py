"""Shared AST index cache to eliminate repeated ast.walk() calls across handlers."""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Type, TypeVar

T = TypeVar("T", bound=ast.AST)


class ASTIndex:
    """Pre-computed index over a function AST node.

    Built once per function being transformed and shared across all handler
    ``find()`` calls, avoiding redundant ``ast.walk()`` traversals.
    """

    __slots__ = (
        "_fn",
        "_parent_map",
        "_stmt_index",
        "_nodes_by_type",
        "_built",
    )

    def __init__(self, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._fn = fn
        self._parent_map: Dict[int, ast.AST] = {}
        self._stmt_index: Dict[int, int] = {}
        self._nodes_by_type: Dict[type, List[ast.AST]] = {}
        self._built = False
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Single DFS walk that populates all internal caches."""
        counter = 0
        stack: List[ast.AST] = [self._fn]
        while stack:
            node = stack.pop()
            self._stmt_index[id(node)] = counter
            counter += 1
            node_type = type(node)
            if node_type not in self._nodes_by_type:
                self._nodes_by_type[node_type] = []
            self._nodes_by_type[node_type].append(node)
            for child in ast.iter_child_nodes(node):
                self._parent_map[id(child)] = node
                stack.append(child)
        self._built = True

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def parent_map(self) -> Dict[int, ast.AST]:
        return self._parent_map

    @property
    def stmt_index(self) -> Dict[int, int]:
        return self._stmt_index

    @property
    def nodes_by_type(self) -> Dict[type, List[ast.AST]]:
        return self._nodes_by_type

    def get_nodes(self, node_type: Type[T]) -> List[T]:
        """Return all nodes of the given AST type found in the function."""
        return self._nodes_by_type.get(node_type, [])  # type: ignore[return-value]

    def get_parent(self, node: ast.AST) -> Optional[ast.AST]:
        """Return the parent of *node*, or ``None`` if it is the root."""
        return self._parent_map.get(id(node))

    # ------------------------------------------------------------------
    # Convenience typed accessors
    # ------------------------------------------------------------------

    @property
    def all_calls(self) -> List[ast.Call]:
        return self.get_nodes(ast.Call)

    @property
    def all_constants(self) -> List[ast.Constant]:
        return self.get_nodes(ast.Constant)

    @property
    def all_returns(self) -> List[ast.Return]:
        return self.get_nodes(ast.Return)

    @property
    def all_yields(self) -> List[ast.Yield]:
        return self.get_nodes(ast.Yield)

    @property
    def all_assigns(self) -> List[ast.Assign | ast.AnnAssign | ast.AugAssign]:
        result: List[ast.Assign | ast.AnnAssign | ast.AugAssign] = []
        result.extend(self.get_nodes(ast.Assign))
        result.extend(self.get_nodes(ast.AnnAssign))
        result.extend(self.get_nodes(ast.AugAssign))
        return result
