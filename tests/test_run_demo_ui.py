import pytest

from demo_game import run_demo


def _scenario(key: str, actual: int, expected: int) -> run_demo.Scenario:
    return run_demo.Scenario(
        key=key,
        title=f"scenario {key}",
        run=lambda: [run_demo.Check(label=f"check {key}", actual=actual, expected=expected)],
    )


def test_select_scenarios_defaults_and_deduplicates_order():
    scenarios = [_scenario("one", 1, 1), _scenario("two", 1, 1)]

    default = run_demo.select_scenarios(scenarios, None)
    selected = run_demo.select_scenarios(scenarios, ["two", "one", "two"])

    assert [s.key for s in default] == ["one", "two"]
    assert [s.key for s in selected] == ["two", "one"]


def test_select_scenarios_rejects_unknown_key():
    scenarios = [_scenario("one", 1, 1)]

    with pytest.raises(ValueError, match=r"Unknown scenario key\(s\): missing"):
        run_demo.select_scenarios(scenarios, ["missing"])


def test_run_selected_scenarios_returns_summary_and_prints_statuses(capsys):
    scenarios = [_scenario("ok", 1, 1), _scenario("bad", 1, 2)]

    summary = run_demo.run_selected_scenarios(scenarios)
    out = capsys.readouterr().out

    assert summary.scenarios_run == 2
    assert summary.checks_total == 2
    assert summary.checks_failed == 1
    assert "[PASS]" in out
    assert "[FAIL]" in out
    assert "Summary: 1/2 checks passed" in out


def test_main_list_mode_does_not_bootstrap_runtime(monkeypatch, capsys):
    monkeypatch.setattr(run_demo, "bootstrap_runtime", lambda: (_ for _ in ()).throw(AssertionError("should not bootstrap")))

    code = run_demo.main(["--list"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Available scenarios:" in out


def test_main_returns_non_zero_when_any_check_fails(monkeypatch):
    monkeypatch.setattr(run_demo, "available_scenarios", lambda: [_scenario("fail", 1, 2)])
    monkeypatch.setattr(run_demo, "bootstrap_runtime", lambda: None)

    code = run_demo.main(["--scenario", "fail"])

    assert code == 1
