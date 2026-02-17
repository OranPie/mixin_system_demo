import pytest

from mixin_system.model import At, POLICY, TYPE
from mixin_system.registry import InjectorSpec
from mixin_system.transformer import MixinTransformer
from mixin_system.errors import MixinMatchError


def _spec(policy: POLICY, *, require=None, expect=None):
    def cb(self_obj, ci):
        return None

    cb.__qualname__ = f"cb_{policy.value.lower()}"
    return InjectorSpec(
        mixin_cls=None,
        callback=cb,
        method="tick",
        at=At(type=TYPE.HEAD, name=None),
        require=require,
        expect=expect,
        policy=policy,
    )


def test_require_mismatch_error_policy_raises():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.raises(MixinMatchError, match="require mismatch"):
        tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.ERROR, require=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_require_mismatch_warn_policy_only_warns(capsys):
    tr = MixinTransformer(module_name="demo", debug=False)
    tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.WARN, require=1), matched=0, expected=1, target="pkg.Target", method="tick")
    assert "require mismatch" in capsys.readouterr().out


def test_require_mismatch_ignore_policy_silent(capsys):
    tr = MixinTransformer(module_name="demo", debug=False)
    tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.IGNORE, require=1), matched=0, expected=1, target="pkg.Target", method="tick")
    assert capsys.readouterr().out == ""


def test_expect_mismatch_strict_policy_raises():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.raises(MixinMatchError, match="expect mismatch"):
        tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.STRICT, expect=2), matched=1, expected=2, target="pkg.Target", method="tick")


def test_expect_mismatch_error_policy_warns(capsys):
    tr = MixinTransformer(module_name="demo", debug=False)
    tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.ERROR, expect=2), matched=1, expected=2, target="pkg.Target", method="tick")
    assert "expect mismatch" in capsys.readouterr().out


def test_selector_enums_reject_invalid_policy_type():
    tr = MixinTransformer(module_name="demo", debug=False)
    spec = _spec(POLICY.ERROR)
    spec.policy = "ERROR"  # force bad type to ensure runtime validation
    with pytest.raises(TypeError, match="POLICY enum"):
        tr._policy(spec)
