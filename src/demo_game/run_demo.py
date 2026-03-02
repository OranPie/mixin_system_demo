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

    src = pathlib.Path(__file__).resolve().parents[2]
    for p in (str(src), str(src.parent)):
        if p not in sys.path:
            sys.path.insert(0, p)

    import mixpy
    import demo_game.patches  # noqa: F401  # ensures injectors are registered
    import demo_game.network.patches  # noqa: F401  # networking injectors

    mixpy.init()


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


# ---------------------------------------------------------------------------
# Networking scenarios
# ---------------------------------------------------------------------------

def _scenario_http_head_block() -> list[Check]:
    from demo_game.network.client import HTTPClient

    client = HTTPClient()
    r_ok = client.get("/api/data")
    r_blocked = client.get("/blocked")
    return [
        Check("GET /api/data → 200", r_ok.status, 200),
        Check("GET /blocked → 403 (injected)", r_blocked.status, 403),
        Check("GET /blocked body", r_blocked.body, "Forbidden"),
    ]


def _scenario_http_param_default_body() -> list[Check]:
    from demo_game.network.client import HTTPClient

    client = HTTPClient()
    r_empty = client.post("/api/items", body="")
    r_full = client.post("/api/items", body='{"name":"x"}')
    return [
        Check("POST empty body becomes '{}'", r_empty.body, 'POST http://example.com/api/items -> {}'),
        Check("POST non-empty body unchanged", r_full.body, 'POST http://example.com/api/items -> {"name":"x"}'),
    ]


def _scenario_http_exception_fallback() -> list[Check]:
    from demo_game.network.client import HTTPClient, Response

    # Override get so fetch triggers ConnectionError (to exercise EXCEPTION injection)
    class _BrokenHTTPClient(HTTPClient):
        def get(self, path: str, headers=None) -> Response:  # type: ignore[override]
            raise ConnectionError("simulated failure")

    client = _BrokenHTTPClient()
    r = client.fetch("/api/data")
    return [
        Check("fetch() fallback on ConnectionError → 503", r.status, 503),
    ]


def _scenario_socket_send_guard() -> list[Check]:
    from demo_game.network.client import SocketClient

    sock = SocketClient()
    sock.connect()
    n = sock.send(b"hello")

    try:
        sock.send(b"")
        caught = False
    except ValueError:
        caught = True

    return [
        Check("send(b'hello') → len 5", n, 5),
        Check("send(b'') raises ValueError (injected)", caught, True),
    ]


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
        # Networking demos
        Scenario("net-http-block", "HEAD blocks specific HTTP path", _scenario_http_head_block),
        Scenario("net-http-body", "PARAMETER fills empty POST body", _scenario_http_param_default_body),
        Scenario("net-http-exception", "EXCEPTION fallback on connection failure", _scenario_http_exception_fallback),
        Scenario("net-socket-guard", "PARAMETER + EXCEPTION guard socket.send()", _scenario_socket_send_guard),
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
    print("MixPy Demo", file=stream)
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
