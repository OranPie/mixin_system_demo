import mixin_system
from mixin_system import (
    mixin, inject, At, TYPE, OP, Loc, When, OCCURRENCE,
    CallSelector, QualifiedSelector, ArgAny, ArgConst,
    SliceSpec, AnchorSpec, NearSpec, KwPattern, STARSTAR_POLICY,
    at_exception,
)

@mixin(target="demo_game.game.player.player.Player")
class PlayerCombatPatch:
    @inject(method="set_health", at=At(type=TYPE.ATTRIBUTE, name="self.health", location=Loc(condition=When("value", OP.LT, 0))))
    def prevent_negative_health(self, ci, value):
        ci.cancel(result=0)

    @inject(method="set_health2", at=At(type=TYPE.PARAMETER, name="value", location=Loc(condition=When("value", OP.LT, 0))))
    def clamp_health_param(self, ci, value, *args, **kw):
        ci.set_value(0)

    @inject(method="calculate_speed", at=At(type=TYPE.CONST, name=1.0))
    def buff_base_speed(self, ci):
        ci.set_value(1.5)

    @inject(
        method="update",
        at=At(
            type=TYPE.INVOKE,
            name="self.calculate_physics",
            selector=CallSelector(func=QualifiedSelector.of("self","calculate_physics"), args=(ArgAny(),))
        )
    )
    def redirect_physics(self, ci, x):
        if self.is_in_space:
            ci.cancel(result=self.custom_space_physics(x))

    @inject(
        method="two_calls",
        at=At(
            type=TYPE.INVOKE,
            name="self.calculate_physics",
            selector=CallSelector(func=QualifiedSelector.of("self","calculate_physics"), args=(ArgAny(),)),
            location=Loc(
                anchor=AnchorSpec(
                    anchor=At(type=TYPE.INVOKE, name="self.calculate_physics", location=Loc(ordinal=0)),
                    offset=0,
                    inclusive=False
                )
            )
        )
    )
    def redirect_second_call_only(self, ci, x):
        if self.is_in_space:
            ci.cancel(result=self.custom_space_physics(x))

    @inject(
        method="slice_demo",
        at=At(
            type=TYPE.CONST,
            name=1.0,
            location=Loc(
                slice=SliceSpec(
                    from_anchor=At(type=TYPE.INVOKE, name="self.calculate_physics", location=Loc(ordinal=0)),
                    to_anchor=At(type=TYPE.INVOKE, name="self.calculate_physics", location=Loc(ordinal=1)),
                )
            )
        )
    )
    def slice_only_first_const(self, ci):
        ci.set_value(2.0)

    @inject(
        method="slice_one_side",
        at=At(
            type=TYPE.CONST,
            name=1.0,
            location=Loc(
                slice=SliceSpec(
                    from_anchor=At(type=TYPE.INVOKE, name="self.calculate_physics", location=Loc(ordinal=0)),
                    to_anchor=None
                )
            )
        )
    )
    def slice_from_invoke_to_end(self, ci):
        ci.set_value(3.0)

    @inject(
        method="near_demo",
        at=At(
            type=TYPE.CONST,
            name=1.0,
            location=Loc(
                near=NearSpec(anchor=At(type=TYPE.INVOKE, name="self.calculate_physics"), max_distance=1),
                occurrence=OCCURRENCE.FIRST
            )
        )
    )
    def near_const_after_invoke(self, ci):
        ci.set_value(5.0)

    # --- INVOKE kwargs strategy tests ---

    @inject(
        method="kw_call_literal",
        at=At(
            type=TYPE.INVOKE,
            name="self.physics2",
            selector=CallSelector(
                func=QualifiedSelector.of("self","physics2"),
                args=(ArgAny(),),
                kwargs=KwPattern.subset(scale=ArgConst(3)),
                starstar_policy=STARSTAR_POLICY.FAIL,
            ),
            location=Loc(condition=When("kwargs.scale", OP.EQ, 3))
        )
    )
    def kw_literal_redirect(self, ci, x, **kw):
        ci.cancel(result=999)

    @inject(
        method="kw_call_unknown",
        at=At(
            type=TYPE.INVOKE,
            name="self.physics2",
            selector=CallSelector(
                func=QualifiedSelector.of("self","physics2"),
                args=(ArgAny(),),
                kwargs=KwPattern.subset(scale=ArgConst(3)),
                starstar_policy=STARSTAR_POLICY.FAIL,
            )
        )
    )
    def kw_unknown_strict(self, ci, x, **kw):
        ci.cancel(result=777)  # should never happen

    @inject(
        method="kw_call_unknown",
        at=At(
            type=TYPE.INVOKE,
            name="self.physics2",
            selector=CallSelector(
                func=QualifiedSelector.of("self","physics2"),
                args=(ArgAny(),),
                kwargs=KwPattern.subset(scale=ArgConst(3)),
                starstar_policy=STARSTAR_POLICY.ASSUME_MATCH,
            )
        )
    )
    def kw_unknown_assume(self, ci, x, **kw):
        ci.cancel(result=888)

    # --- HEAD ctx standardization test ---
    @inject(
        method="accept_kwargs",
        at=At(type=TYPE.HEAD, name=None, location=Loc(condition=When("kwargs.scale", OP.EQ, 7)))
    )
    def head_sees_kwargs(self, ci, x, **kw):
        ci.cancel(result=7777)

    @inject(method="do_nothing", at=At(type=TYPE.TAIL, name=None))
    def override_implicit_return(self, ci, *args, **kw):
        ci.cancel(result=123)

    @inject(method="async_speed", at=At(type=TYPE.CONST, name=1.0))
    def buff_async_base_speed(self, ci):
        ci.set_value(2.5)

    @inject(method="score", at=At(type=TYPE.TAIL, name=None), priority=10)
    def double_score(self, ci, *args, **kw):
        ci.set_return_value(ci.get_context().get("return_value", 0) * 2)

    @inject(method="score", at=At(type=TYPE.TAIL, name=None), priority=20)
    def add_bonus(self, ci, *args, **kw):
        # runs after double_score because priority=20 > 10; set_return_value lets this run
        current = ci.new_value if ci.value_set else ci.get_context().get("return_value", 0)
        ci.set_return_value(current + 1)

    @inject(method="risky_divide", at=at_exception())
    def handle_divide_error(self, ci):
        exc = ci.get_context().get("exception")
        if isinstance(exc, ZeroDivisionError):
            ci.cancel(result=-1)


@mixin(target="demo_game.utils")
class UtilsPatch:
    @inject(method="compute_bonus", at=At(type=TYPE.PARAMETER, name="multiplier"))
    def clamp_multiplier(self, ci, *args, **kw):
        if ci.get_context().get("value", 0) > 10:
            ci.set_value(10.0)
