# Repository Guidelines

## Project Structure & Module Organization
- `mixin_system/` contains the core AST mixin engine (API, import hook, transformer, runtime dispatch, selectors, and location logic).
- `demo_game/` is the runnable example target; `demo_game/patches.py` defines mixins/injectors and `demo_game/run_demo.py` starts the demo.
- `tests/` contains pytest coverage for end-to-end behavior (`test_demo.py`) and bootstrap setup (`conftest.py`).
- Keep new core features in `mixin_system/` and validate them through demo-facing tests rather than ad hoc scripts.

## Build, Test, and Development Commands
- `python -m demo_game.run_demo` — run the sample game with mixins registered.
- `pytest -q` — run the full test suite quietly.
- `pytest -q tests/test_demo.py -k invoke` — run a focused subset while iterating on INVOKE logic.
- No separate build step is required; this repository is pure Python.

## Coding Style & Naming Conventions
- Follow PEP 8 defaults: 4-space indentation, snake_case for functions/variables, PascalCase for classes.
- Keep modules small and single-purpose (this codebase favors readable, composable files).
- Prefer explicit typing where helpful (`X | None`, `Callable`, dataclasses) to match existing code.
- Name mixin classes clearly by target/domain (example: `PlayerCombatPatch`).

## Testing Guidelines
- Use `pytest` with test files named `test_*.py` and test functions named `test_*`.
- Add regression tests for every new injection behavior (HEAD/TAIL/PARAMETER/CONST/INVOKE/ATTRIBUTE) and selector/location edge case.
- Assert observable behavior only (return values, state changes), not AST internals.
- Keep tests deterministic and isolated; rely on `tests/conftest.py` for one-time initialization.

## Commit & Pull Request Guidelines
- This snapshot does not include `.git` metadata; use Conventional Commit style for consistency (e.g., `feat: add near-anchor invoke filter`, `fix: handle implicit tail return`).
- Keep commits focused to one behavior change plus tests.
- PRs should include: concise problem statement, approach summary, test evidence (`pytest -q` output), and any demo impact notes.
- Link related issues and include before/after behavior examples when patch semantics change.

## Architecture Notes
- The runtime depends on import-time weaving; ensure patches are imported before `mixin_system.init()`.
- Registry freezing is intentional for deterministic execution; avoid mutable global side effects after initialization.
