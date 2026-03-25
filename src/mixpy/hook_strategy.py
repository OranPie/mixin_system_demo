"""Hook strategy abstraction and registry.

Defines the ``HookStrategy`` protocol and a ``HookRegistry`` that lets users
choose between AST rewriting (default), monkey-patching, and sys.settrace
interception — or combine them.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class HookStrategy(Protocol):
    """Protocol that all hook strategies must satisfy."""

    name: str

    def activate(self) -> None:
        """Enable this hook strategy."""
        ...

    def deactivate(self) -> None:
        """Disable this hook strategy."""
        ...

    @property
    def is_active(self) -> bool:
        """Return ``True`` if this strategy is currently active."""
        ...


class HookRegistry:
    """Central registry for hook strategies.

    Usage::

        from mixpy.hook_strategy import HookRegistry
        from mixpy.monkey_patch import MonkeyPatchHook
        from mixpy.settrace_hook import SettraceHook

        registry = HookRegistry()
        registry.register(MonkeyPatchHook())
        registry.register(SettraceHook())

        registry.activate("monkey_patch")
        # ... do work ...
        registry.deactivate("monkey_patch")

        # Or activate all at once
        registry.activate_all()
        registry.deactivate_all()
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, HookStrategy] = {}

    def register(self, strategy: HookStrategy) -> None:
        """Register a hook strategy by its ``name`` attribute."""
        if not isinstance(strategy, HookStrategy):
            raise TypeError(
                f"Expected HookStrategy, got {type(strategy).__name__}"
            )
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str) -> None:
        """Remove a previously registered strategy (deactivates it first)."""
        strategy = self._strategies.pop(name, None)
        if strategy is not None and strategy.is_active:
            strategy.deactivate()

    def get(self, name: str) -> HookStrategy:
        """Return the strategy registered under *name*, or raise KeyError."""
        return self._strategies[name]

    def activate(self, name: str) -> None:
        """Activate the strategy registered under *name*."""
        self._strategies[name].activate()

    def deactivate(self, name: str) -> None:
        """Deactivate the strategy registered under *name*."""
        self._strategies[name].deactivate()

    def activate_all(self) -> None:
        """Activate every registered strategy."""
        for s in self._strategies.values():
            if not s.is_active:
                s.activate()

    def deactivate_all(self) -> None:
        """Deactivate every registered strategy."""
        for s in self._strategies.values():
            if s.is_active:
                s.deactivate()

    @property
    def active_strategies(self) -> List[str]:
        """Return names of currently active strategies."""
        return [n for n, s in self._strategies.items() if s.is_active]

    @property
    def registered_strategies(self) -> List[str]:
        """Return names of all registered strategies."""
        return list(self._strategies.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)
