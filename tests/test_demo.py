from demo_game.game.player.player import Player

def test_attribute_condition_blocks_negative_write():
    p = Player(10)
    assert p.set_health(5) == 5
    assert p.health == 5
    assert p.set_health(-3) == 0
    assert p.health == 0

def test_parameter_clamp_on_entry():
    p = Player(10)
    assert p.set_health2(7) == 7
    assert p.health == 7
    assert p.set_health2(-9) == 0
    assert p.health == 0

def test_const_replacement():
    p = Player(10)
    assert p.calculate_speed() == 3.0

def test_invoke_redirect_with_selector_patterns():
    p = Player(10)
    p.is_in_space = False
    assert p.update(3) == 6
    p.is_in_space = True
    assert p.update(3) == 300

def test_location_anchor_selects_second_call_only():
    p = Player(10)
    p.is_in_space = False
    assert p.two_calls(3) == 12
    p.is_in_space = True
    assert p.two_calls(3) == 306

def test_location_slice_limits_const_rewrite():
    p = Player(10)
    assert p.slice_demo(3) == 3.0  # 2.0 + 1.0

def test_location_slice_one_sided():
    p = Player(10)
    assert p.slice_one_side(3) == 6.0

def test_location_near_statement_distance():
    p = Player(10)
    assert p.near_demo(3) == 7.0

def test_invoke_kwargs_dict_literal_resolved_and_condition_works():
    p = Player(10)
    assert p.kw_call_literal(2) == 999  # injector cancels

def test_invoke_kwargs_unknown_starstar_policy():
    p = Player(10)
    # strict policy injector should not match; assume-match injector cancels to 888
    assert p.kw_call_unknown(2, {"scale": 3}) == 888

def test_head_ctx_sees_kwargs_for_kwarg_signature():
    p = Player(10)
    assert p.accept_kwargs(2, scale=7) == 7777
    assert p.accept_kwargs(2, scale=3) == 6  # normal path

def test_tail_implicit_return_override():
    p = Player(10)
    assert p.do_nothing() == 123
