import os, sys, pathlib
os.environ["MIXIN_DEBUG"] = "False"

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mixin_system
import demo_game.patches

mixin_system.init()

from demo_game.game.player.player import Player

p = Player(10)

print("set_health(5) =", p.set_health(5))
print("health =", p.health)
print("set_health(-3) =", p.set_health(-3), "health =", p.health)

p = Player(10)
print("set_health2(7) =", p.set_health2(7), "health =", p.health)
print("set_health2(-9) =", p.set_health2(-9), "health =", p.health)

print("calculate_speed() =", p.calculate_speed())

p.is_in_space = False
print("update(3) normal =", p.update(3))
p.is_in_space = True
print("update(3) in_space =", p.update(3))

p.is_in_space = False
print("two_calls(3) normal =", p.two_calls(3))
p.is_in_space = True
print("two_calls(3) in_space =", p.two_calls(3))

print("slice_demo(3) =", p.slice_demo(3))
print("slice_one_side(3) =", p.slice_one_side(3))
print("near_demo(3) =", p.near_demo(3))

print("kw_call_literal(2) =", p.kw_call_literal(2))
print("kw_call_unknown(2, {'scale':3}) =", p.kw_call_unknown(2, {"scale": 3}))
print("accept_kwargs(2, scale=7) =", p.accept_kwargs(2, scale=7))
print("accept_kwargs(2, scale=3) =", p.accept_kwargs(2, scale=3))

print("do_nothing() =", p.do_nothing())
