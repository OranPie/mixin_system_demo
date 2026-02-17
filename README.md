# mixin_system_demo

A runnable reference implementation of an **import-time AST Mixin system** (Python), supporting:
- **AST transformation** on first import (via MetaPath import hook)
- **runtime injector dispatch** (wrapped callbacks + `CallbackInfo`)
- **selector-based matching** and **location constraints** (slice / near / anchor)

> This repo is designed to be easy to iterate on (small files, pytest tests, readable AST rewrites).

## Features

### Core injection types
- **HEAD**: function entry
- **TAIL**: all explicit returns + implicit tail
- **PARAMETER**: intercept/modify incoming args at entry
- **CONST**: intercept/replace `ast.Constant` values
- **INVOKE**: intercept a call site (supports `CallSelector`)
- **ATTRIBUTE**: intercept attribute writes (e.g. `self.health = value`)

### Selector (INVOKE)
`CallSelector` can constrain:
- function/method target (qualified parts)
- arg patterns (`ArgAny`, `ArgConst`, `ArgName`, `ArgAttr`)
- kwargs subset/exact (`KwPattern`)

### Location constraints
Location filters are applied **after matching**, before instrumentation:
- `ordinal`, `occurrence=FIRST|LAST|ALL`
- `slice=SliceSpec(from_anchor=?, to_anchor=?)` (**supports one-sided**)
- `near=NearSpec(anchor=..., max_distance=N)` (**statement distance**)
- `anchor=AnchorSpec(anchor=..., offset=..., inclusive=...)`

Ordering is based on **(statement index, intra-statement order)**.

## Run demo
From this folder:
```bash
python -m demo_game.run_demo
```

## Run tests
```bash
pytest -q
```

## Notes
- Condition DSL (`When` / `OP`) is enforced by runtime wrappers in `weave.py`.
- For simplicity, INVOKE selector matching ignores `**kwargs` in patterns (can be extended later).


## INVOKE kwargs / **kwargs policy
`CallSelector.starstar_policy`:
- `FAIL` (default): unresolved `**expr` => no match
- `IGNORE`: unresolved `**expr` allowed, but can't satisfy missing required keys
- `ASSUME_MATCH`: unresolved `**expr` allowed; for SUBSET, missing required keys may be assumed present

## Standardized runtime context (ctx)
Every injector sees `ci.get_context()` containing (when available):
- `type`, `target`, `method`, `at`
- `self`, `args`, `kwargs`, `locals`
- type-specific aliases: `value`, `return_value`, `param`, `attr`, `const_value`, `call_args`, `call_kwargs`


## Injector callback args
- **HEAD / TAIL / PARAMETER** dispatch now passes the function's runtime arguments to the injector callbacks, so you can write:
  - `def on_head(self, ci, x, **kw): ...`
  - `def on_tail(self, ci, x, **kw): ...`
- INVOKE passes call-site args/kwargs.
- CONST passes no extra args (use `ci.get_context()['value']`).
