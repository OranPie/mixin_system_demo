"""Monkey-patch hook strategy.

Provides runtime function/method replacement without AST rewriting.
Wraps target functions/methods with dispatchers that call injector callbacks
before/after the original.
"""
from __future__ import annotations
import importlib
import types
from typing import Any, Callable, Dict, List, Optional, Tuple
from .model import TYPE
from .runtime import CallbackInfo, dispatch_injectors
import time


class MonkeyPatchHook:
    """Runtime function/method replacement hook.
    
    Usage:
        hook = MonkeyPatchHook()
        
        # Patch a method with HEAD injection
        hook.patch_method("mymodule.MyClass", "my_method", TYPE.HEAD, callback)
        
        # Patch a module-level function
        hook.patch_function("mymodule", "my_func", TYPE.HEAD, callback)
        
        # Remove a specific patch
        hook.unpatch_method("mymodule.MyClass", "my_method", TYPE.HEAD, callback)
        
        # Remove all patches
        hook.unpatch_all()
    """
    
    name: str = "monkey_patch"

    def __init__(self):
        self._patches: Dict[str, _PatchEntry] = {}  # key -> PatchEntry
        self._originals: Dict[str, Any] = {}  # key -> original function
        self._active: bool = False

    def activate(self) -> None:
        """Mark this hook strategy as active."""
        self._active = True

    def deactivate(self) -> None:
        """Unpatch everything and mark inactive."""
        self.unpatch_all()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active
    
    def patch_method(self, target_class: str, method_name: str, 
                     injection_type: TYPE, callback: Callable,
                     priority: int = 100) -> None:
        """Patch a class method with an injector callback.
        
        Args:
            target_class: Fully qualified class name (e.g., "mymodule.MyClass")
            method_name: Method name to patch
            injection_type: TYPE.HEAD or TYPE.TAIL (supported for monkey-patch)
            callback: Injector callback with signature (self, ci, *args, **kwargs)
            priority: Lower runs first
        """
        cls = self._resolve_class(target_class)
        original = getattr(cls, method_name)
        
        key = f"{target_class}.{method_name}"
        
        if key not in self._originals:
            self._originals[key] = original
            self._patches[key] = _PatchEntry(target=target_class, method=method_name, 
                                              callbacks={}, original=original)
        
        entry = self._patches[key]
        if injection_type not in entry.callbacks:
            entry.callbacks[injection_type] = []
        entry.callbacks[injection_type].append((priority, callback))
        entry.callbacks[injection_type].sort(key=lambda x: x[0])
        
        wrapper = self._make_wrapper(entry)
        setattr(cls, method_name, wrapper)
    
    def patch_function(self, module_name: str, func_name: str,
                       injection_type: TYPE, callback: Callable,
                       priority: int = 100) -> None:
        """Patch a module-level function."""
        mod = importlib.import_module(module_name)
        original = getattr(mod, func_name)
        
        key = f"{module_name}.{func_name}"
        
        if key not in self._originals:
            self._originals[key] = original
            self._patches[key] = _PatchEntry(target=module_name, method=func_name,
                                              callbacks={}, original=original, is_function=True)
        
        entry = self._patches[key]
        if injection_type not in entry.callbacks:
            entry.callbacks[injection_type] = []
        entry.callbacks[injection_type].append((priority, callback))
        entry.callbacks[injection_type].sort(key=lambda x: x[0])
        
        wrapper = self._make_wrapper(entry)
        setattr(mod, func_name, wrapper)
    
    def unpatch_method(self, target_class: str, method_name: str,
                       injection_type: TYPE = None, callback: Callable = None) -> bool:
        """Remove a patch. If callback is None, remove all callbacks for that type.
        If injection_type is also None, remove entire patch."""
        key = f"{target_class}.{method_name}"
        return self._unpatch(key, injection_type, callback, is_class=True)
    
    def unpatch_function(self, module_name: str, func_name: str,
                         injection_type: TYPE = None, callback: Callable = None) -> bool:
        """Remove a function patch."""
        key = f"{module_name}.{func_name}"
        return self._unpatch(key, injection_type, callback, is_class=False)
    
    def unpatch_all(self) -> int:
        """Remove all patches. Returns count of patches removed."""
        count = 0
        for key, original in list(self._originals.items()):
            entry = self._patches.get(key)
            if entry:
                self._restore_original(key, entry)
                count += 1
        self._patches.clear()
        self._originals.clear()
        return count
    
    def list_patches(self) -> List[Dict[str, Any]]:
        """List all active patches."""
        result = []
        for key, entry in self._patches.items():
            for typ, cbs in entry.callbacks.items():
                for priority, cb in cbs:
                    result.append({
                        "target": entry.target,
                        "method": entry.method,
                        "type": typ.value,
                        "callback": getattr(cb, "__qualname__", str(cb)),
                        "priority": priority,
                    })
        return result
    
    # --- Internal ---
    
    def _resolve_class(self, fqn: str) -> type:
        """Resolve 'module.path.ClassName' to class object."""
        parts = fqn.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Expected 'module.ClassName', got '{fqn}'")
        mod = importlib.import_module(parts[0])
        cls = getattr(mod, parts[1])
        if not isinstance(cls, type):
            raise TypeError(f"{fqn} is not a class")
        return cls
    
    def _make_wrapper(self, entry: '_PatchEntry') -> Callable:
        """Create a wrapper function that dispatches to callbacks."""
        original = entry.original
        target = entry.target
        method = entry.method
        callbacks = entry.callbacks
        is_function = entry.is_function
        
        def wrapper(*args, **kwargs):
            self_obj = args[0] if args and not is_function else None
            
            # HEAD callbacks
            head_cbs = callbacks.get(TYPE.HEAD, [])
            if head_cbs:
                ci = CallbackInfo(type=TYPE.HEAD, target=target, method=method,
                                  at_name="HEAD", trace_id=str(time.time_ns()))
                injectors = [cb for _, cb in head_cbs]
                dispatch_injectors(injectors, ci, {}, *args)
                if ci.is_cancelled:
                    return ci.result
            
            # Call original
            result = original(*args, **kwargs)
            
            # TAIL callbacks
            tail_cbs = callbacks.get(TYPE.TAIL, [])
            if tail_cbs:
                ci = CallbackInfo(type=TYPE.TAIL, target=target, method=method,
                                  at_name="TAIL", trace_id=str(time.time_ns()))
                ci._ctx = {"return_value": result, "value": result}
                injectors = [cb for _, cb in tail_cbs]
                dispatch_injectors(injectors, ci, {"return_value": result, "value": result}, *args)
                if ci.is_cancelled:
                    return ci.result
                if ci.value_set:
                    return ci.new_value
            
            return result
        
        wrapper.__wrapped__ = original
        wrapper.__name__ = getattr(original, "__name__", method)
        wrapper.__qualname__ = getattr(original, "__qualname__", f"{target}.{method}")
        return wrapper
    
    def _unpatch(self, key: str, injection_type, callback, is_class: bool) -> bool:
        if key not in self._patches:
            return False
        entry = self._patches[key]
        
        if injection_type is None and callback is None:
            self._restore_original(key, entry)
            del self._patches[key]
            del self._originals[key]
            return True
        
        if injection_type is not None:
            if injection_type not in entry.callbacks:
                return False
            if callback is not None:
                entry.callbacks[injection_type] = [(p, cb) for p, cb in entry.callbacks[injection_type] if cb is not callback]
            else:
                del entry.callbacks[injection_type]
        
        # If no callbacks left, restore original
        if not any(entry.callbacks.values()):
            self._restore_original(key, entry)
            del self._patches[key]
            del self._originals[key]
            return True
        
        # Re-install wrapper with updated callbacks
        if is_class:
            cls = self._resolve_class(entry.target)
            setattr(cls, entry.method, self._make_wrapper(entry))
        else:
            mod = importlib.import_module(entry.target)
            setattr(mod, entry.method, self._make_wrapper(entry))
        return True
    
    def _restore_original(self, key: str, entry: '_PatchEntry') -> None:
        original = self._originals[key]
        if entry.is_function:
            mod = importlib.import_module(entry.target)
            setattr(mod, entry.method, original)
        else:
            cls = self._resolve_class(entry.target)
            setattr(cls, entry.method, original)


class _PatchEntry:
    __slots__ = ('target', 'method', 'callbacks', 'original', 'is_function')
    
    def __init__(self, target: str, method: str, callbacks: Dict[TYPE, List], 
                 original: Any, is_function: bool = False):
        self.target = target
        self.method = method
        self.callbacks = callbacks
        self.original = original
        self.is_function = is_function
