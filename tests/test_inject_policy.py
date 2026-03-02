import warnings

import pytest

from mixpy.model import At, POLICY, TYPE
from mixpy.registry import InjectorSpec
from mixpy.transformer import MixinTransformer
from mixpy.errors import MixinMatchError


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


def test_require_mismatch_warn_policy_only_warns():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.warns(UserWarning, match="require mismatch"):
        tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.WARN, require=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_require_mismatch_ignore_policy_silent():
    tr = MixinTransformer(module_name="demo", debug=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        # IGNORE policy must not raise or warn
        tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.IGNORE, require=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_expect_mismatch_strict_policy_raises():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.raises(MixinMatchError, match="expect mismatch"):
        tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.STRICT, expect=2), matched=1, expected=2, target="pkg.Target", method="tick")


def test_expect_mismatch_error_policy_warns():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.warns(UserWarning, match="expect mismatch"):
        tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.ERROR, expect=2), matched=1, expected=2, target="pkg.Target", method="tick")


def test_require_mismatch_strict_policy_raises():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.raises(MixinMatchError, match="require mismatch"):
        tr._handle_count_mismatch(kind="require", spec=_spec(POLICY.STRICT, require=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_expect_mismatch_warn_policy_warns():
    tr = MixinTransformer(module_name="demo", debug=False)
    with pytest.warns(UserWarning, match="expect mismatch"):
        tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.WARN, expect=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_expect_mismatch_ignore_policy_silent():
    tr = MixinTransformer(module_name="demo", debug=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tr._handle_count_mismatch(kind="expect", spec=_spec(POLICY.IGNORE, expect=1), matched=0, expected=1, target="pkg.Target", method="tick")


def test_selector_enums_reject_invalid_policy_type():
    tr = MixinTransformer(module_name="demo", debug=False)
    spec = _spec(POLICY.ERROR)
    spec.policy = "ERROR"  # force bad type to ensure runtime validation
    with pytest.raises(TypeError, match="POLICY enum"):
        tr._policy(spec)
