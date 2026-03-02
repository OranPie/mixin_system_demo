# Copilot Instructions

## Commands

```bash
PYTHONPATH=src python3 -m demo_game.run_demo              # run demo with all scenarios
PYTHONPATH=src python3 -m demo_game.run_demo --list       # list available scenario keys
PYTHONPATH=src python3 -m demo_game.run_demo --scenario invoke-redirect  # run one scenario
pytest -q                                  # full test suite
pytest -q tests/test_demo.py -k invoke    # run tests matching "invoke"
pytest -q tests/test_weave_unit.py        # run a single test file
```

No build step required — pure Python.

## Architecture

The system rewrites Python source **at import time** via a `sys.meta_path` hook:

1. **Registration phase** (before `mixpy.init()`): patch modules decorated with `@mixin` and `@inject` register `InjectorSpec` entries into a global `REGISTRY` singleton.
2. **Freeze**: `mixpy.init()` freezes the registry and installs `MixinFinder`/`MixinLoader` into `sys.meta_path`.
3. **Weave phase** (on first import of a target module): `MixinLoader.source_to_code` parses the source, runs `MixinTransformer` (an `ast.NodeTransformer`), which calls `handler.find()` → `apply_location()` → `handler.instrument()` per injection point per method.
4. **Runtime**: Instrumented code calls helpers in `runtime.py` (`eval_const`, `eval_invoke`, `eval_attr_write`, `dispatch_injectors`) which create a `CallbackInfo` (`ci`) object, evaluate `When`/`Loc` conditions, and invoke the registered callbacks.

**Critical ordering constraint**: patch modules must be imported before `mixpy.init()` is called. After `init()`, the registry is frozen and no new injectors can be registered.

### Key data flow

```
patches.py  →  @mixin/@inject  →  REGISTRY (InjectorSpec list)
                                         ↓ (frozen at init())
target import  →  MixinLoader  →  MixinTransformer  →  weaved AST
                                         ↓
                              runtime: dispatch_injectors → callbacks(ci)
```

### Module responsibilities

| Module | Role |
|---|---|
| `api.py` | Public decorators (`@mixin`, `@inject`) and `at_*`/`inject_*` shorthand builders |
| `model.py` | Core data types: `TYPE`, `At`, `Loc`, `When`, `OP`, `OCCURRENCE`, `POLICY` |
| `selector.py` | Structural AST matchers: `CallSelector`, `ArgAny/Const/Name/Attr`, `KwPattern`, `STARSTAR_POLICY` |
| `location.py` | Location constraint specs: `SliceSpec`, `NearSpec`, `AnchorSpec` |
| `location_utils.py` | Applies location filters to a list of candidate AST nodes |
| `registry.py` | `REGISTRY` singleton; stores and sorts `InjectorSpec` entries |
| `transformer.py` | `MixinTransformer` — visits `ClassDef`/`FunctionDef` AST nodes and orchestrates weaving |
| `handlers.py` / `builtin_handlers.py` | Per-type `find()` + `instrument()` logic for HEAD/TAIL/PARAMETER/CONST/INVOKE/ATTRIBUTE |
| `weave.py` | Builds the `__mixin_injectors__` map used at runtime for fast key lookup |
| `hook.py` | `MixinFinder` + `MixinLoader` — the `sys.meta_path` import hook |
| `runtime.py` | `CallbackInfo`, `dispatch_injectors`, `eval_const/invoke/attr_write`, `When` evaluator |
| `bootstrap.py` | Injects `__mixin_injectors__` into module globals before `exec_module` |

## Key Conventions

### Injection point types
Seven `TYPE` values exist: `HEAD`, `TAIL`, `PARAMETER`, `CONST`, `INVOKE`, `ATTRIBUTE`, `EXCEPTION`. Each has a dedicated handler. TAIL covers both explicit `return` statements and implicit function-end returns.

### Injector callback signatures
- HEAD/TAIL/PARAMETER: `def callback(self, ci, *method_args, **method_kwargs)`
- INVOKE: `def callback(self, ci, *call_site_args, **call_site_kwargs)`
- CONST: `def callback(self, ci)` — use `ci.get_context()['value']` or `ci.set_value(x)`
- ATTRIBUTE: `def callback(self, ci, value)`
- EXCEPTION: `def callback(self, ci)` — use `ci.get_context()['exception']`; `ci.cancel(result=x)` suppresses the exception

### `CallbackInfo` (`ci`) API
- `ci.cancel(result=x)` — skip original and return `x`; stops subsequent injectors
- `ci.set_value(x)` — replace parameter/const/attribute value (no cancellation)
- `ci.set_return_value(x)` — TAIL only: mutate return value without stopping subsequent injectors
- `ci.get_context()` — returns dict with `type`, `target`, `method`, `at`, `self`, `args`, `kwargs`, `locals`, plus type-specific aliases (`value`, `return_value`, `param`, `attr`, `const_value`, `call_args`, `call_kwargs`, `exception`)
- `ci.call_original(*args, **kwargs)` — INVOKE only; calls through to the original

### `When` condition DSL
Runtime conditions attach to `Loc(condition=When(...))`. Paths support dotted access and `[index]` notation (e.g., `"kwargs.scale"`, `"args[0]"`). Logical combinators: `When.and_()`, `When.or_()`, `When.not_()`. Length operators: `OP.LEN_EQ`, `OP.LEN_GT`, `OP.LEN_LT` apply `len()` to the resolved left value.

### `At` + `Loc` composition
`At` carries the injection type + target name + optional `selector` and `location`. `Loc` carries filtering constraints (`ordinal`, `occurrence`, `condition`, `slice`, `near`, `anchor`). All are frozen dataclasses — compose them, don't mutate.

### Priority and ordering
Injectors are sorted by `(mixin_priority, injector_priority, mixin_class_qualname, callback_qualname, registration_index)`. Lower values run first.

### `require` vs `expect`
- `require`: hard constraint on match count — triggers `POLICY.ERROR` if violated
- `expect`: soft advisory — triggers a warning even under `POLICY.ERROR`

### POLICY hierarchy
- `require` mismatches: `STRICT` / `ERROR` → raise `MixinMatchError`; `WARN` → warning; `IGNORE` → silent
- `expect` mismatches: `STRICT` → raise; `ERROR` / `WARN` → warning; `IGNORE` → silent

### Test isolation
`tests/conftest.py` performs one-time bootstrap (imports patches, calls `mixpy.init()`). Tests must not re-initialize the system. Assert observable behavior (return values, state) only — not AST structure.

### Multiple targets
`@mixin(target=["pkg.A", "pkg.B"])` registers one patch class against multiple targets.

### Module-level function injection
Target the module path directly: `@mixin(target="pkg.utils")` with `@inject(method="my_function", ...)`. The `self` argument in module-level callbacks is `None` (or the first parameter value — avoid relying on it).

### Observability
Set `MIXIN_TRACE=True` (or `mixpy.configure(trace=True)`) to log every injector invocation and cancellation to `stderr`. Set `MIXIN_DEBUG=True` to dump transformed AST to `__pycache__/mixin_dump/`.

### INVOKE `starstar_policy`
When a call site has unresolved `**expr` kwargs: `FAIL` (default) = no match; `IGNORE` = allow but can't satisfy missing keys; `ASSUME_MATCH` = assume unresolved `**expr` covers any required kwargs.

### Debug mode
Set `MIXIN_DEBUG=True` (or pass `debug=True` to `mixpy.init()`) to dump transformed AST to stdout during import.
