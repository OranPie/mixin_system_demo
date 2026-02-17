from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence, TextIO


@dataclass(frozen=True)
class Check:
    label: str
    actual: object
    expected: object

    @property
    def passed(self) -> bool:
        return self.actual == self.expected


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    run: Callable[[], list[Check]]


@dataclass(frozen=True)
class RunSummary:
    scenarios_run: int
    checks_total: int
    checks_failed: int


def bootstrap_runtime() -> None:
    os.environ.setdefault("MIXIN_DEBUG", "False")

    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import mixin_system
    import demo_game.patches  # noqa: F401  # ensures injectors are registered

    mixin_system.init()


def _scenario_attribute_guard() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    first = player.set_health(5)
    first_health = player.health
    second = player.set_health(-3)
    second_health = player.health
    return [
        Check("set_health(5)", first, 5),
        Check("health after set_health(5)", first_health, 5),
        Check("set_health(-3)", second, 0),
        Check("health after set_health(-3)", second_health, 0),
    ]


def _scenario_parameter_clamp() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    first = player.set_health2(7)
    first_health = player.health
    second = player.set_health2(-9)
    second_health = player.health
    return [
        Check("set_health2(7)", first, 7),
        Check("health after set_health2(7)", first_health, 7),
        Check("set_health2(-9)", second, 0),
        Check("health after set_health2(-9)", second_health, 0),
    ]


def _scenario_const_rewrite() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [Check("calculate_speed()", player.calculate_speed(), 3.0)]


def _scenario_invoke_redirect() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    player.is_in_space = False
    normal = player.update(3)
    player.is_in_space = True
    in_space = player.update(3)
    return [
        Check("update(3) normal", normal, 6),
        Check("update(3) in_space", in_space, 300),
    ]


def _scenario_anchor_second_call() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    player.is_in_space = False
    normal = player.two_calls(3)
    player.is_in_space = True
    in_space = player.two_calls(3)
    return [
        Check("two_calls(3) normal", normal, 12),
        Check("two_calls(3) in_space", in_space, 306),
    ]


def _scenario_slice_filters() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [
        Check("slice_demo(3)", player.slice_demo(3), 3.0),
        Check("slice_one_side(3)", player.slice_one_side(3), 6.0),
    ]


def _scenario_near_filter() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [Check("near_demo(3)", player.near_demo(3), 7.0)]


def _scenario_kwargs_policies() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [
        Check("kw_call_literal(2)", player.kw_call_literal(2), 999),
        Check("kw_call_unknown(2, {'scale': 3})", player.kw_call_unknown(2, {"scale": 3}), 888),
    ]


def _scenario_head_kwargs_condition() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [
        Check("accept_kwargs(2, scale=7)", player.accept_kwargs(2, scale=7), 7777),
        Check("accept_kwargs(2, scale=3)", player.accept_kwargs(2, scale=3), 6),
    ]


def _scenario_tail_implicit_return() -> list[Check]:
    from demo_game.game.player.player import Player

    player = Player(10)
    return [Check("do_nothing()", player.do_nothing(), 123)]


def available_scenarios() -> list[Scenario]:
    return [
        Scenario("attribute-guard", "ATTRIBUTE blocks negative writes", _scenario_attribute_guard),
        Scenario("parameter-clamp", "PARAMETER clamps negative input", _scenario_parameter_clamp),
        Scenario("const-rewrite", "CONST rewrites literal values", _scenario_const_rewrite),
        Scenario("invoke-redirect", "INVOKE redirects update call in space", _scenario_invoke_redirect),
        Scenario("anchor-second", "Anchor selects only second matched call", _scenario_anchor_second_call),
        Scenario("slice-filters", "Slice limits constant rewrites", _scenario_slice_filters),
        Scenario("near-filter", "Near constraint applies by statement distance", _scenario_near_filter),
        Scenario("kwargs-policies", "Selector kwargs + **kwargs policy behavior", _scenario_kwargs_policies),
        Scenario("head-kwargs", "HEAD condition can read kwargs", _scenario_head_kwargs_condition),
        Scenario("tail-implicit", "TAIL can override implicit return", _scenario_tail_implicit_return),
    ]


def _ordered_unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def select_scenarios(scenarios: Sequence[Scenario], keys: Sequence[str] | None) -> list[Scenario]:
    if not keys:
        return list(scenarios)

    scenario_map = {scenario.key: scenario for scenario in scenarios}
    requested = _ordered_unique(keys)
    unknown = [key for key in requested if key not in scenario_map]
    if unknown:
        available = ", ".join(sorted(scenario_map.keys()))
        raise ValueError(f"Unknown scenario key(s): {', '.join(unknown)}. Available keys: {available}")

    return [scenario_map[key] for key in requested]


def _print_header(scenarios: Sequence[Scenario], stream: TextIO) -> None:
    print("Mixin System Demo", file=stream)
    print(f"Running {len(scenarios)} scenario(s)...", file=stream)
    print("-" * 72, file=stream)


def run_selected_scenarios(scenarios: Sequence[Scenario], stream: TextIO | None = None) -> RunSummary:
    if stream is None:
        stream = sys.stdout

    checks_total = 0
    checks_failed = 0

    _print_header(scenarios, stream)
    for scenario in scenarios:
        print(f"[{scenario.key}] {scenario.title}", file=stream)
        for check in scenario.run():
            checks_total += 1
            status = "PASS" if check.passed else "FAIL"
            if not check.passed:
                checks_failed += 1
            print(
                f"  - [{status}] {check.label}: expected={check.expected!r}, actual={check.actual!r}",
                file=stream,
            )
        print(file=stream)

    passed = checks_total - checks_failed
    print("-" * 72, file=stream)
    print(
        f"Summary: {passed}/{checks_total} checks passed across {len(scenarios)} scenario(s).",
        file=stream,
    )
    return RunSummary(scenarios_run=len(scenarios), checks_total=checks_total, checks_failed=checks_failed)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run mixin demo scenarios with readable, structured output.")
    parser.add_argument("--list", action="store_true", help="List scenario keys and exit.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        metavar="KEY",
        help="Run only the given scenario key. Repeat for multiple scenarios.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    scenarios = available_scenarios()

    if args.list:
        print("Available scenarios:")
        for scenario in scenarios:
            print(f"  - {scenario.key}: {scenario.title}")
        return 0

    try:
        selected = select_scenarios(scenarios, args.scenarios)
    except ValueError as exc:
        parser.error(str(exc))

    bootstrap_runtime()
    summary = run_selected_scenarios(selected)
    return 1 if summary.checks_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
