# MixPy — Library Usage Guide

This guide explains how to use `mixpy` to inject behavior into Python classes at import time using AST rewriting.

## What the library does

`mixpy` installs a meta-path import hook. When a module is imported, it can rewrite matching class methods and weave injector callbacks into the method body.

Supported injection points:

- `HEAD` - function entry
- `TAIL` - explicit returns + implicit tail
- `PARAMETER` - parameter value interception at entry
- `CONST` - `ast.Constant` interception
- `INVOKE` - call-site interception
- `ATTRIBUTE` - attribute write interception

## Lifecycle (important)

1. Define mixin classes and injector methods.
2. Import the file(s) that register those mixins.
3. Call `mixpy.init()`.
4. Only then import and use target modules/classes.

`init()` freezes the registry. Registering new mixins after `init()` raises an error.

`init(debug=True)` is equivalent to setting `MIXIN_DEBUG=True` before initialization.

## Minimal example

```python
import mixpy
from mixpy import mixin, inject, At, TYPE, Loc, When, OP

@mixin(target="my_game.player.Player")
class PlayerPatch:
    @inject(
        method="set_health",
        at=At(type=TYPE.PARAMETER, name="value", location=Loc(condition=When("value", OP.LT, 0))),
    )
    def clamp_health(self, ci, value, *args, **kwargs):
        ci.set_value(0)

# register patches, then initialize
mixpy.init()

from my_game.player import Player
```

## Core decorators and models

### `@mixin(target="pkg.mod.Class")`
Registers a patch class against a fully-qualified target class path.

You can also pass a class object directly:

```python
@mixin(target=Player)
class PlayerPatch:
    ...
```

You can also set mixin-level ordering:

```python
@mixin(target="my_game.player.Player", priority=10)
class PlayerPatch:
    ...
```

### `@inject(method=..., at=..., priority=..., require=..., expect=...)`
- `method`: target method name on the target class.
- `at`: an `At(...)` object describing injection type and matching details.
- `priority`: lower values run earlier.
- `require`: strict expected match count; mismatch raises `MixinMatchError`.
- `expect`: expected match count.
- `policy`: `POLICY` enum controlling mismatch handling.

`policy` choices:

- `POLICY.ERROR` (default): `require` mismatch raises error; `expect` mismatch warns.
- `POLICY.WARN`: `require`/`expect` mismatch warns.
- `POLICY.IGNORE`: ignore both mismatch checks.
- `POLICY.STRICT`: both `require` and `expect` mismatch raise error.

### Ergonomic helpers (optional)

You can use builders instead of hand-writing `At(...)` each time:

- `at_head()`, `at_tail()`
- `at_parameter("value")`
- `at_const(1.0)`
- `at_invoke("self.call", selector=...)`
- `at_attribute("self.health")`

There are matching shortcut decorators:

- `@inject_head(method="...")`
- `@inject_tail(method="...")`
- `@inject_parameter(method="...", name="...")`
- `@inject_const(method="...", value=...)`
- `@inject_invoke(method="...", name="...", selector=...)`
- `@inject_attribute(method="...", name="...")`

### `At(type=TYPE..., name=..., selector=..., location=...)`
`name` meaning depends on `type`:
- `PARAMETER`: parameter name (for example `"value"`)
- `CONST`: literal value (for example `1.0`)
- `INVOKE`/`ATTRIBUTE`: dotted target name (for example `"self.calculate_physics"`)
- `HEAD`/`TAIL`: typically `None`

## Option matrix (choice -> effect)

### Target and init choices

| Choice | Effect |
| --- | --- |
| `@mixin(target="pkg.mod.Class")` | Direct string target; recommended when patch and target are in different modules/packages. |
| `@mixin(target=SomeClass)` | Auto-resolves to `module.qualname`; avoids typo in target path. |
| `@mixin(..., priority=N)` | Sets mixin-level ordering for one target (lower runs earlier). |
| `init(debug=True)` | Enables AST dump output (`__pycache__/mixin_dump/*.py`) for rewritten modules. |
| `init(debug=False)` or default | No AST dump output. |

Note: choice fields use enums (not raw strings). Passing string literals for enum fields raises `TypeError`.

### `inject(...)` choices

| Field | Choices | Effect |
| --- | --- | --- |
| `priority` | int (default `100`) | Lower runs earlier inside the same injection key `(target, method, type, at_name)`. |
| `require` | `None` or int | If set and actual match count differs, raises `MixinMatchError` and aborts transform. |
| `expect` | `None` or int | If set and debug enabled, prints warning on mismatch; does not abort. |
| `policy` | `POLICY.ERROR` / `WARN` / `IGNORE` / `STRICT` | Controls behavior when `require`/`expect` mismatch occurs. |

### `TYPE` behavioral choices

| `TYPE` | Where it runs | `cancel(...)` effect | `set_value(...)` effect |
| --- | --- | --- | --- |
| `HEAD` | Function entry | Returns provided result immediately. | No direct effect in current runtime. |
| `TAIL` | Every explicit/implicit return point | Overrides return value. | No direct effect in current runtime. |
| `PARAMETER` | Entry, per matched parameter | Returns immediately if cancelled. | Rebinds matched parameter before body continues. |
| `CONST` | Constant expression site | Replaces expression result with cancelled result. | Replaces constant value. |
| `INVOKE` | Intercepted call site | Replaces call result. | No direct effect; use call-arg APIs instead. |
| `ATTRIBUTE` | Attribute assignment write path | Replaces assigned value with cancelled result. | Rewrites assigned value. |

## Callback behavior (`CallbackInfo`)

Common methods:
- `ci.cancel(result=...)` - short-circuit and return result.
- `ci.set_value(...)` - replace current value (for points that support mutation).
- `ci.get_context()` - read normalized runtime context.
- `ci.call_original(*args, **kwargs)` - call original function (INVOKE only), optionally with overridden arguments.
- `ci.get_call_args()` / `ci.set_call_args(*args, **kwargs)` - inspect or rewrite INVOKE call arguments before execution.
- `ci.parameter_name`, `ci.get_parameter()`, `ci.set_parameter(...)` - parameter-oriented helpers for PARAMETER injectors.

If an injector calls `ci.call_original(...)` itself, runtime reuses that result and will not call the original function a second time.

Extra callback args by type:
- `HEAD` / `TAIL` / `PARAMETER`: target function args/kwargs
- `INVOKE`: intercepted call args/kwargs
- `ATTRIBUTE`: the new value being assigned
- `CONST`: no extra positional args (use context value)

### INVOKE call control choices

| Choice | Effect |
| --- | --- |
| `ci.get_call_args()` | Returns current `(args, kwargs)` that will be used for original call. |
| `ci.set_call_args(*args, **kwargs)` | Updates call args for subsequent injectors and final original call. |
| `ci.call_original()` | Calls original with current call args. |
| `ci.call_original(*args, **kwargs)` | Overrides call args then calls original immediately. |
| Injector calls `call_original(...)` and does not cancel | Runtime returns that captured result (no duplicate original invocation). |

## Conditions (`When` + `OP`)

Attach runtime predicates with `Loc(condition=When(...))`.

Example:

```python
Loc(condition=When("kwargs.scale", OP.EQ, 7))
```

Path resolution supports dotted access and index access (for example `"args[0]"`).

## Selectors for `INVOKE`

Use `CallSelector` for structural matching:

- `func=QualifiedSelector.of("self", "physics2")`
- positional arg patterns: `ArgAny`, `ArgConst`, `ArgName`, `ArgAttr`
- keyword matching: `KwPattern.subset(...)` or `KwPattern.exact(...)`
- `starstar_policy` for unresolved `**kwargs`:
  - `FAIL` (default)
  - `IGNORE`
  - `ASSUME_MATCH`

### Selector mode matrix

| Selector option | Choices | Effect |
| --- | --- | --- |
| `args_mode` | `ARGS_MODE.PREFIX` (default) | Call can have extra positional args after patterns. |
| `args_mode` | `ARGS_MODE.EXACT` | Call positional arg count must equal pattern count. |
| `KwPattern.mode` | `KW_MODE.SUBSET` | Required keyword patterns must exist and match (unless ASSUME_MATCH + unresolved `**kwargs`). |
| `KwPattern.mode` | `KW_MODE.EXACT` | Known kwargs key set must exactly match pattern key set. |
| `starstar_policy` | `STARSTAR_POLICY.FAIL` | Any unresolved `**expr` causes non-match. |
| `starstar_policy` | `STARSTAR_POLICY.IGNORE` | Unresolved `**expr` allowed; does not satisfy missing required keys. |
| `starstar_policy` | `STARSTAR_POLICY.ASSUME_MATCH` | For `SUBSET`, missing required keys may be assumed present when unresolved `**expr` exists; `EXACT` behaves like `IGNORE`. |

## Location constraints

Add `location=Loc(...)` to narrow matched nodes:

- `ordinal` and `occurrence` (`FIRST`, `LAST`, `ALL`)
- `slice=SliceSpec(from_anchor=..., to_anchor=...)` (one-sided supported)
- `near=NearSpec(anchor=..., max_distance=N)` (statement distance)
- `anchor=AnchorSpec(anchor=..., offset=..., inclusive=...)`

Filtering order is: `slice -> near -> anchor -> occurrence -> ordinal`.

### Location option matrix

| Option | Choices | Effect |
| --- | --- | --- |
| `occurrence` | `OCCURRENCE.ALL` (default) | Keep all matches after earlier filters. |
| `occurrence` | `OCCURRENCE.FIRST` | Keep first ordered match only. |
| `occurrence` | `OCCURRENCE.LAST` | Keep last ordered match only. |
| `ordinal` | `None` or int | Pick match by 0-based index after occurrence filter. |
| `slice.from_anchor` / `slice.to_anchor` | `At` or `None` | Supports one-sided ranges (start-only or end-only). |
| `slice.include_from` / `slice.include_to` | bool | Include/exclude anchor boundary in range checks. |
| `near.max_distance` | int | Statement-distance bound around anchor statement. |
| `anchor.offset` | `>=0` or `<0` | Positive walks forward from anchor; negative walks backward. |
| `anchor.inclusive` | bool | Include anchor position itself when selecting relative match. |

## Debugging and inspection

Set:

```bash
MIXIN_DEBUG=True
```

The transformed source is dumped under `__pycache__/mixin_dump/`.

## Error model and runtime notes

- `MixinMatchError`: raised during transform when `require` does not match actual hits.
- `RuntimeError` (registry frozen): registering mixins/injectors after `init()` is blocked.
- `RuntimeError` from `call_original`/`set_call_args`: thrown when used outside `INVOKE`.
- `TypeError` from `merge_kwargs`: duplicate keyword keys while merging explicit kwargs and `**kwargs`.
- Import hook recompiles from source on load so AST weaving logic changes apply consistently even if old bytecode exists.

## Multiple mixins on one target (resolver rules)

When many mixins inject into the same target method, execution order is deterministic:

1. `mixin priority` (from `@mixin(..., priority=...)`, ascending)
2. injector `priority` (from `@inject(..., priority=...)`, ascending)
3. mixin class path (lexicographic)
4. callback qualname (lexicographic)
5. registration index (earlier registration first)

This allows coarse ordering at mixin level and fine ordering per injector inside each mixin.

## Practical tips

- Keep patch registration in a dedicated module (for example `demo_game/patches.py`).
- Make injectors side-effect-light and deterministic.
- Add regression tests per injector behavior and per selector/location edge case.
- If a patch appears ignored, verify import order: targets imported before `init()` are not rewritten.

---

## Networking use-case demo

MixPy ships with a networking example in `src/demo_game/network/`. It demonstrates all major injection types against simulated HTTP and socket clients — **no real network I/O** is performed.

### Scenarios

| Scenario key | What it demonstrates |
|---|---|
| `net-http-block` | `HEAD` injector blocks requests to `/blocked` → returns 403 |
| `net-http-body` | `PARAMETER` injector fills an empty POST body with `"{}"` |
| `net-http-exception` | `EXCEPTION` injector catches `ConnectionError` → returns 503 |
| `net-socket-guard` | `PARAMETER` + `EXCEPTION` guard `SocketClient.send()` |

```bash
PYTHONPATH=src python3 -m demo_game.run_demo --scenario net-http-block
```

---

## Debug and observability

### Log levels

Set `MIXPY_LOG_LEVEL` to control output verbosity:

```bash
MIXPY_LOG_LEVEL=DEBUG MIXIN_TRACE=True python3 ...
```

| Level | Shows |
|---|---|
| `DEBUG` | Full injector trace (same as `MIXIN_TRACE=True`) |
| `INFO` | AST dump notifications, config changes |
| `WARN` | `require`/`expect` mismatches (default) |
| `ERROR` | Fatal weaving errors only |

### Programmatic logging

```python
import mixpy
mixpy.log("INFO", "Patch loaded for Player.set_health")
```

### ANSI colour

Colour is emitted automatically when `sys.stderr` is a TTY. Override with:
```bash
FORCE_COLOR=1 MIXIN_TRACE=True python3 -m demo_game.run_demo
```
