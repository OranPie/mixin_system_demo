def compute_bonus(base: int, multiplier: float=1.0) -> float:
    _mixin_inj_param_multiplier = __mixin_injectors__.get(('demo_game.utils', 'compute_bonus', 'PARAMETER', 'multiplier'), [])
    if _mixin_inj_param_multiplier:
        _mixin_ci_param_multiplier = mixin_system_runtime.CallbackInfo(type=mixin_system_model.TYPE.PARAMETER, target='demo_game.utils', method='compute_bonus', at_name='multiplier', trace_id=str(mixin_system_runtime.time.time_ns()))
        mixin_system_runtime.dispatch_injectors(_mixin_inj_param_multiplier, _mixin_ci_param_multiplier, {'self': base, 'args': [base, multiplier], 'kwargs': {}, 'locals': locals(), 'param': 'multiplier', 'value': multiplier}, base, base, multiplier)
        if _mixin_ci_param_multiplier.is_cancelled:
            return _mixin_ci_param_multiplier.result
        if _mixin_ci_param_multiplier.value_set:
            multiplier = _mixin_ci_param_multiplier.new_value
    return base * multiplier