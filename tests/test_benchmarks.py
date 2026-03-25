"""Benchmark test suite for mixpy hot-path functions.

Run with:  PYTHONPATH=src python3 -m pytest tests/test_benchmarks.py -v -s
"""
from __future__ import annotations

import ast
import time
from typing import Any, Dict, List

import pytest

from mixpy.model import TYPE, OP, When
from mixpy.runtime import (
    CallbackInfo,
    _eval_when,
    _resolve_path,
    dispatch_injectors,
    merge_kwargs,
)
from mixpy.selector import (
    ARGS_MODE,
    ArgAny,
    ArgConst,
    ArgName,
    CallSelector,
    KwPattern,
    QualifiedSelector,
    WildcardSelector,
)
from mixpy.ast_index import ASTIndex

benchmark = pytest.mark.benchmark

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITERATIONS = 10_000
AST_ITERATIONS = 1_000


def _timed(fn, iterations: int) -> float:
    """Run *fn* for *iterations* and return elapsed seconds."""
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    return time.perf_counter() - start


def _noop_callback(self_obj, ci, *args, **kwargs):
    """No-op injector callback."""
    pass


def _make_ci() -> CallbackInfo:
    return CallbackInfo(
        type=TYPE.HEAD,
        target="bench.Target",
        method="some_method",
        at_name="HEAD",
        trace_id="bench-0",
    )


# ---------------------------------------------------------------------------
# AST fixtures
# ---------------------------------------------------------------------------

_COMPLEX_FUNC_SRC = """\
def complex_function(a, b, c=10, d=None):
    x = a + b
    y = x * c
    if d is not None:
        y = y + d
    result = []
    for i in range(y):
        val = i ** 2
        if val > 100:
            result.append(val)
        elif val > 50:
            result.append(val // 2)
    total = sum(result)
    avg = total / max(len(result), 1)
    msg = "computed avg={:.2f}".format(avg)
    print(msg)
    data = {"total": total, "avg": avg, "items": result}
    processed = list(filter(lambda v: v > 60, result))
    final = sorted(processed, reverse=True)
    log_entry = str(final)
    print(log_entry)
    return data
"""


def _parse_func(src: str = _COMPLEX_FUNC_SRC) -> ast.FunctionDef:
    tree = ast.parse(src)
    return tree.body[0]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


@benchmark
def test_bench_selector_match():
    """Measure CallSelector.match() throughput across varying complexity."""
    # Simple: no constraints
    sel_simple = CallSelector()
    # Qualified function match
    sel_func = CallSelector(func=QualifiedSelector.of("self", "process"))
    # Args matching
    const_node = ast.Constant(value=42)
    name_node = ast.Name(id="x", ctx=ast.Load())
    sel_args = CallSelector(
        func=QualifiedSelector.of("math", "pow"),
        args=(ArgConst(42), ArgAny()),
        args_mode=ARGS_MODE.PREFIX,
    )
    # Wildcard + kwargs
    sel_wild = CallSelector(
        func=WildcardSelector.of("self.calc_*"),
        kwargs=KwPattern.subset(scale=ArgAny()),
    )
    # Complex: args + kwargs + wildcard
    sel_complex = CallSelector(
        func=WildcardSelector.of("*.process"),
        args=(ArgConst(42), ArgName("x")),
        args_mode=ARGS_MODE.EXACT,
        kwargs=KwPattern.subset(mode=ArgConst("fast")),
    )

    func_parts_match = ("self", "process")
    func_parts_calc = ("self", "calc_damage")
    func_parts_math = ("math", "pow")
    func_parts_obj = ("obj", "process")
    args_two = [const_node, name_node]
    kw_scale = {"scale": ast.Constant(value=1.5)}
    kw_mode = {"mode": ast.Constant(value="fast")}

    def run():
        sel_simple.match(func_parts_match, [const_node], {})
        sel_func.match(func_parts_match, [], {})
        sel_func.match(("other", "method"), [], {})
        sel_args.match(func_parts_math, args_two, {})
        sel_wild.match(func_parts_calc, [], kw_scale)
        sel_complex.match(func_parts_obj, args_two, kw_mode)

    elapsed = _timed(run, ITERATIONS)
    per_call = elapsed / (ITERATIONS * 6)
    print(f"\n  selector_match: {elapsed:.4f}s total, {per_call*1e6:.2f}µs/match ({ITERATIONS}×6 matches)")
    assert elapsed < 2.0, f"selector match too slow: {elapsed:.2f}s"


@benchmark
def test_bench_dispatch_latency():
    """Measure dispatch_injectors overhead with no-op callbacks."""
    callbacks: List = [_noop_callback, _noop_callback, _noop_callback]
    ctx: Dict[str, Any] = {"value": 42}

    def run():
        ci = _make_ci()
        dispatch_injectors(callbacks, ci, ctx, None)

    elapsed = _timed(run, ITERATIONS)
    per_dispatch = elapsed / ITERATIONS
    print(f"\n  dispatch_latency: {elapsed:.4f}s total, {per_dispatch*1e6:.2f}µs/dispatch ({ITERATIONS} iters, 3 callbacks)")
    assert elapsed < 2.0, f"dispatch too slow: {elapsed:.2f}s"


@benchmark
def test_bench_resolve_path():
    """Measure _resolve_path performance: simple vs dotted vs indexed."""
    ctx = {
        "x": 42,
        "self": type("Obj", (), {"attr": type("Inner", (), {"nested": 99})()})(),
        "args": [10, 20, 30],
    }

    def run_simple():
        _resolve_path(ctx, "x")

    def run_dotted():
        _resolve_path(ctx, "self.attr.nested")

    def run_indexed():
        _resolve_path(ctx, "args[0]")

    t_simple = _timed(run_simple, ITERATIONS)
    t_dotted = _timed(run_dotted, ITERATIONS)
    t_indexed = _timed(run_indexed, ITERATIONS)

    print(
        f"\n  resolve_path ({ITERATIONS} iters):"
        f"\n    simple key:    {t_simple:.4f}s ({t_simple/ITERATIONS*1e6:.2f}µs/call)"
        f"\n    dotted path:   {t_dotted:.4f}s ({t_dotted/ITERATIONS*1e6:.2f}µs/call)"
        f"\n    indexed path:  {t_indexed:.4f}s ({t_indexed/ITERATIONS*1e6:.2f}µs/call)"
        f"\n    dotted/simple: {t_dotted/max(t_simple, 1e-9):.1f}x"
    )
    assert t_simple < 2.0
    assert t_dotted < 2.0
    assert t_indexed < 2.0


@benchmark
def test_bench_eval_when():
    """Measure condition evaluation for simple and composite When nodes."""
    ctx = {"x": 42, "y": 10, "name": "hello", "items": [1, 2, 3]}

    cond_eq = When(left="x", op=OP.EQ, right=42)
    cond_gt = When(left="y", op=OP.GT, right=5)

    cond_and = When.and_(
        When(left="x", op=OP.GT, right=0),
        When(left="y", op=OP.LT, right=100),
        When(left="name", op=OP.EQ, right="hello"),
    )
    cond_or = When.or_(
        When(left="x", op=OP.EQ, right=99),
        When(left="y", op=OP.EQ, right=10),
        When(left="name", op=OP.EQ, right="world"),
    )

    def run_simple():
        _eval_when(cond_eq, ctx)
        _eval_when(cond_gt, ctx)

    def run_composite():
        _eval_when(cond_and, ctx)
        _eval_when(cond_or, ctx)

    t_simple = _timed(run_simple, ITERATIONS)
    t_composite = _timed(run_composite, ITERATIONS)

    print(
        f"\n  eval_when ({ITERATIONS} iters):"
        f"\n    simple (EQ+GT):     {t_simple:.4f}s ({t_simple/ITERATIONS*1e6:.2f}µs/pair)"
        f"\n    composite (AND+OR): {t_composite:.4f}s ({t_composite/ITERATIONS*1e6:.2f}µs/pair)"
        f"\n    composite/simple:   {t_composite/max(t_simple, 1e-9):.1f}x"
    )
    assert t_simple < 2.0
    assert t_composite < 2.0


@benchmark
def test_bench_merge_kwargs():
    """Measure merge_kwargs throughput for various dict sizes."""
    small_a = {"x": 1, "y": 2}
    small_b = {"z": 3}

    medium_a = {f"key_{i}": i for i in range(10)}
    medium_b = {f"val_{i}": i for i in range(10)}

    triple_a = {"a": 1, "b": 2}
    triple_b = {"c": 3, "d": 4}
    triple_c = {"e": 5, "f": 6}

    def run_small():
        merge_kwargs(small_a, small_b)

    def run_medium():
        merge_kwargs(medium_a, medium_b)

    def run_triple():
        merge_kwargs(triple_a, triple_b, triple_c)

    t_small = _timed(run_small, ITERATIONS)
    t_medium = _timed(run_medium, ITERATIONS)
    t_triple = _timed(run_triple, ITERATIONS)

    print(
        f"\n  merge_kwargs ({ITERATIONS} iters):"
        f"\n    2 small dicts:     {t_small:.4f}s ({t_small/ITERATIONS*1e6:.2f}µs/call)"
        f"\n    2 medium dicts:    {t_medium:.4f}s ({t_medium/ITERATIONS*1e6:.2f}µs/call)"
        f"\n    3 dicts:           {t_triple:.4f}s ({t_triple/ITERATIONS*1e6:.2f}µs/call)"
    )
    assert t_small < 2.0
    assert t_medium < 2.0
    assert t_triple < 2.0


@benchmark
def test_bench_ast_index_build():
    """Measure ASTIndex construction on a moderately complex function."""
    func_node = _parse_func()

    num_nodes = len(list(ast.walk(func_node)))
    print(f"\n  AST node count: {num_nodes}")

    def run():
        ASTIndex(func_node)

    elapsed = _timed(run, AST_ITERATIONS)
    per_build = elapsed / AST_ITERATIONS

    idx = ASTIndex(func_node)
    print(
        f"  ast_index_build ({AST_ITERATIONS} iters):"
        f"\n    total: {elapsed:.4f}s, {per_build*1e6:.2f}µs/build"
        f"\n    calls: {len(idx.all_calls)}, constants: {len(idx.all_constants)}, returns: {len(idx.all_returns)}"
    )
    assert elapsed < 2.0, f"ASTIndex build too slow: {elapsed:.2f}s"


@benchmark
def test_bench_accel_vs_python():
    """Compare C accelerator vs pure-Python dispatch paths."""
    from mixpy._dispatch import ACCEL_AVAILABLE

    if not ACCEL_AVAILABLE:
        pytest.skip("C accelerator not available")

    from mixpy._accel import fast_resolve_path as c_resolve
    from mixpy._accel import fast_eval_when as c_eval_when
    from mixpy._accel import fast_merge_kwargs as c_merge
    from mixpy.runtime import _resolve_path as py_resolve
    from mixpy.runtime import _eval_when as py_eval_when
    from mixpy.runtime import merge_kwargs as py_merge

    ctx = {
        "x": 42,
        "self": type("Obj", (), {"attr": type("Inner", (), {"nested": 99})()})(),
        "args": [10, 20, 30],
    }
    cond = When(left="x", op=OP.EQ, right=42)

    small_a = {"a": 1, "b": 2}
    small_b = {"c": 3, "d": 4}

    # resolve_path
    t_py_resolve = _timed(lambda: py_resolve(ctx, "self.attr.nested"), ITERATIONS)
    t_c_resolve = _timed(lambda: c_resolve(ctx, "self.attr.nested"), ITERATIONS)

    # eval_when — C version takes decomposed args
    t_py_when = _timed(lambda: py_eval_when(cond, ctx), ITERATIONS)
    t_c_when = _timed(lambda: c_eval_when(cond.left, cond.op.value, cond.right, ctx), ITERATIONS)

    # merge_kwargs
    t_py_merge = _timed(lambda: py_merge(small_a, small_b), ITERATIONS)
    t_c_merge = _timed(lambda: c_merge(small_a, small_b), ITERATIONS)

    print(
        f"\n  accel vs python ({ITERATIONS} iters):"
        f"\n    resolve_path:  C={t_c_resolve:.4f}s  Py={t_py_resolve:.4f}s  speedup={t_py_resolve/max(t_c_resolve, 1e-9):.1f}x"
        f"\n    eval_when:     C={t_c_when:.4f}s  Py={t_py_when:.4f}s  speedup={t_py_when/max(t_c_when, 1e-9):.1f}x"
        f"\n    merge_kwargs:  C={t_c_merge:.4f}s  Py={t_py_merge:.4f}s  speedup={t_py_merge/max(t_c_merge, 1e-9):.1f}x"
    )
    assert t_c_resolve < t_py_resolve * 5, "C path should not be drastically slower than Python"
