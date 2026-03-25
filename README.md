# MixPy

**Import-time AST mixin injection for Python** — weave callbacks into classes *before* you even run them.

MixPy installs a `sys.meta_path` hook that rewrites Python source at import time. You describe *where* to inject behaviour (HEAD of a method, a specific CONST value, an INVOKE call-site …) and MixPy rewriters the AST so your callbacks run without modifying the original source.

```bash
pip install mixpy        # once published; or: PYTHONPATH=src python3 -m demo_game.run_demo
pytest -q                # run the full test suite
```

---

## Documentation

- Full usage guide: [`docs/library_usage.md`](docs/library_usage.md)
- Hook strategies: [`docs/hook_strategies.md`](docs/hook_strategies.md)
- C accelerator: [`docs/accelerator.md`](docs/accelerator.md)
- 中文文档：[`docs/library_usage_zh.md`](docs/library_usage_zh.md)

---

## Feature overview

### Hook strategies

MixPy offers three interception strategies — use one or combine them:

| Strategy | Mechanism | Injection types | Best for |
|---|---|---|---|
| **AST Rewriting** (default) | Import-time source transform | All 13 | Deterministic, zero-overhead interception |
| **Monkey-Patch** | Runtime function replacement | HEAD, TAIL | Post-init patching, third-party code |
| **sys.settrace** | Interpreter trace callback | HEAD, TAIL | Debugging, coverage, temporary hooks |

See [`docs/hook_strategies.md`](docs/hook_strategies.md) for API details and examples.

### Injection types (13)

| Type | Where it fires | Typical use |
|---|---|---|
| `HEAD` | Function entry | logging, auth checks, early-return |
| `TAIL` | Every `return` + implicit tail | result mutation, audit |
| `PARAMETER` | Per-parameter at entry | validation, clamping |
| `CONST` | `ast.Constant` expression | feature-flags, config overrides |
| `INVOKE` | Call-site interception | mock, redirect, retry |
| `ATTRIBUTE` | Attribute write (`self.x = v`) | invariant guards |
| `EXCEPTION` | `except` clause | fallback, error enrichment |
| `YIELD` | Each `yield` expression | stream transformation |
| `ATTR_READ` | Attribute read (`x = obj.attr`) | caching, lazy-load, access logging |
| `LOOP` | `for`/`while` entry and exit | iteration guards, metrics |
| `WITH` | Context manager enter/exit | resource tracking |
| `AWAIT` | `await` expressions | async interception, caching |
| `SUBSCRIPT` | `obj[key]` read/write | access control, proxy |

### Selector + location constraints

`CallSelector` narrows INVOKE matching by:
- function/method qualified name
- positional arg patterns (`ArgAny`, `ArgConst`, `ArgName`, `ArgAttr`)
- keyword patterns (`KwPattern.subset(...)` / `KwPattern.exact(...)`)
- `starstar_policy` for unresolved `**kwargs` (`FAIL` / `IGNORE` / `ASSUME_MATCH`)

Location filters let you target the *Nth* match, a slice between anchors, or only nodes *near* a given statement.

### New in this release

| Feature | Description |
|---|---|
| **Advanced selectors** | `ArgRegex`, `ArgTypeCheck`, `ArgExpr` for flexible argument matching; `AndPattern` / `OrPattern` / `NotPattern` for boolean composition; `WildcardSelector` for glob-style name matching |
| **Fluent builder API** | `At.invoke("print").first()`, `Loc.between(a, b)` — concise, chainable injection point construction |
| **C accelerator** | Optional `_accel` C extension for 2–5× faster runtime dispatch; pure-Python fallback is automatic. See [`docs/accelerator.md`](docs/accelerator.md) |
| **Performance** | AST index cache (`ast_index.py`) eliminates repeated `ast.walk()` calls; memoized trace flag and pre-compiled regex in runtime |

### Networking demo

`src/demo_game/network/` shows MixPy applied to simulated HTTP and socket clients:

- Block forbidden paths with a HEAD injector
- Fill empty POST bodies via PARAMETER
- Return 503 fallback responses via EXCEPTION
- Guard `socket.send()` against empty data

Run it:

```bash
PYTHONPATH=src python3 -m demo_game.run_demo --scenario net-http-block
PYTHONPATH=src python3 -m demo_game.run_demo --scenario net-socket-guard
```

---

## Quick-start

```python
import mixpy
from mixpy import mixin, inject, At, TYPE, Loc, When, OP

@mixin(target="my_game.player.Player")
class PlayerPatch:
    @inject(
        method="set_health",
        at=At(type=TYPE.PARAMETER, name="value",
              location=Loc(condition=When("value", OP.LT, 0))),
    )
    def clamp_health(self, ci, value, *args, **kwargs):
        ci.set_value(0)

# Register patches BEFORE init()
mixpy.init()

from my_game.player import Player  # weaving happens here
```

---

## Lifecycle (important)

1. Import patch modules (registers injectors into the global `REGISTRY`).
2. Call `mixpy.init()` — freezes registry, installs import hook.
3. Import target modules — weaving happens on first import.

Registering patches *after* `init()` raises a descriptive `RuntimeError` with a tip.

---

## Debug & observability

| Env var | Values | Effect |
|---|---|---|
| `MIXIN_DEBUG` | `True` | Dump weaved AST to `.weaved/` with header |
| `MIXIN_TRACE` | `True` | Log every injector invocation to `stderr` |
| `MIXPY_LOG_LEVEL` | `DEBUG` / `INFO` / `WARN` / `ERROR` | Filter `mixpy.log()` output |
| `FORCE_COLOR` | any | Force ANSI colour even in non-tty environments |

```python
mixpy.configure(debug=True, trace=True)
mixpy.log("INFO", "custom message")
```

---

## Run the demo

```bash
PYTHONPATH=src python3 -m demo_game.run_demo              # all scenarios
PYTHONPATH=src python3 -m demo_game.run_demo --list       # list scenario keys
PYTHONPATH=src python3 -m demo_game.run_demo --scenario invoke-redirect
```

## Run tests

```bash
pytest -q
pytest -q tests/test_demo.py -k invoke
pytest -q tests/test_network_demo.py
```

---

## INVOKE kwargs / `**kwargs` policy

`CallSelector.starstar_policy`:
- `FAIL` (default): unresolved `**expr` → no match
- `IGNORE`: unresolved `**expr` allowed; can't satisfy missing required keys
- `ASSUME_MATCH`: assume unresolved `**expr` covers any required kwargs

## Runtime context (`ci.get_context()`)

Every injector receives a `CallbackInfo` (`ci`) with:

```python
ctx = ci.get_context()
# common keys: type, target, method, at, self, args, kwargs, locals
# aliases: value, return_value, param, attr, const_value, call_args, call_kwargs, exception
```

### Key `ci` methods

| Method | Effect |
|---|---|
| `ci.cancel(result=x)` | Short-circuit; return `x` from the injection point |
| `ci.set_value(x)` | Mutate parameter / const / attribute without cancelling |
| `ci.set_return_value(x)` | TAIL: mutate return value, keep running subsequent injectors |
| `ci.call_original(*args, **kw)` | INVOKE only: call through to the original function |
| `ci.get_call_args()` / `ci.set_call_args(...)` | Inspect / rewrite INVOKE call arguments |
