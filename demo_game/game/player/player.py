class Player:
    def __init__(self, health: int):
        self.health = health
        self.is_in_space = False

    def set_health(self, value: int) -> int:
        self.health = value
        return self.health

    def set_health2(self, value: int) -> int:
        self.health = value
        return self.health

    def calculate_speed(self) -> float:
        base = 1.0
        return base * 2

    def calculate_physics(self, x: int) -> int:
        return x * 2

    def physics2(self, x: int, scale: int = 2, mode: str = "A") -> int:
        return x * scale

    def kw_call_literal(self, x: int) -> int:
        # **kwargs is a dict literal with static keys
        return self.physics2(x, **{"scale": 3})

    def kw_call_unknown(self, x: int, opts: dict) -> int:
        # **kwargs is unknown at AST time
        return self.physics2(x, **opts)

    def accept_kwargs(self, x: int, **kw) -> int:
        return x * int(kw.get("scale", 1))

    def custom_space_physics(self, x: int) -> int:
        return x * 100

    def update(self, x: int) -> int:
        return self.calculate_physics(x)

    def two_calls(self, x: int) -> int:
        return self.calculate_physics(x) + self.calculate_physics(x)

    def slice_demo(self, x: int) -> float:
        a = self.calculate_physics(x)
        b = 1.0
        c = self.calculate_physics(x)
        d = 1.0
        return b + d

    def slice_one_side(self, x: int) -> float:
        a = self.calculate_physics(x)
        b = 1.0
        c = 1.0
        return b + c

    def near_demo(self, x: int) -> float:
        a = 1.0
        b = self.calculate_physics(x)
        c = 1.0
        d = 1.0
        return a + c + d

    def do_nothing(self):
        x = 1
        x += 1
