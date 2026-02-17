# Library Usage Guide

This guide explains how to use `mixin_system` to inject behavior into Python classes at import time using AST rewriting.

## What the library does

`mixin_system` installs a meta-path import hook. When a module is imported, it can rewrite matching class methods and weave injector callbacks into the method body.

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
3. Call `mixin_system.init()`.
4. Only then import and use target modules/classes.

`init()` freezes the registry. Registering new mixins after `init()` raises an error.

## Minimal example

```python
import mixin_system
from mixin_system import mixin, inject, At, TYPE, Loc, When, OP

@mixin(target="my_game.player.Player")
class PlayerPatch:
    @inject(
        method="set_health",
        at=At(type=TYPE.PARAMETER, name="value", location=Loc(condition=When("value", OP.LT, 0))),
    )
    def clamp_health(self, ci, value, *args, **kwargs):
        ci.set_value(0)

# register patches, then initialize
mixin_system.init()

from my_game.player import Player
```

## Core decorators and models

### `@mixin(target="pkg.mod.Class")`
Registers a patch class against a fully-qualified target class path.

### `@inject(method=..., at=..., priority=..., require=..., expect=...)`
- `method`: target method name on the target class.
- `at`: an `At(...)` object describing injection type and matching details.
- `priority`: lower values run earlier.
- `require`: strict expected match count; mismatch raises `MixinMatchError`.
- `expect`: warning-only count check when `MIXIN_DEBUG=True`.

`policy` exists in the API but is currently a placeholder in this demo implementation.

### `At(type=TYPE..., name=..., selector=..., location=...)`
`name` meaning depends on `type`:
- `PARAMETER`: parameter name (for example `"value"`)
- `CONST`: literal value (for example `1.0`)
- `INVOKE`/`ATTRIBUTE`: dotted target name (for example `"self.calculate_physics"`)
- `HEAD`/`TAIL`: typically `None`

## Callback behavior (`CallbackInfo`)

Common methods:
- `ci.cancel(result=...)` - short-circuit and return result.
- `ci.set_value(...)` - replace current value (for points that support mutation).
- `ci.get_context()` - read normalized runtime context.
- `ci.call_original()` - available for `INVOKE` injectors.

Extra callback args by type:
- `HEAD` / `TAIL` / `PARAMETER`: target function args/kwargs
- `INVOKE`: intercepted call args/kwargs
- `ATTRIBUTE`: the new value being assigned
- `CONST`: no extra positional args (use context value)

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

## Location constraints

Add `location=Loc(...)` to narrow matched nodes:

- `ordinal` and `occurrence` (`FIRST`, `LAST`, `ALL`)
- `slice=SliceSpec(from_anchor=..., to_anchor=...)` (one-sided supported)
- `near=NearSpec(anchor=..., max_distance=N)` (statement distance)
- `anchor=AnchorSpec(anchor=..., offset=..., inclusive=...)`

Filtering order is: `slice -> near -> anchor -> occurrence -> ordinal`.

## Debugging and inspection

Set:

```bash
MIXIN_DEBUG=True
```

The transformed source is dumped under `__pycache__/mixin_dump/`.

## Practical tips

- Keep patch registration in a dedicated module (for example `demo_game/patches.py`).
- Make injectors side-effect-light and deterministic.
- Add regression tests per injector behavior and per selector/location edge case.
- If a patch appears ignored, verify import order: targets imported before `init()` are not rewritten.
