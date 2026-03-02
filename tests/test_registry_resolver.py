from mixpy.model import At, TYPE
from mixpy.registry import InjectorSpec, Registry


def _cb(name):
    def fn(*args, **kwargs):
        return name

    fn.__name__ = name
    fn.__qualname__ = name
    return fn


def test_multiple_mixins_same_target_are_ordered_by_mixin_then_injector_priority():
    registry = Registry()

    class MixA:
        pass

    class MixB:
        pass

    registry.register_mixin("pkg.Target", MixA, priority=10)
    registry.register_mixin("pkg.Target", MixB, priority=1)

    at = At(type=TYPE.HEAD, name=None)
    spec_a = InjectorSpec(mixin_cls=MixA, callback=_cb("a"), method="tick", at=at, priority=1)
    spec_b = InjectorSpec(mixin_cls=MixB, callback=_cb("b"), method="tick", at=at, priority=50)
    spec_c = InjectorSpec(mixin_cls=MixB, callback=_cb("c"), method="tick", at=at, priority=5)

    registry.register_injector("pkg.Target", spec_a)
    registry.register_injector("pkg.Target", spec_b)
    registry.register_injector("pkg.Target", spec_c)

    ordered = registry.get_injectors("pkg.Target", "tick")
    assert [s.callback.__name__ for s in ordered] == ["c", "b", "a"]
    assert [s.mixin_priority for s in ordered] == [1, 1, 10]


def test_registration_index_breaks_ties_stably_for_same_mixin_and_priority():
    registry = Registry()

    class Mix:
        pass

    registry.register_mixin("pkg.Target", Mix, priority=3)
    at = At(type=TYPE.HEAD, name=None)

    first = InjectorSpec(mixin_cls=Mix, callback=_cb("same"), method="tick", at=at, priority=7)
    second = InjectorSpec(mixin_cls=Mix, callback=_cb("same"), method="tick", at=at, priority=7)

    registry.register_injector("pkg.Target", first)
    registry.register_injector("pkg.Target", second)

    ordered = registry.get_injectors("pkg.Target", "tick")
    assert [s.registration_index for s in ordered] == sorted(s.registration_index for s in ordered)


def test_mixin_list_target_registers_against_all_targets():
    from mixpy.api import mixin, inject
    from mixpy.model import At, TYPE
    from mixpy.registry import Registry
    import mixpy.api as api_mod

    # Use a fresh Registry to avoid polluting global state
    original = api_mod.REGISTRY
    fresh = Registry()
    api_mod.REGISTRY = fresh
    try:
        @mixin(target=["pkg.A", "pkg.B"])
        class MultiPatch:
            @inject(method="tick", at=At(type=TYPE.HEAD, name=None))
            def on_tick(self, ci):
                pass

        assert fresh.get_injectors("pkg.A", "tick")
        assert fresh.get_injectors("pkg.B", "tick")
        assert not fresh.get_injectors("pkg.C", "tick")
    finally:
        api_mod.REGISTRY = original
