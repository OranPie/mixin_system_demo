import sys
import pathlib

# Ensure src/ layout is on path for pytest invocation from repo folder
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (str(SRC), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import mixpy
import demo_game.patches  # register patches
import demo_game.network.patches  # register network patches

mixpy.init()
