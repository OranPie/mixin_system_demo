import ast

import pytest

from mixpy.selector import (
    ARGS_MODE,
    KW_MODE,
    STARSTAR_POLICY,
    ArgAny,
    ArgAttr,
    ArgConst,
    ArgName,
    CallSelector,
    KwPattern,
    QualifiedSelector,
)


def parse_expr(src: str) -> ast.AST:
    return ast.parse(src, mode="eval").body


def test_argattr_matches_name_and_nested_attribute():
    assert ArgAttr.of("value").match(parse_expr("value"))
    assert ArgAttr.of("self", "player", "health").match(parse_expr("self.player.health"))
    assert not ArgAttr.of("self", "health").match(parse_expr("other.health"))


def test_callselector_exact_args_mode_requires_same_arity():
    selector = CallSelector(
        func=QualifiedSelector.of("self", "fn"),
        args=(ArgConst(1), ArgName("x")),
        args_mode=ARGS_MODE.EXACT,
    )

    assert selector.match(
        ("self", "fn"),
        [parse_expr("1"), parse_expr("x")],
        {},
    )
    assert not selector.match(
        ("self", "fn"),
        [parse_expr("1"), parse_expr("x"), parse_expr("3")],
        {},
    )


def test_callselector_fail_policy_rejects_unresolved_starstar_kwargs():
    selector = CallSelector(
        func=QualifiedSelector.of("self", "run"),
        args=(ArgAny(),),
        kwargs=KwPattern.subset(scale=ArgConst(3)),
        starstar_policy=STARSTAR_POLICY.FAIL,
    )

    assert not selector.match(
        ("self", "run"),
        [parse_expr("x")],
        {"scale": parse_expr("3")},
        has_unresolved_starstar=True,
    )


def test_callselector_assume_match_allows_missing_subset_kwarg_with_unknown_starstar():
    selector = CallSelector(
        func=QualifiedSelector.of("self", "run"),
        args=(ArgAny(),),
        kwargs=KwPattern.subset(scale=ArgConst(3)),
        starstar_policy=STARSTAR_POLICY.ASSUME_MATCH,
    )

    assert selector.match(
        ("self", "run"),
        [parse_expr("x")],
        {},
        has_unresolved_starstar=True,
    )


def test_callselector_exact_kwargs_uses_known_keys_when_starstar_unresolved():
    selector = CallSelector(
        func=QualifiedSelector.of("self", "run"),
        args=(ArgAny(),),
        kwargs=KwPattern.exact(scale=ArgConst(3)),
        starstar_policy=STARSTAR_POLICY.ASSUME_MATCH,
    )

    assert selector.match(
        ("self", "run"),
        [parse_expr("x")],
        {"scale": parse_expr("3")},
        has_unresolved_starstar=True,
    )


def test_selector_choices_require_enums_not_strings():
    with pytest.raises(TypeError, match="ARGS_MODE"):
        CallSelector(args_mode="EXACT")
    with pytest.raises(TypeError, match="STARSTAR_POLICY"):
        CallSelector(starstar_policy="FAIL")
    with pytest.raises(TypeError, match="KW_MODE"):
        KwPattern(items=(("scale", ArgConst(3)),), mode="SUBSET")
