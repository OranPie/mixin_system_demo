"""sys.settrace-based hook strategy.

Provides runtime call/line-level interception using Python's trace infrastructure.
No AST rewriting needed — intercepts at the interpreter level.

Trade-offs:
- Pro: Works on any code, no import-time transformation needed
- Pro: Can be enabled/disabled dynamically
- Con: Significant performance overhead (trace function called on every line/call)
- Con: Cannot intercept at the same granularity as AST (no CONST/ATTRIBUTE interception)

Supports: HEAD (call), TAIL (return), INVOKE (call to specific functions)
"""
from __future__ import annotations
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from .model import TYPE
from .runtime import CallbackInfo, dispatch_injectors
import time


class SettraceHook:
    """sys.settrace-based interception hook.
    
    Usage:
        hook = SettraceHook()
        
        # Register a HEAD callback for a specific function
        hook.on_call("mymodule.MyClass.my_method", callback)
        
        # Register a TAIL callback
        hook.on_return("mymodule.MyClass.my_method", callback)
        
        # Enable tracing
        hook.enable()
        
        # ... code runs with tracing active ...
        
        # Disable tracing
        hook.disable()
    """
    
    name: str = "settrace"

    def __init__(self):
        self._call_hooks: Dict[str, List[Tuple[int, Callable]]] = {}  # qualname -> [(priority, cb)]
        self._return_hooks: Dict[str, List[Tuple[int, Callable]]] = {}
        self._enabled = False
        self._previous_trace: Optional[Callable] = None
        self._lock = threading.Lock()

    def activate(self) -> None:
        """Enable sys.settrace interception."""
        self.enable()

    def deactivate(self) -> None:
        """Disable sys.settrace interception."""
        self.disable()

    @property
    def is_active(self) -> bool:
        return self._enabled
    
    def on_call(self, qualname: str, callback: Callable, priority: int = 100) -> None:
        """Register a callback for when a function is called (HEAD equivalent).
        
        Args:
            qualname: Qualified name to match (e.g., "MyClass.my_method" or "my_function")
            callback: Injector callback (self_or_none, ci, *args, **kwargs)
            priority: Lower runs first
        """
        with self._lock:
            if qualname not in self._call_hooks:
                self._call_hooks[qualname] = []
            self._call_hooks[qualname].append((priority, callback))
            self._call_hooks[qualname].sort(key=lambda x: x[0])
    
    def on_return(self, qualname: str, callback: Callable, priority: int = 100) -> None:
        """Register a callback for when a function returns (TAIL equivalent)."""
        with self._lock:
            if qualname not in self._return_hooks:
                self._return_hooks[qualname] = []
            self._return_hooks[qualname].append((priority, callback))
            self._return_hooks[qualname].sort(key=lambda x: x[0])
    
    def remove_hook(self, qualname: str, injection_type: TYPE = None, 
                    callback: Callable = None) -> bool:
        """Remove hooks for a qualname."""
        with self._lock:
            hooks_map = self._call_hooks if injection_type == TYPE.HEAD else self._return_hooks if injection_type == TYPE.TAIL else None
            
            if hooks_map is None:
                # Remove from both
                removed = False
                if qualname in self._call_hooks:
                    if callback:
                        self._call_hooks[qualname] = [(p, cb) for p, cb in self._call_hooks[qualname] if cb is not callback]
                    else:
                        del self._call_hooks[qualname]
                    removed = True
                if qualname in self._return_hooks:
                    if callback:
                        self._return_hooks[qualname] = [(p, cb) for p, cb in self._return_hooks[qualname] if cb is not callback]
                    else:
                        del self._return_hooks[qualname]
                    removed = True
                return removed
            
            if qualname not in hooks_map:
                return False
            if callback:
                hooks_map[qualname] = [(p, cb) for p, cb in hooks_map[qualname] if cb is not callback]
            else:
                del hooks_map[qualname]
            return True
    
    def enable(self) -> None:
        """Enable tracing. Installs sys.settrace hook."""
        if self._enabled:
            return
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace_dispatch)
        # Also set for current thread
        threading.settrace(self._trace_dispatch)
        self._enabled = True
    
    def disable(self) -> None:
        """Disable tracing. Restores previous trace function."""
        if not self._enabled:
            return
        sys.settrace(self._previous_trace)
        threading.settrace(self._previous_trace or (lambda *a: None))
        self._enabled = False
        self._previous_trace = None
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    def list_hooks(self) -> List[Dict[str, Any]]:
        """List all registered hooks."""
        result = []
        for qn, cbs in self._call_hooks.items():
            for priority, cb in cbs:
                result.append({"qualname": qn, "type": "HEAD", "callback": getattr(cb, "__qualname__", str(cb)), "priority": priority})
        for qn, cbs in self._return_hooks.items():
            for priority, cb in cbs:
                result.append({"qualname": qn, "type": "TAIL", "callback": getattr(cb, "__qualname__", str(cb)), "priority": priority})
        return result
    
    def clear(self) -> None:
        """Remove all hooks."""
        with self._lock:
            self._call_hooks.clear()
            self._return_hooks.clear()
    
    # --- Trace function ---
    
    def _trace_dispatch(self, frame, event, arg):
        """Main trace function installed via sys.settrace."""
        if event == "call":
            return self._handle_call(frame, arg)
        elif event == "return":
            self._handle_return(frame, arg)
        return self._trace_dispatch
    
    def _get_qualname(self, frame) -> Optional[str]:
        """Extract qualified name from frame."""
        code = frame.f_code
        qualname = code.co_qualname if hasattr(code, 'co_qualname') else code.co_name
        return qualname
    
    def _handle_call(self, frame, arg) -> Optional[Callable]:
        """Handle 'call' trace event."""
        qualname = self._get_qualname(frame)
        if qualname is None:
            return self._trace_dispatch
        
        hooks = self._call_hooks.get(qualname)
        if not hooks:
            return self._trace_dispatch
        
        ci = CallbackInfo(
            type=TYPE.HEAD, target=frame.f_code.co_filename,
            method=qualname, at_name="HEAD",
            trace_id=str(time.time_ns())
        )
        
        # Extract args from frame locals
        varnames = frame.f_code.co_varnames
        local_vals = frame.f_locals
        args_list = []
        for name in varnames[:frame.f_code.co_argcount]:
            if name in local_vals:
                args_list.append(local_vals[name])
        
        self_obj = args_list[0] if args_list else None
        injectors = [cb for _, cb in hooks]
        dispatch_injectors(injectors, ci, {}, *args_list)
        
        # Note: cancellation in settrace HEAD doesn't prevent the call
        # (the frame is already executing). We store the result for return.
        if ci.is_cancelled:
            frame.f_locals['__settrace_cancel__'] = ci.result
        
        return self._trace_dispatch
    
    def _handle_return(self, frame, return_value) -> None:
        """Handle 'return' trace event."""
        qualname = self._get_qualname(frame)
        if qualname is None:
            return
        
        hooks = self._return_hooks.get(qualname)
        if not hooks:
            return
        
        ci = CallbackInfo(
            type=TYPE.TAIL, target=frame.f_code.co_filename,
            method=qualname, at_name="TAIL",
            trace_id=str(time.time_ns())
        )
        ci._ctx = {"return_value": return_value, "value": return_value}
        
        varnames = frame.f_code.co_varnames
        local_vals = frame.f_locals
        args_list = []
        for name in varnames[:frame.f_code.co_argcount]:
            if name in local_vals:
                args_list.append(local_vals[name])
        
        self_obj = args_list[0] if args_list else None
        injectors = [cb for _, cb in hooks]
        dispatch_injectors(injectors, ci, {"return_value": return_value, "value": return_value}, *args_list)
        
        # Note: settrace cannot actually change the return value.
        # The callback can observe but not modify. This is a limitation.
