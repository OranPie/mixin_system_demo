# MixPy — Hook Strategies

MixPy supports three distinct hook strategies for intercepting Python code. Each strategy offers different trade-offs between capability, performance, and flexibility.

---

## Strategy comparison

| Strategy | Mechanism | Injection types | Performance | Best for |
|---|---|---|---|---|
| **AST Rewriting** (default) | Import-time source transform | All 13 types | Zero runtime overhead | Deterministic interception |
| **Monkey-Patch** | Runtime function replacement | HEAD, TAIL | Low overhead | Post-init / third-party patching |
| **sys.settrace** | Interpreter trace callback | HEAD (call), TAIL (return) | Significant overhead | Debugging, coverage, temporary hooks |

---

## 1. AST Rewriting (default)

The default strategy. A `sys.meta_path` hook intercepts module imports, parses the source, and rewrites the AST before compilation.

### How it works

1. `MixinFinder` on `sys.meta_path` detects target module imports.
2. `MixinLoader.source_to_code` parses the module source into an AST.
3. `MixinTransformer` (an `ast.NodeTransformer`) walks the AST and injects callback dispatch code at each registered injection point.
4. The rewritten AST is compiled and executed — the original source is never modified on disk.

### Supported injection types

All 13: `HEAD`, `TAIL`, `PARAMETER`, `CONST`, `INVOKE`, `ATTRIBUTE`, `EXCEPTION`, `YIELD`, `ATTR_READ`, `LOOP`, `WITH`, `AWAIT`, `SUBSCRIPT`.

### Example

```python
import mixpy
from mixpy import mixin, inject, At, TYPE

@mixin(target="my_app.service.UserService")
class UserServicePatch:
    @inject(method="create_user", at=At(type=TYPE.HEAD))
    def log_creation(self, ci, *args, **kwargs):
        print(f"Creating user: {args}")

# Standard lifecycle: register → init → import target
mixpy.init()
from my_app.service import UserService
```

### When to use

- You want all 13 injection point types.
- Target modules are imported **after** `mixpy.init()`.
- You need zero runtime dispatch overhead (callbacks are woven directly into bytecode).

---

## 2. Monkey-Patch (`MonkeyPatchHook`)

Replaces functions and methods at runtime with thin wrappers that dispatch registered callbacks before and after the original code.

### How it works

1. `patch_method()` or `patch_function()` saves a reference to the original callable.
2. A wrapper function is installed in its place.
3. On each call, the wrapper fires HEAD callbacks, calls the original, then fires TAIL callbacks.
4. `unpatch_method()` / `unpatch_all()` restores originals.

### Supported injection types

- `HEAD` — fires before the original function body.
- `TAIL` — fires after the original returns (receives the return value).

### API

| Function | Description |
|---|---|
| `patch_method(cls, method_name, callback)` | Wrap a class method with a HEAD/TAIL callback |
| `patch_function(module, func_name, callback)` | Wrap a module-level function |
| `unpatch_method(cls, method_name)` | Restore the original class method |
| `unpatch_all()` | Restore all patched callables at once |

### Example

```python
from mixpy.hooks import MonkeyPatchHook

hook = MonkeyPatchHook()

# Patch a class method
def log_attack(ci, *args, **kwargs):
    print(f"Attack called with: {args}")

hook.patch_method(Player, "attack", log_attack)

# Use normally — wrapper fires automatically
player = Player("Hero")
player.attack(target)  # prints log, then runs original

# Patch a module-level function
def log_save(ci, *args, **kwargs):
    print(f"Saving game state...")

hook.patch_function(game_utils, "save_state", log_save)

# Clean up
hook.unpatch_method(Player, "attack")
hook.unpatch_all()  # or remove everything at once
```

### When to use

- You need to patch code that was imported **before** `mixpy.init()`.
- You are patching third-party libraries you don't control.
- You need to apply and remove patches dynamically at runtime.

---

## 3. sys.settrace (`SettraceHook`)

Uses Python's `sys.settrace` mechanism to intercept function call and return events at the interpreter level.

### How it works

1. `enable()` installs a trace function via `sys.settrace()`.
2. On every `"call"` event, registered `on_call` callbacks fire.
3. On every `"return"` event, registered `on_return` callbacks fire.
4. `disable()` removes the trace function and restores the previous one.

### Supported injection types

- `HEAD` — fires on `"call"` events (function entry).
- `TAIL` — fires on `"return"` events (function exit).

### API

| Method | Description |
|---|---|
| `on_call(func_filter, callback)` | Register a callback for function entry events |
| `on_return(func_filter, callback)` | Register a callback for function return events |
| `enable()` | Install the trace function via `sys.settrace` |
| `disable()` | Remove the trace function and restore the previous one |

### Example

```python
from mixpy.hooks import SettraceHook

hook = SettraceHook()

# Intercept calls to any function named "calculate_damage"
def trace_damage(frame, func_name):
    print(f"→ {func_name} called, locals: {frame.f_locals}")

hook.on_call("calculate_damage", trace_damage)

# Intercept returns from "calculate_damage"
def trace_damage_return(frame, func_name, return_value):
    print(f"← {func_name} returned {return_value}")

hook.on_return("calculate_damage", trace_damage_return)

# Activate tracing
hook.enable()

# ... run game logic — every matching call/return is traced ...
player.attack(enemy)

# Deactivate when done
hook.disable()
```

### Trade-offs

| Pro | Con |
|---|---|
| Works on **any** Python code, even C-extension wrappers | Significant performance overhead (trace fires on every call) |
| No import-time setup required | Only supports HEAD and TAIL (no fine-grained AST points) |
| Useful for temporary diagnostic hooks | Global effect — one `sys.settrace` handler at a time |

### When to use

- Debugging or profiling sessions where you need temporary interception.
- Coverage or tracing tools that must observe all function calls.
- Situations where neither AST rewriting nor monkey-patching is feasible.

---

## 4. HookStrategy Protocol & Registry

All three strategies conform to the `HookStrategy` protocol. You can manage them through `HookRegistry`.

### HookStrategy protocol

```python
from typing import Protocol

class HookStrategy(Protocol):
    @property
    def name(self) -> str:
        """Unique name identifying this strategy."""
        ...

    def activate(self) -> None:
        """Enable this hook strategy."""
        ...

    def deactivate(self) -> None:
        """Disable this hook strategy."""
        ...

    @property
    def is_active(self) -> bool:
        """Whether this strategy is currently active."""
        ...
```

### HookRegistry

The registry manages multiple strategies and ensures clean activation/deactivation.

```python
from mixpy.hooks import HookRegistry, MonkeyPatchHook, SettraceHook

registry = HookRegistry()

# Register strategies
mp_hook = MonkeyPatchHook()
st_hook = SettraceHook()

registry.register(mp_hook)
registry.register(st_hook)

# Activate a strategy by name
registry.activate("monkey_patch")

# Check status
print(registry.active_strategies)   # ["monkey_patch"]
print(mp_hook.is_active)            # True

# Activate multiple strategies simultaneously
registry.activate("settrace")
print(registry.active_strategies)   # ["monkey_patch", "settrace"]

# Deactivate one
registry.deactivate("settrace")

# Deactivate all
registry.deactivate_all()
```

### Combining strategies

You can use multiple strategies together. A common pattern is AST rewriting for your own code and monkey-patching for third-party dependencies:

```python
import mixpy
from mixpy.hooks import MonkeyPatchHook

# AST rewriting for your modules (default, activated by init)
import my_app.patches
mixpy.init()

# Monkey-patch for a third-party library already imported
hook = MonkeyPatchHook()
hook.patch_method(ThirdPartyClient, "send", my_interceptor)
```

---

## Choosing a strategy

```
Do you control the target's import order?
├── Yes → AST Rewriting (all 13 injection types, zero overhead)
└── No
    ├── Need to patch at runtime? → Monkey-Patch (HEAD/TAIL, low overhead)
    └── Need temporary tracing / debugging? → sys.settrace (HEAD/TAIL, high overhead)
```
