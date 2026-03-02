from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Tuple
import ast

from .model import At, TYPE, Loc
from .registry import InjectorSpec

@dataclass
class Match:
    node: ast.AST
    parent: Optional[ast.AST]
    field: Optional[str]
    index: Optional[int]
    at: At

class TypeHandler(Protocol):
    type: TYPE
    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]: ...
    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None: ...

_HANDLERS: dict[TYPE, TypeHandler] = {}

def register_handler(handler: TypeHandler) -> None:
    _HANDLERS[handler.type] = handler

def get_handler(t: TYPE) -> TypeHandler:
    return _HANDLERS[t]
